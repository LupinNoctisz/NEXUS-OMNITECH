import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.api import protocol as proto
from nexus.api.server import RpcServer
from nexus.core import NexusCore

from conftest import PASSWORD


class Client:
    def __init__(self, server):
        self.server = server
        self._id = 0

    def call(self, method, **params):
        self._id += 1
        raw = json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}).encode()
        return json.loads(self.server.handle(raw))

    def ok(self, method, **params):
        response = self.call(method, **params)
        assert "error" not in response, response
        return response["result"]

    def err(self, method, **params):
        response = self.call(method, **params)
        assert "error" in response, response
        return response["error"]


@pytest.fixture
def rpc(core):
    core.logout()
    return Client(RpcServer(core))


@pytest.fixture
def logged(rpc):
    rpc.ok("auth.login", name="admin", password=PASSWORD)
    return rpc


# --- sessão do protocolo / autenticação -------------------------------------------------
def test_hello_needs_no_login_and_lists_methods(rpc):
    hello = rpc.ok("rpc.hello")
    assert hello["protocol"] == proto.PROTOCOL_VERSION and hello["authenticated"] is False
    assert {"status.get", "backups.restore", "auth.login"} <= set(hello["methods"])


def test_everything_else_requires_login(rpc):
    for method in ("status.get", "devices.list", "backups.list", "technicians.list", "security.overview"):
        assert rpc.err(method)["code"] == proto.NOT_AUTHENTICATED


def test_login_then_status(logged):
    status = logged.ok("status.get")
    assert status["actor"] == "admin" and status["sync"]["state"] == "not_configured"


def test_wrong_login_is_generic_and_locks(rpc):
    first = rpc.err("auth.login", name="admin", password="senha-errada-123")  # nexus:allow-secret (valor fictício de teste)
    assert first["code"] == proto.NOT_AUTHENTICATED
    unknown = rpc.err("auth.login", name="fantasma", password="senha-errada-123")  # nexus:allow-secret (valor fictício de teste)
    assert first["message"] == unknown["message"]
    for _ in range(6):
        rpc.err("auth.login", name="admin", password="senha-errada-123")  # nexus:allow-secret (valor fictício de teste)
    assert rpc.err("auth.login", name="admin", password=PASSWORD)["code"] == proto.NOT_AUTHENTICATED


def test_logout_ends_access(logged):
    logged.ok("auth.logout")
    assert logged.err("status.get")["code"] == proto.NOT_AUTHENTICATED


def test_password_never_reaches_log_or_audit(core, rpc):
    rpc.ok("auth.login", name="admin", password=PASSWORD)
    rpc.err("auth.login", name="admin", password="senha-vazada-no-rpc-1")  # nexus:allow-secret (valor fictício de teste)
    dump = (core.paths.logs / "nexus.log").read_text(encoding="utf-8") + json.dumps(core.audit.recent(50))
    assert PASSWORD not in dump and "senha-vazada-no-rpc-1" not in dump


def test_change_password_over_rpc(logged):
    assert logged.err("auth.change_password", old_password="errada-errada-1", new_password="nova-senha-forte-1")["code"] == proto.NOT_AUTHENTICATED  # nexus:allow-secret
    logged.ok("auth.change_password", old_password=PASSWORD, new_password="nova-senha-forte-1")  # nexus:allow-secret (valor fictício de teste)
    logged.ok("auth.logout")
    assert logged.err("auth.login", name="admin", password=PASSWORD)
    logged.ok("auth.login", name="admin", password="nova-senha-forte-1")  # nexus:allow-secret (valor fictício de teste)


# --- validação de requisição e de parâmetros ------------------------------------------------
def test_malformed_messages(core):
    server = RpcServer(core)
    parse = lambda raw: json.loads(server.handle(raw))["error"]["code"]
    assert parse(b"nao-e-json") == proto.PARSE_ERROR
    assert parse(b"\xff\xfe") == proto.PARSE_ERROR
    assert parse(b"[1,2]") == proto.INVALID_REQUEST
    assert parse(b'{"id":1,"method":"rpc.hello"}') == proto.INVALID_REQUEST           # sem jsonrpc
    assert parse(b'{"jsonrpc":"2.0","id":1,"method":5}') == proto.INVALID_REQUEST
    assert parse(b'{"jsonrpc":"2.0","id":true,"method":"rpc.hello"}') == proto.INVALID_REQUEST
    assert parse(b'{"jsonrpc":"2.0","id":1,"method":"rpc.hello","params":[1]}') == proto.INVALID_PARAMS


