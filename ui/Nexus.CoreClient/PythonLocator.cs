using System.ComponentModel;
using System.Diagnostics;
using System.Text;
using System.Text.RegularExpressions;

namespace Nexus.CoreClient;

public static class PythonRequirements
{
    /// <summary>Versão mínima do Python aceita pelo núcleo (pyproject: requires-python &gt;= 3.12).</summary>
    public static readonly Version Minimum = new(3, 12);
}

/// <param name="Explicit">Escolha deliberada (variável NEXUS_PYTHON ou configuração): se não servir, não há plano B automático.</param>
public sealed record PythonCandidate(string Path, string Source, bool Explicit = false);

public sealed record PythonProbeResult(bool Ok, Version? Version, string? Problem);

public sealed record PythonResolution(PythonCandidate? Selected, Version? Version, IReadOnlyList<string> Rejected, bool ExplicitFailure)
{
    public bool Found => Selected is not null;
}

/// <summary>Executa/inspeciona um candidato (separado para poder ser substituído nos testes).</summary>
public interface IPythonProbe
{
    Task<PythonProbeResult> ProbeAsync(string path, CancellationToken ct);
}

/// <summary>
/// Escolhe o interpretador: candidatos na ordem de prioridade; o primeiro que EXECUTA e é &gt;= 3.12 vence.
/// Não usa "qualquer python do PATH" às cegas: cada um é executado e a versão é conferida.
/// </summary>
public sealed class PythonLocator
{
    private readonly IPythonProbe _probe;

    public PythonLocator(IPythonProbe probe) => _probe = probe;

    public async Task<PythonResolution> ResolveAsync(IEnumerable<PythonCandidate> candidates, CancellationToken ct = default)
    {
        var rejected = new List<string>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var candidate in candidates)
        {
            var key = candidate.Path.Trim();
            if (key.Length == 0 || !seen.Add(key)) continue;

            var result = await _probe.ProbeAsync(candidate.Path, ct).ConfigureAwait(false);
            if (result.Ok && result.Version is not null && result.Version >= PythonRequirements.Minimum)
            {
                return new PythonResolution(candidate, result.Version, rejected, false);
            }

            var why = result.Ok
                ? $"versão {result.Version} (é necessário {PythonRequirements.Minimum.Major}.{PythonRequirements.Minimum.Minor} ou mais novo)"
                : result.Problem ?? "não pôde ser executado";
            rejected.Add($"{candidate.Source}: {candidate.Path} — {why}");
            if (candidate.Explicit)
            {
                return new PythonResolution(null, null, rejected, true);
            }
        }
        return new PythonResolution(null, null, rejected, false);
    }
}

/// <summary>Executa "python -I -c ..." (modo isolado) com limite de tempo e confere versão e módulos que o núcleo exige.</summary>
public sealed class ProcessPythonProbe : IPythonProbe
{
    private const string Script =
        "import sys, sqlite3, hashlib; hashlib.scrypt; print('%d.%d.%d' % sys.version_info[:3])";

    public async Task<PythonProbeResult> ProbeAsync(string path, CancellationToken ct)
    {
        if (IsStoreAlias(path))
        {
            return new PythonProbeResult(false, null,
                "é o atalho da Microsoft Store (não é um Python instalado) — instale o Python ou escolha o python.exe real");
        }
        if (!File.Exists(path) && Path.IsPathRooted(path))
        {
            return new PythonProbeResult(false, null, "arquivo não encontrado");
        }

        var info = new ProcessStartInfo
        {
            FileName = path,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
        };
        info.ArgumentList.Add("-I");
        info.ArgumentList.Add("-c");
        info.ArgumentList.Add(Script);

        try
        {
            using var process = Process.Start(info);
            if (process is null) return new PythonProbeResult(false, null, "não pôde ser executado");

            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeout.CancelAfter(TimeSpan.FromSeconds(15));
            var stdout = process.StandardOutput.ReadToEndAsync(timeout.Token);
            var stderr = process.StandardError.ReadToEndAsync(timeout.Token);
            try
            {
                await process.WaitForExitAsync(timeout.Token).ConfigureAwait(false);
                var output = (await stdout.ConfigureAwait(false)).Trim();
                var error = (await stderr.ConfigureAwait(false)).Trim();
                if (process.ExitCode != 0)
                {
                    var last = error.Split('\n').LastOrDefault()?.Trim();
                    return new PythonProbeResult(false, null, string.IsNullOrEmpty(last) ? "falhou ao executar" : last);
                }
                return Version.TryParse(output, out var version)
                    ? new PythonProbeResult(true, version, null)
                    : new PythonProbeResult(false, null, "resposta inesperada ao consultar a versão");
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested)
            {
                try { process.Kill(true); } catch (InvalidOperationException) { }
                return new PythonProbeResult(false, null, "não respondeu em 15 segundos");
            }
        }
        catch (Win32Exception ex)
        {
            return new PythonProbeResult(false, null, "não pôde ser executado: " + ex.Message);
        }
    }

    /// <summary>%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe abre a Microsoft Store quando o Python não está instalado.</summary>
    public static bool IsStoreAlias(string path)
    {
        var normalized = path.Replace('/', '\\');
        var directory = Path.GetDirectoryName(normalized) ?? "";
        return directory.EndsWith("\\Microsoft\\WindowsApps", StringComparison.OrdinalIgnoreCase);
    }
}

