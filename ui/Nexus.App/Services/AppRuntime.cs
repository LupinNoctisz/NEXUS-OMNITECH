using System.Reflection;
using System.Windows;
using Microsoft.Win32;
using Nexus.CoreClient;
using Nexus.Presentation;

namespace Nexus.App.Services;

/// <summary>O que a interface sabe sobre o seu próprio ambiente (versão, Python em uso) e a escolha manual do Python.</summary>
public sealed class AppRuntime : IRuntimeInfo
{
    private readonly UiSettingsStore _store;

    public AppRuntime(UiSettingsStore store) => _store = store;

    public static string Version
    {
        get
        {
            var info = Assembly.GetEntryAssembly()?.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion;
            return string.IsNullOrWhiteSpace(info) ? "0.0.0" : info.Split('+')[0];
        }
    }

    public string AppVersion => Version;
    public string PythonPath { get; private set; } = "—";
    public string PythonVersion { get; private set; } = "—";
    public string CorePath { get; private set; } = "—";

    public void Set(CoreLaunchOptions options)
    {
        PythonPath = options.PythonPath;
        PythonVersion = options.PythonVersion?.ToString() ?? "—";
        CorePath = options.CorePath;
    }

    public async Task<string?> ChoosePythonAsync()
    {
        var dialog = new OpenFileDialog
        {
            Title = "Escolha o python.exe (Python 3.12 ou mais novo)",
            Filter = "Python (python.exe)|python.exe|Executáveis (*.exe)|*.exe",
            CheckFileExists = true,
        };
        if (dialog.ShowDialog() != true) return null;

        var probe = await new ProcessPythonProbe().ProbeAsync(dialog.FileName, default);
        var minimum = PythonRequirements.Minimum;
        if (!probe.Ok || probe.Version is null || probe.Version < minimum)
        {
            var reason = probe.Ok ? $"versão {probe.Version} (precisa de {minimum.Major}.{minimum.Minor} ou mais nova)" : probe.Problem;
            var text = $"Esse Python não pode ser usado: {reason}";
            MessageBox.Show(Application.Current.MainWindow, text, "NEXUS OMNITECH", MessageBoxButton.OK, MessageBoxImage.Warning);
            return text;
        }

        _store.Update(s => s with { PythonPath = dialog.FileName });
        UiLog.Info($"Python escolhido manualmente: {dialog.FileName} ({probe.Version})");
        return $"Python {probe.Version} salvo ({dialog.FileName}). Reinicie o NEXUS para usá-lo.";
    }
}