def test_unknown_method(logged):
    assert logged.err("os.exec", cmd="calc")["code"] == proto.METHOD_NOT_FOUND
    assert logged.err("core.__class__")["code"] == proto.METHOD_NOT_FOUND


@pytest.mark.parametrize("method,params", [
    ("devices.add", {"kind": "geladeira"}),                       # fora da lista
    ("devices.add", {}),                                          # obrigatório ausente
    ("devices.add", {"kind": "pc", "ninguem": 1}),                # parâmetro desconhecido
    ("sessions.start", {"device_id": True}),                      # bool não é inteiro
    ("sessions.start", {"device_id": "1"}),
    ("sessions.start", {"device_id": 0}),
    ("audit.list", {"limit": 100000}),
    ("settings.set", {"key": "k" * 500, "value": 1}),
    ("devices.add", {"kind": "pc", "label": "a\x00b"}),
    ("modules.register", {"id": "nexus.demo", "confirmed": "sim"}),
])
def test_parameter_validation(logged, method, params):
    assert logged.err(method, **params)["code"] == proto.INVALID_PARAMS


def test_notification_gets_no_response(core):
    server = RpcServer(core)
    assert server.handle(b'{"jsonrpc":"2.0","method":"rpc.hello"}') is None


def test_internal_errors_do_not_leak_details(core, logged):
    server = logged.server

    def boom(core_, params):
        raise RuntimeError("detalhe-interno-secreto")
    server.methods["status.get"] = server.methods["status.get"].__class__("status.get", boom, {})
    error = logged.err("status.get")
    assert error["code"] == proto.INTERNAL_ERROR and "detalhe-interno-secreto" not in json.dumps(error)
    assert "detalhe-interno-secreto" in (core.paths.logs / "nexus.log").read_text(encoding="utf-8")


# --- permissões continuam valendo pela API ----------------------------------------------------
def test_viewer_cannot_mutate_over_rpc(core, rpc, login_as):
    login_as("leitor", "viewer")
    client = Client(RpcServer(core))
    assert client.err("sessions.start", device_id=1)["code"] == proto.PERMISSION_DENIED
    assert client.err("devices.scan")["code"] == proto.PERMISSION_DENIED
    assert client.err("modules.enable", id="nexus.x")["code"] == proto.PERMISSION_DENIED
    assert client.err("technicians.add", name="x", role="admin", password=PASSWORD)["code"] == proto.PERMISSION_DENIED


def test_technicians_list_has_no_hash(logged):
    rows = logged.ok("technicians.list")
    assert rows and "password_hash" not in rows[0] and "scrypt$" not in json.dumps(rows)


# --- funcionalidades reais ----------------------------------------------------------------------
def test_devices_and_sessions_flow(logged):
    device_id = logged.ok("devices.add", kind="pc", model="Notebook X", label="Cliente A")["id"]
    assert logged.ok("devices.list")[0]["model"] == "Notebook X"
    session_id = logged.ok("sessions.start", device_id=device_id, kind="pc_diagnostics")["id"]
    assert logged.err("sessions.start", device_id=device_id, kind="pc_diagnostics")["code"] == proto.NEXUS_ERROR
    logged.ok("sessions.finish", id=session_id, summary="ok")
    assert logged.ok("sessions.recent")[0]["status"] == "completed"
    actions = [o["action"] for o in logged.ok("audit.list", session_id=session_id)]
    assert actions == ["session.finish", "session.start"]


def test_scan_reports_real_host(logged):
    result = logged.ok("devices.scan")
    assert result["found"] >= 1
    assert any(d["source"] == "local-host" for d in logged.ok("devices.list", connection="connected"))