/// <summary>Onde procurar Python no Windows, em ordem de prioridade.</summary>
public static class PythonSources
{
    public static IEnumerable<PythonCandidate> Enumerate(string? environmentPython, string? configuredPython)
    {
        if (!string.IsNullOrWhiteSpace(environmentPython))
        {
            yield return new PythonCandidate(environmentPython.Trim(), "variável NEXUS_PYTHON", Explicit: true);
        }
        if (!string.IsNullOrWhiteSpace(configuredPython))
        {
            yield return new PythonCandidate(configuredPython.Trim(), "caminho configurado no NEXUS", Explicit: true);
        }

        foreach (var path in PyLauncher()) yield return new PythonCandidate(path, "py launcher");
        foreach (var path in Registry()) yield return new PythonCandidate(path, "registro do Windows");
        foreach (var path in UvPythons()) yield return new PythonCandidate(path, "uv");
        foreach (var path in CommonFolders()) yield return new PythonCandidate(path, "pasta padrão de instalação");
        foreach (var path in OnPath()) yield return new PythonCandidate(path, "PATH");
    }

    private static readonly Regex VersionInText = new(@"3\.(\d+)", RegexOptions.Compiled);

    private static int MinorOf(string text)
    {
        var match = VersionInText.Match(text);
        return match.Success ? int.Parse(match.Groups[1].Value) : -1;
    }

    private static string RunPyLauncher()
    {
        try
        {
            var info = new ProcessStartInfo("py", "-0p")
            {
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using var process = Process.Start(info);
            if (process is null) return "";
            var output = process.StandardOutput.ReadToEnd();
            if (!process.WaitForExit(8000))
            {
                try { process.Kill(true); } catch (InvalidOperationException) { }
                return "";
            }
            return output;
        }
        catch (Exception ex) when (ex is Win32Exception or InvalidOperationException or IOException)
        {
            return "";
        }
    }

    private static IEnumerable<string> PyLauncher()
    {
        if (!OperatingSystem.IsWindows()) yield break;
        var output = RunPyLauncher();
        var found = new List<(int Minor, string Path)>();
        foreach (var line in output.Split('\n'))
        {
            var index = line.IndexOf(":\\", StringComparison.Ordinal);
            if (index < 1) continue;
            var path = line[(index - 1)..].Trim();
            if (path.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) found.Add((MinorOf(line), path));
        }
        foreach (var (_, path) in found.OrderByDescending(f => f.Minor)) yield return path;
    }

    private static List<(int Minor, string Path)> ReadRegistry()
    {
        var results = new List<(int Minor, string Path)>();
        if (!OperatingSystem.IsWindows()) return results;
        foreach (var hive in new[] { Microsoft.Win32.Registry.CurrentUser, Microsoft.Win32.Registry.LocalMachine })
        {
            foreach (var root in new[] { @"SOFTWARE\Python\PythonCore", @"SOFTWARE\WOW6432Node\Python\PythonCore" })
            {
                try
                {
                    using var core = hive.OpenSubKey(root);
                    if (core is null) continue;
                    foreach (var versionName in core.GetSubKeyNames())
                    {
                        using var install = core.OpenSubKey(versionName + @"\InstallPath");
                        if (install is null) continue;
                        var exe = install.GetValue("ExecutablePath") as string;
                        if (string.IsNullOrWhiteSpace(exe))
                        {
                            var dir = install.GetValue(null) as string;
                            if (!string.IsNullOrWhiteSpace(dir)) exe = Path.Combine(dir, "python.exe");
                        }
                        if (!string.IsNullOrWhiteSpace(exe)) results.Add((MinorOf(versionName), exe));
                    }
                }
                catch (Exception ex) when (ex is System.Security.SecurityException or UnauthorizedAccessException or IOException)
                {
                    // sem acesso a essa chave: segue para as próximas fontes
                }
            }
        }
        return results;
    }

    private static IEnumerable<string> Registry()
    {
        foreach (var (_, path) in ReadRegistry().OrderByDescending(r => r.Minor)) yield return path;
    }

    private static IEnumerable<string> UvPythons()
    {
        foreach (var variable in new[] { Environment.SpecialFolder.ApplicationData, Environment.SpecialFolder.LocalApplicationData })
        {
            var root = Path.Combine(Environment.GetFolderPath(variable), "uv", "python");
            foreach (var path in SubfolderExecutables(root, "cpython-3.*")) yield return path;
        }
    }

    private static IEnumerable<string> CommonFolders()
    {
        var local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        foreach (var path in SubfolderExecutables(Path.Combine(local, "Programs", "Python"), "Python3*")) yield return path;
        var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        foreach (var path in SubfolderExecutables(programFiles, "Python3*")) yield return path;
    }

    private static string[] SafeDirectories(string root, string pattern)
    {
        try { return Directory.GetDirectories(root, pattern); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return Array.Empty<string>(); }
    }

    private static IEnumerable<string> SubfolderExecutables(string root, string pattern)
    {
        if (!Directory.Exists(root)) yield break;
        var folders = SafeDirectories(root, pattern);
        foreach (var folder in folders.OrderByDescending(f => MinorOf(Path.GetFileName(f))).ThenByDescending(f => f))
        {
            var exe = Path.Combine(folder, OperatingSystem.IsWindows() ? "python.exe" : "bin/python3");
            if (File.Exists(exe)) yield return exe;
        }
    }

    private static IEnumerable<string> OnPath()
    {
        var names = OperatingSystem.IsWindows() ? new[] { "python.exe" } : new[] { "python3", "python" };
        foreach (var directory in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
        {
            if (string.IsNullOrWhiteSpace(directory)) continue;
            foreach (var name in names)
            {
                string candidate;
                try { candidate = Path.Combine(directory.Trim('"'), name); }
                catch (ArgumentException) { continue; }
                if (File.Exists(candidate)) yield return candidate;
            }
        }
    }
}
