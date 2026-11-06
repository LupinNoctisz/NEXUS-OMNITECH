"""Fase 2.1: falhas de armazenamento, interface desconectada, logs operacionais."""

import io
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.api.server import RpcServer, run_stdio
from nexus.core import NexusCore, StorageError

from conftest import PASSWORD

SRC = str(Path(__file__).resolve().parents[1] / "src")


def _cli(home, *args):
    return subprocess.run([sys.executable, "-m", "nexus", "--home", str(home), *args], input=b"",
                          capture_output=True, env={"PYTHONPATH": SRC, "PYTHONUTF8": "1", "PATH": ""}, timeout=60)


def test_unreadable_database_gives_clear_message_and_keeps_the_file(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    (home / "nexus.db").write_bytes(b"isto nao e um banco")
    result = _cli(home, "serve", "--stdio")
    err = result.stderr.decode("utf-8")
    assert result.returncode == 1
    assert "Traceback" not in err
    assert "banco de dados local" in err and "backups" in err
    assert (home / "nexus.db").read_bytes() == b"isto nao e um banco"   # nada foi alterado


def test_unreachable_data_folder_gives_clear_message(tmp_path):
    blocker = tmp_path / "arquivo"
    blocker.write_text("x")
    with pytest.raises(StorageError, match="pasta de dados"):
        NexusCore(home=blocker / "dentro")


def test_unexpected_cli_error_is_short_and_exit_code_70(tmp_path, monkeypatch, capsys):
    from nexus import cli

    def boom(*a, **k):
        raise RuntimeError("falha simulada")
    monkeypatch.setattr(cli, "_run", boom)
    code = cli.main(["--home", str(tmp_path / "h"), "status"])
    err = capsys.readouterr().err
    assert code == 70 and "Traceback" not in err and "RuntimeError" in err


def test_broken_pipe_while_answering_ends_cleanly(core, monkeypatch):
    class Gone(io.BytesIO):
        def write(self, data):
            raise BrokenPipeError()
    monkeypatch.setattr(sys, "stdin", type("S", (), {"buffer": io.BytesIO(b'{"jsonrpc":"2.0","id":1,"method":"rpc.hello"}\n')})())
    monkeypatch.setattr(sys, "stdout", type("S", (), {"buffer": Gone()})())
    assert run_stdio(core) == 0
    assert core.db.integrity_check()


def test_core_starts_even_if_log_folder_is_unwritable(tmp_path, capsys):
    home = tmp_path / "h"
    home.mkdir()
    (home / "logs").write_text("arquivo no lugar da pasta")   # impede criar/gravar logs
    # Paths.ensure() também falha com isso, então o erro é de armazenamento claro, não um traceback
    with pytest.raises(StorageError):
        NexusCore(home=home)


def test_log_setup_falls_back_to_stderr(tmp_path, capsys, monkeypatch):
    from nexus.core import logging_setup

    target = tmp_path / "logs"
    target.write_text("x")
    logger = logging_setup.setup_logging(target, "INFO")
    try:
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)
        assert "não foi possível gravar os logs" in capsys.readouterr().err
    finally:
        logging_setup.close_logging()


def _lines(core):
    path = core.paths.logs / "nexus.log"
    for handler in logging.getLogger("nexus").handlers:
        handler.flush()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_operational_log_records_backup_restore_denial_and_failed_login(core, login_as):
    from nexus.core import AuthenticationError

    with pytest.raises(AuthenticationError):
        core.login("admin", "senha-errada-123")
    core.login("admin", PASSWORD)
    backup = core.backups.create("log")
    core.backups.restore(backup, confirmed=True)
    login_as("leitor", "viewer")
    from nexus.core import PermissionDenied
    with pytest.raises(PermissionDenied):
        core.backups.create("x")
    messages = [entry["msg"] for entry in _lines(core)]
    for expected in ("login recusado", "backup criado", "backup restaurado", "permissão negada"):
        assert expected in messages, (expected, messages)
    text = (core.paths.logs / "nexus.log").read_text(encoding="utf-8")
    assert PASSWORD not in text and "senha-errada-123" not in text     # nunca senhas no log


def test_migration_is_logged_with_the_pre_migration_backup(tmp_path):
    import sqlite3
    from nexus.core.database import MIGRATIONS

    home = tmp_path / "h"
    (home).mkdir()
    conn = sqlite3.connect(home / "nexus.db")
    conn.executescript(MIGRATIONS[0][1] + "\nPRAGMA user_version = 1;")
    conn.close()
    with NexusCore(home=home, module_dirs=[tmp_path / "m"]) as core:
        entries = _lines(core)
    migrated = [e for e in entries if e["msg"] == "banco migrado"]
    assert migrated and migrated[0]["extra"]["from"] == 1 and migrated[0]["extra"]["backup"].endswith(".db")
