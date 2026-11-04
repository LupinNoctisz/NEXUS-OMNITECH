using System.Text.Json;
using System.Windows;
using Nexus.App.Services;
using Nexus.CoreClient;
using Nexus.Presentation;

namespace Nexus.App;

public partial class App : Application
{
    private readonly UiSettingsStore _store = new();
    private readonly AppRuntime _runtime;
    private JsonRpcConnection? _connection;
    private ProcessTransport? _transport;
    private SingleInstance? _single;
    private bool _exiting;

    public App()
    {
        _runtime = new AppRuntime(_store);
    }

    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        ShutdownMode = ShutdownMode.OnExplicitShutdown;
        InstallCrashHandlers();

        var selfTestFile = SelfTestTarget(e.Args);
        if (selfTestFile is not null)
        {
            await RunSelfTestAsync(selfTestFile);
            return;
        }

        _single = SingleInstance.TryAcquire();
        if (_single is null)
        {
            Shutdown(0); // já está aberto: a primeira instância foi avisada e vem para a frente
            return;
        }

        try
        {
            var theme = new ThemeService(_store);
            theme.Apply(_store.Load().Theme ?? "dark");

            if (!await ConnectAsync())
            {
                Shutdown(1);
                return;
            }

            var window = new MainWindow(_api!, new SessionContext(), new DialogService(), theme, _runtime, _store);
            MainWindow = window;
            ShutdownMode = ShutdownMode.OnMainWindowClose;
            _single.ListenForActivation(() => Dispatcher.Invoke(window.BringToFront));
            window.Show();
            UiLog.Info($"NEXUS {AppRuntime.Version} iniciado (Python {_runtime.PythonVersion})");
        }
        catch (Exception ex)
        {
            UiLog.Error("Falha ao iniciar: " + ex);
            Fail("Falha ao iniciar o NEXUS:\n\n" + ex.Message);
            Shutdown(1);
        }
    }

    private CoreApi? _api;

    // --- inicialização do núcleo -------------------------------------------------------------
    /// <summary>Descobre o Python, inicia o núcleo e confere protocolo/versão. false = usuário desistiu ou erro mostrado.</summary>
    private async Task<bool> ConnectAsync()
    {
        while (true)
        {
            try
            {
                var options = await CoreStartup.ResolveAsync(_store.Load().PythonPath);
                await StartAndCheckAsync(options);
                _runtime.Set(options);
                return true;
            }
            catch (PythonNotFoundException ex)
            {
                UiLog.Error("Python não encontrado: " + ex.Message);
                var answer = MessageBox.Show(
                    ex.Message + "\n\nDeseja escolher o python.exe manualmente agora?",
                    "NEXUS OMNITECH — Python necessário", MessageBoxButton.YesNo, MessageBoxImage.Warning);
                if (answer != MessageBoxResult.Yes) return false;
                if (await _runtime.ChoosePythonAsync() is null) return false;
                // volta ao início do laço: tenta de novo com o caminho gravado
            }
            catch (CoreException ex)
            {
                var detail = _transport?.StderrTail;
                UiLog.Error("Falha ao iniciar o núcleo: " + ex.Message + (string.IsNullOrWhiteSpace(detail) ? "" : " | " + detail));
                await DisposeConnectionAsync();
                Fail(ex.Message + (string.IsNullOrWhiteSpace(detail) ? "" : "\n\nDetalhes do núcleo:\n" + detail)
                     + "\n\nO registro completo está em: " + UiLog.FilePath());
                return false;
            }
        }
    }

    private async Task StartAndCheckAsync(CoreLaunchOptions options)
    {
        await DisposeConnectionAsync();
        _transport = ProcessTransport.Start(options);
        _connection = new JsonRpcConnection(_transport);
        _connection.Start();
        _api = new CoreApi(_connection);

        var hello = await _api.HelloAsync();
        if (hello.Protocol != "1.0")
        {
            throw new CoreUnavailableException(
                $"Versão de protocolo incompatível: o núcleo usa {hello.Protocol}, a interface espera 1.0. Reinstale o NEXUS.");
        }
        if (!VersionCompat.IsCompatible(hello.CoreVersion, AppRuntime.Version))
        {
            throw new CoreUnavailableException(
                $"O núcleo ({hello.CoreVersion}) e a interface ({AppRuntime.Version}) são de versões incompatíveis. Reinstale o NEXUS.");
        }
        var api = _api;
        api.Disconnected += (_, _) => Dispatcher.Invoke(() =>
        {
            if (ReferenceEquals(api, _api)) OnCoreDisconnected(); // ignora o fim esperado (encerramento/retentativa)
        });
    }

    private async Task DisposeConnectionAsync()
    {
        var connection = _connection;
        _connection = null;
        _transport = null;
        _api = null;
        if (connection is not null)
        {
            try { await connection.DisposeAsync(); } catch (Exception ex) { UiLog.Error("Erro ao encerrar o núcleo: " + ex.Message); }
        }
    }

    // --- autoteste (usado pelo CI e para diagnóstico): sem janela, grava um JSON com o resultado ------
    private static string? SelfTestTarget(string[] args)
    {
        var index = Array.IndexOf(args, "--selftest");
        return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
    }

    private async Task RunSelfTestAsync(string outputFile)
    {
        var report = new Dictionary<string, object?> { ["app_version"] = AppRuntime.Version };
        var exitCode = 0;
        try
        {
            var options = await CoreStartup.ResolveAsync(_store.Load().PythonPath);
            await StartAndCheckAsync(options);
            var hello = await _api!.HelloAsync();
            var setup = await _api.GetSetupStatusAsync();
            report["python_path"] = options.PythonPath;
            report["python_version"] = options.PythonVersion?.ToString();
            report["core_path"] = options.CorePath;
            report["core_version"] = hello.CoreVersion;
            report["protocol"] = hello.Protocol;
            report["schema_version"] = hello.SchemaVersion;
            report["initialized"] = setup.Initialized;

            var transport = _transport!;
            await DisposeConnectionAsync();
            report["core_killed_on_exit"] = transport.KilledOnDispose;
            report["core_exit_code"] = transport.ExitCode;
            if (transport.KilledOnDispose || transport.ExitCode != 0) throw new InvalidOperationException("o núcleo não encerrou de forma limpa");
            report["ok"] = true;
        }
        catch (Exception ex)
        {
            report["ok"] = false;
            report["error"] = ex.Message;
            exitCode = 3;
            await DisposeConnectionAsync();
        }
        try
        {
            File.WriteAllText(outputFile, JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            exitCode = 4;
        }
        _exiting = true;
        Shutdown(exitCode);
    }

    // --- falhas e encerramento -----------------------------------------------------------------------
    private void OnCoreDisconnected()
    {
        if (_exiting) return;
        _exiting = true;
        UiLog.Error("O núcleo encerrou inesperadamente.");
        MessageBox.Show("O núcleo do NEXUS foi encerrado inesperadamente. O aplicativo será fechado; " +
                        "seus dados não são perdidos. Detalhes em:\n" + UiLog.FilePath(),
            "NEXUS OMNITECH", MessageBoxButton.OK, MessageBoxImage.Error);
        Shutdown(2);
    }

    private static void Fail(string message)
        => MessageBox.Show(message, "NEXUS OMNITECH — não foi possível iniciar", MessageBoxButton.OK, MessageBoxImage.Error);

    private void InstallCrashHandlers()
    {
        DispatcherUnhandledException += (_, args) =>
        {
            UiLog.Error("Erro não tratado na interface: " + args.Exception);
            args.Handled = true; // o aplicativo continua aberto
            MessageBox.Show("Ocorreu um erro inesperado, mas o NEXUS continua aberto.\n\n" + args.Exception.Message +
                            "\n\nDetalhes em: " + UiLog.FilePath(), "NEXUS OMNITECH", MessageBoxButton.OK, MessageBoxImage.Warning);
        };
        AppDomain.CurrentDomain.UnhandledException += (_, args) => UiLog.Error("Erro fatal: " + args.ExceptionObject);
        TaskScheduler.UnobservedTaskException += (_, args) =>
        {
            UiLog.Error("Tarefa com erro não observado: " + args.Exception);
            args.SetObserved();
        };
    }

    protected override void OnExit(ExitEventArgs e)
    {
        _exiting = true;
        try
        {
            Task.Run(DisposeConnectionAsync).Wait(TimeSpan.FromSeconds(10)); // fecha a entrada do núcleo e espera ele sair
        }
        catch (Exception ex)
        {
            UiLog.Error("Erro ao encerrar: " + ex.Message);
        }
        _single?.Dispose();
        base.OnExit(e);
    }
}
