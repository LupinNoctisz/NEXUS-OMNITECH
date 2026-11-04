using System.Text.Json;
using System.Threading.Channels;
using Nexus.CoreClient;

namespace Nexus.Tests;

public sealed class FakeTransport : IRpcTransport
{
    private readonly Channel<string> _incoming = Channel.CreateUnbounded<string>();

    public List<string> Written { get; } = new();

    /// <summary>Recebe a linha enviada e devolve a resposta a entregar (ou null para não responder).</summary>
    public Func<string, string?>? Responder { get; set; }

    public Task WriteLineAsync(string line, CancellationToken ct)
    {
        lock (Written) Written.Add(line);
        var reply = Responder?.Invoke(line);
        if (reply is not null) _incoming.Writer.TryWrite(reply);
        return Task.CompletedTask;
    }

    public async Task<string?> ReadLineAsync(CancellationToken ct)
    {
        try
        {
            return await _incoming.Reader.ReadAsync(ct);
        }
        catch (ChannelClosedException)
        {
            return null;
        }
    }

    public void Push(string line) => _incoming.Writer.TryWrite(line);
    public void CloseRemote() => _incoming.Writer.TryComplete();

    public ValueTask DisposeAsync()
    {
        _incoming.Writer.TryComplete();
        return ValueTask.CompletedTask;
    }
}

public class JsonRpcConnectionTests
{
    private static long IdOf(string request)
    {
        using var document = JsonDocument.Parse(request);
        return document.RootElement.GetProperty("id").GetInt64();
    }

    private static string Result(string request, string resultJson) =>
        $"{{\"jsonrpc\":\"2.0\",\"id\":{IdOf(request)},\"result\":{resultJson}}}";

    private static (FakeTransport Transport, JsonRpcConnection Connection) Create(TimeSpan? timeout = null)
    {
        var transport = new FakeTransport();
        var connection = new JsonRpcConnection(transport, timeout);
        connection.Start();
        return (transport, connection);
    }

    [Fact]
    public async Task Sends_snake_case_params_and_returns_typed_result()
    {
        var (transport, connection) = Create();
        transport.Responder = request => Result(request, "{\"id\":7}");
        await using var guard = connection;

        var result = await connection.InvokeAsync<IdResult>("sessions.start",
            new Dictionary<string, object?> { ["device_id"] = 3L, ["kind"] = "general" });

        Assert.Equal(7, result.Id);
        using var sent = JsonDocument.Parse(transport.Written.Single());
        var root = sent.RootElement;
        Assert.Equal("2.0", root.GetProperty("jsonrpc").GetString());
        Assert.Equal("sessions.start", root.GetProperty("method").GetString());
        Assert.Equal(3, root.GetProperty("params").GetProperty("device_id").GetInt32());
        Assert.DoesNotContain('\n', transport.Written.Single());
    }

    [Fact]
    public async Task Error_response_becomes_RpcException()
    {
        var (transport, connection) = Create();
        transport.Responder = request =>
            $"{{\"jsonrpc\":\"2.0\",\"id\":{IdOf(request)},\"error\":{{\"code\":-32001,\"message\":\"negado\",\"data\":{{\"type\":\"PermissionDenied\"}}}}}}";
        await using var guard = connection;

        var error = await Assert.ThrowsAsync<RpcException>(() => connection.InvokeAsync<OkResult>("devices.scan"));
        Assert.Equal(RpcCodes.PermissionDenied, error.Code);
        Assert.Equal("PermissionDenied", error.ErrorType);
        Assert.Equal("negado", error.Message);
    }

    [Fact]
    public async Task Ignores_garbage_and_responses_for_unknown_ids()
    {
        var (transport, connection) = Create();
        transport.Responder = request => Result(request, "{\"ok\":true}");
        await using var guard = connection;
        transport.Push("isto não é json");
        transport.Push("{\"jsonrpc\":\"2.0\",\"id\":999,\"result\":{\"ok\":false}}");
        transport.Push("{\"jsonrpc\":\"2.0\",\"id\":null,\"error\":{\"code\":-32700,\"message\":\"x\"}}");

        var result = await connection.InvokeAsync<OkResult>("auth.logout");
        Assert.True(result.Ok);
    }

