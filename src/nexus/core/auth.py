"""Autenticação local por senha individual (scrypt, biblioteca padrão).

* Senhas nunca são gravadas nem registradas: só o hash ``scrypt$N$r$p$salt$hash`` (parâmetros
  guardados junto, o que permite aumentar o custo no futuro sem invalidar senhas antigas).
* Bloqueio temporário após falhas consecutivas; mensagem de erro única (não revela se o usuário existe).
* A identidade do núcleo só muda por ``NexusCore.login()``; não existe mais ator por variável de
  ambiente nem por parâmetro do construtor.

Limite conhecido: código Python rodando DENTRO do mesmo processo é confiável (pode alterar o estado
interno). O que isto protege é a fronteira do processo: quem conversa com o núcleo (CLI, RPC) precisa
provar quem é.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from .errors import AuthenticationError, PermissionDenied, ValidationError
from .permissions import ANONYMOUS, Permission

if TYPE_CHECKING:
    from .app import NexusCore

SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
KEY_LENGTH = 32
MIN_LENGTH = 10
MAX_LENGTH = 256
MAX_FAILED_ATTEMPTS = 5
LOCK_MINUTES = 5
GENERIC_FAILURE = "Credenciais inválidas ou conta temporariamente bloqueada."


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_LENGTH, maxmem=256 * n * r * p)


def validate_password(password: str) -> None:
    if not isinstance(password, str):
        raise ValidationError("Senha inválida.")
    if len(password) < MIN_LENGTH:
        raise ValidationError(f"A senha deve ter pelo menos {MIN_LENGTH} caracteres.")
    if len(password) > MAX_LENGTH:
        raise ValidationError(f"A senha deve ter no máximo {MAX_LENGTH} caracteres.")
    if password.isdigit() or len(set(password)) < 4:
        raise ValidationError("Senha fraca demais: use caracteres variados (não apenas números ou repetições).")


def hash_password(password: str) -> str:
    validate_password(password)
    salt = os.urandom(16)
    digest = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        actual = _derive(password, base64.b64decode(salt_b64), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


_dummy_hash: str | None = None


def _burn_time(password: str) -> None:
    """Gasta o mesmo tempo de uma verificação real (evita distinguir usuário inexistente por tempo)."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("nexus-valor-descartavel-0")
    verify_password(password, _dummy_hash)


class AuthService:
    def __init__(self, core: "NexusCore"):
        self._core = core

    def authenticate(self, name: str, password: str) -> None:
        """Valida credenciais. Levanta AuthenticationError (mensagem única) em qualquer falha."""
        core = self._core
        name = (name or "")[:64]
        password = password if isinstance(password, str) else ""
        row = core.technicians.credentials(name)
        now = datetime.now(timezone.utc)
        usable = bool(row and row["active"] and row["password_hash"])
        locked = bool(row and row["locked_until"] and datetime.fromisoformat(row["locked_until"]) > now)

        if usable and not locked and verify_password(password, row["password_hash"]):
            core.technicians.clear_failures(name)
            core.audit.record("auth.login", technician=name, outcome="ok")
            return

        _burn_time(password)
        if row and not locked:
            lock_until = (now + timedelta(minutes=LOCK_MINUTES)).isoformat(timespec="seconds")
            locked_now = core.technicians.register_failure(name, MAX_FAILED_ATTEMPTS, lock_until)
        else:
            locked_now = False
        core.audit.record("auth.login", technician=ANONYMOUS, target=name, outcome="failed",
                          details={"locked": locked or locked_now})
        core.log.warning("login recusado", extra={"technician": name, "locked": locked or locked_now})
        raise AuthenticationError(GENERIC_FAILURE)

    def set_password(self, name: str, new_password: str, old_password: str | None = None) -> str:
        """Define/altera a senha. Devolve o motivo ('self', 'reset' ou 'claim') para registro.

        * o próprio técnico: informa a senha atual;
        * administrador: redefine a senha de outro técnico;
        * sem login: apenas para contas LEGADAS ainda sem senha ('claim', ver docs/SECURITY.md).
        """
        core = self._core
        validate_password(new_password)
        record = core.technicians.credentials(name)
        if record is None or not record["active"]:
            raise ValidationError("Técnico não encontrado ou inativo.")

        if core.actor == name and core.actor != ANONYMOUS:
            if not record["password_hash"] or not old_password or not verify_password(old_password, record["password_hash"]):
                raise AuthenticationError("Senha atual incorreta.")
            reason = "self"
        elif core.actor != ANONYMOUS:
            core.require(Permission.TECHNICIANS_MANAGE)
            reason = "reset"
        elif record["password_hash"] is None:
            reason = "claim"
        else:
            raise PermissionDenied("Faça login para alterar a senha.")

        core.technicians.set_password_hash(name, hash_password(new_password))
        core.technicians.clear_failures(name)
        core.audit.record(f"auth.password_{reason}", technician=core.actor, target=name)
        return reason
