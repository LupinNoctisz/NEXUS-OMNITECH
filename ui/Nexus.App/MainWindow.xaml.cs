using System.Windows;
using Nexus.App.Views;
using Nexus.CoreClient;
using Nexus.Presentation;

namespace Nexus.App;

public partial class MainWindow : Window
{
    private readonly ICoreApi _api;
    private readonly SessionContext _session;
    private readonly IDialogService _dialogs;
    private readonly IThemeService _theme;
    private readonly IRuntimeInfo _runtime;
    private readonly UiSettingsStore _store;

    public MainWindow(ICoreApi api, SessionContext session, IDialogService dialogs, IThemeService theme,
        IRuntimeInfo runtime, UiSettingsStore store)
    {
        InitializeComponent();
        _api = api;
        _session = session;
        _dialogs = dialogs;
        _theme = theme;
        _runtime = runtime;
        _store = store;
        RestoreWindowState();
        Loaded += async (_, _) => await ShowStartScreenAsync();
    }

    /// <summary>Traz a janela para a frente (segunda abertura do programa).</summary>
    public void BringToFront()
    {
        if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal;
        Activate();
        Topmost = true;   // truque padrão para vencer a proteção de foco do Windows
        Topmost = false;
        Focus();
    }

    private async Task ShowStartScreenAsync()
    {
        try
        {
            var setup = await _api.GetSetupStatusAsync();
            if (setup.Initialized) ShowLogin();
            else Host.Content = new SetupView(new SetupViewModel(_api, _session), OnLoggedInAsync);
        }
        catch (CoreException ex)
        {
            UiLog.Error("Falha ao consultar o estado inicial: " + ex.Message);
            MessageBox.Show(this, "Não foi possível iniciar a tela de acesso:\n\n" + ex.Message,
                "NEXUS OMNITECH", MessageBoxButton.OK, MessageBoxImage.Error);
            Close();
        }
    }

    private void ShowLogin()
    {
        _session.Clear();
        Host.Content = new LoginView(new LoginViewModel(_api, _session), OnLoggedInAsync);
    }

    private async Task OnLoggedInAsync()
    {
        var shell = new ShellViewModel(_api, _session, _dialogs, _theme, _runtime);
        shell.LogoutRequested += (_, _) => Dispatcher.Invoke(ShowLogin);
        Host.Content = shell; // o DataTemplate (Views/Templates.xaml) cria o ShellView
        await shell.InitializeAsync();
    }

    private void RestoreWindowState()
    {
        var saved = _store.Load();
        if (saved.WindowWidth is double width && saved.WindowHeight is double height)
        {
            Width = Math.Min(width, SystemParameters.VirtualScreenWidth);
            Height = Math.Min(height, SystemParameters.VirtualScreenHeight);
        }
        if (saved.WindowMaximized) WindowState = WindowState.Maximized;
    }

    protected override void OnClosing(System.ComponentModel.CancelEventArgs e)
    {
        var maximized = WindowState == WindowState.Maximized;
        var bounds = maximized ? RestoreBounds : new Rect(0, 0, ActualWidth, ActualHeight);
        if (bounds.Width >= 600 && bounds.Height >= 400)
        {
            _store.Update(s => s with { WindowWidth = bounds.Width, WindowHeight = bounds.Height, WindowMaximized = maximized });
        }
        base.OnClosing(e);
    }
}
