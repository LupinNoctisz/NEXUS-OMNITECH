import sqlite3

import pytest

from nexus.core import (AuthenticationError, BackupError, ConfirmationRequired, NexusCore, NexusError,
                        PermissionDenied, ValidationError)
from nexus.core.devices import DeviceInfo, UsbProvider
from nexus.core.permissions import Role

from conftest import PASSWORD
from nexus.core.safety import DestructiveRequest


# --- banco / auditoria ------------------------------------------------------
def test_schema_migrated(core):
    assert core.db.schema_version == 2  # v2 = autenticação por senha
    assert core.db.integrity_check()


def test_audit_chain_detects_tampering(core):
    core.add_technician("ana", "technician", PASSWORD)
    core.add_technician("bia", "viewer", PASSWORD)
    assert core.audit.verify().ok
    core.db.execute("UPDATE operations SET target = 'forjado' WHERE id = 2")
    result = core.audit.verify()
    assert not result.ok and result.first_bad_id == 2


def test_audit_redacts_credentials(core):
    core.audit.record("x", details={"password": "123", "nested": {"api_key": "abc", "ok": 1}})
    details = core.audit.recent(1)[0]["details"]
    assert "123" not in details and "abc" not in details and '"ok":1' in details


# --- permissões -------------------------------------------------------------
def test_anonymous_is_read_only(tmp_path):
    with NexusCore(home=tmp_path / "h") as anon:
        with pytest.raises(PermissionDenied):
            anon.devices.scan()
        assert anon.audit.recent(1)[0]["action"] == "permission.denied"


def test_viewer_cannot_start_session(core, login_as):
    login_as("leitor", Role.VIEWER)
    with pytest.raises(PermissionDenied):
        core.sessions.start(1)


def test_bootstrap_only_once(core):
    with pytest.raises(NexusError):
        core.bootstrap_admin("outro", PASSWORD)


def test_inactive_technician_cannot_login(core):
    core.add_technician("tec", "technician", PASSWORD)
    core.set_technician_active("tec", False)
    with pytest.raises(AuthenticationError):
        core.login("tec", PASSWORD)


# --- configurações ----------------------------------------------------------
def test_settings_validation(core):
    assert core.settings.get("ui.theme") == "dark"
    core.set_setting("ui.theme", "light")
    assert core.settings.get("ui.theme") == "light"
    with pytest.raises(ValidationError):
        core.set_setting("ui.theme", "neon")
    with pytest.raises(ValidationError):
        core.set_setting("inexistente", 1)


# --- dispositivos / sessões -------------------------------------------------
def test_scan_registers_real_host(core):
    report = core.devices.scan()
    assert report.found >= 1
    host = [d for d in core.devices.list() if d["source"] == "local-host"]
    assert host and host[0]["kind"] == "pc" and host[0]["connection"] == "connected"


def test_scan_marks_missing_as_disconnected(core):
    class Fake:
        name = "fake"
        items = [DeviceInfo(uid="f:1", kind="usb", source="fake")]
        def discover(self):
            return list(self.items)
    fake = Fake()
    core.devices.providers = [fake]
    core.devices.scan()
    assert core.devices.list("connected")[0]["uid"] == "f:1"
    fake.items = []
    core.devices.scan()
    assert core.devices.list()[0]["connection"] == "disconnected"


def test_provider_failure_is_isolated(core):
    class Broken:
        name = "broken"
        def discover(self):
            raise RuntimeError("falhou")
    core.devices.providers = [Broken()]
    report = core.devices.scan()
    assert "broken" in report.errors


def test_usb_linux_sysfs_parsing(tmp_path):
    dev = tmp_path / "1-2"
    dev.mkdir()
    for name, value in {"idVendor": "18d1", "idProduct": "4ee7", "manufacturer": "Google",
                        "product": "Pixel", "serial": "ABC123", "bDeviceClass": "00"}.items():
        (dev / name).write_text(value + "\n")
    (tmp_path / "1-2:1.0").mkdir()
    hub = tmp_path / "usb1"
    hub.mkdir()
    (hub / "idVendor").write_text("1d6b")
    (hub / "idProduct").write_text("0002")
    (hub / "bDeviceClass").write_text("09")
    found = UsbProvider(sysfs_root=tmp_path, platform_name="linux").discover()
    assert len(found) == 1 and found[0].uid == "usb:18d1:4ee7:ABC123" and found[0].vendor == "Google"


