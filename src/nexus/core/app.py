"""NexusCore: fachada que monta e expõe todos os serviços do núcleo."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .. import __version__
from .audit import AuditLog
from .backup import BackupManager
from .database import SCHEMA_VERSION, Database
from .devices import DeviceRegistry
from .errors import NexusError, PermissionDenied
from .logging_setup import close_logging, setup_logging
from .modules import ModuleRegistry
from .paths import Paths, default_home
from .permissions import ANONYMOUS, ROLE_PERMISSIONS, Permission, Role, TechnicianRepository
from .safety import SafetyGuard
from .sessions import SessionManager
from .settings import SettingsStore

BACKUP_STALE_DAYS = 7
SESSION_STALE_HOURS = 24


class NexusCore:
    def __init__(self, home: Path | str | None = None, actor: str | None = None,
                 module_dirs: list[Path] | None = None):
        self.paths = Paths(Path(home).expanduser() if home else default_home())
        self.paths.ensure()
        self.db = Database(self.paths.db)
        self.settings = SettingsStore(self.db)
        self.log = setup_logging(self.paths.logs, self.settings.get("log.level"))
        self.audit = AuditLog(self.db)
        self.technicians = TechnicianRepository(self.db)
        self.actor = actor or os.environ.get("NEXUS_TECHNICIAN") or ANONYMOUS
        self.devices = DeviceRegistry(self)
        self.sessions = SessionManager(self)
        self.backups = BackupManager(self)
        self.safety = SafetyGuard(self)
        bundled = Path(__file__).resolve().parents[3] / "modules"
        self.modules = ModuleRegistry(self, module_dirs or [self.paths.modules, bundled], __version__)
        self.log.info("núcleo iniciado", extra={"version": __version__, "actor": self.actor})

    # -- identidade e permissões ------------------------------------------
    @property
    def role(self) -> Role:
        return Role.VIEWER if self.actor == ANONYMOUS else self.technicians.role_of(self.actor)

    def can(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[self.role]

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            self.audit.record("permission.denied", technician=self.actor, outcome="denied",
                              details={"permission": str(permission), "role": str(self.role)})
            raise PermissionDenied(
                f"'{self.actor}' ({self.role}) não possui a permissão '{permission}'.")

    def bootstrap_admin(self, name: str) -> int:
        """Cria o primeiro administrador. Só é permitido enquanto não houver técnicos."""
        if self.technicians.count() > 0:
            raise NexusError("O sistema já foi inicializado; use um administrador para adicionar técnicos.")
        technician_id = self.technicians.add(name, Role.ADMIN)
        self.actor = name
        self.audit.record("technician.bootstrap", technician=name, target=name)
        return technician_id

    def add_technician(self, name: str, role: Role | str = Role.TECHNICIAN) -> int:
        self.require(Permission.TECHNICIANS_MANAGE)
        technician_id = self.technicians.add(name, role)
        self.audit.record("technician.add", technician=self.actor, target=name, details={"role": str(role)})
        return technician_id

    def set_setting(self, key: str, value: Any) -> None:
        self.require(Permission.SETTINGS_WRITE)
        self.settings.set(key, value)
        self.audit.record("settings.set", technician=self.actor, target=key, details={"value": value})

    # -- painel inicial ----------------------------------------------------
    def status(self) -> dict[str, Any]:
        verification = self.audit.verify()
        modules = self.modules.status()
        sessions_open = self.sessions.open_sessions()
        alerts: list[dict[str, str]] = []

        if self.technicians.count() == 0:
            alerts.append({"level": "info", "message": "Nenhum técnico cadastrado. Execute 'nexus init --admin NOME'."})
        if not verification.ok:
            alerts.append({"level": "critical", "message": f"Histórico adulterado a partir do registro {verification.first_bad_id}."})
        if not self.db.integrity_check():
            alerts.append({"level": "critical", "message": "Banco local falhou na verificação de integridade."})
        for module in modules:
            if module["integrity_ok"] is False:
                alerts.append({"level": "critical", "message": f"Módulo {module['id']} falhou na integridade: {'; '.join(module['problems'])}"})
        limit = datetime.now(timezone.utc) - timedelta(hours=SESSION_STALE_HOURS)
        for session in sessions_open:
            if datetime.fromisoformat(session["started_at"]) < limit:
                alerts.append({"level": "warning", "message": f"Sessão {session['id']} aberta há mais de {SESSION_STALE_HOURS}h."})
        backups = self.backups.list()
        if backups:
            newest = datetime.fromtimestamp(backups[0].stat().st_mtime, timezone.utc)
            if datetime.now(timezone.utc) - newest > timedelta(days=BACKUP_STALE_DAYS):
                alerts.append({"level": "warning", "message": f"Último backup tem mais de {BACKUP_STALE_DAYS} dias."})
        else:
            alerts.append({"level": "info", "message": "Nenhum backup do banco local foi criado ainda."})

        return {
            "version": __version__,
            "schema_version": self.db.schema_version,
            "expected_schema_version": SCHEMA_VERSION,
            "mode": self.settings.get("mode"),
            "actor": self.actor,
            "role": str(self.role),
            "devices_connected": self.devices.list(connection="connected") if self.can(Permission.DEVICES_READ) else [],
            "recent_sessions": self.sessions.recent(5),
            "recent_operations": self.audit.recent(5),
            "modules": modules,
            "sync": {"state": "not_configured", "detail": "Sincronização online será implementada na etapa 8."},
            "audit": {"ok": verification.ok, "records": verification.records},
            "alerts": alerts,
        }

    def close(self) -> None:
        self.modules.unload_all()
        self.db.close()
        close_logging()

    def __enter__(self) -> "NexusCore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
