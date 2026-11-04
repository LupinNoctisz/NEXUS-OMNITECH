"""Lista FECHADA de métodos expostos à interface. Nada fora desta lista pode ser chamado.

Cada método declara seus parâmetros; as permissões continuam sendo aplicadas pelo núcleo
(``core.require``), então a interface nunca recebe mais poder do que o técnico autenticado tem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .. import __version__
from ..core import NexusCore
from ..core.auth import MAX_LENGTH as PASSWORD_MAX
from ..core.devices import KINDS
from ..core.permissions import ANONYMOUS, ROLE_PERMISSIONS, Permission
from ..core.sessions import SESSION_KINDS
from .protocol import PROTOCOL_VERSION, Param

Handler = Callable[[NexusCore, dict[str, Any]], Any]


@dataclass(frozen=True)
class Method:
    name: str
    handler: Handler
    params: dict[str, Param]
    requires_login: bool = True
    description: str = ""


def _whoami(core: NexusCore) -> dict[str, Any]:
    return {"actor": core.actor, "role": str(core.role),
            "permissions": sorted(str(p) for p in ROLE_PERMISSIONS[core.role]),
            "authenticated": core.actor != ANONYMOUS}


def build_registry(shutdown: Callable[[], None]) -> dict[str, Method]:
    methods: dict[str, Method] = {}

    def add(name: str, handler: Handler, params: dict[str, Param] | None = None, *,
            requires_login: bool = True, description: str = "") -> None:
        methods[name] = Method(name, handler, params or {}, requires_login, description)

    # --- sessão do protocolo -------------------------------------------------------
    add("rpc.hello", lambda c, p: {
        "protocol": PROTOCOL_VERSION, "core_version": __version__, "schema_version": c.db.schema_version,
        "methods": sorted(methods), **_whoami(c)}, requires_login=False,
        description="Versão do protocolo e métodos disponíveis.")
    add("rpc.shutdown", lambda c, p: (shutdown(), {"ok": True})[1], requires_login=False,
        description="Encerra o servidor.")

    # --- autenticação ----------------------------------------------------------------
    add("auth.login", lambda c, p: (c.login(p["name"], p["password"]), _whoami(c))[1],
        {"name": Param("str", max_len=64), "password": Param("str", max_len=PASSWORD_MAX)},
        requires_login=False, description="Entra com nome e senha.")
    add("setup.status", lambda c, p: {"initialized": c.technicians.count() > 0}, requires_login=False,
        description="Informa se já existe algum técnico (primeiro uso = ainda não).")
    add("setup.create_admin", lambda c, p: (c.bootstrap_admin(p["name"], p["password"]), _whoami(c))[1],
        {"name": Param("str", max_len=64), "password": Param("str", max_len=PASSWORD_MAX)},
        requires_login=False,
        description="Cria o PRIMEIRO administrador. O núcleo recusa se já houver qualquer técnico.")
    add("auth.logout", lambda c, p: (c.logout(), {"ok": True})[1], requires_login=False)
    add("auth.whoami", lambda c, p: _whoami(c), requires_login=False)
    add("auth.change_password",
        lambda c, p: {"changed": c.set_password(c.actor, p["new_password"], p["old_password"])},
        {"old_password": Param("str", max_len=PASSWORD_MAX), "new_password": Param("str", max_len=PASSWORD_MAX)})

    # --- painel e segurança -------------------------------------------------------------
    add("status.get", lambda c, p: c.status(), description="Painel inicial (dados reais do núcleo).")
    add("security.overview", lambda c, p: c.security_overview())
    add("system.paths", lambda c, p: {
        "home": str(c.paths.home), "database": str(c.paths.db), "logs": str(c.paths.logs),
        "backups": str(c.paths.backups), "modules": str(c.paths.modules)},
        description="Onde o NEXUS guarda dados, logs, backups e módulos instalados.")

    # --- dispositivos ---------------------------------------------------------------------
    add("devices.list", lambda c, p: c.devices.list(p["connection"]),
        {"connection": Param("str", required=False, choices=("connected", "disconnected", "unknown"))})
    add("devices.scan", lambda c, p: _scan(c))
    add("devices.add", lambda c, p: {"id": c.devices.add_manual(
        p["kind"], vendor=p["vendor"], model=p["model"], serial=p["serial"], label=p["label"])},
        {"kind": Param("str", choices=KINDS), "vendor": Param("str", False), "model": Param("str", False),
         "serial": Param("str", False), "label": Param("str", False)})

    # --- sessões -----------------------------------------------------------------------------
    add("sessions.recent", lambda c, p: c.sessions.recent(p["limit"]),
        {"limit": Param("int", False, minimum=1, maximum=200, default=10)})
    add("sessions.open", lambda c, p: c.sessions.open_sessions())
    add("sessions.start", lambda c, p: {"id": c.sessions.start(p["device_id"], p["kind"])},
        {"device_id": Param("int", minimum=1), "kind": Param("str", False, choices=SESSION_KINDS, default="general")})
    add("sessions.finish", lambda c, p: (c.sessions.finish(p["id"], status=p["status"], summary=p["summary"]), {"ok": True})[1],
        {"id": Param("int", minimum=1),
         "status": Param("str", False, choices=("completed", "aborted"), default="completed"),
         "summary": Param("str", False, max_len=2000)})

    # --- histórico --------------------------------------------------------------------------------
    add("audit.list", lambda c, p: _audit_list(c, p["limit"], p["session_id"]),
        {"limit": Param("int", False, minimum=1, maximum=500, default=50),
         "session_id": Param("int", False, minimum=1)})
    add("audit.verify", lambda c, p: _audit_verify(c))

    # --- módulos -------------------------------------------------------------------------------------
    add("modules.list", lambda c, p: c.modules.status())
    add("modules.verify", lambda c, p: _module_verify(c, p["id"]), {"id": Param("str", max_len=100)})
    add("modules.register", lambda c, p: (c.modules.register(p["id"], confirmed=p["confirmed"]), {"ok": True})[1],
        {"id": Param("str", max_len=100), "confirmed": Param("bool", False, default=False)})
    add("modules.enable", lambda c, p: (c.modules.enable(p["id"]), {"ok": True})[1], {"id": Param("str", max_len=100)})
    add("modules.disable", lambda c, p: (c.modules.disable(p["id"]), {"ok": True})[1], {"id": Param("str", max_len=100)})

    # --- backups (sempre por NOME, nunca por caminho) ------------------------------------------------------
    add("backups.list", lambda c, p: c.backups.describe())
    add("backups.create", lambda c, p: {"name": c.backups.create(p["reason"]).name},
        {"reason": Param("str", False, max_len=30, default="manual")})
    add("backups.verify", lambda c, p: (c.backups.verify(c.backups.path_for(p["name"])), {"ok": True})[1],
        {"name": Param("str", max_len=100)})
    add("backups.restore", lambda c, p: _restore(c, p["name"], p["confirmed"]),
        {"name": Param("str", max_len=100), "confirmed": Param("bool", False, default=False)})

    # --- configurações e técnicos --------------------------------------------------------------------------------
    add("settings.get_all", lambda c, p: c.settings.all())
    add("settings.set", lambda c, p: (c.set_setting(p["key"], p["value"]), {"ok": True})[1],
        {"key": Param("str", max_len=100), "value": Param("any")})
    add("technicians.list", lambda c, p: c.technicians.list())
    add("technicians.add", lambda c, p: {"id": c.add_technician(p["name"], p["role"], p["password"])},
        {"name": Param("str", max_len=64), "role": Param("str", choices=("viewer", "technician", "admin")),
         "password": Param("str", max_len=PASSWORD_MAX)})
    add("technicians.set_active", lambda c, p: (c.set_technician_active(p["name"], p["active"]), {"ok": True})[1],
        {"name": Param("str", max_len=64), "active": Param("bool")})
    add("technicians.set_password", lambda c, p: {"changed": c.set_password(p["name"], p["new_password"])},
        {"name": Param("str", max_len=64), "new_password": Param("str", max_len=PASSWORD_MAX)})
    return methods


# --- auxiliares ------------------------------------------------------------------------------------------------
def _scan(core: NexusCore) -> dict[str, Any]:
    report = core.devices.scan()
    return {"found": report.found, "errors": report.errors}


def _audit_list(core: NexusCore, limit: int, session_id: int | None) -> list[dict[str, Any]]:
    core.require(Permission.AUDIT_READ)
    return core.audit.recent(limit, session_id=session_id)


def _audit_verify(core: NexusCore) -> dict[str, Any]:
    core.require(Permission.AUDIT_READ)
    result = core.audit.verify()
    return {"ok": result.ok, "records": result.records, "first_bad_id": result.first_bad_id}


def _module_verify(core: NexusCore, module_id: str) -> dict[str, Any]:
    report = core.modules.verify(module_id)
    return {"ok": report.ok, "problems": report.problems}


def _restore(core: NexusCore, name: str, confirmed: bool) -> dict[str, Any]:
    safety_copy = core.backups.restore(core.backups.path_for(name), confirmed=confirmed)
    return {"safety_backup": safety_copy.name, "session_active": core.actor != ANONYMOUS}
