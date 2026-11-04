using System.Globalization;
using System.Text.Json;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public interface IDialogService
{
    /// <summary>Pede confirmação. Com <paramref name="requiredText"/>, o usuário precisa digitá-lo para confirmar.</summary>
    Task<bool> ConfirmAsync(string title, string message, string confirmText, string? requiredText = null);

    void ShowInfo(string title, string message);
}

/// <summary>Informações do ambiente de execução da interface (quem inicia o núcleo) e a escolha manual do Python.</summary>
public interface IRuntimeInfo
{
    string AppVersion { get; }
    string PythonPath { get; }
    string PythonVersion { get; }
    string CorePath { get; }

    /// <summary>Abre a escolha do python.exe, valida e grava. Devolve a mensagem para o usuário (null se cancelou).</summary>
    Task<string?> ChoosePythonAsync();
}

public interface IThemeService
{
    string Current { get; }
    void Apply(string theme);
}

/// <summary>Quem está logado e o que pode fazer (as permissões vêm do núcleo, nunca são inventadas aqui).</summary>
public interface ISessionContext
{
    string Actor { get; }
    string Role { get; }
    bool IsAuthenticated { get; }
    bool Can(string permission);
    void Set(WhoAmI who);
    void Clear();
}

public sealed class SessionContext : ISessionContext
{
    private HashSet<string> _permissions = new();

    public string Actor { get; private set; } = "anonymous";
    public string Role { get; private set; } = "viewer";
    public bool IsAuthenticated { get; private set; }

    public bool Can(string permission) => IsAuthenticated && _permissions.Contains(permission);

    public void Set(WhoAmI who)
    {
        Actor = who.Actor;
        Role = who.Role;
        IsAuthenticated = who.Authenticated;
        _permissions = new HashSet<string>(who.Permissions);
    }

    public void Clear()
    {
        Actor = "anonymous";
        Role = "viewer";
        IsAuthenticated = false;
        _permissions = new HashSet<string>();
    }
}

public sealed record Option(string Value, string Label);

public sealed record KeyValueRow(string Key, string Value);

public sealed record NavItem(string Key, string Title, string Glyph, Func<PageViewModel> Create);

/// <summary>Datas do núcleo vêm em UTC (ISO 8601); a interface mostra no horário local.</summary>
public static class TimeText
{
    private static readonly CultureInfo PtBr = CultureInfo.GetCultureInfo("pt-BR");

    public static string Local(string? utcIso)
    {
        if (string.IsNullOrWhiteSpace(utcIso)) return "—";
        return DateTimeOffset.TryParse(utcIso, CultureInfo.InvariantCulture, DateTimeStyles.None, out var value)
            ? value.ToLocalTime().ToString("dd/MM/yyyy HH:mm:ss", PtBr)
            : utcIso;
    }
}

/// <summary>Traduções de valores técnicos do núcleo para a interface (valores desconhecidos aparecem como vieram).</summary>
public static class Labels
{
    public static string Kind(string value) => value switch
    {
        "pc" => "Computador",
        "usb" => "USB",
        "mobile" => "Dispositivo móvel",
        "console" => "Console",
        "other" => "Outro",
        _ => value,
    };

    public static string Connection(string value) => value switch
    {
        "connected" => "Conectado",
        "disconnected" => "Desconectado",
        "unknown" => "Desconhecido",
        _ => value,
    };

    public static string SessionStatus(string value) => value switch
    {
        "open" => "Aberta",
        "completed" => "Concluída",
        "aborted" => "Abortada",
        _ => value,
    };

    public static string SessionKind(string value) => value switch
    {
        "pc_diagnostics" => "Diagnóstico de PC",
        "mobile" => "Mobile",
        "console" => "Console",
        "electronics" => "Eletrônica",
        "general" => "Geral",
        _ => value,
    };

    public static string Role(string value) => value switch
    {
        "viewer" => "Somente leitura",
        "technician" => "Técnico",
        "admin" => "Administrador",
        _ => value,
    };

    public static string ModuleStatus(string value) => value switch
    {
        "planned" => "Planejado (não implementado)",
        "available" => "Disponível",
        _ => value,
    };

    public static string Describe(JsonElement element) => element.ValueKind switch
    {
        JsonValueKind.String => element.GetString() ?? "",
        JsonValueKind.Null => "—",
        _ => element.ToString(),
    };
}
