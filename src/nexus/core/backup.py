"""Backups do banco local, com verificação de integridade e restauração segura."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import BackupError, ConfirmationRequired
from .permissions import Permission
from .util import sha256_file

if TYPE_CHECKING:
    from .app import NexusCore

_NAME = re.compile(r"^nexus-\d{8}-\d{6}-[a-z0-9_-]+\.db$")


def _check_sqlite_file(path: Path) -> None:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"Arquivo de backup inválido: {exc}") from exc
    if not result or result[0] != "ok":
        raise BackupError("O backup falhou na verificação de integridade do SQLite.")


class BackupManager:
    def __init__(self, core: "NexusCore"):
        self._core = core

    @property
    def folder(self) -> Path:
        return self._core.paths.backups

    def create(self, reason: str = "manual") -> Path:
        self._core.require(Permission.BACKUP_MANAGE)
        reason = re.sub(r"[^a-z0-9_-]", "-", reason.lower())[:30] or "manual"
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        target = self.folder / f"nexus-{stamp}-{reason}.db"
        counter = 1
        while target.exists():
            target = self.folder / f"nexus-{stamp}-{reason}-{counter}.db"
            counter += 1
        try:
            self._core.db.backup_to(target)
            _check_sqlite_file(target)
            digest = sha256_file(target)
            Path(str(target) + ".sha256").write_text(f"{digest}  {target.name}\n", encoding="utf-8")
        except Exception as exc:
            target.unlink(missing_ok=True)
            raise BackupError(f"Falha ao criar backup: {exc}") from exc
        self._prune()
        self._core.audit.record("backup.create", technician=self._core.actor, target=target.name,
                                details={"reason": reason, "sha256": digest})
        return target

    def list(self) -> list[Path]:
        if not self.folder.exists():
            return []
        return sorted((p for p in self.folder.glob("nexus-*.db") if _NAME.match(p.name)), reverse=True)

    def verify(self, path: Path) -> None:
        """Levanta BackupError se o arquivo estiver corrompido ou divergir do checksum."""
        path = Path(path)
        if not path.is_file():
            raise BackupError(f"Backup não encontrado: {path}")
        sidecar = Path(str(path) + ".sha256")
        if sidecar.exists():
            expected = sidecar.read_text(encoding="utf-8").split()[0]
            if sha256_file(path) != expected:
                raise BackupError("O checksum do backup não confere: arquivo alterado ou corrompido.")
        _check_sqlite_file(path)

    def restore(self, path: Path, *, confirmed: bool = False) -> Path:
        """Restaura um backup. Cria antes um backup do estado atual e devolve o caminho dele."""
        self._core.require(Permission.BACKUP_RESTORE)
        if not confirmed:
            raise ConfirmationRequired("A restauração substitui todos os dados locais. Confirme explicitamente.")
        path = Path(path)
        self.verify(path)
        safety_copy = self.create("pre-restore")
        self._core.db.restore_from(path)
        self._core.audit.record("backup.restore", technician=self._core.actor, target=path.name,
                                details={"pre_restore_backup": safety_copy.name})
        return safety_copy

    def _prune(self) -> None:
        keep = int(self._core.settings.get("backup.keep"))
        for old in self.list()[keep:]:
            old.unlink(missing_ok=True)
            Path(str(old) + ".sha256").unlink(missing_ok=True)
