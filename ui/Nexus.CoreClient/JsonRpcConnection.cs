using System.Text.Json;

namespace Nexus.CoreClient;

public interface IJsonRpc
{
    Task<T> InvokeAsync<T>(string method, IReadOnlyDictionary<string, object?>? parameters = null,
        CancellationToken ct = default);
}

/// <summary>
/// JSON-RPC 2.0 sobre um canal de linhas. O núcleo atende uma requisição por vez, então as chamadas
/// são serializadas por um semáforo; um laço de leitura entrega cada resposta à chamada correspondente.
/// </summary>
public sealed class JsonRpcConnection : IJsonRpc, IAsyncDisposable
{
    private readonly IRpcTransport _transport;
    private readonly TimeSpan _timeout;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly object _sync = new();
    private readonly Dictionary<long, TaskCompletionSource<JsonElement>> _pending = new();
    private readonly CancellationTokenSource _lifetime = new();
    private long _nextId;
    private Task? _reader;
    private bool _closed;
    private string _closeReason = "O núcleo do NEXUS foi encerrado.";

    public JsonRpcConnection(IRpcTransport transport, TimeSpan? timeout = null)
    {
        _transport = transport;
        _timeout = timeout ?? TimeSpan.FromSeconds(60);
    }

    public event EventHandler? Closed;

    public void Start()
    {
        _reader = Task.Run(ReadLoopAsync);
    }

    public async Task<T> InvokeAsync<T>(string method, IReadOnlyDictionary<string, object?>? parameters = null,
        CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var id = Interlocked.Increment(ref _nextId);
            var completion = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
            lock (_sync)
            {
                if (_closed) throw new CoreUnavailableException(_closeReason);
                _pending[id] = completion;
            }

            using var timeoutSource = CancellationTokenSource.CreateLinkedTokenSource(ct);
            timeoutSource.CancelAfter(_timeout);
            try
            {
                var request = new Dictionary<string, object?>
                {
                    ["jsonrpc"] = "2.0",
                    ["id"] = id,
                    ["method"] = method,
                    ["params"] = parameters ?? new Dictionary<string, object?>(),
                };
                var line = JsonSerializer.Serialize(request, CoreJson.Options);
                await _transport.WriteLineAsync(line, timeoutSource.Token).ConfigureAwait(false);

                using var registration = timeoutSource.Token.Register(() => completion.TrySetCanceled());
                var result = await completion.Task.ConfigureAwait(false);
                var value = result.Deserialize<T>(CoreJson.Options);
                if (value is null) throw new CoreUnavailableException($"Resposta vazia do núcleo ({method}).");
                return value;
            }
            catch (OperationCanceledException) when (!ct.IsCancellationRequested)
            {
                throw new CoreUnavailableException($"Tempo esgotado aguardando o núcleo ({method}).");
            }
            finally
            {
                lock (_sync) _pending.Remove(id);
            }
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task ReadLoopAsync()
    {
        try
        {
            while (!_lifetime.IsCancellationRequested)
            {
                var line = await _transport.ReadLineAsync(_lifetime.Token).ConfigureAwait(false);
                if (line is null) break;
                if (line.Length == 0) continue;
                Dispatch(line);
            }
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception ex)
        {
            _closeReason = "A comunicação com o núcleo falhou: " + ex.Message;
        }
        finally
        {
            Close();
        }
    }

    private void Dispatch(string line)
    {
        try
        {
            using var document = JsonDocument.Parse(line);
            var root = document.RootElement;
            if (!root.TryGetProperty("id", out var idElement)
                || idElement.ValueKind != JsonValueKind.Number
                || !idElement.TryGetInt64(out var id))
            {
                return; // resposta sem id numérico (ex.: erro de parse do servidor): não há quem aguarde
            }

            TaskCompletionSource<JsonElement>? completion;
            lock (_sync) _pending.TryGetValue(id, out completion);
            if (completion is null) return; // chamada que já expirou

            if (root.TryGetProperty("error", out var error))
            {
                var code = error.GetProperty("code").GetInt32();
                var message = error.GetProperty("message").GetString() ?? "Erro desconhecido do núcleo.";
                var type = "";
                if (error.TryGetProperty("data", out var data) && data.TryGetProperty("type", out var typeElement))
                {
                    type = typeElement.GetString() ?? "";
                }
                completion.TrySetException(new RpcException(code, type, message));
            }
            else if (root.TryGetProperty("result", out var result))
            {
                completion.TrySetResult(result.Clone());
            }
            else
            {
                completion.TrySetException(new CoreUnavailableException("Resposta do núcleo sem 'result'."));
            }
        }
        catch (JsonException)
        {
            // linha inválida: ignorada
        }
    }

    private void Close()
    {
        List<TaskCompletionSource<JsonElement>> toFail;
        lock (_sync)
        {
            if (_closed) return;
            _closed = true;
            toFail = _pending.Values.ToList();
            _pending.Clear();
        }
        foreach (var completion in toFail)
        {
            completion.TrySetException(new CoreUnavailableException(_closeReason));
        }
        Closed?.Invoke(this, EventArgs.Empty);
    }

    public async ValueTask DisposeAsync()
    {
        _lifetime.Cancel();
        await _transport.DisposeAsync().ConfigureAwait(false);
        if (_reader is not null)
        {
            try { await _reader.WaitAsync(TimeSpan.FromSeconds(3)).ConfigureAwait(false); }
            catch (TimeoutException) { }
        }
        _lifetime.Dispose();
    }
}
