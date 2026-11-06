using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public sealed partial class ShellViewModel : ObservableObject
{
    private readonly ICoreApi _api;
    private readonly ISessionContext _session;
    private readonly IThemeService _theme;
    private readonly Dictionary<string, PageViewModel> _pages = new();

    public ShellViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs, IThemeService theme,
        IRuntimeInfo runtime)
    {
        _api = api;
        _session = session;
        _theme = theme;
        var all = new List<NavItem>
        {
            new("home", "Início", "", () => new HomeViewModel(api, session, dialogs)),
            new("devices", "Dispositivos", "", () => new DevicesViewModel(api, session, dialogs)),
            new("diagnostics", "Diagnósticos", "", () => new DiagnosticsViewModel(api, session, dialogs)),
            new("history", "Histórico", "", () => new HistoryViewModel(api, session, dialogs)),
            new("modules", "Módulos", "", () => new ModulesViewModel(api, session, dialogs)),
            new("backups", "Backups", "", () => new BackupsViewModel(api, session, dialogs)),
            new("security", "Segurança", "", () => new SecurityViewModel(api, session, dialogs), "security.read"),
            new("settings", "Configurações", "", () => new SettingsViewModel(api, session, dialogs, theme, runtime), "settings.read"),
            new("account", "Minha conta", "", () => new AccountViewModel(api, session, dialogs)),
        };
        // seções administrativas ficam escondidas de quem não tem a permissão (o núcleo também recusa a chamada)
        Items = all.Where(item => item.Requires is null || session.Can(item.Requires)).ToList();
    }

    public IReadOnlyList<NavItem> Items { get; }

    public string Actor => _session.Actor;
    public string RoleText => Labels.Role(_session.Role);

    [ObservableProperty]
    private NavItem? _selectedItem;

    [ObservableProperty]
    private PageViewModel? _currentPage;

    /// <summary>Pedido para voltar à tela de login (logout ou sessão perdida).</summary>
    public event EventHandler? LogoutRequested;

    partial void OnSelectedItemChanged(NavItem? value)
    {
        if (value is null) return;
        if (!_pages.TryGetValue(value.Key, out var page))
        {
            page = value.Create();
            page.SessionLost += (_, _) => LogoutRequested?.Invoke(this, EventArgs.Empty);
            _pages[value.Key] = page;
        }
        CurrentPage = page;
        _ = page.LoadAsync(); // erros são tratados dentro de LoadAsync (RunAsync)
    }

    /// <summary>Aplica o tema salvo no núcleo e abre a primeira página.</summary>
    public async Task InitializeAsync()
    {
        try
        {
            // sem 'settings.read' o núcleo recusaria (e auditaria) a chamada: o tema padrão vale até o usuário alternar
            var settings = _session.Can("settings.read")
                ? await _api.GetSettingsAsync()
                : new Dictionary<string, System.Text.Json.JsonElement>();
            if (settings.TryGetValue("ui.theme", out var theme) && theme.ValueKind == System.Text.Json.JsonValueKind.String)
            {
                _theme.Apply(theme.GetString() ?? "dark");
            }
        }
        catch (CoreException)
        {
            // o tema padrão continua; a página inicial mostrará o erro real, se houver
        }
        SelectedItem = Items[0];
    }

    [RelayCommand]
    private async Task LogoutAsync()
    {
        try
        {
            await _api.LogoutAsync();
        }
        catch (CoreException)
        {
            // mesmo com falha, a interface volta ao login
        }
        _session.Clear();
        LogoutRequested?.Invoke(this, EventArgs.Empty);
    }

    [RelayCommand]
    private async Task ToggleThemeAsync()
    {
        var next = _theme.Current == "dark" ? "light" : "dark";
        _theme.Apply(next);
        if (!_session.Can("settings.write")) return; // sem permissão: vale só nesta execução
        try
        {
            await _api.SetSettingAsync("ui.theme", next);
        }
        catch (CoreException)
        {
        }
    }
}
