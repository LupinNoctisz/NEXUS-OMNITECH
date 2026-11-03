#!/usr/bin/env python3
"""Varredura de segredos e dados pessoais (somente biblioteca padrão).

Uso:
    python scripts/scan_secrets.py              # arquivos rastreados pelo Git
    python scripts/scan_secrets.py --staged     # apenas o que está no stage (hook pre-commit)
    python scripts/scan_secrets.py --history    # todo o histórico do Git (linhas adicionadas e nomes de arquivos)

Marque um falso positivo legítimo com ``nexus:allow-secret`` na mesma linha. Os valores encontrados
NUNCA são impressos por completo.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ALLOW_MARK = "nexus:allow-secret"
MAX_BYTES = 1_000_000

SECRET_PATTERNS: dict[str, str] = {
    "chave AWS": r"AKIA[0-9A-Z]{16}",
    "token GitHub": r"\bgh[pousr]_[A-Za-z0-9]{30,}",
    "token GitHub (fine-grained)": r"github_pat_[A-Za-z0-9_]{20,}",
    "chave estilo sk-": r"\bsk-[A-Za-z0-9_-]{20,}",
    "chave Supabase": r"\bsb_(secret|publishable)_[A-Za-z0-9_-]{10,}",
    "JWT": r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}",
    "chave privada": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "token Slack": r"xox[baprs]-[A-Za-z0-9-]{10,}",
    "credencial atribuída": (
        r"(?i)(pass(word|wd)?|senha|secret|segredo|token|api[_-]?key|credential|credencial)"
        r"[\w-]*[\"']?\s*[:=]\s*[\"'][^\"'\s]{6,}[\"']"
    ),
}
PII_PATTERNS: dict[str, str] = {
    "CPF": r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b",
    "CNPJ": r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b",
    "telefone BR": r"\(\d{2}\)\s?9?\d{4}-\d{4}",
    "e-mail": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
}
EMAIL_ALLOWED = re.compile(
    r"(@(example\.(com|org|net|invalid)|users\.noreply\.github\.com|noreply\.github\.com|anthropic\.com)$|^noreply@)", re.I
)
FORBIDDEN_NAMES = re.compile(
    r"(^|/)(\.env(\.(?!example$)[^/]*)?|id_rsa[^/]*|id_ed25519[^/]*|credentials[^/]*\.json|service-account[^/]*\.json"
    r"|secrets\.[^/]+|[^/]+\.(pem|key|pfx|p12|jks|keystore|db|db-wal|db-shm|sqlite3?))$",
    re.I,
)
SELF = Path(__file__).name


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    sample: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule} ({self.sample})"


def _mask(value: str) -> str:
    value = value.strip()
    return value[:4] + "***" if len(value) > 4 else "***"


def scan_text(text: str, path: str) -> list[Finding]:
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARK in line:
            continue
        for rule, pattern in SECRET_PATTERNS.items():
            match = re.search(pattern, line)
            if match:
                findings.append(Finding(path, number, rule, _mask(match.group(0))))
        for rule, pattern in PII_PATTERNS.items():
            for match in re.finditer(pattern, line):
                if rule == "e-mail" and EMAIL_ALLOWED.search(match.group(0)):
                    continue
                findings.append(Finding(path, number, f"possível dado pessoal: {rule}", _mask(match.group(0))))
    return findings


def check_name(path: str) -> list[Finding]:
    if FORBIDDEN_NAMES.search(path.replace("\\", "/")):
        return [Finding(path, 0, "arquivo que não deve ser versionado", "nome")]
    return []


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return result.stdout


def scan_files(paths: list[str], root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for rel in paths:
        if Path(rel).name == SELF:
            continue
        findings += check_name(rel)
        target = root / rel
        try:
            if not target.is_file() or target.stat().st_size > MAX_BYTES:
                continue
            text = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue  # binário ou ilegível
        findings += scan_text(text, rel)
    return findings


def scan_history() -> list[Finding]:
    findings: list[Finding] = []
    for name in sorted(set(_git("log", "--all", "--name-only", "--format=").splitlines())):
        if name:
            findings += check_name(name)
    current = "?"
    for raw in _git("log", "--all", "-p", "--format=", "--no-color").splitlines():
        if raw.startswith("+++ b/"):
            current = raw[6:]
        elif raw.startswith("+") and not raw.startswith("+++") and Path(current).name != SELF:
            findings += scan_text(raw[1:], f"{current} (histórico)")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--staged", action="store_true", help="somente arquivos no stage")
    mode.add_argument("--history", action="store_true", help="todo o histórico do Git")
    args = parser.parse_args(argv)

    root = Path(_git("rev-parse", "--show-toplevel").strip())
    if args.history:
        findings = scan_history()
    elif args.staged:
        names = _git("diff", "--cached", "--name-only", "--diff-filter=ACM").splitlines()
        findings = scan_files(names, root)
    else:
        findings = scan_files(_git("ls-files").splitlines(), root)

    if findings:
        print("POSSÍVEIS SEGREDOS / DADOS PESSOAIS ENCONTRADOS:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print("\nSe for um segredo real: NÃO faça commit, REVOGUE-O no serviço de origem e gere outro.\n"
              f"Se for um falso positivo legítimo, marque a linha com '{ALLOW_MARK}'.", file=sys.stderr)
        return 1
    print("Varredura concluída: nenhum segredo ou dado pessoal encontrado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
