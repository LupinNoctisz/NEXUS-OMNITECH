"""Proteção para operações destrutivas.

Nenhuma operação que possa alterar ou apagar dados do dispositivo roda sem:
  1. permissão ``destructive.run``;
  2. confirmação explícita do técnico;
  3. autorização registrada do proprietário do dispositivo;
  4. backup/salvaguarda concluído com sucesso ANTES da ação;
  5. registro no histórico (início, resultado e falhas).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, TypeVar

from .errors import BackupError, ConfirmationRequired, ValidationError
from .permissions import Permission

if TYPE_CHECKING:
    from .app import NexusCore

T = TypeVar("T")
MIN_AUTH_LEN = 5


@dataclass(frozen=True)
class DestructiveRequest:
    operation: str
    device_id: int
    description: str
    owner_authorization: str  # ex.: "Autorizado por Maria Silva (proprietária), OS 1234"
    confirmed: bool = False
    session_id: int | None = None


class SafetyGuard:
    def __init__(self, core: "NexusCore"):
        self._core = core

    def run(self, request: DestructiveRequest, action: Callable[[], T],
            backup: Callable[[], Path | str | None]) -> T:
        core = self._core
        core.require(Permission.DESTRUCTIVE_RUN)
        if not request.confirmed:
            raise ConfirmationRequired(f"Confirmação necessária para: {request.description}")
        if len((request.owner_authorization or "").strip()) < MIN_AUTH_LEN:
            raise ConfirmationRequired("Registre a autorização do proprietário do dispositivo antes de continuar.")
        if not request.operation.strip():
            raise ValidationError("Operação sem identificação.")
        if core.devices.get(request.device_id) is None:
            raise ValidationError(f"Dispositivo {request.device_id} não encontrado.")

        base = {"description": request.description, "authorization": request.owner_authorization}
        try:
            saved = backup()
        except Exception as exc:
            core.audit.record("destructive.aborted", technician=core.actor, target=str(request.device_id),
                              session_id=request.session_id, outcome="backup_failed",
                              details={**base, "operation": request.operation, "error": str(exc)})
            raise BackupError(f"Backup falhou; operação NÃO executada: {exc}") from exc

        core.audit.record("destructive.start", technician=core.actor, target=str(request.device_id),
                          session_id=request.session_id,
                          details={**base, "operation": request.operation, "backup": str(saved) if saved else None})
        try:
            result = action()
        except Exception as exc:
            core.audit.record("destructive.finish", technician=core.actor, target=str(request.device_id),
                              session_id=request.session_id, outcome="failed",
                              details={"operation": request.operation, "error": str(exc)})
            raise
        core.audit.record("destructive.finish", technician=core.actor, target=str(request.device_id),
                          session_id=request.session_id, details={"operation": request.operation})
        return result
