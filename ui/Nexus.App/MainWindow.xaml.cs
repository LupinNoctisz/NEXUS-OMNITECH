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

    public MainWindow(ICoreApi api, SessionContext session, IDialogService dialogs, IThemeService theme)
    {
        InitializeComponent();
        _api = api;
        _session = session;
        _dialogs = dialogs;
        _theme = theme;
        ShowLogin();
    }

    private void ShowLogin()
    {
        _session.Clear();
        Host.Content = new LoginView(new LoginViewModel(_api, _session), OnLoggedInAsync);
    }

    private async Task OnLoggedInAsync()
    {
        var shell = new ShellViewModel(_api, _session, _dialogs, _theme);
        shell.LogoutRequested += (_, _) => Dispatcher.Invoke(ShowLogin);
        Host.Content = shell; // o DataTemplate (Views/Templates.xaml) cria o ShellView
        await shell.InitializeAsync();
    }
}
