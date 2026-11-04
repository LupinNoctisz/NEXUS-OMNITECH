#!/usr/bin/env python3
"""Gera ui/Nexus.Tests/Fixtures/*.json: respostas REAIS do servidor JSON-RPC com dados FICTÍCIOS.

Os testes em C# desserializam estes arquivos para garantir que os DTOs da interface batem com o que o
núcleo realmente devolve (contrato UI <-> núcleo). Rode de novo sempre que o protocolo mudar:

    python scripts/dump_rpc_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexus.api.server import RpcServer  # noqa: E402
from nexus.core import NexusCore, auth  # noqa: E402
from nexus.core.devices import DeviceInfo  # noqa: E402
from nexus.core.modules import seal_manifest  # noqa: E402

OUT = ROOT / "ui" / "Nexus.Tests" / "Fixtures"
PASSWORD = "senha-ficticia-123"  # nexus:allow-secret (valor fictício)
auth.SCRYPT_N = 2**10  # apenas para gerar rápido; o hash guarda os parâmetros


class DemoProvider:
    name = "demo"

    def discover(self):
        return [DeviceInfo(uid="usb:18d1:4ee7:DEMO0001", kind="usb", source="demo", vendor="Demo Vendor",
                           model="Demo Phone", serial="DEMO0001",
                           properties={"vendor_id": "18d1", "product_id": "4ee7", "speed_mbps": "480"})]


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="nexus_fixtures_"))
    try:
        module_root = work / "mods" / "nexus.demo"
        module_root.mkdir(parents=True)
        (module_root / "module.py").write_text(
            "class Module:\n    def initialize(self, ctx):\n        pass\n    def shutdown(self):\n        pass\n",
            encoding="utf-8")
        (module_root / "manifest.json").write_text(json.dumps({
            "id": "nexus.demo", "name": "Módulo de demonstração", "version": "1.0.0",
            "publisher": "LMF Informática", "status": "available", "entry": "module.py:Module"}), encoding="utf-8")
        seal_manifest(module_root)

        core = NexusCore(home=work / "home", module_dirs=[work / "mods", ROOT / "modules"])
        core.bootstrap_admin("tecnico.demo", PASSWORD)
        core.add_technician("leitor.demo", "viewer", PASSWORD)
        core.devices.providers = [DemoProvider()]
        core.devices.scan()
        manual = core.devices.add_manual("pc", vendor="Demo", model="Notebook Demo", label="Cliente Demo A")
        finished = core.sessions.start(manual, "pc_diagnostics")
        core.sessions.finish(finished, summary="Sessão de demonstração")
        core.sessions.start(1, "general")
        core.modules.register("nexus.demo", confirmed=True)
        core.modules.enable("nexus.demo")
        core.backups.create("demo")
        core.logout()

        server = RpcServer(core)
        counter = 0
        saved: dict[str, dict] = {}

        def call(fixture: str, method: str, /, **params):
            nonlocal counter
            counter += 1
            request = {"jsonrpc": "2.0", "id": counter, "method": method, "params": params}
            saved[fixture] = json.loads(server.handle(json.dumps(request).encode()))

        call("hello", "rpc.hello")
        call("setup_status", "setup.status")
        call("error_already_initialized", "setup.create_admin", name="intruso", password=PASSWORD)
        call("error_not_authenticated", "status.get")
        call("login", "auth.login", name="tecnico.demo", password=PASSWORD)
        call("status", "status.get")
        call("security_overview", "security.overview")
        call("system_paths", "system.paths")
        call("devices_list", "devices.list")
        call("scan_result", "devices.scan")
        call("sessions_recent", "sessions.recent", limit=10)
        call("sessions_open", "sessions.open")
        call("audit_list", "audit.list", limit=5)
        call("audit_verify", "audit.verify")
        call("modules_list", "modules.list")
        call("module_verify", "modules.verify", id="nexus.demo")
        call("backups_list", "backups.list")
        call("settings_all", "settings.get_all")
        call("technicians_list", "technicians.list")
        backup_name = saved["backups_list"]["result"][0]["name"]
        call("restore_result", "backups.restore", name=backup_name, confirmed=True)
        call("error_confirmation", "backups.restore", name=backup_name)
        call("error_validation", "settings.set", key="ui.theme", value="neon")
        call("error_invalid_params", "devices.add", kind="geladeira")
        core.logout()
        core.login("leitor.demo", PASSWORD)
        call("error_permission", "devices.scan")
        core.close()

        OUT.mkdir(parents=True, exist_ok=True)
        for name, response in saved.items():
            (OUT / f"{name}.json").write_text(json.dumps(response, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{len(saved)} arquivo(s) gravados em {OUT}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
