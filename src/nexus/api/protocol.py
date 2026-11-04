"""Protocolo: códigos de erro, validação de parâmetros e codificação das mensagens."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

PROTOCOL_VERSION = "1.0"
MAX_LINE_BYTES = 1_048_576  # 1 MiB por mensagem

# JSON-RPC 2.0
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
# aplicação NEXUS
NEXUS_ERROR = -32000
PERMISSION_DENIED = -32001
NOT_AUTHENTICATED = -32002
CONFIRMATION_REQUIRED = -32003
INTEGRITY_ERROR = -32004
MODULE_ERROR = -32005
BACKUP_ERROR = -32006
VALIDATION_ERROR = -32007


class RpcError(Exception):
    def __init__(self, code: int, message: str, error_type: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.error_type = error_type


@dataclass(frozen=True)
class Param:
    """Descreve um parâmetro aceito por um método. Parâmetros não declarados são rejeitados."""
    kind: str  # "str" | "int" | "bool" | "any"
    required: bool = True
    max_len: int = 256
    choices: tuple | None = None
    minimum: int | None = None
    maximum: int | None = None
    default: Any = None


def _check(method: str, name: str, value: Any, spec: Param) -> Any:
    def bad(reason: str) -> RpcError:
        return RpcError(INVALID_PARAMS, f"{method}: parâmetro '{name}' inválido ({reason}).", "InvalidParams")

    if spec.kind == "str":
        if not isinstance(value, str):
            raise bad("esperado texto")
        if len(value) > spec.max_len:
            raise bad(f"máximo de {spec.max_len} caracteres")
        if "\x00" in value:
            raise bad("caractere nulo")
    elif spec.kind == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise bad("esperado inteiro")
        if spec.minimum is not None and value < spec.minimum:
            raise bad(f"mínimo {spec.minimum}")
        if spec.maximum is not None and value > spec.maximum:
            raise bad(f"máximo {spec.maximum}")
    elif spec.kind == "bool":
        if not isinstance(value, bool):
            raise bad("esperado verdadeiro/falso")
    elif spec.kind != "any":
        raise AssertionError(f"tipo de parâmetro desconhecido: {spec.kind}")
    if spec.choices is not None and value not in spec.choices:
        raise bad("valor não permitido")
    return value


def validate_params(method: str, params: dict[str, Any], spec: dict[str, Param]) -> dict[str, Any]:
    unknown = set(params) - set(spec)
    if unknown:
        raise RpcError(INVALID_PARAMS, f"{method}: parâmetros desconhecidos: {', '.join(sorted(unknown))}.", "InvalidParams")
    clean: dict[str, Any] = {}
    for name, rule in spec.items():
        if name in params and params[name] is not None:
            clean[name] = _check(method, name, params[name], rule)
        elif rule.required:
            raise RpcError(INVALID_PARAMS, f"{method}: parâmetro obrigatório ausente: '{name}'.", "InvalidParams")
        else:
            clean[name] = rule.default
    return clean


def encode(message: dict[str, Any]) -> bytes:
    """Linha JSON em ASCII puro (sem problemas de codificação do console do Windows)."""
    return json.dumps(message, ensure_ascii=True, default=str, separators=(",", ":")).encode("ascii") + b"\n"
