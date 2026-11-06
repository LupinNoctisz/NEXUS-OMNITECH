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
    SchemaVersionError,
    StorageError,
    ValidationError,
)

__all__ = [
    "NexusCore",
    "NexusError",
    "SchemaVersionError",
    "StorageError",
    "PermissionDenied",
    "AuthenticationError",
    "ConfirmationRequired",
    "IntegrityError",
    "ModuleError",
    "BackupError",
    "ValidationError",
]
