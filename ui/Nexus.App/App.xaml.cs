using System.Windows;
using Nexus.App.Services;
using Nexus.CoreClient;
using Nexus.Presentation;

namespace Nexus.App;

public partial class App : Application
{
    private JsonRpcConnection? _connection;
    private bool _exiting;

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        ShutdownMode = ShutdownMode.OnExplicitShutdown;

        try
        {
            var options = CoreLaunchOptions.FromEnvironment();
            var transport = ProcessTransport.Start(options);
            _connection = new JsonRpcConnection(transport);
            _connection.Start();
            var api = new CoreApi(_connection);

            var hello = await api.HelloAsync();
            if (hello.Protocol != "1.0")
            {
                throw new CoreUnavailableException(
                    $"Versão de protocolo incompatível: o núcleo usa {hello.Protocol}, a interface espera 1.0.");
            }

            api.Disconnected += (_, _) => Dispatcher.Invoke(OnCoreDisconnected);

            var window = new MainWindow(api, new SessionContext(), new DialogService(), new ThemeService());
            MainWindow = window;
            ShutdownMode = ShutdownMode.OnMainWindowClose;
            window.Show();
        }
        catch (CoreException ex)
        {
            Fail(ex.Message);
        }
        catch (Exception ex)
        {
            Fail("Falha ao iniciar o NEXUS: " + ex.Message);
        }
    }

    private void OnCoreDisconnected()
    {
        if (_exiting) return;
        MessageBox.Show("O núcleo do NEXUS foi encerrado inesperadamente. O aplicativo será fechado; " +
                        "consulte o log do NEXUS para detalhes.", "NEXUS OMNITECH", MessageBoxButton.OK, MessageBoxImage.Error);
        Shutdown(2);
    }

    private void Fail(string message)
    {
        MessageBox.Show(message, "NEXUS OMNITECH — não foi possível iniciar", MessageBoxButton.OK, MessageBoxImage.Error);
        Shutdown(1);
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _exiting = true;
        try
        {
            _connection?.DisposeAsync().AsTask().Wait(TimeSpan.FromSeconds(3));
        }
        catch
        {
            // encerrando: nada a fazer
        }
        base.OnExit(e);
    }
}
