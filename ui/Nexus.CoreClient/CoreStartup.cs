namespace Nexus.CoreClient;

/// <summary>Decide COMO iniciar o núcleo (Python + pasta do núcleo + pasta de dados) ou explica por que não dá.</summary>
public static class CoreStartup
{
    public static async Task<CoreLaunchOptions> ResolveAsync(string? configuredPython, IPythonProbe? probe = null,
        CancellationToken ct = default)
    {
        var corePath = Environment.GetEnvironmentVariable("NEXUS_CORE_PATH");
        if (string.IsNullOrWhiteSpace(corePath)) corePath = CoreLaunchOptions.FindCorePath();
        if (corePath is null || !File.Exists(Path.Combine(corePath, "nexus", "__init__.py")))
        {
            throw new CoreUnavailableException(
                "Os arquivos do núcleo do NEXUS não foram encontrados (pasta 'core' ao lado do programa). " +
                "A instalação parece incompleta: reinstale o NEXUS OMNITECH.");
        }

        var locator = new PythonLocator(probe ?? new ProcessPythonProbe());
        var resolution = await locator.ResolveAsync(
            PythonSources.Enumerate(Environment.GetEnvironmentVariable("NEXUS_PYTHON"), configuredPython), ct).ConfigureAwait(false);

        if (!resolution.Found)
        {
            throw new PythonNotFoundException(DescribeFailure(resolution), resolution.Rejected, resolution.ExplicitFailure);
        }

        var home = Environment.GetEnvironmentVariable("NEXUS_HOME");
        return new CoreLaunchOptions(resolution.Selected!.Path, corePath, string.IsNullOrWhiteSpace(home) ? null : home)
        {
            PythonVersion = resolution.Version,
        };
    }

    public static string DescribeFailure(PythonResolution resolution)
    {
        var minimum = $"{PythonRequirements.Minimum.Major}.{PythonRequirements.Minimum.Minor}";
        var text = resolution.ExplicitFailure
            ? $"O Python indicado não pode ser usado (é necessário Python {minimum} ou mais novo)."
            : $"Não foi encontrado um Python {minimum} ou mais novo neste computador.\n\n" +
              "Instale o Python (por exemplo: winget install Python.Python.3.12, ou pelo python.org / uv) " +
              "e abra o NEXUS de novo — ou escolha o python.exe manualmente.";
        if (resolution.Rejected.Count > 0)
        {
            text += "\n\nO que foi verificado:\n• " + string.Join("\n• ", resolution.Rejected);
        }
        return text;
    }
}

/// <summary>O núcleo e a interface precisam ser da mesma série (major.minor).</summary>
public static class VersionCompat
{
    public static bool TryParse(string? text, out Version version)
    {
        version = new Version(0, 0);
        if (string.IsNullOrWhiteSpace(text)) return false;
        var core = text.Split('+', '-')[0];
        return Version.TryParse(core, out var parsed) && (version = parsed) is not null;
    }

    public static bool IsCompatible(string? coreVersion, string? appVersion)
        => TryParse(coreVersion, out var core) && TryParse(appVersion, out var app)
           && core.Major == app.Major && core.Minor == app.Minor;
}
