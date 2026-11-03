"""Configurações gerais com valores padrão e validação."""

from __future__ import annotations

import json
from typing import Any, Callable

from .database import Database
from .errors import ValidationError
from .util import utc_now


def _one_of(*allowed: str) -> Callable[[Any], bool]:
    return lambda v: v in allowed


def _int_between(low: int, high: int) -> Callable[[Any], bool]:
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and low <= v <= high


def _str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(i, str) and i.strip() for i in v)


# chave -> (padrão, validador)
SCHEMA: dict[str, tuple[Any, Callable[[Any], bool]]] = {
    "ui.theme": ("dark", _one_of("dark", "light")),
    "ui.language": ("pt-BR", _one_of("pt-BR", "en-US")),
    "mode": ("local", _one_of("local", "online")),
    "log.level": ("INFO", _one_of("DEBUG", "INFO", "WARNING", "ERROR")),
    "backup.keep": (10, _int_between(1, 200)),
    "modules.trusted_publishers": (["LMF Informática"], _str_list),
}


class SettingsStore:
    def __init__(self, db: Database):
        self._db = db

    def get(self, key: str) -> Any:
        if key not in SCHEMA:
            raise ValidationError(f"Configuração desconhecida: {key}")
        row = self._db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
        if row is None:
            default = SCHEMA[key][0]
            return list(default) if isinstance(default, list) else default
        return json.loads(row["value"])

    def set(self, key: str, value: Any) -> None:
        if key not in SCHEMA:
            raise ValidationError(f"Configuração desconhecida: {key}")
        if not SCHEMA[key][1](value):
            raise ValidationError(f"Valor inválido para {key}: {value!r}")
        self._db.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False), utc_now()),
        )

    def all(self) -> dict[str, Any]:
        return {key: self.get(key) for key in SCHEMA}
