"""Exceções do núcleo. Todas herdam de NexusError."""


class NexusError(Exception):
    """Erro base da plataforma."""


class ValidationError(NexusError):
    """Dado de entrada inválido."""


class PermissionDenied(NexusError):
    """O técnico atual não possui a permissão necessária."""


class AuthenticationError(NexusError):
    """Credenciais inválidas, conta inativa/bloqueada ou sessão não autenticada."""


class ConfirmationRequired(NexusError):
    """Operação sensível exige confirmação/autorização explícita."""


class StorageError(NexusError):
    """O armazenamento local (banco ou pasta de dados) está ilegível, corrompido ou inacessível."""


class IntegrityError(NexusError):
    """Falha de verificação de integridade (módulo, log, arquivo)."""


class ModuleError(NexusError):
    """Erro de gerenciamento ou carregamento de módulo."""


class SchemaVersionError(NexusError):
    """O banco foi criado por uma versão mais nova do NEXUS (não há downgrade automático)."""


class BackupError(NexusError):
    """Falha ao criar ou restaurar um backup."""
