"""Estabilidade: histórico grande, verificação incremental, concorrência e uso de índices."""

import threading
import tracemalloc

import pytest

from nexus.core import NexusCore, auth
from nexus.core.audit import AuditLog

from conftest import PASSWORD


@pytest.fixture
def big(tmp_path):
    with NexusCore(home=tmp_path / "h", module_dirs=[tmp_path / "m"]) as core:
        core.bootstrap_admin("admin", PASSWORD)
        with core.db.transaction():
            for i in range(12_000):
                core.audit.record("carga.teste", target=str(i), details={"i": i})
        yield core


def test_full_verify_streams_in_constant_memory(big):
    tracemalloc.start()
    try:
        result = big.audit.verify()
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert result.ok and result.records >= 12_000 and result.is_full
    assert peak < 6_000_000, f"verificação usou {peak / 1e6:.1f} MB: não está em lotes"


def test_status_does_not_rescan_the_whole_chain_each_time(big, monkeypatch):
    big.status()  # a primeira chamada faz a conferência completa
    scans = {"rows": 0}
    original = AuditLog._scan

    def counting(self, prev, after_id, count):
        scans["rows"] += 1
        assert after_id > 0, "a segunda chamada deveria partir do ponto já conferido"
        return original(self, prev, after_id, count)

    monkeypatch.setattr(AuditLog, "_scan", counting)
    big.audit.record("nova.operacao")
    status = big.status()
    assert status["audit"]["ok"] and status["audit"]["scope"] == "incremental"
    assert scans["rows"] == 1


def test_incremental_detects_tampering_of_new_records(big):
    big.status()
    last = big.audit.record("depois.do.checkpoint")
    big.db.execute("UPDATE operations SET outcome = 'adulterado' WHERE id = ?", (last,))
    result = big.audit.verify_incremental()
    assert not result.ok and result.first_bad_id == last


def test_full_verify_still_catches_old_tampering_that_incremental_cannot(big):
    big.status()
    big.db.execute("UPDATE operations SET target = 'alterado' WHERE id = 500")
    assert big.audit.verify_incremental().ok            # limitação documentada do modo incremental
    full = big.audit.verify()
    assert not full.ok and full.first_bad_id == 500     # a conferência completa pega


def test_incremental_after_restore_rescans_everything(tmp_path):
    with NexusCore(home=tmp_path / "h", module_dirs=[tmp_path / "m"]) as core:
        core.bootstrap_admin("admin", PASSWORD)
        backup = core.backups.create("antes")
        for i in range(30):
            core.audit.record("depois", target=str(i))
        core.audit.verify_incremental()
        core.backups.restore(backup, confirmed=True)
        result = core.audit.verify_incremental()
        assert result.ok and result.is_full


def test_concurrent_writers_keep_a_valid_chain(tmp_path):
    with NexusCore(home=tmp_path / "h", module_dirs=[tmp_path / "m"]) as core:
        core.bootstrap_admin("admin", PASSWORD)
        before = core.audit.verify().records
        errors: list[Exception] = []

        def worker(n: int) -> None:
            try:
                for i in range(150):
                    core.audit.record("concorrente", target=f"{n}-{i}")
                    if i % 25 == 0:
                        core.audit.verify_incremental()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        final = core.audit.verify()
        assert final.ok and final.records == before + 8 * 150


@pytest.mark.parametrize("sql", [
    "SELECT * FROM sessions WHERE status = 'open' ORDER BY id",
    "SELECT * FROM devices WHERE connection = 'connected' ORDER BY last_seen DESC",
    "SELECT * FROM devices ORDER BY last_seen DESC",
    "SELECT * FROM operations WHERE session_id = 1 ORDER BY id DESC LIMIT 10",
])
def test_frequent_queries_do_not_scan_whole_tables(core, sql):
    plan = " | ".join(str(row[3]) for row in core.db.query_all("EXPLAIN QUERY PLAN " + sql))
    assert "SEARCH" in plan or "USING INDEX" in plan or "USING COVERING INDEX" in plan, plan


def test_status_does_full_rescan_after_interval(big, monkeypatch):
    from nexus.core import audit as audit_mod

    big.status()
    big.db.execute("UPDATE operations SET target = 'alterado' WHERE id = 500")
    assert big.status()["audit"]["ok"]                       # dentro do intervalo: só incremental
    monkeypatch.setattr(audit_mod, "FULL_RESCAN_SECONDS", 0.0)
    assert not big.status()["audit"]["ok"]                   # intervalo vencido: pega a adulteração
    assert not big.security_overview()["audit"]["ok"]        # a tela Segurança sempre confere tudo