    [Fact]
    public async Task Concurrent_calls_each_receive_their_own_response()
    {
        var (transport, connection) = Create();
        transport.Responder = request =>
        {
            using var document = JsonDocument.Parse(request);
            var echo = document.RootElement.GetProperty("params").GetProperty("n").GetInt32();
            return Result(request, $"{{\"id\":{echo}}}");
        };
        await using var guard = connection;

        var calls = Enumerable.Range(1, 20)
            .Select(n => connection.InvokeAsync<IdResult>("x.y", new Dictionary<string, object?> { ["n"] = n }))
            .ToArray();
        var results = await Task.WhenAll(calls);

        Assert.Equal(Enumerable.Range(1, 20).Select(n => (long)n), results.Select(r => r.Id));
    }

    [Fact]
    public async Task Times_out_when_core_does_not_answer()
    {
        var (_, connection) = Create(TimeSpan.FromMilliseconds(200));
        await using var guard = connection;

        var error = await Assert.ThrowsAsync<CoreUnavailableException>(() => connection.InvokeAsync<OkResult>("status.get"));
        Assert.Contains("Tempo esgotado", error.Message);
    }

    [Fact]
    public async Task Closing_fails_pending_and_future_calls_and_raises_event()
    {
        var (transport, connection) = Create();
        var closed = new TaskCompletionSource();
        connection.Closed += (_, _) => closed.TrySetResult();
        await using var guard = connection;

        var pending = connection.InvokeAsync<OkResult>("status.get");
        await Task.Delay(100);
        transport.CloseRemote();

        await Assert.ThrowsAsync<CoreUnavailableException>(() => pending);
        await closed.Task.WaitAsync(TimeSpan.FromSeconds(5));
        await Assert.ThrowsAsync<CoreUnavailableException>(() => connection.InvokeAsync<OkResult>("status.get"));
    }

    [Fact]
    public async Task CoreApi_uses_expected_method_names_and_parameter_keys()
    {
        var rpc = new RecordingRpc();
        var api = new CoreApi(rpc);

        await api.LoginAsync("ana", "x");
        await api.StartSessionAsync(5, "pc_diagnostics");
        await api.FinishSessionAsync(5, "aborted", null);
        await api.RestoreBackupAsync("nexus-1.db", true);
        await api.RegisterModuleAsync("nexus.demo", true);
        await api.ListAuditAsync(25, 9);
        await api.SetSettingAsync("backup.keep", 12);
        await api.AddTechnicianAsync("bia", "viewer", "pw");

        Assert.Equal(new[]
        {
            "auth.login", "sessions.start", "sessions.finish", "backups.restore",
            "modules.register", "audit.list", "settings.set", "technicians.add",
        }, rpc.Methods);
        Assert.Equal(new[] { "device_id", "kind" }, rpc.Params[1].Keys.ToArray());
        Assert.Equal(new[] { "id", "status", "summary" }, rpc.Params[2].Keys.ToArray());
        Assert.Equal(new[] { "name", "confirmed" }, rpc.Params[3].Keys.ToArray());
        Assert.Equal(new[] { "limit", "session_id" }, rpc.Params[5].Keys.ToArray());
    }

    private sealed class RecordingRpc : IJsonRpc
    {
        public List<string> Methods { get; } = new();
        public List<IReadOnlyDictionary<string, object?>> Params { get; } = new();

        public Task<T> InvokeAsync<T>(string method, IReadOnlyDictionary<string, object?>? parameters = null,
            CancellationToken ct = default)
        {
            Methods.Add(method);
            Params.Add(parameters ?? new Dictionary<string, object?>());
            // respostas mínimas que satisfazem cada tipo de retorno usado acima
            var json = typeof(T) == typeof(WhoAmI)
                ? "{\"actor\":\"ana\",\"role\":\"admin\",\"permissions\":[],\"authenticated\":true}"
                : typeof(T) == typeof(RestoreResult)
                    ? "{\"safety_backup\":\"a.db\",\"session_active\":true}"
                    : typeof(T) == typeof(List<OperationDto>)
                        ? "[]"
                        : typeof(T) == typeof(IdResult) ? "{\"id\":1}" : "{\"ok\":true}";
            return Task.FromResult(JsonSerializer.Deserialize<T>(json, CoreJson.Options)!);
        }
    }
}
