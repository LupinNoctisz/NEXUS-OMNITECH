"""NexusCore: fachada que monta e expõe todos os serviços do núcleo."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .. import __version__
from .audit import AuditLog
from .auth import AuthService, hash_password
from .backup import BackupManager
from .database import SCHEMA_VERSION, Database
from .devices import DeviceRegistry
from .errors import NexusError, PermissionDenied, StorageError, ValidationError
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
    def __init__(self, home: Path | str | None = None, module_dirs: list[Path] | None = None):
        self.paths = Paths(Path(home).expanduser() if home else default_home())
        try:
            self.paths.ensure()
        except OSError as exc:
            raise StorageError(
                f"Não foi possível acessar a pasta de dados do NEXUS ({self.paths.home}): {exc}. "
                "Verifique permissões e espaço em disco; nenhum dado foi alterado.") from exc
        try:
            self.db = Database(self.paths.db)
        except sqlite3.Error as exc:
            raise StorageError(
                f"Não foi possível abrir o banco de dados local ({self.paths.db}): {exc}. Nenhum dado foi alterado. "
                "Se o arquivo estiver corrompido, restaure uma cópia da pasta 'backups' (ou do seu backup externo); "
                "não apague a pasta de dados.") from exc
        self.settings = SettingsStore(self.db)
        self.log = setup_logging(self.paths.logs, self.settings.get("log.level"))
        self.audit = AuditLog(self.db)
        self.technicians = TechnicianRepository(self.db)
        self.auth = AuthService(self)
        self._actor = ANONYMOUS
        self.devices = DeviceRegistry(self)
        self.sessions = SessionManager(self)
        self.backups = BackupManager(self)
        self.safety = SafetyGuard(self)
        bundled = Path(__file__).resolve().parents[3] / "modules"
        self.modules = ModuleRegistry(self, module_dirs or [self.paths.modules, bundled], __version__)
        self.log.info("núcleo iniciado", extra={"version": __version__, "schema": self.db.schema_version})
        if self.db.migrated_from is not None:
            self.log.info("banco migrado", extra={"from": self.db.migrated_from, "to": self.db.schema_version,
                                                  "backup": self.db.pre_migration_backup})

    # -- identidade e permissões ------------------------------------------
    @property
    def actor(self) -> str:
        """Técnico autenticado (somente leitura). Só muda por login()/logout()."""
        return self._actor

    @property
    def role(self) -> Role:
        return Role.VIEWER if self._actor == ANONYMOUS else self.technicians.role_of(self._actor)

    def login(self, name: str, password: str) -> Role:
        self.auth.authenticate(name, password)  # levanta AuthenticationError
        self._actor = name
        return self.role

    def logout(self) -> None:
        if self._actor != ANONYMOUS:
            self.audit.record("auth.logout", technician=self._actor)
            self._actor = ANONYMOUS

    def revalidate_actor(self) -> bool:
        """Encerra a sessão se o técnico deixou de existir/estar ativo (ex.: após restaurar um backup)."""
        if self._actor == ANONYMOUS:
            return True
        record = self.technicians.get(self._actor)
        if record is None or not record["active"] or not record["has_password"]:
            self._actor = ANONYMOUS
            return False
        return True

    def can(self, permission: Permission) -> bool:
        return permission in ROLE_PERMISSIONS[self.role]

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            self.audit.record("permission.denied", technician=self._actor, outcome="denied",
                              details={"permission": str(permission), "role": str(self.role)})
            self.log.warning("permissão negada", extra={"technician": self._actor, "permission": str(permission)})
            raise PermissionDenied(
                f"'{self._actor}' ({self.role}) não possui a permissão '{permission}'.")

    # -- técnicos ----------------------------------------------------------
    def bootstrap_admin(self, name: str, password: str) -> int:
        """Cria o primeiro administrador (com senha) e inicia a sessão dele."""
        if self.technicians.count() > 0:
            raise NexusError("O sistema já foi inicializado; use um administrador para adicionar técnicos.")
        technician_id = self.technicians.add(name, Role.ADMIN, hash_password(password))
        self._actor = name.strip()
        self.audit.record("technician.bootstrap", technician=self._actor, target=self._actor)
        return technician_id

    def add_technician(self, name: str, role: Role | str, password: str) -> int:
        self.require(Permission.TECHNICIANS_MANAGE)
        technician_id = self.technicians.add(name, role, hash_password(password))
        self.audit.record("technician.add", technician=self._actor, target=name.strip(), details={"role": str(Role(role))})
        return technician_id

    def set_technician_active(self, name: str, active: bool) -> None:
        self.require(Permission.TECHNICIANS_MANAGE)
        record = self.technicians.get(name)
        if record is None:
            raise ValidationError(f"Técnico não encontrado: {name}")
        if not active and record["role"] == Role.ADMIN and record["active"] and self.technicians.count_active_admins() <= 1:
            raise ValidationError("Não é possível desativar o último administrador ativo.")
        self.technicians.set_active(name, active)
        self.audit.record("technician.activate" if active else "technician.deactivate",
                          technician=self._actor, target=name)
        self.revalidate_actor()

    def set_password(self, name: str, new_password: str, old_password: str | None = None) -> str:
        return self.auth.set_password(name, new_password, old_password)

    def set_setting(self, key: str, value: Any) -> None:
        self.require(Permission.SETTINGS_WRITE)
        self.settings.set(key, value)
        self.audit.record("settings.set", technician=self._actor, target=key, details={"value": value})

    # -- segurança e painel inicial -----------------------------------------
    def security_overview(self) -> dict[str, Any]:
        verification = self.audit.verify()  # tela Segurança: sempre a conferência completa
        technicians = self.technicians.list()
        now = datetime.now(timezone.utc)
        return {
            "actor": self._actor,
            "role": str(self.role),
            "permissions": sorted(str(p) for p in ROLE_PERMISSIONS[self.role]),
            "audit": {"ok": verification.ok, "records": verification.records, "first_bad_id": verification.first_bad_id,
                      "scope": verification.scope},
            "database_integrity": self.db.integrity_check(),
            "technicians": {
                "total": len(technicians),
                "active": sum(1 for t in technicians if t["active"]),
                "without_password": sum(1 for t in technicians if t["active"] and not t["has_password"]),
                "locked": sum(1 for t in technicians
                              if t["locked_until"] and datetime.fromisoformat(t["locked_until"]) > now),
            },
            "trusted_publishers": self.settings.get("modules.trusted_publishers"),
            "modules": [{"id": m["id"], "status": m["status"], "integrity_ok": m["integrity_ok"], "problems": m["problems"]}
                        for m in self.modules.status()],
        }

    def status(self) -> dict[str, Any]:
        verification = self.audit.verify_incremental()
        modules = self.modules.status()
        sessions_open = self.sessions.open_sessions()
        technicians = self.technicians.list()
        alerts: list[dict[str, str]] = []

        if not technicians:
            alerts.append({"level": "info", "message": "Nenhum técnico cadastrado. Execute 'nexus init --admin NOME'."})
        missing_pw = [t["name"] for t in technicians if t["active"] and not t["has_password"]]
        if missing_pw and (self._actor == ANONYMOUS or self.can(Permission.TECHNICIANS_MANAGE)):  # só admin (ou uso local sem login)
            alerts.append({"level": "warning", "message": "Técnicos ativos sem senha (não conseguem entrar): " + ", ".join(missing_pw)})
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
            "actor": self._actor,
            "role": str(self.role),
            "devices_connected": self.devices.list(connection="connected") if self.can(Permission.DEVICES_READ) else [],
            "recent_sessions": self.sessions.recent(5),
            "recent_operations": self.audit.recent(5),
            "modules": modules,
            "backups": {"count": len(backups),
                        "latest": backups[0].name if backups else None,
                        "latest_utc": (datetime.fromtimestamp(backups[0].stat().st_mtime, timezone.utc)
                                       .isoformat(timespec="seconds") if backups else None)},
            "sync": {"state": "not_configured", "detail": "Sincronização online será implementada na etapa 8."},
            "audit": {"ok": verification.ok, "records": verification.records, "scope": verification.scope},
            "alerts": alerts,
        }

    def close(self) -> None:
        self.log.info("núcleo encerrado")
        self.modules.unload_all()
        self.db.close()
        close_logging()

    def __enter__(self) -> "NexusCore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
