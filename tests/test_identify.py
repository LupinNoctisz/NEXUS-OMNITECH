import json

import pytest

from nexus.core.devices import LocalHostProvider, UsbProvider
from nexus.core.identify import clean_value, identify

from conftest import PASSWORD  # noqa: F401


def test_labeled_text_is_split_into_three_fields():
    r = identify("Fabricante: Lenovo\nModelo: IdeaPad 3 15ITL6\nSerial Number: PF3ABCDE")
    assert (r["vendor"], r["model"], r["serial"]) == ("Lenovo", "IdeaPad 3 15ITL6", "PF3ABCDE")
    assert r["sources"] == {"serial": "rótulo", "vendor": "rótulo", "model": "rótulo"}
    assert r["warnings"] == []


def test_known_vendor_and_serial_in_free_text_is_marked_as_guess():
    r = identify("Dell Inspiron 15 3520 S/N: ABC1234")
    assert (r["vendor"], r["model"], r["serial"]) == ("Dell", "Inspiron 15 3520", "ABC1234")
    assert r["sources"]["model"] == "texto restante"
    assert any("palpite" in w for w in r["warnings"])


def test_service_tag_does_not_swallow_the_vendor():
    r = identify("Service Tag: 7XK9L53 Dell Latitude 5420")
    assert (r["vendor"], r["model"], r["serial"]) == ("Dell", "Latitude 5420", "7XK9L53")


def test_imei_goes_to_serial_with_warning_and_label_is_not_part_of_model():
    r = identify("Samsung Galaxy A54 IMEI: 356938035643809")
    assert (r["vendor"], r["model"], r["serial"]) == ("Samsung", "Galaxy A54", "356938035643809")
    assert r["kind"] == "mobile"
    assert any("IMEI" in w for w in r["warnings"])


def test_two_serials_are_never_guessed():
    r = identify("S/N: 12345AB  SN: 99887XY HP Pavilion")
    assert r["serial"] is None
    assert r["alternatives"]["serial"] == ["12345AB", "99887XY"]
    assert r["vendor"] == "HP" and r["model"] == "Pavilion"


@pytest.mark.parametrize("text", ["", "   ", "To be filled by O.E.M.", "Default string", "N/A"])
def test_empty_or_placeholder_text_invents_nothing(text):
    r = identify(text)
    assert (r["vendor"], r["model"], r["serial"]) == (None, None, None)


@pytest.mark.parametrize("serial", ["0000", "1111111", "N/A", "ABC"])
def test_junk_serials_are_rejected(serial):
    assert identify(f"Modelo: X1 S/N: {serial}")["serial"] is None


def test_clean_value():
    assert clean_value("  Dell   Inc. ") == "Dell Inc"
    assert clean_value("To be filled by O.E.M.") is None
    assert clean_value("(Standard system devices)") is None
    assert clean_value(None) is None


def test_add_manual_drops_placeholders_and_requires_something(core):
    from nexus.core import ValidationError
    with pytest.raises(ValidationError):
        core.devices.add_manual("pc", vendor="N/A", model="Default string", serial="0000")
    device = core.devices.add_manual("pc", vendor=" Dell  ", model="Latitude", serial="TBD0000")
    row = [d for d in core.devices.list() if d["id"] == device][0]
    assert row["vendor"] == "Dell" and row["model"] == "Latitude"


def test_identify_requires_manage_permission(core, login_as):
    from nexus.core import PermissionDenied
    assert core.devices.identify("Dell Latitude S/N: ABCD1234")["vendor"] == "Dell"
    login_as("leitor", "viewer")
    with pytest.raises(PermissionDenied):
        core.devices.identify("Dell Latitude")


def test_local_host_reads_dmi_and_drops_placeholders(tmp_path):
    dmi = tmp_path / "dmi"
    dmi.mkdir()
    (dmi / "sys_vendor").write_text("LENOVO\n")
    (dmi / "product_name").write_text("To be filled by O.E.M.\n")
    # product_serial ausente (exige privilégio): campo fica vazio, sem erro
    info = LocalHostProvider(dmi_root=dmi, platform_name="linux").discover()[0]
    assert info.vendor == "LENOVO" and info.model is None and info.serial is None
    (dmi / "product_name").write_text("20XW0055BR\n")
    (dmi / "product_serial").write_text("PF3ABCDE\n")
    info = LocalHostProvider(dmi_root=dmi, platform_name="linux").discover()[0]
    assert (info.vendor, info.model, info.serial) == ("LENOVO", "20XW0055BR", "PF3ABCDE")


def test_local_host_windows_cim_and_failure(tmp_path):
    out = json.dumps({"Manufacturer": "Dell Inc.", "Model": "Latitude 5420", "Serial": "7XK9L53"})
    info = LocalHostProvider(runner=lambda cmd: out, platform_name="win32").discover()[0]
    assert (info.vendor, info.model, info.serial) == ("Dell Inc", "Latitude 5420", "7XK9L53")

    def boom(cmd):
        raise OSError("sem powershell")
    info = LocalHostProvider(runner=boom, platform_name="win32").discover()[0]
    assert info.vendor is None and info.label  # continua listado pelo nome


def test_windows_usb_serial_only_when_not_generated_by_windows():
    out = json.dumps([
        {"InstanceId": "USB\\VID_0951&PID_1666\\0019E06B4A5FDC91", "FriendlyName": "USB Mass Storage Device",
         "Manufacturer": "(Standard USB Host Controller)", "Status": "OK"},
        {"InstanceId": "USB\\VID_046D&PID_C52B\\6&2a1b3c4d&0&2", "FriendlyName": "Receptor", "Manufacturer": "Logitech",
         "Status": "OK"},
    ])
    first, second = UsbProvider.parse_windows_pnp(out)
    assert first.serial == "0019E06B4A5FDC91" and first.vendor is None
    assert second.serial is None and second.vendor == "Logitech"


def test_identify_over_rpc_is_registered():
    from nexus.api.methods import build_registry
    assert "devices.identify" in build_registry(lambda: None)

