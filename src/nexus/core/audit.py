"""Histórico de operações com encadeamento de hashes (detecta adulteração).

Cada registro inclui o hash do anterior. Alterar ou remover um registro do meio
quebra a cadeia e é detectado por ``verify()``. Remover registros do FIM não é
detectável apenas localmente; a âncora do hash final na nuvem está prevista para
a etapa de sincronização.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .database import Database
from .util import canonical_json, redact, sha256_bytes, utc_now

GENESIS = "0" * 64


@dataclass(frozen=True)
class AuditVerification:
    ok: bool
    records: int
    first_bad_id: int | None = None


def _digest(prev: str, ts: str, technician: str, action: str, target: str | None,
            session_id: int | None, details: str, outcome: str) -> str:
    payload = canonical_json([prev, ts, technician, action, target, session_id, details, outcome])
    return sha256_bytes(payload.encode("utf-8"))


class AuditLog:
    def __init__(self, db: Database):
        self._db = db

    def record(
        self,
        action: str,
        *,
        technician: str = "system",
        target: str | None = None,
        session_id: int | None = None,
        details: dict[str, Any] | None = None,
        outcome: str = "ok",
    ) -> int:
        details_json = canonical_json(redact(details or {}))
        with self._db.transaction():
            last = self._db.query_one("SELECT hash FROM operations ORDER BY id DESC LIMIT 1")
            prev = last["hash"] if last else GENESIS
            ts = utc_now()
            digest = _digest(prev, ts, technician, action, target, session_id, details_json, outcome)
            cursor = self._db.execute(
                "INSERT INTO operations (ts, technician, action, target, session_id, details, outcome, prev_hash, hash)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (ts, technician, action, target, session_id, details_json, outcome, prev, digest),
            )
            return int(cursor.lastrowid)

    def recent(self, limit: int = 50, session_id: int | None = None) -> list[dict[str, Any]]:
        if session_id is None:
            rows = self._db.query_all("SELECT * FROM operations ORDER BY id DESC LIMIT ?", (limit,))
        else:
            rows = self._db.query_all(
                "SELECT * FROM operations WHERE session_id = ? ORDER BY id DESC LIMIT ?", (session_id, limit)
            )
        return [dict(r) for r in rows]

    def verify(self) -> AuditVerification:
        prev = GENESIS
        count = 0
        for row in self._db.query_all("SELECT * FROM operations ORDER BY id ASC"):
            expected = _digest(prev, row["ts"], row["technician"], row["action"], row["target"],
                               row["session_id"], row["details"], row["outcome"])
            if row["prev_hash"] != prev or row["hash"] != expected:
                return AuditVerification(False, count, int(row["id"]))
            prev = row["hash"]
            count += 1
        return AuditVerification(True, count)
