import json
from pathlib import Path

import pytest

from nexus.core import NexusCore
from nexus.core.modules import seal_manifest


@pytest.fixture
def core(tmp_path):
    """Núcleo isolado, sem módulos empacotados, com um administrador."""
    instance = NexusCore(home=tmp_path / "home", module_dirs=[tmp_path / "mods"])
    instance.bootstrap_admin("admin")
    yield instance
    instance.close()


@pytest.fixture
def make_module(tmp_path):
    """Cria e sela um módulo de teste real em tmp/mods."""
    def _make(name="demo", publisher="LMF Informática", status="available", code=None):
        root = tmp_path / "mods" / f"nexus.{name}"
        root.mkdir(parents=True, exist_ok=True)
        (root / "module.py").write_text(code or (
            "class Module:\n"
            "    def initialize(self, ctx):\n"
            "        self.ctx = ctx\n"
            "        self.started = True\n"
            "    def shutdown(self):\n"
            "        self.started = False\n"
        ), encoding="utf-8")
        (root / "manifest.json").write_text(json.dumps({
            "id": f"nexus.{name}", "name": name, "version": "1.0.0", "publisher": publisher,
            "status": status, "entry": "module.py:Module", "min_core": "0.1.0",
        }), encoding="utf-8")
        seal_manifest(root)
        return root
    return _make
