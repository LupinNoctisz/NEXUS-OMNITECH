import json

from nexus.cli import main


def run(tmp_path, *args, actor=None):
    argv = ["--home", str(tmp_path / "h")]
    if actor:
        argv += ["--as", actor]
    return main(argv + list(args))


def test_init_status_and_audit(tmp_path, capsys):
    assert run(tmp_path, "init", "--admin", "lmf") == 0
    assert run(tmp_path, "init", "--admin", "outro") == 1  # já inicializado
    capsys.readouterr()
    assert run(tmp_path, "status", actor="lmf") == 0
    status = json.loads(capsys.readouterr().out)
    assert status["role"] == "admin" and status["sync"]["state"] == "not_configured"
    assert run(tmp_path, "audit", "verify") == 0


def test_permission_error_returns_1(tmp_path, capsys):
    run(tmp_path, "init", "--admin", "lmf")
    capsys.readouterr()
    assert run(tmp_path, "devices", "scan") == 1
    assert "permissão" in capsys.readouterr().err


def test_settings_roundtrip(tmp_path, capsys):
    run(tmp_path, "init", "--admin", "lmf")
    assert run(tmp_path, "settings", "set", "ui.theme", '"light"', actor="lmf") == 0
    assert run(tmp_path, "settings", "set", "ui.theme", '"neon"', actor="lmf") == 1
    assert run(tmp_path, "settings", "set", "ui.theme", "nao-json", actor="lmf") == 1
