"""Logs estruturados (JSON Lines) com rotação e redação de credenciais."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .util import redact

_RESERVED = set(logging.LogRecord("x", 0, "x", 0, "", (), None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
        if extras:
            payload["extra"] = redact(extras)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("nexus")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    close_logging()
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        Path(log_dir) / "nexus.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    handler.set_name("nexus-file")
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def close_logging() -> None:
    logger = logging.getLogger("nexus")
    for handler in list(logger.handlers):
        if handler.get_name() == "nexus-file":
            handler.close()
            logger.removeHandler(handler)
