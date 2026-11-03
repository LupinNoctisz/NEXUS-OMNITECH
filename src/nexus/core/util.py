"""Utilitários pequenos e sem dependências."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


_SENSITIVE = re.compile(r"(pass(word|wd)?|senha|token|secret|segredo|api[_-]?key|credential|credencial|license[_-]?key|chave)", re.I)


def redact(value: Any) -> Any:
    """Remove valores de chaves que parecem credenciais (recursivo)."""
    if isinstance(value, dict):
        return {k: ("***" if _SENSITIVE.search(str(k)) else redact(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value
