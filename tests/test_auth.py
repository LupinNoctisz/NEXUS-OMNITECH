import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from nexus.core import (AuthenticationError, NexusCore, NexusError, PermissionDenied, ValidationError, auth)
from nexus.core.database import MIGRATIONS, SCHEMA_VERSION
from nexus.core.permissions import Permission, Role

from conftest import PASSWORD


# --- hash e senha ---------------------------------------------------------------
def test_hash_roundtrip_and_format():
    encoded = auth.hash_password(PASSWORD)
    assert encoded.startswith("scrypt$") and PASSWORD not in encoded
    assert auth.verify_password(PASSWORD, encoded)
    assert not auth.verify_password(PASSWORD + "x", encoded)


def test_hash_is_salted():
    assert auth.hash_password(PASSWORD) != auth.hash_password(PASSWORD)


def test_old_hashes_keep_working_after_cost_change(monkeypatch):
    encoded = auth.hash_password(PASSWORD)
    monkeypatch.setattr(auth, "SCRYPT_N", 2**11)  # custo novo não invalida o hash antigo
    assert auth.verify_password(PASSWORD, encoded)


@pytest.mark.parametrize("bad", ["curta", "1234567890", "aaaaaaaaaaaa", "", "x" * 300])
def test_weak_passwords_rejected(bad):
    with pytest.raises(ValidationError):
        auth.validate_password(bad)


@pytest.mark.parametrize("broken", ["", "lixo", "scrypt$a$b$c$d$e", "bcrypt$1$2$3$4$5", "scrypt$1024$8$1$@@$@@"])
def test_malformed_hash_never_verifies(broken):
    assert auth.verify_password(PASSWORD, broken) is False


# --- login ------------------------------------------------------------------------
def test_login_logout_and_audit(core):
    core.logout()
    assert core.actor == "anonymous"
    assert core.login("admin", PASSWORD) == Role.ADMIN
    core.logout()
    actions = [o["action"] for o in core.audit.recent(3)]
    assert actions[:2] == ["auth.logout", "auth.login"]


def test_wrong_password_and_unknown_user_have_same_message(core):
    core.logout()
    with pytest.raises(AuthenticationError) as wrong:
        core.login("admin", "senha-errada-123")
    with pytest.raises(AuthenticationError) as unknown:
        core.login("fantasma", "senha-errada-123")
    assert str(wrong.value) == str(unknown.value)
    assert core.actor == "anonymous"


def test_password_is_never_logged_or_audited(core):
    core.logout()
    with pytest.raises(AuthenticationError):
        core.login("admin", "senha-vazada-no-log-1")
    core.login("admin", PASSWORD)
    dump = json.dumps(core.audit.recent(50)) + (core.paths.logs / "nexus.log").read_text(encoding="utf-8")
    assert "senha-vazada-no-log-1" not in dump and PASSWORD not in dump


def test_lockout_after_repeated_failures_blocks_even_correct_password(core):
    core.logout()
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        with pytest.raises(AuthenticationError):
            core.login("admin", "senha-errada-123")
    with pytest.raises(AuthenticationError):
        core.login("admin", PASSWORD)  # senha certa, mas conta bloqueada
    assert core.security_overview()["technicians"]["locked"] == 1


def test_lockout_expires(core):
    core.logout()
    for _ in range(auth.MAX_FAILED_ATTEMPTS):
        with pytest.raises(AuthenticationError):
            core.login("admin", "senha-errada-123")
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(timespec="seconds")
    core.db.execute("UPDATE technicians SET locked_until = ? WHERE name = 'admin'", (past,))
    assert core.login("admin", PASSWORD) == Role.ADMIN


