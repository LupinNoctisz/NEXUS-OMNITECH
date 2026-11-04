using System.Diagnostics;

namespace Nexus.App.Services;

/// <summary>
/// Garante uma única instância por sessão do Windows. Uma segunda abertura apenas avisa a primeira
/// (que vem para a frente) e encerra — dois processos usando o mesmo banco SQLite seriam um risco sem necessidade.
/// O nome do mutex é o mesmo usado pelo instalador (AppMutex) para avisar que o NEXUS está aberto.
/// </summary>
public sealed class SingleInstance : IDisposable
{
    public const string MutexName = "NexusOmnitech.SingleInstance";
    private const string ActivateName = "NexusOmnitech.Activate";

    private readonly Mutex _mutex;
    private readonly EventWaitHandle _activate;
    private volatile bool _disposed;

    private SingleInstance(Mutex mutex, EventWaitHandle activate)
    {
        _mutex = mutex;
        _activate = activate;
    }

    /// <summary>Devolve null se já existe outra instância (que foi avisada).</summary>
    public static SingleInstance? TryAcquire()
    {
        var mutex = new Mutex(initiallyOwned: true, MutexName, out var created);
        if (!created)
        {
            mutex.Dispose();
            try
            {
                using var existing = EventWaitHandle.OpenExisting(ActivateName);
                existing.Set();
            }
            catch (Exception ex) when (ex is WaitHandleCannotBeOpenedException or UnauthorizedAccessException)
            {
                // a primeira instância ainda está iniciando: nada a fazer
            }
            return null;
        }
        return new SingleInstance(mutex, new EventWaitHandle(false, EventResetMode.AutoReset, ActivateName));
    }

    public void ListenForActivation(Action onActivate)
    {
        var thread = new Thread(() =>
        {
            while (!_disposed)
            {
                try
                {
                    if (_activate.WaitOne(500)) onActivate();
                }
                catch (ObjectDisposedException)
                {
                    return;
                }
            }
        })
        {
            IsBackground = true,
            Name = "nexus-activation",
        };
        thread.Start();
    }

    public void Dispose()
    {
        _disposed = true;
        try { _mutex.ReleaseMutex(); } catch (ApplicationException) { }
        _mutex.Dispose();
        _activate.Dispose();
    }
}
