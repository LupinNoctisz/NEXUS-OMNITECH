"""Exceções do núcleo. Todas herdam de NexusError."""


class NexusError(Exception):
    """Erro base da plataforma."""


class ValidationError(NexusError):
    """Dado de entrada inválido."""


class PermissionDenied(NexusError):
    """O técnico atual não possui a permissão necessária."""


class ConfirmationRequired(NexusError):
    """Operação sensível exige confirmação/autorização explícita."""


class IntegrityError(NexusError):
    """Falha de verificação de integridade (módulo, log, arquivo)."""


class ModuleError(NexusError):
    """Erro de gerenciamento ou carregamento de módulo."""


class BackupError(NexusError):
    """Falha ao criar ou restaurar um backup."""
