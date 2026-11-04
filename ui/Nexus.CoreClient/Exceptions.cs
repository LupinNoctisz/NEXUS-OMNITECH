namespace Nexus.CoreClient;

/// <summary>Códigos de erro do protocolo (ver docs/PROTOCOL.md).</summary>
public static class RpcCodes
{
    public const int PermissionDenied = -32001;
    public const int NotAuthenticated = -32002;
    public const int ConfirmationRequired = -32003;
    public const int IntegrityError = -32004;
    public const int ModuleError = -32005;
    public const int BackupError = -32006;
    public const int ValidationError = -32007;
}

public abstract class CoreException : Exception
{
    protected CoreException(string message, Exception? inner = null) : base(message, inner) { }
}

/// <summary>O núcleo respondeu com um erro (permissão, validação, integridade...).</summary>
public sealed class RpcException : CoreException
{
    public int Code { get; }
    public string ErrorType { get; }

    public RpcException(int code, string errorType, string message) : base(message)
    {
        Code = code;
        ErrorType = errorType;
    }
}

/// <summary>O núcleo não iniciou, encerrou ou não respondeu a tempo.</summary>
public sealed class CoreUnavailableException : CoreException
{
    public CoreUnavailableException(string message, Exception? inner = null) : base(message, inner) { }
}

/// <summary>Nenhum Python compatível foi encontrado (ou o escolhido pelo usuário não serve).</summary>
public sealed class PythonNotFoundException : CoreException
{
    public IReadOnlyList<string> Rejected { get; }

    /// <summary>true quando o problema é um caminho escolhido de propósito (variável/configuração): não há "plano B" automático.</summary>
    public bool ExplicitChoice { get; }

    public PythonNotFoundException(string message, IReadOnlyList<string> rejected, bool explicitChoice) : base(message)
    {
        Rejected = rejected;
        ExplicitChoice = explicitChoice;
    }
}
