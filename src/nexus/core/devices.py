"""Gerenciamento de dispositivos e descoberta por provedores.

Somente dados realmente lidos do sistema ou informados pelo técnico são
gravados. Não existem dispositivos de demonstração.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Protocol

from .errors import ValidationError
from .identify import clean_value, identify
from .permissions import Permission
from .util import sha256_bytes, utc_now

if TYPE_CHECKING:
    from .app import NexusCore

KINDS = ("pc", "usb", "mobile", "console", "other")


@dataclass
class DeviceInfo:
    uid: str
    kind: str
    source: str
    vendor: str | None = None
    model: str | None = None
    serial: str | None = None
    label: str | None = None
    connection: str = "connected"
    properties: dict[str, Any] = field(default_factory=dict)


class DeviceProvider(Protocol):
    name: str

    def discover(self) -> list[DeviceInfo]: ...


@dataclass
class ScanReport:
    found: int = 0
    errors: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Provedores
# --------------------------------------------------------------------------
class LocalHostProvider:
    """Identifica o computador onde o NEXUS está rodando (dados reais da plataforma).

    Fabricante, modelo e serial vêm do firmware (DMI no Linux; CIM no Windows). Textos de
    preenchimento como "To be filled by O.E.M." são descartados: o campo fica vazio.
    """

    name = "local-host"

    def __init__(self, dmi_root: Path | None = None, runner: Callable[[list[str]], str] | None = None,
                 platform_name: str | None = None):
        self._dmi = dmi_root or Path("/sys/class/dmi/id")
        self._run = runner or UsbProvider._default_runner
        self._platform = platform_name or sys.platform

    def _hardware_identity(self) -> dict[str, str | None]:
        empty: dict[str, str | None] = {"vendor": None, "model": None, "serial": None}
        try:
            if self._platform == "win32":
                script = ("$c = Get-CimInstance Win32_ComputerSystem; $b = Get-CimInstance Win32_BIOS; "
                          "[pscustomobject]@{Manufacturer=$c.Manufacturer; Model=$c.Model; Serial=$b.SerialNumber} "
                          "| ConvertTo-Json -Compress")
                data = json.loads(self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script]) or "{}")
                return {"vendor": clean_value(data.get("Manufacturer")), "model": clean_value(data.get("Model")),
                        "serial": clean_value(data.get("Serial"))}
            if self._platform.startswith("linux"):
                return {"vendor": clean_value(_read(self._dmi / "sys_vendor")),
                        "model": clean_value(_read(self._dmi / "product_name")),
                        # product_serial exige privilégio de administrador no Linux; sem ele fica vazio
                        "serial": clean_value(_read(self._dmi / "product_serial"))}
        except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
            pass  # identificação é opcional: o computador continua listado pelo nome
        return empty

    def discover(self) -> list[DeviceInfo]:
        node = platform.node() or "desconhecido"
        identity = self._hardware_identity()
        return [
            DeviceInfo(
                uid="host:" + sha256_bytes(node.encode("utf-8"))[:16],
                kind="pc",
                source=self.name,
                vendor=identity["vendor"],
                model=identity["model"],
                serial=identity["serial"],
                label=node,
                properties={
                    "os": platform.system(),
                    "os_release": platform.release(),
                    "os_version": platform.version(),
                    "arch": platform.machine(),
                    "python": platform.python_version(),
                },
            )
        ]


_VIDPID = re.compile(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})", re.I)
_HUB_CLASS = "09"


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip() or None
    except OSError:
        return None


class UsbProvider:
    """Lista dispositivos USB presentes (Linux: sysfs; Windows: PowerShell/PnP)."""

    name = "usb"

    def __init__(self, sysfs_root: Path | None = None,
                 runner: Callable[[list[str]], str] | None = None,
                 platform_name: str | None = None):
        self._sysfs = sysfs_root or Path("/sys/bus/usb/devices")
        self._run = runner or self._default_runner
        self._platform = platform_name or sys.platform

    @staticmethod
    def _default_runner(cmd: list[str]) -> str:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True).stdout

    def discover(self) -> list[DeviceInfo]:
        if self._platform == "win32":
            return self._discover_windows()
        if self._platform.startswith("linux"):
            return self._discover_linux()
        raise NotImplementedError(f"Enumeração USB ainda não suportada em {self._platform}.")

    def _discover_linux(self) -> list[DeviceInfo]:
        devices: list[DeviceInfo] = []
        if not self._sysfs.is_dir():
            return devices
        for entry in sorted(self._sysfs.iterdir()):
            if ":" in entry.name:  # interfaces, não dispositivos
                continue
            vid, pid = _read(entry / "idVendor"), _read(entry / "idProduct")
            if not vid or not pid:
                continue  # root hubs/entradas sem ID
            if _read(entry / "bDeviceClass") == _HUB_CLASS:
                continue
            serial = clean_value(_read(entry / "serial"))
            devices.append(
                DeviceInfo(
                    uid=f"usb:{vid}:{pid}:{serial or entry.name}",
                    kind="usb",
                    source=self.name,
                    vendor=clean_value(_read(entry / "manufacturer")),
                    model=clean_value(_read(entry / "product")),
                    serial=serial,
                    properties={"vendor_id": vid, "product_id": pid, "bus_path": entry.name,
                                "speed_mbps": _read(entry / "speed")},
                )
            )
        return devices

    def _discover_windows(self) -> list[DeviceInfo]:
        script = (
            "Get-PnpDevice -PresentOnly -Class USB,WPD,AndroidUsbDeviceClass -ErrorAction SilentlyContinue | "
            "Select-Object InstanceId,FriendlyName,Manufacturer,Status | ConvertTo-Json -Compress"
        )
        output = self._run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])
        return self.parse_windows_pnp(output, self.name)

    @staticmethod
    def parse_windows_pnp(output: str, source: str = "usb") -> list[DeviceInfo]:
        output = output.strip()
        if not output:
            return []
        data = json.loads(output)
        if isinstance(data, dict):
            data = [data]
        devices: list[DeviceInfo] = []
        for item in data:
            instance = item.get("InstanceId") or ""
            match = _VIDPID.search(instance)
            if not match:
                continue
            vid, pid = match.group(1).lower(), match.group(2).lower()
            tail = instance.rsplit("\\", 1)[-1]
            # Se o Windows gerou o sufixo (contém "&"), ele NÃO é o serial do aparelho.
            serial = clean_value(tail) if "&" not in tail and len(tail) >= 4 else None
            devices.append(
                DeviceInfo(
                    uid=f"usb:{vid}:{pid}:{tail}",
                    kind="usb",
                    source=source,
                    vendor=clean_value(item.get("Manufacturer")),
                    model=clean_value(item.get("FriendlyName")),
                    serial=serial,
                    properties={"vendor_id": vid, "product_id": pid, "instance_id": instance,
                                "pnp_status": item.get("Status")},
                )
            )
        return devices


# --------------------------------------------------------------------------
# Repositório
# --------------------------------------------------------------------------
class DeviceRegistry:
    def __init__(self, core: "NexusCore"):
        self._core = core
        self.providers: list[DeviceProvider] = [LocalHostProvider(), UsbProvider()]

    def register_provider(self, provider: DeviceProvider) -> None:
        self.providers.append(provider)

    def upsert(self, info: DeviceInfo) -> int:
        if info.kind not in KINDS:
            raise ValidationError(f"Tipo de dispositivo inválido: {info.kind}")
        now = utc_now()
        self._core.db.execute(
            "INSERT INTO devices (uid, kind, source, vendor, model, serial, label, connection, first_seen, last_seen, properties)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(uid) DO UPDATE SET kind=excluded.kind, source=excluded.source,"
            " vendor=COALESCE(excluded.vendor, vendor), model=COALESCE(excluded.model, model),"
            " serial=COALESCE(excluded.serial, serial), label=COALESCE(excluded.label, label),"
            " connection=excluded.connection, last_seen=excluded.last_seen, properties=excluded.properties",
            (info.uid, info.kind, info.source, info.vendor, info.model, info.serial, info.label,
             info.connection, now, now, json.dumps(info.properties, ensure_ascii=False, default=str)),
        )
        return int(self._core.db.query_one("SELECT id FROM devices WHERE uid = ?", (info.uid,))["id"])

    def identify(self, text: str) -> dict[str, Any]:
        """Sugere fabricante, modelo e serial a partir de um texto. Não grava nada."""
        self._core.require(Permission.DEVICES_MANAGE)
        return identify(text)

    def add_manual(self, kind: str, *, vendor: str | None = None, model: str | None = None,
                   serial: str | None = None, label: str | None = None) -> int:
        self._core.require(Permission.DEVICES_MANAGE)
        vendor, model, serial, label = (clean_value(v) for v in (vendor, model, serial, label))
        if not any((vendor, model, serial, label)):
            raise ValidationError("Informe ao menos fabricante, modelo, serial ou identificação.")
        device_id = self.upsert(DeviceInfo(
            uid=f"manual:{uuid.uuid4().hex[:12]}", kind=kind, source="manual",
            vendor=vendor, model=model, serial=serial, label=label, connection="unknown"))
        self._core.audit.record("device.add", technician=self._core.actor, target=str(device_id),
                                details={"kind": kind, "vendor": vendor, "model": model})
        return device_id

    def scan(self) -> ScanReport:
        self._core.require(Permission.DEVICES_MANAGE)
        report = ScanReport()
        for provider in self.providers:
            try:
                found = provider.discover()
            except Exception as exc:  # um provedor com falha não derruba os demais
                report.errors[provider.name] = f"{type(exc).__name__}: {exc}"
                self._core.log.warning("provedor de dispositivos falhou", extra={"provider": provider.name, "error": str(exc)})
                continue
            uids = []
            for info in found:
                self.upsert(info)
                uids.append(info.uid)
            report.found += len(found)
            marks = ",".join("?" for _ in uids)
            clause = f" AND uid NOT IN ({marks})" if uids else ""
            self._core.db.execute(
                "UPDATE devices SET connection='disconnected' WHERE source = ? AND connection='connected'" + clause,
                (provider.name, *uids),
            )
        self._core.audit.record("device.scan", technician=self._core.actor,
                                details={"found": report.found, "errors": report.errors},
                                outcome="ok" if not report.errors else "partial")
        return report

    def get(self, device_id: int) -> dict | None:
        row = self._core.db.query_one("SELECT * FROM devices WHERE id = ?", (device_id,))
        return self._decode(row) if row else None

    def list(self, connection: str | None = None) -> list[dict]:
        self._core.require(Permission.DEVICES_READ)
        if connection:
            rows = self._core.db.query_all("SELECT * FROM devices WHERE connection = ? ORDER BY last_seen DESC", (connection,))
        else:
            rows = self._core.db.query_all("SELECT * FROM devices ORDER BY last_seen DESC")
        return [self._decode(r) for r in rows]

    @staticmethod
    def _decode(row) -> dict:
        data = dict(row)
        data["properties"] = json.loads(data["properties"])
        return data
