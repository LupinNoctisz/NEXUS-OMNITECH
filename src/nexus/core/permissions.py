"""Papéis e permissões.

O técnico é identificado por nome e senha (scrypt, ver ``auth``). As permissões são aplicadas no núcleo
(``NexusCore.require``), nunca pela interface: o papel decide o que cada chamada pode fazer.
Observação: quem tem acesso direto ao arquivo do banco no disco pode contorná-las; a proteção é contra
erro operacional e uso indevido pela interface, não contra o dono da máquina.
"""

from __future__ import annotations

from enum import StrEnum

from .database import Database
from .errors import ValidationError
from .util import utc_now


class Role(StrEnum):
    VIEWER = "viewer"
    TECHNICIAN = "technician"
    ADMIN = "admin"


class Permission(StrEnum):
    DEVICES_READ = "devices.read"
    DEVICES_MANAGE = "devices.manage"
    SESSIONS_RUN = "sessions.run"
    DIAGNOSTICS_RUN = "diagnostics.run"
    DESTRUCTIVE_RUN = "destructive.run"
    MODULES_MANAGE = "modules.manage"
    SETTINGS_WRITE = "settings.write"
    AUDIT_READ = "audit.read"
    BACKUP_MANAGE = "backup.manage"
    BACKUP_RESTORE = "backup.restore"
    TECHNICIANS_MANAGE = "technicians.manage"


_VIEWER = {Permission.DEVICES_READ, Permission.AUDIT_READ}
_TECH = _VIEWER | {
    Permission.DEVICES_MANAGE,
    Permission.SESSIONS_RUN,
    Permission.DIAGNOSTICS_RUN,
    Permission.DESTRUCTIVE_RUN,
    Permission.BACKUP_MANAGE,
}
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset(_VIEWER),
    Role.TECHNICIAN: frozenset(_TECH),
    Role.ADMIN: frozenset(Permission),
}

ANONYMOUS = "anonymous"


RESERVED_NAMES = {ANONYMOUS, "system"}
_PUBLIC = (
    "id, name, role, active, created_at, failed_attempts, locked_until, "
    "(password_hash IS NOT NULL) AS has_password"
)


def _valid_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValidationError("Nome do técnico não pode ser vazio.")
    if len(name) > 64 or any(ord(c) < 32 for c in name):
        raise ValidationError("Nome do técnico inválido (máx. 64 caracteres, sem caracteres de controle).")
    if name.lower() in RESERVED_NAMES:
        raise ValidationError(f"O nome '{name}' é reservado.")
    return name


def _public(row) -> dict:
    data = dict(row)
    data["active"] = bool(data["active"])
    data["has_password"] = bool(data["has_password"])
    return data


class TechnicianRepository:
    """Acesso aos técnicos. O hash da senha NUNCA sai deste módulo, exceto via credentials()."""

    def __init__(self, db: Database):
        self._db = db

    def add(self, name: str, role: Role | str = Role.TECHNICIAN, password_hash: str | None = None) -> int:
        name = _valid_name(name)
        role = Role(role)
        cursor = self._db.execute(
            "INSERT INTO technicians (name, role, active, created_at, password_hash) VALUES (?,?,1,?,?)",
            (name, role.value, utc_now(), password_hash),
        )
        return int(cursor.lastrowid)

    def get(self, name: str) -> dict | None:
        row = self._db.query_one(f"SELECT {_PUBLIC} FROM technicians WHERE name = ?", (name,))
        return _public(row) if row else None

    def list(self) -> list[dict]:
        return [_public(r) for r in self._db.query_all(f"SELECT {_PUBLIC} FROM technicians ORDER BY name")]

    def count(self) -> int:
        return int(self._db.query_one("SELECT COUNT(*) AS n FROM technicians")["n"])

    def count_active_admins(self) -> int:
        return int(self._db.query_one(
            "SELECT COUNT(*) AS n FROM technicians WHERE role = 'admin' AND active = 1")["n"])

    def set_active(self, name: str, active: bool) -> None:
        self._db.execute("UPDATE technicians SET active = ? WHERE name = ?", (1 if active else 0, name))

    def role_of(self, name: str) -> Role:
        """Papel efetivo. Desconhecido ou inativo => somente leitura."""
        record = self.get(name)
        if record is None or not record["active"]:
            return Role.VIEWER
        return Role(record["role"])

    # -- credenciais (uso interno do AuthService) -----------------------------
    def credentials(self, name: str):
        return self._db.query_one(
            "SELECT name, role, active, password_hash, failed_attempts, locked_until FROM technicians WHERE name = ?",
            (name,))

    def set_password_hash(self, name: str, password_hash: str) -> None:
        self._db.execute("UPDATE technicians SET password_hash = ? WHERE name = ?", (password_hash, name))

    def register_failure(self, name: str, max_failed: int, lock_until: str) -> bool:
        """Conta uma falha; ao atingir o limite bloqueia e zera o contador. Devolve True se bloqueou."""
        with self._db.transaction():
            self._db.execute("UPDATE technicians SET failed_attempts = failed_attempts + 1 WHERE name = ?", (name,))
            row = self._db.query_one("SELECT failed_attempts FROM technicians WHERE name = ?", (name,))
            if row and row["failed_attempts"] >= max_failed:
                self._db.execute(
                    "UPDATE technicians SET failed_attempts = 0, locked_until = ? WHERE name = ?", (lock_until, name))
                return True
        return False

    def clear_failures(self, name: str) -> None:
        self._db.execute("UPDATE technicians SET failed_attempts = 0, locked_until = NULL WHERE name = ?", (name,))