def test_audit_verify_detects_tampering(core, logged):
    assert logged.ok("audit.verify")["ok"] is True
    core.db.execute("UPDATE operations SET outcome = 'x' WHERE id = 1")
    assert logged.ok("audit.verify")["ok"] is False


def test_modules_over_rpc(core, logged, make_module):
    make_module()
    assert logged.err("modules.register", id="nexus.demo")["code"] == proto.CONFIRMATION_REQUIRED
    logged.ok("modules.register", id="nexus.demo", confirmed=True)
    logged.ok("modules.enable", id="nexus.demo")
    assert logged.ok("modules.verify", id="nexus.demo")["ok"] is True
    (core.modules.discover()["nexus.demo"].root / "module.py").write_text("x = 1\n")
    assert logged.err("modules.enable", id="nexus.demo")["code"] == proto.INTEGRITY_ERROR
    listing = {m["id"]: m for m in logged.ok("modules.list")}
    assert listing["nexus.demo"]["integrity_ok"] is False


def test_settings_over_rpc(logged):
    logged.ok("settings.set", key="ui.theme", value="light")
    assert logged.ok("settings.get_all")["ui.theme"] == "light"
    assert logged.err("settings.set", key="ui.theme", value="neon")["code"] == proto.VALIDATION_ERROR


def test_security_overview_over_rpc(logged):
    overview = logged.ok("security.overview")
    assert overview["audit"]["ok"] and overview["database_integrity"] and overview["role"] == "admin"


# --- backups: por nome, nunca por caminho ----------------------------------------------------------
def test_backups_flow(logged):
    name = logged.ok("backups.create", reason="manual")["name"]
    assert logged.ok("backups.list")[0]["name"] == name
    logged.ok("backups.verify", name=name)
    assert logged.err("backups.restore", name=name)["code"] == proto.CONFIRMATION_REQUIRED
    result = logged.ok("backups.restore", name=name, confirmed=True)
    assert result["session_active"] is True and result["safety_backup"].endswith(".db")


@pytest.mark.parametrize("name", ["../x.db", "/etc/passwd", "C:\\Windows\\system.db", "nexus-20200101-000000-x.db", "nexus-x.db", ""])
def test_backup_names_cannot_escape_or_reference_missing_files(logged, name):
    for method in ("backups.verify", "backups.restore"):
        extra = {"confirmed": True} if method == "backups.restore" else {}
        assert logged.err(method, name=name, **extra)["code"] == proto.BACKUP_ERROR


def test_restore_reports_lost_session(core, logged):
    name = logged.ok("backups.create", reason="antes")["name"]
    logged.ok("technicians.add", name="novo", role="admin", password=PASSWORD)
    logged.ok("auth.logout")
    logged.ok("auth.login", name="novo", password=PASSWORD)
    result = logged.ok("backups.restore", name=name, confirmed=True)
    assert result["session_active"] is False
    assert logged.err("status.get")["code"] == proto.NOT_AUTHENTICATED


# --- laço de leitura (stdio) ---------------------------------------------------------------------------
def test_serve_loop_handles_oversize_blank_and_shutdown(core):
    server = RpcServer(core, max_line=200)
    big = b'{"jsonrpc":"2.0","id":1,"method":"rpc.hello","params":{"x":"' + b"a" * 5000 + b'"}}\n'
    payload = big + b"\n" + b'{"jsonrpc":"2.0","id":2,"method":"rpc.hello"}\n' + b'{"jsonrpc":"2.0","id":3,"method":"rpc.shutdown"}\n' + b'{"jsonrpc":"2.0","id":4,"method":"rpc.hello"}\n'
    out = io.BytesIO()
    server.serve(io.BytesIO(payload), out)
    lines = [json.loads(line) for line in out.getvalue().splitlines()]
    assert lines[0]["error"]["code"] == proto.INVALID_REQUEST
    assert lines[1]["id"] == 2 and lines[1]["result"]["protocol"] == "1.0"
    assert lines[2]["id"] == 3 and len(lines) == 3  # nada depois do shutdown


