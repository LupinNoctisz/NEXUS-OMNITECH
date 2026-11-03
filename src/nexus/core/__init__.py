"""NEXUS CORE - núcleo da plataforma."""

from .app import NexusCore
from .errors import (
    AuthenticationError,
    BackupError,
    ConfirmationRequired,
    IntegrityError,
    ModuleError,
    NexusError,
    PermissionDenied,
    ValidationError,
)

__all__ = [
    "NexusCore",
    "NexusError",
    "PermissionDenied",
    "AuthenticationError",
    "ConfirmationRequired",
    "IntegrityError",
    "ModuleError",
    "BackupError",
    "ValidationError",
]
