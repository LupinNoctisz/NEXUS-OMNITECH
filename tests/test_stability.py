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


# --- restauração de backup: casos de falha não podem estragar o banco em uso ----------------------
def _snapshot(core):
    return core.technicians.count(), core.audit.verify().records


def test_restore_of_tampered_backup_leaves_database_untouched(core):
    path = core.backups.create("x")
    with path.open("ab") as handle:
        handle.write(b"lixo")
    core.add_technician("ana", "technician", PASSWORD)
    before = _snapshot(core)
    from nexus.core import BackupError
    with pytest.raises(BackupError):
        core.backups.restore(path, confirmed=True)
    assert _snapshot(core) == before


def test_restore_of_newer_schema_backup_is_refused_and_keeps_current_data(core):
    import sqlite3
    from nexus.core import BackupError as NexusError
    path = core.backups.create("x")
    (path.with_name(path.name + ".sha256")).unlink()          # simula backup sem checksum
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    core.add_technician("ana", "technician", PASSWORD)
    before = _snapshot(core)
    with pytest.raises(NexusError):
        core.backups.restore(path, confirmed=True)
    assert core.db.schema_version == 3
    assert _snapshot(core) == before
    assert core.technicians.get("ana") is not None


# --- matriz de permissões por RPC (travada: mudar exige decisão consciente) ---------------------------
_MUTATING = {
    "devices.scan": "devices.manage", "backups.create": "backup.manage", "backups.restore": "backup.restore",
    "modules.register": "modules.manage", "modules.enable": "modules.manage", "modules.disable": "modules.manage",
    "settings.set": "settings.write", "technicians.add": "technicians.manage",
    "technicians.set_active": "technicians.manage", "sessions.start": "sessions.run",
}


@pytest.mark.parametrize("role", ["viewer", "technician", "admin"])
def test_rpc_permission_matrix_for_mutating_methods(core, login_as, role):
    import json
    from nexus.api.server import RpcServer
    from nexus.core.permissions import ROLE_PERMISSIONS, Role

    login_as("u-" + role, role) if role != "admin" else login_as("admin")
    server = RpcServer(core)
    params = {"backups.restore": {"name": "x", "confirmed": True}, "settings.set": {"key": "ui.theme", "value": "dark"},
              "technicians.add": {"name": "zz", "role": "viewer", "password": PASSWORD},
              "technicians.set_active": {"name": "admin", "active": True}, "sessions.start": {"device_id": 1},
              "modules.register": {"id": "x"}, "modules.enable": {"id": "x"}, "modules.disable": {"id": "x"}}
    for method, permission in _MUTATING.items():
        raw = server.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                                        "params": params.get(method, {})}).encode())
        error = json.loads(raw).get("error")
        allowed = any(str(p) == permission for p in ROLE_PERMISSIONS[Role(role)])
        assert (error is not None and error["code"] == -32001) == (not allowed), (role, method, error)


# --- leitura restrita (decisão do dono: Segurança/Configurações só admin; lista de técnicos reduzida) ---
ADMIN_ONLY_READS = ("security.overview", "settings.get_all", "system.paths")


@pytest.mark.parametrize("role", ["viewer", "technician"])
def test_admin_only_reads_are_denied_and_audited(core, login_as, role):
    import json
    from nexus.api.server import RpcServer

    login_as("u-" + role, role)
    server = RpcServer(core)
    for method in ADMIN_ONLY_READS:
        reply = json.loads(server.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method}).encode()))
        assert reply["error"]["code"] == -32001, method
    denied = [r for r in core.audit.recent(50) if r["action"] == "permission.denied"]
    assert len(denied) >= len(ADMIN_ONLY_READS)


def test_admin_can_still_read_everything(core):
    import json
    from nexus.api.server import RpcServer

    server = RpcServer(core)
    core.login("admin", PASSWORD)
    for method in ADMIN_ONLY_READS:
        reply = json.loads(server.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": method}).encode()))
        assert "result" in reply, method


def test_technician_list_is_minimal_for_non_admins_and_complete_for_admin(core, login_as):
    import json
    from nexus.api.server import RpcServer

    login_as("tec", "technician")
    server = RpcServer(core)

    def listing():
        return json.loads(server.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "technicians.list"}).encode()))["result"]

    rows = listing()
    assert {r["name"] for r in rows} >= {"admin", "tec"}
    assert all(set(r) == {"name", "role", "active"} for r in rows)
    login_as("admin")
    assert all({"failed_attempts", "locked_until", "has_password", "created_at"} <= set(r) for r in listing())


def test_missing_password_alert_is_only_for_admin(core, login_as):
    core.db.execute("INSERT INTO technicians(name, role, active, created_at) VALUES ('sem.senha','viewer',1,'2026-01-01T00:00:00+00:00')")
    login_as("tec", "technician")
    assert not any("sem senha" in a["message"] for a in core.status()["alerts"])
    login_as("admin")
    assert any("sem senha" in a["message"] for a in core.status()["alerts"])