def test_successful_login_resets_failure_counter(core):
    core.logout()
    for _ in range(auth.MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(AuthenticationError):
            core.login("admin", "senha-errada-123")
    core.login("admin", PASSWORD)
    core.logout()
    for _ in range(auth.MAX_FAILED_ATTEMPTS - 1):
        with pytest.raises(AuthenticationError):
            core.login("admin", "senha-errada-123")
    assert core.login("admin", PASSWORD) == Role.ADMIN


def test_failed_login_is_audited_without_granting_identity(core):
    core.logout()
    with pytest.raises(AuthenticationError):
        core.login("admin", "senha-errada-123")
    last = core.audit.recent(1)[0]
    assert last["action"] == "auth.login" and last["outcome"] == "failed" and last["technician"] == "anonymous"


# --- identidade não falsificável ----------------------------------------------------
def test_actor_is_read_only(core):
    with pytest.raises(AttributeError):
        core.actor = "admin"


def test_environment_variable_no_longer_grants_identity(tmp_path, monkeypatch):
    with NexusCore(home=tmp_path / "h") as first:
        first.bootstrap_admin("admin", PASSWORD)
    monkeypatch.setenv("NEXUS_TECHNICIAN", "admin")
    with NexusCore(home=tmp_path / "h") as again:
        assert again.actor == "anonymous" and again.role == Role.VIEWER


def test_constructor_has_no_actor_parameter(tmp_path):
    with pytest.raises(TypeError):
        NexusCore(home=tmp_path / "h", actor="admin")


@pytest.mark.parametrize("name", ["anonymous", "ANONYMOUS", "system", "", "  ", "x" * 65, "a\nb"])
def test_reserved_or_invalid_names_rejected(core, name):
    with pytest.raises(ValidationError):
        core.add_technician(name, "technician", PASSWORD)


# --- troca / redefinição / contas legadas ---------------------------------------------
def test_self_change_requires_current_password(core, login_as):
    login_as("ana")
    with pytest.raises(AuthenticationError):
        core.set_password("ana", "nova-senha-forte-1", old_password="errada-errada-1")  # nexus:allow-secret (valor fictício de teste)
    assert core.set_password("ana", "nova-senha-forte-1", old_password=PASSWORD) == "self"
    core.logout()
    assert core.login("ana", "nova-senha-forte-1") == Role.TECHNICIAN


def test_admin_can_reset_but_technician_cannot_reset_others(core, login_as):
    login_as("ana"); login_as("bia")
    with pytest.raises(PermissionDenied):
        core.set_password("ana", "nova-senha-forte-1")
    login_as("admin")
    assert core.set_password("ana", "nova-senha-forte-1") == "reset"
    core.logout()
    assert core.login("ana", "nova-senha-forte-1")


def test_anonymous_cannot_change_a_password_that_exists(core):
    core.logout()
    with pytest.raises(PermissionDenied):
        core.set_password("admin", "nova-senha-forte-1")


def test_cannot_deactivate_last_admin(core):
    with pytest.raises(ValidationError):
        core.set_technician_active("admin", False)


def test_deactivating_self_or_other_revalidates_session(core, login_as):
    login_as("ana")
    login_as("admin")
    core.add_technician("chefe", "admin", PASSWORD)
    core.set_technician_active("ana", False)
    core.logout()
    with pytest.raises(AuthenticationError):
        core.login("ana", PASSWORD)


# --- migração v1 -> v2 com dados existentes ---------------------------------------------
def make_v1_database(path):
    conn = sqlite3.connect(path)
    conn.executescript(MIGRATIONS[0][1])
    conn.execute("PRAGMA user_version = 1")
    conn.execute("INSERT INTO technicians (name, role, active, created_at) VALUES ('legado', 'admin', 1, '2026-11-03T00:00:00+00:00')")
    conn.execute("INSERT INTO devices (uid, kind, source, connection, first_seen, last_seen) VALUES ('manual:1','pc','manual','unknown','t','t')")
    conn.commit()
    conn.close()


def test_migration_v1_to_v2_preserves_data_and_flags_legacy_accounts(tmp_path):
    home = tmp_path / "h"
    (home).mkdir()
    make_v1_database(home / "nexus.db")
    with NexusCore(home=home, module_dirs=[tmp_path / "m"]) as core:
        assert core.db.schema_version == SCHEMA_VERSION == 3
        assert core.technicians.get("legado")["has_password"] is False
        assert core.db.query_one("SELECT COUNT(*) AS n FROM devices")["n"] == 1
        with pytest.raises(AuthenticationError):
            core.login("legado", PASSWORD)  # conta sem senha não entra
        assert any("sem senha" in a["message"] for a in core.status()["alerts"])
        # reivindicação explícita e auditada da conta legada
        assert core.set_password("legado", PASSWORD) == "claim"
        assert core.audit.recent(1)[0]["action"] == "auth.password_claim"
        assert core.login("legado", PASSWORD) == Role.ADMIN


def test_claim_is_impossible_once_password_exists(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    make_v1_database(home / "nexus.db")
    with NexusCore(home=home, module_dirs=[tmp_path / "m"]) as core:
        core.set_password("legado", PASSWORD)
        core.logout()
        with pytest.raises(PermissionDenied):
            core.set_password("legado", "outra-senha-forte-1")


# --- restore revalida o ator ---------------------------------------------------------------
def test_restore_ends_session_if_actor_missing_in_backup(core):
    backup = core.backups.create("antes")
    core.add_technician("novo", "admin", PASSWORD)
    core.login("novo", PASSWORD)
    core.backups.restore(backup, confirmed=True)
    assert core.actor == "anonymous"  # 'novo' não existe no backup restaurado


def test_restore_keeps_session_if_actor_exists(core):
    backup = core.backups.create("antes")
    core.backups.restore(backup, confirmed=True)
    assert core.actor == "admin"


def test_technician_listing_never_exposes_hash(core):
    row = core.technicians.list()[0]
    assert "password_hash" not in row and row["has_password"] is True
    assert "scrypt$" not in json.dumps(core.security_overview())


def test_security_overview_reflects_real_state(core):
    overview = core.security_overview()
    assert overview["actor"] == "admin" and overview["role"] == "admin"
    assert Permission.MODULES_MANAGE in overview["permissions"]
    assert overview["audit"]["ok"] and overview["database_integrity"]


# --- atualização do banco: backup antes de migrar e proteção contra downgrade ----------------
def test_migration_makes_verified_backup_of_existing_database_first(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    make_v1_database(home / "nexus.db")
    with NexusCore(home=home, module_dirs=[tmp_path / "m"]) as core:
        backups = [p for p in core.paths.backups.glob("nexus-*-pre-migration-v1*.db")]
        assert len(backups) == 1
        assert (core.paths.backups / (backups[0].name + ".sha256")).exists()
        core.backups.verify(backups[0])  # checksum + integridade conferem
        old = sqlite3.connect(backups[0])
        assert old.execute("PRAGMA user_version").fetchone()[0] == 1  # cópia do estado ANTES
        old.close()


def test_fresh_database_makes_no_migration_backup(tmp_path):
    with NexusCore(home=tmp_path / "h", module_dirs=[tmp_path / "m"]) as core:
        assert list(core.paths.backups.glob("*pre-migration*")) == []


def test_newer_database_is_refused_and_left_untouched(tmp_path):
    from nexus.core import SchemaVersionError

    home = tmp_path / "h"
    with NexusCore(home=home, module_dirs=[tmp_path / "m"]):
        pass
    conn = sqlite3.connect(home / "nexus.db")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    conn.close()
    before = (home / "nexus.db").read_bytes()
    with pytest.raises(SchemaVersionError):
        NexusCore(home=home, module_dirs=[tmp_path / "m"])
    assert sqlite3.connect(home / "nexus.db").execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION + 5
    assert not list((home / "backups").glob("*pre-migration*"))
