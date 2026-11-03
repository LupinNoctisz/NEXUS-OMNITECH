"""Interface de linha de comando do NEXUS CORE.

Autenticação: ``--as NOME`` pede a senha do técnico (prompt oculto) ou lê a primeira linha da entrada
padrão com ``--password-stdin``. Sem ``--as`` o acesso é anônimo (somente leitura).
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from . import PRODUCT_NAME, TAGLINE, VENDOR, __version__
from .core import NexusCore, NexusError
from .core.modules import seal_manifest
from .core.permissions import ANONYMOUS


def _print(data) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _read_secret(prompt: str, from_stdin: bool, confirm: bool = False) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass(prompt)
    if confirm and getpass.getpass("Repita a senha: ") != first:
        raise NexusError("As senhas não conferem.")
    return first


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus", description=f"{PRODUCT_NAME} by {VENDOR} - {TAGLINE}")
    parser.add_argument("--version", action="version", version=f"{PRODUCT_NAME} {__version__}")
    parser.add_argument("--home", help="pasta de dados (padrão: NEXUS_HOME ou diretório do usuário)")
    parser.add_argument("--as", dest="actor", help="entrar como este técnico (pede a senha)")
    parser.add_argument("--password-stdin", action="store_true",
                        help="lê senhas da entrada padrão (uma por linha) em vez de pedir no terminal")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="cria o primeiro administrador (pede a senha)")
    init.add_argument("--admin", required=True)

    sub.add_parser("status", help="painel inicial (dispositivos, sessões, alertas, módulos)")
    sub.add_parser("security", help="visão geral de segurança (permissões, integridade, técnicos)")

    serve = sub.add_parser("serve", help="servidor JSON-RPC para a interface gráfica")
    serve.add_argument("--stdio", action="store_true", required=True, help="único modo suportado: entrada/saída padrão")

    tech = sub.add_parser("technician", help="gerencia técnicos").add_subparsers(dest="action", required=True)
    add = tech.add_parser("add")
    add.add_argument("name")
    add.add_argument("--role", choices=["viewer", "technician", "admin"], default="technician")
    tech.add_parser("list")
    tech.add_parser("set-password").add_argument("name")
    active = tech.add_parser("set-active")
    active.add_argument("name")
    active.add_argument("--inactive", action="store_true")

    dev = sub.add_parser("devices", help="dispositivos").add_subparsers(dest="action", required=True)
    dev.add_parser("scan")
    dev.add_parser("list")
    manual = dev.add_parser("add")
    manual.add_argument("--kind", required=True)
    manual.add_argument("--vendor")
    manual.add_argument("--model")
    manual.add_argument("--serial")
    manual.add_argument("--label")

    ses = sub.add_parser("sessions", help="sessões de diagnóstico").add_subparsers(dest="action", required=True)
    sl = ses.add_parser("list")
    sl.add_argument("--limit", type=int, default=10)
    ses.add_parser("open")
    ss = ses.add_parser("start")
    ss.add_argument("--device", type=int, required=True)
    ss.add_argument("--kind", default="general")
    sf = ses.add_parser("finish")
    sf.add_argument("id", type=int)
    sf.add_argument("--status", choices=["completed", "aborted"], default="completed")
    sf.add_argument("--summary")

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
    restore.add_argument("file", help="nome do backup (como em 'backup list') ou caminho")
    restore.add_argument("--confirm", action="store_true")

    settings = sub.add_parser("settings", help="configurações").add_subparsers(dest="action", required=True)
    settings.add_parser("list")
    setter = settings.add_parser("set")
    setter.add_argument("key")
    setter.add_argument("value", help="valor em JSON (ex.: '\"light\"' ou 10)")
    return parser


def _run(core: NexusCore, args: argparse.Namespace, login_password: str | None) -> int:
    cmd, action = args.command, getattr(args, "action", None)
    stdin = args.password_stdin
    if cmd == "status":
        _print(core.status())
    elif cmd == "security":
        _print(core.security_overview())
    elif cmd == "technician":
        if action == "add":
            password = _read_secret(f"Senha inicial de {args.name}: ", stdin, confirm=True)
            core.add_technician(args.name, args.role, password)
            print(f"Técnico '{args.name}' adicionado como {args.role}.")
        elif action == "list":
            _print(core.technicians.list())
        elif action == "set-password":
            new = _read_secret(f"Nova senha de {args.name}: ", stdin, confirm=True)
            reason = core.set_password(args.name, new, old_password=login_password if args.actor == args.name else None)
            print({"self": "Senha alterada.", "reset": "Senha redefinida.",
                   "claim": "Senha definida para a conta (que não tinha senha)."}[reason])
        else:
            core.set_technician_active(args.name, not args.inactive)
            print(f"Técnico '{args.name}' {'desativado' if args.inactive else 'ativado'}.")
    elif cmd == "devices":
        if action == "scan":
            report = core.devices.scan()
            _print({"found": report.found, "errors": report.errors})
        elif action == "list":
            _print(core.devices.list())
        else:
            print(f"Dispositivo {core.devices.add_manual(args.kind, vendor=args.vendor, model=args.model, serial=args.serial, label=args.label)} registrado.")
    elif cmd == "sessions":
        if action == "list":
            _print(core.sessions.recent(args.limit))
        elif action == "open":
            _print(core.sessions.open_sessions())
        elif action == "start":
            print(f"Sessão {core.sessions.start(args.device, args.kind)} iniciada.")
        else:
            core.sessions.finish(args.id, status=args.status, summary=args.summary)
            print(f"Sessão {args.id} encerrada ({args.status}).")
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
            _print(core.backups.describe())
        else:
            target = Path(args.file)
            if target.name == args.file:  # apenas um nome: resolve na pasta de backups
                target = core.backups.path_for(args.file)
            safety_copy = core.backups.restore(target, confirmed=args.confirm)
            print(f"Restaurado. Estado anterior preservado em: {safety_copy}")
            if core.actor == ANONYMOUS:
                print("Aviso: o técnico atual não existe/está inativo no backup restaurado; a sessão foi encerrada.")
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
        with NexusCore(home=args.home) as core:
            if args.command == "init":
                password = _read_secret("Senha do administrador: ", args.password_stdin, confirm=True)
                core.bootstrap_admin(args.admin, password)
                print(f"Administrador '{args.admin.strip()}' criado. Pasta de dados: {core.paths.home}")
                return 0
            if args.command == "serve":
                from .api.server import run_stdio
                return run_stdio(core)
            login_password = None
            if args.actor:
                login_password = _read_secret(f"Senha de {args.actor}: ", args.password_stdin)
                core.login(args.actor, login_password)
            return _run(core, args, login_password)
    except NexusError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Valor JSON inválido: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
