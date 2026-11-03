"""Localização dos dados locais da plataforma."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def default_home() -> Path:
    override = os.environ.get("NEXUS_HOME")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "NexusOmnitech"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "nexus-omnitech"


@dataclass(frozen=True)
class Paths:
    home: Path

    @property
    def db(self) -> Path:
        return self.home / "nexus.db"

    @property
    def logs(self) -> Path:
        return self.home / "logs"

    @property
    def backups(self) -> Path:
        return self.home / "backups"

    @property
    def modules(self) -> Path:
        return self.home / "modules"

    @property
    def reports(self) -> Path:
        return self.home / "reports"

    @property
    def module_data(self) -> Path:
        return self.home / "module_data"

    def ensure(self) -> None:
        for folder in (self.home, self.logs, self.backups, self.modules, self.reports, self.module_data):
            folder.mkdir(parents=True, exist_ok=True)