def test_responses_are_pure_ascii(core):
    server = RpcServer(core)
    core.add_technician("José Ação", "viewer", PASSWORD)
    out = server.handle(b'{"jsonrpc":"2.0","id":1,"method":"rpc.hello"}')
    assert out.isascii()
    core.login("admin", PASSWORD)
    assert server.handle(b'{"jsonrpc":"2.0","id":2,"method":"technicians.list"}').isascii()


# --- ponta a ponta: processo real `nexus serve --stdio` --------------------------------------------------------
def test_real_subprocess_end_to_end(tmp_path):
    home = tmp_path / "h"
    with NexusCore(home=home, module_dirs=[tmp_path / "m"]) as seed:
        seed.bootstrap_admin("lmf", PASSWORD)
    src = Path(__file__).resolve().parents[1] / "src"
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "rpc.hello"},
        {"jsonrpc": "2.0", "id": 2, "method": "status.get"},
        {"jsonrpc": "2.0", "id": 3, "method": "auth.login", "params": {"name": "lmf", "password": PASSWORD}},
        {"jsonrpc": "2.0", "id": 4, "method": "status.get"},
        {"jsonrpc": "2.0", "id": 5, "method": "rpc.shutdown"},
    ]
    result = subprocess.run(
        [sys.executable, "-m", "nexus", "--home", str(home), "serve", "--stdio"],
        input=("\n".join(json.dumps(m) for m in messages) + "\n").encode(),
        capture_output=True, timeout=60, env={**os.environ, "PYTHONPATH": str(src)})
    assert result.returncode == 0, result.stderr.decode()
    responses = {r["id"]: r for r in (json.loads(line) for line in result.stdout.splitlines())}
    assert responses[1]["result"]["authenticated"] is False
    assert responses[2]["error"]["code"] == proto.NOT_AUTHENTICATED
    assert responses[3]["result"]["role"] == "admin"
    assert responses[4]["result"]["actor"] == "lmf" and responses[4]["result"]["audit"]["ok"] is True
    assert PASSWORD not in result.stdout.decode() and PASSWORD not in result.stderr.decode()


# --- primeiro uso (setup.*) ----------------------------------------------------------------
@pytest.fixture
def fresh_rpc(tmp_path):
    with NexusCore(home=tmp_path / "novo", module_dirs=[tmp_path / "m"]) as empty:
        yield Client(RpcServer(empty)), empty


def test_setup_status_reports_first_run_and_needs_no_login(fresh_rpc):
    rpc, _ = fresh_rpc
    assert rpc.ok("setup.status") == {"initialized": False}


def test_setup_creates_first_admin_logged_in_and_only_once(fresh_rpc):
    rpc, core = fresh_rpc
    who = rpc.ok("setup.create_admin", name="primeiro", password=PASSWORD)
    assert who["actor"] == "primeiro" and who["role"] == "admin" and who["authenticated"] is True
    assert rpc.ok("setup.status") == {"initialized": True}
    assert core.audit.recent(1)[0]["action"] == "technician.bootstrap"
    second = rpc.err("setup.create_admin", name="intruso", password=PASSWORD)
    assert "já foi inicializado" in second["message"]
    assert core.technicians.get("intruso") is None


def test_setup_rejects_weak_password_and_creates_nothing(fresh_rpc):
    rpc, core = fresh_rpc
    error = rpc.err("setup.create_admin", name="primeiro", password="curta")
    assert error["code"] == proto.VALIDATION_ERROR
    assert core.technicians.count() == 0


def test_setup_is_refused_when_technicians_already_exist(rpc):
    error = rpc.err("setup.create_admin", name="outro", password=PASSWORD)
    assert "já foi inicializado" in error["message"]


def test_system_paths_are_real_and_require_login(rpc, core):
    assert rpc.err("system.paths")["code"] == proto.NOT_AUTHENTICATED
    rpc.ok("auth.login", name="admin", password=PASSWORD)
    paths = rpc.ok("system.paths")
    assert Path(paths["home"]) == core.paths.home
    assert Path(paths["database"]) == core.paths.db and Path(paths["database"]).is_file()
    assert set(paths) == {"home", "database", "logs", "backups", "modules"}
