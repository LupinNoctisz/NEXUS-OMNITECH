import json
from pathlib import Path

import pytest

from nexus.core import NexusCore, auth
from nexus.core.modules import seal_manifest

PASSWORD = "senha-de-teste-123"  # nexus:allow-secret (valor fictício de teste)


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch):
    """Custo de scrypt baixo apenas nos testes (produção usa 2**15)."""
    monkeypatch.setattr(auth, "SCRYPT_N", 2**10)


@pytest.fixture
def core(tmp_path):
    """Núcleo isolado, sem módulos empacotados, com um administrador."""
    instance = NexusCore(home=tmp_path / "home", module_dirs=[tmp_path / "mods"])
    instance.bootstrap_admin("admin", PASSWORD)
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


@pytest.fixture
def login_as(core):
    """login_as('tec', 'technician') cria o técnico (como admin) e entra como ele; login_as('admin') volta ao admin."""
    def _login(name, role="technician"):
        if name != "admin" and core.technicians.get(name) is None:
            core.login("admin", PASSWORD)
            core.add_technician(name, role, PASSWORD)
        core.login(name, PASSWORD)
    return _login
