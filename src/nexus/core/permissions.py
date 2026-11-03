"""Papéis e permissões.

Nesta etapa a identidade do técnico é DECLARATIVA (nome informado ao abrir o
núcleo). Autenticação real (senha/licença) entra na etapa de licenciamento; até
lá, o sistema de permissões protege contra erro operacional, não contra um
usuário local malicioso com acesso ao banco de dados.
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


class TechnicianRepository:
    def __init__(self, db: Database):
        self._db = db

    def add(self, name: str, role: Role | str = Role.TECHNICIAN) -> int:
        name = name.strip()
        if not name:
            raise ValidationError("Nome do técnico não pode ser vazio.")
        role = Role(role)
        cursor = self._db.execute(
            "INSERT INTO technicians (name, role, active, created_at) VALUES (?,?,1,?)",
            (name, role.value, utc_now()),
        )
        return int(cursor.lastrowid)

    def get(self, name: str) -> dict | None:
        row = self._db.query_one("SELECT * FROM technicians WHERE name = ?", (name,))
        return dict(row) if row else None

    def list(self) -> list[dict]:
        return [dict(r) for r in self._db.query_all("SELECT * FROM technicians ORDER BY name")]

    def count(self) -> int:
        return int(self._db.query_one("SELECT COUNT(*) AS n FROM technicians")["n"])

    def set_active(self, name: str, active: bool) -> None:
        self._db.execute("UPDATE technicians SET active = ? WHERE name = ?", (1 if active else 0, name))

    def role_of(self, name: str) -> Role:
        """Papel efetivo. Desconhecido ou inativo => somente leitura."""
        record = self.get(name)
        if record is None or not record["active"]:
            return Role.VIEWER
        return Role(record["role"])
