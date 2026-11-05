"""Histórico de operações com encadeamento de hashes (detecta adulteração).

Cada registro inclui o hash do anterior. Alterar ou remover um registro do meio
quebra a cadeia e é detectado por ``verify()``. Remover registros do FIM não é
detectável apenas localmente; a âncora do hash final na nuvem está prevista para
a etapa de sincronização.
"""

from __future__ import annotations

import time
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
    #: "full" = a cadeia inteira foi conferida agora; "incremental" = só o que é novo desde a última conferência completa
    scope: str = "full"

    @property
    def is_full(self) -> bool:
        return self.scope == "full"


def _digest(prev: str, ts: str, technician: str, action: str, target: str | None,
            session_id: int | None, details: str, outcome: str) -> str:
    payload = canonical_json([prev, ts, technician, action, target, session_id, details, outcome])
    return sha256_bytes(payload.encode("utf-8"))


_BATCH = 2000
FULL_RESCAN_SECONDS = 300.0  # no máximo 5 min sem conferir a cadeia inteira


class AuditLog:
    def __init__(self, db: Database):
        self._db = db
        # (id do último registro conferido, hash dele, quantidade conferida) da última verificação que passou
        self._checkpoint: tuple[int, str, int] | None = None
        self._full_at = 0.0

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

    def _scan(self, prev: str, after_id: int, count: int) -> AuditVerification:
        """Confere a cadeia a partir de ``after_id`` em lotes (memória constante; o banco não fica travado o tempo todo)."""
        last_id = after_id
        while True:
            rows = self._db.query_all(
                "SELECT * FROM operations WHERE id > ? ORDER BY id ASC LIMIT ?", (last_id, _BATCH))
            if not rows:
                break
            for row in rows:
                expected = _digest(prev, row["ts"], row["technician"], row["action"], row["target"],
                                   row["session_id"], row["details"], row["outcome"])
                if row["prev_hash"] != prev or row["hash"] != expected:
                    return AuditVerification(False, count, int(row["id"]))
                prev = row["hash"]
                count += 1
                last_id = int(row["id"])
        if last_id:
            self._checkpoint = (last_id, prev, count)
        return AuditVerification(True, count)

    def verify(self) -> AuditVerification:
        """Conferência COMPLETA de toda a cadeia (é a que detecta adulteração em registros antigos)."""
        self._checkpoint = None
        result = self._scan(GENESIS, 0, 0)
        self._full_at = time.monotonic()
        return result

    def verify_incremental(self) -> AuditVerification:
        """
        Barata o bastante para o painel inicial: só confere o que é novo desde a última verificação que passou.
        A primeira chamada do processo (ou depois de restaurar um backup) faz a conferência completa.
        Alterações em registros antigos já conferidos só aparecem na conferência completa, que é refeita a cada
        ``FULL_RESCAN_SECONDS`` e sempre na tela Segurança (``verify()``).
        """
        checkpoint = self._checkpoint
        if checkpoint is not None and time.monotonic() - self._full_at < FULL_RESCAN_SECONDS:
            last_id, last_hash, count = checkpoint
            row = self._db.query_one("SELECT hash FROM operations WHERE id = ?", (last_id,))
            if row is not None and row["hash"] == last_hash:
                result = self._scan(last_hash, last_id, count)
                return AuditVerification(result.ok, result.records, result.first_bad_id, scope="incremental")
        return self.verify()