def test_usb_windows_json_parsing():
    sample = '[{"InstanceId":"USB\\\\VID_04E8&PID_6860\\\\R58M1234","FriendlyName":"SAMSUNG Mobile","Manufacturer":"SAMSUNG","Status":"OK"}]'
    found = UsbProvider.parse_windows_pnp(sample)
    assert found[0].uid == "usb:04e8:6860:R58M1234"


def test_session_lifecycle(core):
    device = core.devices.add_manual("pc", model="Notebook X", label="Cliente A")
    sid = core.sessions.start(device, "pc_diagnostics")
    with pytest.raises(NexusError):
        core.sessions.start(device, "pc_diagnostics")  # já aberta
    core.sessions.finish(sid, summary="ok")
    with pytest.raises(NexusError):
        core.sessions.finish(sid)
    assert core.sessions.get(sid)["status"] == "completed"
    assert [o["action"] for o in core.audit.recent(10, session_id=sid)] == ["session.finish", "session.start"]


def test_session_unknown_device(core):
    with pytest.raises(ValidationError):
        core.sessions.start(999)


# --- operações destrutivas --------------------------------------------------
def _request(device, **kw):
    base = dict(operation="wipe", device_id=device, description="Restaurar de fábrica",
                owner_authorization="Autorizado por Maria Silva, OS 42", confirmed=True)
    base.update(kw)
    return DestructiveRequest(**base)


def test_destructive_requires_confirmation_and_authorization(core):
    device = core.devices.add_manual("mobile", model="Aparelho")
    ran = []
    with pytest.raises(ConfirmationRequired):
        core.safety.run(_request(device, confirmed=False), lambda: ran.append(1), lambda: "bkp")
    with pytest.raises(ConfirmationRequired):
        core.safety.run(_request(device, owner_authorization=""), lambda: ran.append(1), lambda: "bkp")
    assert ran == []


def test_destructive_aborts_when_backup_fails(core):
    device = core.devices.add_manual("mobile", model="Aparelho")
    ran = []
    def bad_backup():
        raise OSError("sem espaço")
    with pytest.raises(BackupError):
        core.safety.run(_request(device), lambda: ran.append(1), bad_backup)
    assert ran == []
    assert core.audit.recent(1)[0]["outcome"] == "backup_failed"


def test_destructive_success_and_failure_are_logged(core):
    device = core.devices.add_manual("mobile", model="Aparelho")
    assert core.safety.run(_request(device), lambda: 7, lambda: "bkp.img") == 7
    actions = [o["action"] for o in core.audit.recent(3)]
    assert actions[:2] == ["destructive.finish", "destructive.start"]
    def boom():
        raise RuntimeError("erro no aparelho")
    with pytest.raises(RuntimeError):
        core.safety.run(_request(device), boom, lambda: "bkp.img")
    assert core.audit.recent(1)[0]["outcome"] == "failed"


# --- backup -----------------------------------------------------------------
def test_backup_create_verify_restore(core):
    core.add_technician("ana", "technician", PASSWORD)
    path = core.backups.create("teste")
    core.backups.verify(path)
    core.add_technician("bia", "technician", PASSWORD)
    assert core.technicians.count() == 3
    with pytest.raises(ConfirmationRequired):
        core.backups.restore(path)
    safety_copy = core.backups.restore(path, confirmed=True)
    assert core.technicians.count() == 2
    assert safety_copy.exists()
    assert core.audit.recent(1)[0]["action"] == "backup.restore"


def test_backup_detects_corruption(core):
    path = core.backups.create()
    with path.open("ab") as handle:
        handle.write(b"lixo")
    with pytest.raises(BackupError):
        core.backups.verify(path)


def test_backup_invalid_file_rejected(core, tmp_path):
    fake = tmp_path / "nexus-20200101-000000-x.db"
    fake.write_bytes(b"isto nao e sqlite" * 100)
    with pytest.raises(BackupError):
        core.backups.verify(fake)


def test_backup_prunes_old(core):
    core.set_setting("backup.keep", 2)
    for i in range(4):
        core.backups.create(f"b{i}")
    assert len(core.backups.list()) == 2


# --- painel inicial ---------------------------------------------------------
def test_status_reports_real_state(core):
    status = core.status()
    assert status["sync"]["state"] == "not_configured"
    assert status["audit"]["ok"] is True
    assert any("backup" in a["message"].lower() for a in status["alerts"])
    core.db.execute("UPDATE operations SET outcome = 'x' WHERE id = 1")
    assert any(a["level"] == "critical" for a in core.status()["alerts"])
