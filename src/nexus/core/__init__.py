"""NEXUS CORE - núcleo da plataforma."""

from .app import NexusCore
from .errors import (
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
    "ConfirmationRequired",
    "IntegrityError",
    "ModuleError",
    "BackupError",
    "ValidationError",
]
