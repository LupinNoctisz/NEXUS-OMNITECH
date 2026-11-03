"""Interface de linha de comando do NEXUS CORE (usada por técnicos e pela futura UI)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import PRODUCT_NAME, TAGLINE, VENDOR, __version__
from .core import NexusCore, NexusError
from .core.modules import seal_manifest


def _print(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus", description=f"{PRODUCT_NAME} by {VENDOR} - {TAGLINE}")
    parser.add_argument("--version", action="version", version=f"{PRODUCT_NAME} {__version__}")
    parser.add_argument("--home", help="pasta de dados (padrão: NEXUS_HOME ou diretório do usuário)")
    parser.add_argument("--as", dest="actor", help="nome do técnico (ou variável NEXUS_TECHNICIAN)")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="cria o primeiro administrador")
    init.add_argument("--admin", required=True)

    sub.add_parser("status", help="painel inicial (dispositivos, sessões, alertas, módulos)")

    tech = sub.add_parser("technician", help="gerencia técnicos").add_subparsers(dest="action", required=True)
    add = tech.add_parser("add")
    add.add_argument("name")
    add.add_argument("--role", choices=["viewer", "technician", "admin"], default="technician")
    tech.add_parser("list")

    dev = sub.add_parser("devices", help="dispositivos").add_subparsers(dest="action", required=True)
    dev.add_parser("scan")
    dev.add_parser("list")
    manual = dev.add_parser("add")
    manual.add_argument("--kind", required=True)
    manual.add_argument("--vendor")
    manual.add_argument("--model")
    manual.add_argument("--serial")
    manual.add_argument("--label")

    mod = sub.add_parser("modules", help="módulos").add_subparsers(dest="action", required=True)
    mod.add_parser("list")
    for name in ("verify", "enable", "disable"):
        mod.add_parser(name).add_argument("id")
    reg = mod.add_parser("register")
    reg.add_argument("id")
    reg.add_argument("--confirm", action="store_true", help="confirma o registro do módulo")
    seal = mod.add_parser("seal", help="(desenvolvedor) grava os hashes dos arquivos no manifesto")
    seal.add_argument("directory")

    audit = sub.add_parser("audit", help="histórico de operações").add_subparsers(dest="action", required=True)
    listing = audit.add_parser("list")
    listing.add_argument("--limit", type=int, default=20)
    audit.add_parser("verify")

    backup = sub.add_parser("backup", help="backups do banco local").add_subparsers(dest="action", required=True)
    backup.add_parser("create")
    backup.add_parser("list")
    restore = backup.add_parser("restore")
    restore.add_argument("file")
    restore.add_argument("--confirm", action="store_true")

    settings = sub.add_parser("settings", help="configurações").add_subparsers(dest="action", required=True)
    settings.add_parser("list")
    setter = settings.add_parser("set")
    setter.add_argument("key")
    setter.add_argument("value", help="valor em JSON (ex.: '\"light\"' ou 10)")
    return parser


def _run(core: NexusCore, args: argparse.Namespace) -> int:
    cmd, action = args.command, getattr(args, "action", None)
    if cmd == "init":
        core.bootstrap_admin(args.admin)
        print(f"Administrador '{args.admin}' criado. Pasta de dados: {core.paths.home}")
    elif cmd == "status":
        _print(core.status())
    elif cmd == "technician":
        if action == "add":
            core.add_technician(args.name, args.role)
            print(f"Técnico '{args.name}' adicionado como {args.role}.")
        else:
            _print(core.technicians.list())
    elif cmd == "devices":
        if action == "scan":
            report = core.devices.scan()
            _print({"found": report.found, "errors": report.errors})
        elif action == "list":
            _print(core.devices.list())
        else:
            print(f"Dispositivo {core.devices.add_manual(args.kind, vendor=args.vendor, model=args.model, serial=args.serial, label=args.label)} registrado.")
    elif cmd == "modules":
        if action == "list":
            _print(core.modules.status())
        elif action == "verify":
            report = core.modules.verify(args.id)
            _print({"ok": report.ok, "problems": report.problems})
            return 0 if report.ok else 2
        elif action == "register":
            core.modules.register(args.id, confirmed=args.confirm)
            print(f"Módulo {args.id} registrado (desativado). Use 'modules enable'.")
        elif action == "enable":
            core.modules.enable(args.id)
            print(f"Módulo {args.id} ativado.")
        elif action == "disable":
            core.modules.disable(args.id)
            print(f"Módulo {args.id} desativado.")
        elif action == "seal":
            files = seal_manifest(Path(args.directory))
            print(f"Manifesto selado com {len(files)} arquivo(s).")
    elif cmd == "audit":
        if action == "list":
            _print(core.audit.recent(args.limit))
        else:
            result = core.audit.verify()
            _print({"ok": result.ok, "records": result.records, "first_bad_id": result.first_bad_id})
            return 0 if result.ok else 2
    elif cmd == "backup":
        if action == "create":
            print(core.backups.create())
        elif action == "list":
            _print([p.name for p in core.backups.list()])
        else:
            safety_copy = core.backups.restore(Path(args.file), confirmed=args.confirm)
            print(f"Restaurado. Estado anterior preservado em: {safety_copy}")
    elif cmd == "settings":
        if action == "list":
            _print(core.settings.all())
        else:
            core.set_setting(args.key, json.loads(args.value))
            print(f"{args.key} atualizado.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with NexusCore(home=args.home, actor=args.actor) as core:
            return _run(core, args)
    except NexusError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Valor JSON inválido: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
