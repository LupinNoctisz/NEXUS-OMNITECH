using System.Text.Json;
using System.Text.Json.Serialization;

namespace Nexus.CoreClient;

/// <summary>
/// Preferências que a interface precisa ANTES de o núcleo existir (caminho do Python, tema inicial, janela).
/// Preferências de negócio (tema por técnico, backups mantidos...) continuam no núcleo.
/// </summary>
public sealed record UiSettings
{
    [JsonPropertyName("python_path")] public string? PythonPath { get; init; }
    [JsonPropertyName("theme")] public string? Theme { get; init; }
    [JsonPropertyName("window_width")] public double? WindowWidth { get; init; }
    [JsonPropertyName("window_height")] public double? WindowHeight { get; init; }
    [JsonPropertyName("window_maximized")] public bool WindowMaximized { get; init; }
}

public sealed class UiSettingsStore
{
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = true };
    private readonly string _file;

    /// <summary>Padrão: %APPDATA%\NexusOmnitech\ui-settings.json (configuração do usuário, roaming).</summary>
    public UiSettingsStore(string? directory = null)
    {
        directory ??= Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "NexusOmnitech");
        _file = Path.Combine(directory, "ui-settings.json");
    }

    public string FilePath => _file;

    /// <summary>Arquivo ausente, corrompido ou com valores absurdos → padrões seguros (nunca impede o app de abrir).</summary>
    public UiSettings Load()
    {
        try
        {
            if (!File.Exists(_file)) return new UiSettings();
            var loaded = JsonSerializer.Deserialize<UiSettings>(File.ReadAllText(_file), Options);
            return loaded is null ? new UiSettings() : Sanitize(loaded);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
        {
            return new UiSettings();
        }
    }

    /// <summary>Gravação atômica (arquivo temporário + troca). Falhas de disco não derrubam o app: devolve false.</summary>
    public bool Save(UiSettings settings)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_file)!);
            var temp = _file + ".tmp";
            File.WriteAllText(temp, JsonSerializer.Serialize(Sanitize(settings), Options));
            File.Move(temp, _file, overwrite: true);
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    public UiSettings Update(Func<UiSettings, UiSettings> change)
    {
        var next = change(Load());
        Save(next);
        return next;
    }

    private static UiSettings Sanitize(UiSettings value) => value with
    {
        PythonPath = string.IsNullOrWhiteSpace(value.PythonPath) ? null : value.PythonPath.Trim(),
        Theme = value.Theme is "dark" or "light" ? value.Theme : null,
        WindowWidth = value.WindowWidth is >= 600 and <= 10000 ? value.WindowWidth : null,
        WindowHeight = value.WindowHeight is >= 400 and <= 10000 ? value.WindowHeight : null,
    };
}

/// <summary>Registro simples da interface (ui.log, ao lado dos logs do núcleo). Nunca deve receber senhas.</summary>
public static class UiLog
{
    private static readonly object Gate = new();

    public static string? Directory { get; set; }

    public static string FilePath()
    {
        var home = Environment.GetEnvironmentVariable("NEXUS_HOME");
        var root = !string.IsNullOrWhiteSpace(home)
            ? home
            : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "NexusOmnitech");
        return Path.Combine(Directory ?? Path.Combine(root, "logs"), "ui.log");
    }

    public static void Write(string level, string message)
    {
        try
        {
            lock (Gate)
            {
                var file = FilePath();
                System.IO.Directory.CreateDirectory(Path.GetDirectoryName(file)!);
                if (File.Exists(file) && new FileInfo(file).Length > 1_000_000)
                {
                    File.Move(file, file + ".1", overwrite: true);
                }
                File.AppendAllText(file, $"{DateTimeOffset.UtcNow:O} [{level}] {message}{Environment.NewLine}");
            }
        }
        catch (Exception)
        {
            // registrar é "o melhor possível": nunca pode causar falha no aplicativo (caminho inválido, disco cheio...)
        }
    }

    public static void Info(string message) => Write("INFO", message);
    public static void Error(string message) => Write("ERROR", message);
}
