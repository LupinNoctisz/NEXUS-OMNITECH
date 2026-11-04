#!/usr/bin/env python3
"""Confere que núcleo (pyproject + __init__) e interface (csproj) têm a MESMA versão major.minor.patch."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def find(path: str, pattern: str) -> str:
    match = re.search(pattern, (ROOT / path).read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"versão não encontrada em {path}")
    return match.group(1)


versions = {
    "pyproject.toml": find("pyproject.toml", r'(?m)^version\s*=\s*"([^"]+)"'),
    "src/nexus/__init__.py": find("src/nexus/__init__.py", r'__version__\s*=\s*"([^"]+)"'),
    "ui/Nexus.App/Nexus.App.csproj": find("ui/Nexus.App/Nexus.App.csproj", r"<Version>([^<]+)</Version>"),
}
for name, value in versions.items():
    print(f"{value:10} {name}")
if len(set(versions.values())) != 1:
    sys.exit("ERRO: versões diferentes entre núcleo e interface.")
print("Versões consistentes.")
