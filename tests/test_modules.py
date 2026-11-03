import json

import pytest

from nexus.core import ConfirmationRequired, IntegrityError, ModuleError, PermissionDenied


def test_register_requires_confirmation(core, make_module):
    make_module()
    with pytest.raises(ConfirmationRequired):
        core.modules.register("nexus.demo")


def test_full_lifecycle_loads_and_unloads(core, make_module):
    make_module()
    core.modules.register("nexus.demo", confirmed=True)
    core.modules.enable("nexus.demo")
    assert core.modules.load_enabled() == {}
    instance = core.modules.loaded["nexus.demo"]
    assert instance.started is True
    assert instance.ctx.data_dir.is_dir()
    core.modules.disable("nexus.demo")
    assert "nexus.demo" not in core.modules.loaded and instance.started is False


def test_enable_requires_registration(core, make_module):
    make_module()
    with pytest.raises(ModuleError):
        core.modules.enable("nexus.demo")


def test_untrusted_publisher_rejected(core, make_module):
    make_module("externo", publisher="Terceiro Ltda")
    with pytest.raises(ModuleError, match="não confiável"):
        core.modules.register("nexus.externo", confirmed=True)


def test_trusting_publisher_is_explicit_admin_action(core, make_module):
    make_module("externo", publisher="Terceiro Ltda")
    core.set_setting("modules.trusted_publishers", ["LMF Informática", "Terceiro Ltda"])
    core.modules.register("nexus.externo", confirmed=True)


def test_planned_module_cannot_be_registered(core, tmp_path):
    root = tmp_path / "mods" / "nexus.futuro"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({
        "id": "nexus.futuro", "name": "F", "version": "0.0.0", "publisher": "LMF Informática", "status": "planned"}))
    with pytest.raises(ModuleError, match="não está disponível"):
        core.modules.register("nexus.futuro", confirmed=True)


def test_tampered_file_blocks_register_enable_and_load(core, make_module):
    root = make_module()
    core.modules.register("nexus.demo", confirmed=True)
    core.modules.enable("nexus.demo")
    (root / "module.py").write_text("raise SystemExit('malicioso')\n", encoding="utf-8")
    assert not core.modules.verify("nexus.demo").ok
    blocked = core.modules.load_enabled()
    assert "nexus.demo" in blocked and "nexus.demo" not in core.modules.loaded
    with pytest.raises(IntegrityError):
        core.modules.enable("nexus.demo")
    with pytest.raises(IntegrityError):
        core.modules.register("nexus.demo", confirmed=True)


def test_undeclared_executable_is_flagged(core, make_module):
    root = make_module()
    (root / "extra.ps1").write_text("Write-Host oi")
    report = core.modules.verify("nexus.demo")
    assert not report.ok and any("extra.ps1" in p for p in report.problems)


def test_manifest_change_after_register_is_flagged(core, make_module):
    root = make_module()
    core.modules.register("nexus.demo", confirmed=True)
    data = json.loads((root / "manifest.json").read_text())
    data["version"] = "9.9.9"
    (root / "manifest.json").write_text(json.dumps(data))
    assert any("manifesto alterado" in p for p in core.modules.verify("nexus.demo").problems)


def test_path_traversal_in_manifest_is_flagged(core, make_module, tmp_path):
    root = make_module()
    data = json.loads((root / "manifest.json").read_text())
    data["files"]["../../fora.txt"] = "0" * 64
    (root / "manifest.json").write_text(json.dumps(data))
    assert any("fora da pasta" in p or "ausente" in p for p in core.modules.verify("nexus.demo").problems)


def test_module_with_bad_interface_is_blocked(core, make_module):
    make_module("ruim", code="class Module:\n    pass\n")
    core.modules.register("nexus.ruim", confirmed=True)
    core.modules.enable("nexus.ruim")
    assert "nexus.ruim" in core.modules.load_enabled()


def test_module_actions_are_audited_with_module_prefix(core, make_module):
    make_module()
    core.modules.register("nexus.demo", confirmed=True)
    core.modules.enable("nexus.demo")
    core.modules.load_enabled()
    core.modules.loaded["nexus.demo"].ctx.audit_record("teste")
    assert core.audit.recent(1)[0]["action"] == "nexus.demo:teste"


def test_technician_cannot_manage_modules(core, make_module):
    make_module()
    core.add_technician("tec", "technician")
    core.actor = "tec"
    with pytest.raises(PermissionDenied):
        core.modules.register("nexus.demo", confirmed=True)


def test_bundled_planned_modules_are_listed():
    from pathlib import Path
    from nexus.core.modules import Manifest
    root = Path(__file__).resolve().parents[1] / "modules"
    manifests = [Manifest.from_dir(p) for p in sorted(root.iterdir()) if p.is_dir()]
    assert {m.id for m in manifests} == {
        "nexus.pc_diagnostics", "nexus.mobile_tools", "nexus.console_tools",
        "nexus.electronics_lab", "nexus.intelligence"}
    assert all(m.status == "planned" for m in manifests)
