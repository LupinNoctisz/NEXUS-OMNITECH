import io
import json

import pytest

from nexus.cli import main
from nexus.core import auth

PW = "senha-de-teste-123"  # nexus:allow-secret (valor fictício de teste)


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch):
    monkeypatch.setattr(auth, "SCRYPT_N", 2**10)


def run(tmp_path, monkeypatch, *args, actor=None, stdin=""):
    """Executa o CLI lendo senhas da entrada padrão (uma por linha)."""
    argv = ["--home", str(tmp_path / "h"), "--password-stdin"]
    if actor:
        argv += ["--as", actor]
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return main(argv + list(args))


def init(tmp_path, monkeypatch, name="lmf"):
    assert run(tmp_path, monkeypatch, "init", "--admin", name, stdin=PW + "\n") == 0


def test_init_status_and_audit(tmp_path, monkeypatch, capsys):
    init(tmp_path, monkeypatch)
    assert run(tmp_path, monkeypatch, "init", "--admin", "outro", stdin=PW + "\n") == 1  # já inicializado
    capsys.readouterr()
    assert run(tmp_path, monkeypatch, "status", actor="lmf", stdin=PW + "\n") == 0
    status = json.loads(capsys.readouterr().out)
    assert status["role"] == "admin" and status["sync"]["state"] == "not_configured"
    assert run(tmp_path, monkeypatch, "audit", "verify") == 0


def test_wrong_password_is_rejected(tmp_path, monkeypatch, capsys):
    init(tmp_path, monkeypatch)
    capsys.readouterr()
    assert run(tmp_path, monkeypatch, "status", actor="lmf", stdin="senha-errada-123\n") == 1
    assert "Credenciais inválidas" in capsys.readouterr().err


def test_anonymous_cannot_scan(tmp_path, monkeypatch, capsys):
    init(tmp_path, monkeypatch)
    capsys.readouterr()
    assert run(tmp_path, monkeypatch, "devices", "scan") == 1
    assert "permissão" in capsys.readouterr().err


def test_weak_password_rejected_on_init(tmp_path, monkeypatch, capsys):
    assert run(tmp_path, monkeypatch, "init", "--admin", "lmf", stdin="123\n") == 1
    assert "pelo menos" in capsys.readouterr().err


def test_settings_roundtrip(tmp_path, monkeypatch):
    init(tmp_path, monkeypatch)
    assert run(tmp_path, monkeypatch, "settings", "set", "ui.theme", '"light"', actor="lmf", stdin=PW + "\n") == 0
    assert run(tmp_path, monkeypatch, "settings", "set", "ui.theme", '"neon"', actor="lmf", stdin=PW + "\n") == 1
    assert run(tmp_path, monkeypatch, "settings", "set", "ui.theme", "nao-json", actor="lmf", stdin=PW + "\n") == 1


def test_technician_and_password_flow(tmp_path, monkeypatch, capsys):
    init(tmp_path, monkeypatch)
    new_pw = "outra-senha-forte-9"  # nexus:allow-secret (valor fictício de teste)
    assert run(tmp_path, monkeypatch, "technician", "add", "ana", actor="lmf", stdin=f"{PW}\n{PW}\n") == 0
    # o próprio técnico troca a senha (login + nova senha)
    assert run(tmp_path, monkeypatch, "technician", "set-password", "ana", actor="ana", stdin=f"{PW}\n{new_pw}\n") == 0
    capsys.readouterr()
    assert run(tmp_path, monkeypatch, "status", actor="ana", stdin=PW + "\n") == 1       # senha antiga não vale mais
    assert run(tmp_path, monkeypatch, "status", actor="ana", stdin=new_pw + "\n") == 0


def test_sessions_cli(tmp_path, monkeypatch, capsys):
    init(tmp_path, monkeypatch)
    assert run(tmp_path, monkeypatch, "devices", "add", "--kind", "pc", "--model", "Notebook X", actor="lmf", stdin=PW + "\n") == 0
    assert run(tmp_path, monkeypatch, "sessions", "start", "--device", "1", "--kind", "pc_diagnostics", actor="lmf", stdin=PW + "\n") == 0
    assert run(tmp_path, monkeypatch, "sessions", "finish", "1", "--summary", "ok", actor="lmf", stdin=PW + "\n") == 0
    capsys.readouterr()
    assert run(tmp_path, monkeypatch, "sessions", "list", actor="lmf", stdin=PW + "\n") == 0
    assert json.loads(capsys.readouterr().out)[0]["status"] == "completed"


def test_backup_restore_by_name(tmp_path, monkeypatch, capsys):
    init(tmp_path, monkeypatch)
    assert run(tmp_path, monkeypatch, "backup", "create", actor="lmf", stdin=PW + "\n") == 0
    capsys.readouterr()
    assert run(tmp_path, monkeypatch, "backup", "list", actor="lmf", stdin=PW + "\n") == 0
    name = json.loads(capsys.readouterr().out)[0]["name"]
    assert run(tmp_path, monkeypatch, "backup", "restore", name, actor="lmf", stdin=PW + "\n") == 1  # sem --confirm
    assert run(tmp_path, monkeypatch, "backup", "restore", name, "--confirm", actor="lmf", stdin=PW + "\n") == 0
