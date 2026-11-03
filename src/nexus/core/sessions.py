"""Sessões de diagnóstico: ciclo de vida de um atendimento técnico a um dispositivo."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .errors import NexusError, ValidationError
from .permissions import Permission
from .util import utc_now

if TYPE_CHECKING:
    from .app import NexusCore

SESSION_KINDS = ("pc_diagnostics", "mobile", "console", "electronics", "general")


class SessionManager:
    def __init__(self, core: "NexusCore"):
        self._core = core

    def start(self, device_id: int, kind: str = "general") -> int:
        self._core.require(Permission.SESSIONS_RUN)
        if kind not in SESSION_KINDS:
            raise ValidationError(f"Tipo de sessão inválido: {kind}")
        if self._core.devices.get(device_id) is None:
            raise ValidationError(f"Dispositivo {device_id} não encontrado.")
        already = self._core.db.query_one(
            "SELECT id FROM sessions WHERE device_id = ? AND kind = ? AND status = 'open'", (device_id, kind))
        if already:
            raise NexusError(f"Já existe a sessão aberta {already['id']} deste tipo para o dispositivo.")
        with self._core.db.transaction():
            cursor = self._core.db.execute(
                "INSERT INTO sessions (device_id, kind, technician, status, started_at) VALUES (?,?,?, 'open', ?)",
                (device_id, kind, self._core.actor, utc_now()))
            session_id = int(cursor.lastrowid)
            self._core.audit.record("session.start", technician=self._core.actor, target=str(device_id),
                                    session_id=session_id, details={"kind": kind})
        return session_id

    def finish(self, session_id: int, *, status: str = "completed", summary: str | None = None) -> None:
        self._core.require(Permission.SESSIONS_RUN)
        if status not in ("completed", "aborted"):
            raise ValidationError("Status final deve ser 'completed' ou 'aborted'.")
        with self._core.db.transaction():
            session = self.get(session_id)
            if session is None:
                raise ValidationError(f"Sessão {session_id} não encontrada.")
            if session["status"] != "open":
                raise NexusError(f"A sessão {session_id} já foi encerrada.")
            self._core.db.execute(
                "UPDATE sessions SET status = ?, ended_at = ?, summary = ? WHERE id = ?",
                (status, utc_now(), summary, session_id))
            self._core.audit.record("session.finish", technician=self._core.actor, session_id=session_id,
                                    details={"status": status})

    def get(self, session_id: int) -> dict | None:
        row = self._core.db.query_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(row) if row else None

    def recent(self, limit: int = 10) -> list[dict]:
        rows = self._core.db.query_all(
            "SELECT s.*, d.label AS device_label, d.model AS device_model FROM sessions s"
            " JOIN devices d ON d.id = s.device_id ORDER BY s.id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def open_sessions(self) -> list[dict]:
        return [dict(r) for r in self._core.db.query_all("SELECT * FROM sessions WHERE status = 'open' ORDER BY id")]
