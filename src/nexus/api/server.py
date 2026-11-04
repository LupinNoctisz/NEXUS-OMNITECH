"""Servidor JSON-RPC 2.0, uma mensagem JSON por linha, sobre stdin/stdout.

Sem porta de rede: o único cliente possível é o processo que iniciou este (a interface WPF).
Somente a saída padrão carrega o protocolo; qualquer ``print`` acidental é desviado para stderr.
Lotes (arrays) não são suportados. Chamadas sem ``id`` (notificações) são executadas sem resposta.
"""

from __future__ import annotations

import json
import sys
from typing import Any, BinaryIO

from ..core import (AuthenticationError, BackupError, ConfirmationRequired, IntegrityError, ModuleError,
                    NexusCore, NexusError, PermissionDenied, ValidationError)
from ..core.permissions import ANONYMOUS
from . import protocol as proto
from .methods import Method, build_registry

_ERROR_MAP: list[tuple[type[Exception], int]] = [
    (PermissionDenied, proto.PERMISSION_DENIED),
    (AuthenticationError, proto.NOT_AUTHENTICATED),
    (ConfirmationRequired, proto.CONFIRMATION_REQUIRED),
    (IntegrityError, proto.INTEGRITY_ERROR),
    (ModuleError, proto.MODULE_ERROR),
    (BackupError, proto.BACKUP_ERROR),
    (ValidationError, proto.VALIDATION_ERROR),
    (NexusError, proto.NEXUS_ERROR),
]


class RpcServer:
    def __init__(self, core: NexusCore, max_line: int = proto.MAX_LINE_BYTES):
        self.core = core
        self.max_line = max_line
        self.stopped = False
        self.methods: dict[str, Method] = build_registry(self._stop)

    def _stop(self) -> None:
        self.stopped = True

    # -- uma mensagem ------------------------------------------------------------------
    def handle(self, raw: bytes) -> bytes | None:
        try:
            request = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self._error(None, proto.PARSE_ERROR, "JSON inválido.", "ParseError")
        if not isinstance(request, dict):
            return self._error(None, proto.INVALID_REQUEST, "A requisição deve ser um objeto JSON.", "InvalidRequest")

        has_id = "id" in request
        request_id = request.get("id")
        if has_id and (isinstance(request_id, bool) or not (request_id is None or isinstance(request_id, (str, int)))):
            return self._error(None, proto.INVALID_REQUEST, "'id' deve ser texto, número ou nulo.", "InvalidRequest")
        method_name = request.get("method")
        if request.get("jsonrpc") != "2.0" or not isinstance(method_name, str):
            return self._error(request_id, proto.INVALID_REQUEST, "Requisição JSON-RPC 2.0 inválida.", "InvalidRequest")
        params = request.get("params", {})
        params = {} if params is None else params
        if not isinstance(params, dict):
            return self._error(request_id, proto.INVALID_PARAMS, "'params' deve ser um objeto.", "InvalidParams")

        try:
            result = self._dispatch(method_name, params)
        except proto.RpcError as exc:
            return self._error(request_id, exc.code, exc.message, exc.error_type) if has_id else None
        except NexusError as exc:
            code = next(code for kind, code in _ERROR_MAP if isinstance(exc, kind))
            return self._error(request_id, code, str(exc), type(exc).__name__) if has_id else None
        except Exception:  # defeito inesperado: detalhes só no log, nunca na resposta
            self.core.log.exception("erro interno no RPC", extra={"rpc_method": method_name})
            return self._error(request_id, proto.INTERNAL_ERROR, "Erro interno. Consulte o log do NEXUS.", "InternalError") if has_id else None
        return proto.encode({"jsonrpc": "2.0", "id": request_id, "result": result}) if has_id else None

    def _dispatch(self, name: str, params: dict[str, Any]) -> Any:
        method = self.methods.get(name)
        if method is None:
            raise proto.RpcError(proto.METHOD_NOT_FOUND, f"Método desconhecido: {name}", "MethodNotFound")
        if method.requires_login and self.core.actor == ANONYMOUS:
            raise proto.RpcError(proto.NOT_AUTHENTICATED, "Autenticação necessária.", "AuthenticationError")
        clean = proto.validate_params(name, params, method.params)
        self.core.log.debug("rpc", extra={"rpc_method": name})  # parâmetros nunca vão para o log
        return method.handler(self.core, clean)

    @staticmethod
    def _error(request_id: Any, code: int, message: str, error_type: str | None) -> bytes:
        error: dict[str, Any] = {"code": code, "message": message}
        if error_type:
            error["data"] = {"type": error_type}
        return proto.encode({"jsonrpc": "2.0", "id": request_id, "error": error})

    # -- laço principal ----------------------------------------------------------------------
    def serve(self, stdin: BinaryIO, stdout: BinaryIO) -> None:
        while not self.stopped:
            line = stdin.readline(self.max_line + 1)
            if not line:
                break  # EOF: a interface encerrou
            if len(line) > self.max_line and not line.endswith(b"\n"):
                while True:  # descarta o restante da linha gigante
                    chunk = stdin.readline(65536)
                    if not chunk or chunk.endswith(b"\n"):
                        break
                stdout.write(self._error(None, proto.INVALID_REQUEST, "Mensagem grande demais.", "InvalidRequest"))
                stdout.flush()
                continue
            line = line.strip()
            if not line:
                continue
            response = self.handle(line)
            if response is not None:
                stdout.write(response)
                stdout.flush()


def run_stdio(core: NexusCore) -> int:
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    sys.stdout = sys.stderr  # protege o canal do protocolo contra prints acidentais
    try:
        RpcServer(core).serve(stdin, stdout)
    finally:
        sys.stdout = sys.__stdout__
    return 0
