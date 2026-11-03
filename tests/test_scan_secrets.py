import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "scan_secrets.py"
spec = importlib.util.spec_from_file_location("scan_secrets", SCRIPT)
scan = importlib.util.module_from_spec(spec)
sys.modules["scan_secrets"] = scan
spec.loader.exec_module(scan)

# Os exemplos abaixo são montados em tempo de execução para que o próprio arquivo de teste
# não contenha literais que pareçam segredos ou dados pessoais.
FAKE_KEY = "abcdef" + "1234567890"
PRIVATE_HEADER = "-----BEGIN RSA " + "PRIVATE KEY-----"
FAKE_CPF = "123.456." + "789-09"
FAKE_CNPJ = "12.345.678" + "/0001-95"
FAKE_PHONE = "(92) 99123" + "-4567"
FAKE_EMAIL = "pessoa" + "@gmail.com"


def rules(text):
    return {f.rule for f in scan.scan_text(text, "x.py")}


def test_detects_assigned_credential_and_masks_value():
    findings = scan.scan_text("api_key = '" + FAKE_KEY + "'", "x.py")
    assert findings and FAKE_KEY not in str(findings[0])


@pytest.mark.parametrize("text,rule", [
    ("AKIA" + "A" * 16, "chave AWS"),
    ("ghp_" + "a" * 36, "token GitHub"),
    (PRIVATE_HEADER, "chave privada"),
    ("sb_secret_" + "a" * 20, "chave Supabase"),
    ("cliente " + FAKE_CPF, "possível dado pessoal: CPF"),
    ("cnpj " + FAKE_CNPJ, "possível dado pessoal: CNPJ"),
    ("fone " + FAKE_PHONE, "possível dado pessoal: telefone BR"),
    ("contato " + FAKE_EMAIL, "possível dado pessoal: e-mail"),
])
def test_detects(text, rule):
    assert rule in rules(text)


@pytest.mark.parametrize("text", [
    "contato exemplo@example.com",
    "Co-Authored-By: Claude <noreply@anthropic.com>",
    "NEXUS_SUPABASE_ANON_KEY=preencha-localmente",
    "senha = 'abc'",
    "PASSWORD = 'valor-de-teste-longo'  # nexus:allow-secret",
])
def test_ignores_safe_lines(text):
    assert rules(text) == set()


@pytest.mark.parametrize("name,flagged", [
    (".env", True), (".env.production", True), (".env.example", False),
    ("keys/id_rsa", True), ("credentials.json", True), ("nexus.db", True),
    ("src/nexus/core/app.py", False), ("docs/SECURITY.md", False),
])
def test_forbidden_names(name, flagged):
    assert bool(scan.check_name(name)) is flagged


def test_repository_is_clean():
    """A árvore versionada não pode conter segredos nem dados pessoais."""
    assert scan.main([]) == 0
