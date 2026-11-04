using System.Text.Json;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public sealed partial class SettingsViewModel : PageViewModel
{
    private readonly IThemeService _theme;
    private readonly IRuntimeInfo _runtime;
    private string _loadedTheme = "dark";
    private int _loadedKeep = 10;
    private string _loadedLogLevel = "INFO";

    public SettingsViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs, IThemeService theme,
        IRuntimeInfo runtime)
        : base(api, session, dialogs)
    {
        _theme = theme;
        _runtime = runtime;
    }

    public override string Title => "Configurações";

    public IReadOnlyList<Option> ThemeOptions { get; } = new List<Option> { new("dark", "Escuro"), new("light", "Claro") };

    public IReadOnlyList<Option> LogLevelOptions { get; } = new List<Option>
    {
        new("DEBUG", "Depuração"), new("INFO", "Informações"), new("WARNING", "Avisos"), new("ERROR", "Somente erros"),
    };

    public bool CanWrite => Session.Can("settings.write");

    [ObservableProperty] private string _selectedTheme = "dark";
    [ObservableProperty] private string _backupKeepText = "10";
    [ObservableProperty] private string _selectedLogLevel = "INFO";
    [ObservableProperty] private string _modeText = "—";
    [ObservableProperty] private string _publishersText = "—";
    [ObservableProperty] private string _coreText = "—";
    [ObservableProperty] private string? _message;
    [ObservableProperty] private string _pythonText = "—";
    [ObservableProperty] private string _appText = "—";
    [ObservableProperty] private string _dataText = "—";
    [ObservableProperty] private string _backupsPathText = "—";
    [ObservableProperty] private string _logsPathText = "—";

    protected override async Task LoadCoreAsync()
    {
        var settings = await Api.GetSettingsAsync();
        var hello = await Api.HelloAsync();

        _loadedTheme = Read(settings, "ui.theme", "dark");
        _loadedKeep = settings.TryGetValue("backup.keep", out var keep) && keep.ValueKind == JsonValueKind.Number
            ? keep.GetInt32()
            : 10;
        _loadedLogLevel = Read(settings, "log.level", "INFO");

        SelectedTheme = _loadedTheme;
        BackupKeepText = _loadedKeep.ToString();
        SelectedLogLevel = _loadedLogLevel;
        ModeText = Read(settings, "mode", "local") == "local" ? "Local (offline)" : "Online";
        PublishersText = settings.TryGetValue("modules.trusted_publishers", out var publishers)
            && publishers.ValueKind == JsonValueKind.Array
            ? string.Join(", ", publishers.EnumerateArray().Select(p => p.GetString() ?? ""))
            : "—";
        CoreText = $"Núcleo {hello.CoreVersion} · protocolo {hello.Protocol} · banco v{hello.SchemaVersion}";
        AppText = $"Interface {_runtime.AppVersion}";
        PythonText = $"Python {_runtime.PythonVersion} — {_runtime.PythonPath}";
        var paths = await Api.GetSystemPathsAsync();
        DataText = paths.Home;
        BackupsPathText = paths.Backups;
        LogsPathText = paths.Logs;
    }

    [RelayCommand]
    private Task SaveAsync() => RunAsync(async () =>
    {
        if (!int.TryParse(BackupKeepText.Trim(), out var keep) || keep < 1 || keep > 200)
        {
            ErrorMessage = "Quantidade de backups deve ser um número entre 1 e 200.";
            return;
        }

        var changed = 0;
        if (SelectedTheme != _loadedTheme)
        {
            await Api.SetSettingAsync("ui.theme", SelectedTheme);
            _theme.Apply(SelectedTheme);
            changed++;
        }
        if (keep != _loadedKeep)
        {
            await Api.SetSettingAsync("backup.keep", keep);
            changed++;
        }
        if (SelectedLogLevel != _loadedLogLevel)
        {
            await Api.SetSettingAsync("log.level", SelectedLogLevel);
            changed++;
        }
        Message = changed == 0
            ? "Nenhuma alteração."
            : $"{changed} configuração(ões) salva(s). O nível de log vale a partir da próxima execução.";
        await LoadCoreAsync();
    });

    [RelayCommand]
    private async Task ChoosePythonAsync()
    {
        var result = await _runtime.ChoosePythonAsync();
        if (result is not null) Message = result;
    }

    private static string Read(Dictionary<string, JsonElement> settings, string key, string fallback)
        => settings.TryGetValue(key, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? fallback
            : fallback;
}
