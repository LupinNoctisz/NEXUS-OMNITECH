using System.ComponentModel;
using System.Diagnostics;
using System.Text;

namespace Nexus.CoreClient;

/// <summary>Canal de linhas (uma mensagem JSON por linha).</summary>
public interface IRpcTransport : IAsyncDisposable
{
    Task WriteLineAsync(string line, CancellationToken ct);

    /// <summary>Devolve null quando o outro lado fechou o canal.</summary>
    Task<string?> ReadLineAsync(CancellationToken ct);
}

/// <summary>Como iniciar o núcleo Python (processo filho, sem porta de rede).</summary>
public sealed record CoreLaunchOptions(string PythonPath, string CorePath, string? HomePath)
{
    /// <summary>Versão do Python escolhida (informativa).</summary>
    public Version? PythonVersion { get; init; }

    /// <summary>
    /// NEXUS_PYTHON (padrão "python"), NEXUS_CORE_PATH (pasta que contém o pacote "nexus", ex.: .../src)
    /// e NEXUS_HOME (opcional). Sem NEXUS_CORE_PATH, procura "src/nexus" subindo a partir do executável.
    /// </summary>
    public static CoreLaunchOptions FromEnvironment()
    {
        var python = Environment.GetEnvironmentVariable("NEXUS_PYTHON");
        if (string.IsNullOrWhiteSpace(python)) python = "python";

        var corePath = Environment.GetEnvironmentVariable("NEXUS_CORE_PATH");
        if (string.IsNullOrWhiteSpace(corePath)) corePath = FindCorePath();
        if (corePath is null)
        {
            throw new CoreUnavailableException(
                "Não foi possível localizar o núcleo do NEXUS. Defina NEXUS_CORE_PATH com a pasta 'src' do projeto.");
        }

        var home = Environment.GetEnvironmentVariable("NEXUS_HOME");
        return new CoreLaunchOptions(python, corePath, string.IsNullOrWhiteSpace(home) ? null : home);
    }

    /// <summary>
    /// Instalado: &lt;pasta do app&gt;\core\nexus. Desenvolvimento: sobe a partir do executável procurando "src/nexus".
    /// </summary>
    public static string? FindCorePath()
    {
        var installed = Path.Combine(AppContext.BaseDirectory, "core");
        if (File.Exists(Path.Combine(installed, "nexus", "__init__.py"))) return installed;

        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        for (var depth = 0; depth < 10 && directory is not null; depth++, directory = directory.Parent)
        {
            var candidate = Path.Combine(directory.FullName, "src");
            if (File.Exists(Path.Combine(candidate, "nexus", "__init__.py"))) return candidate;
        }
        return null;
    }
}

/// <summary>Executa "python -m nexus serve --stdio" e conversa pela entrada/saída padrão.</summary>
public sealed class ProcessTransport : IRpcTransport
{
    private readonly Process _process;
    private readonly StreamWriter _stdin;
    private readonly StreamReader _stdout;
    private readonly object _tailLock = new();
    private readonly Queue<string> _stderrTail = new();

    private ProcessTransport(Process process)
    {
        _process = process;
        _stdin = process.StandardInput;
        _stdin.AutoFlush = true;
        _stdin.NewLine = "\n";
        _stdout = process.StandardOutput;
    }

    public static ProcessTransport Start(CoreLaunchOptions options)
    {
        var info = new ProcessStartInfo
        {
            FileName = options.PythonPath,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false),
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        info.ArgumentList.Add("-m");
        info.ArgumentList.Add("nexus");
        if (options.HomePath is not null)
        {
            info.ArgumentList.Add("--home");
            info.ArgumentList.Add(options.HomePath);
        }
        info.ArgumentList.Add("serve");
        info.ArgumentList.Add("--stdio");

        var existing = Environment.GetEnvironmentVariable("PYTHONPATH");
        info.Environment["PYTHONPATH"] = string.IsNullOrEmpty(existing)
            ? options.CorePath
            : options.CorePath + Path.PathSeparator + existing;
        info.Environment["PYTHONUTF8"] = "1";
        info.Environment["PYTHONIOENCODING"] = "utf-8";

        Process? process;
        try
        {
            process = Process.Start(info);
        }
        catch (Win32Exception ex)
        {
            throw new CoreUnavailableException(
                $"Não foi possível executar o Python ('{options.PythonPath}'). Instale o Python 3.12 ou defina NEXUS_PYTHON.", ex);
        }
        if (process is null) throw new CoreUnavailableException("O processo do núcleo não pôde ser iniciado.");

        var transport = new ProcessTransport(process);
        process.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is null) return;
            lock (transport._tailLock)
            {
                transport._stderrTail.Enqueue(e.Data);
                while (transport._stderrTail.Count > 20) transport._stderrTail.Dequeue();
            }
        };
        process.BeginErrorReadLine();
        return transport;
    }

    /// <summary>Últimas linhas escritas pelo núcleo em stderr (diagnóstico de falhas de inicialização).</summary>
    public string StderrTail
    {
        get
        {
            lock (_tailLock) return string.Join(Environment.NewLine, _stderrTail);
        }
    }

    public async Task WriteLineAsync(string line, CancellationToken ct)
    {
        try
        {
            await _stdin.WriteLineAsync(line.AsMemory(), ct).ConfigureAwait(false);
        }
        catch (IOException ex)
        {
            throw new CoreUnavailableException("O núcleo do NEXUS não está mais respondendo.", ex);
        }
    }

    public async Task<string?> ReadLineAsync(CancellationToken ct)
    {
        return await _stdout.ReadLineAsync(ct).ConfigureAwait(false);
    }

    /// <summary>true se o núcleo não encerrou sozinho ao fechar a entrada e precisou ser finalizado à força.</summary>
    public bool KilledOnDispose { get; private set; }

    /// <summary>Código de saída do núcleo (disponível depois de DisposeAsync).</summary>
    public int? ExitCode { get; private set; }

    public ValueTask DisposeAsync()
    {
        try { _stdin.Close(); } catch (IOException) { }
        try
        {
            if (!_process.WaitForExit(5000))
            {
                KilledOnDispose = true;
                _process.Kill(true);
                _process.WaitForExit(2000);
            }
            if (_process.HasExited) ExitCode = _process.ExitCode;
        }
        catch (InvalidOperationException) { }
        _process.Dispose();
        return ValueTask.CompletedTask;
    }
}
