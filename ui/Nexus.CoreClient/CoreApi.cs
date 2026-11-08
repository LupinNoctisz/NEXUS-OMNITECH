using System.Text.Json;

namespace Nexus.CoreClient;

/// <summary>Implementação tipada de <see cref="ICoreApi"/> sobre um <see cref="IJsonRpc"/>.</summary>
public sealed class CoreApi : ICoreApi
{
    private readonly IJsonRpc _rpc;

    public CoreApi(IJsonRpc rpc)
    {
        _rpc = rpc;
        if (rpc is JsonRpcConnection connection)
        {
            connection.Closed += (_, _) => Disconnected?.Invoke(this, EventArgs.Empty);
        }
    }

    public event EventHandler? Disconnected;

    private static Dictionary<string, object?> P(params (string Key, object? Value)[] items)
    {
        var map = new Dictionary<string, object?>();
        foreach (var (key, value) in items) map[key] = value;
        return map;
    }

    public Task<HelloInfo> HelloAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<HelloInfo>("rpc.hello", null, ct);

    public Task<SetupStatus> GetSetupStatusAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<SetupStatus>("setup.status", null, ct);

    public Task<WhoAmI> CreateAdminAsync(string name, string password, CancellationToken ct = default)
        => _rpc.InvokeAsync<WhoAmI>("setup.create_admin", P(("name", name), ("password", password)), ct);

    public Task<SystemPaths> GetSystemPathsAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<SystemPaths>("system.paths", null, ct);

    public Task<WhoAmI> LoginAsync(string name, string password, CancellationToken ct = default)
        => _rpc.InvokeAsync<WhoAmI>("auth.login", P(("name", name), ("password", password)), ct);

    public async Task LogoutAsync(CancellationToken ct = default)
        => await _rpc.InvokeAsync<OkResult>("auth.logout", null, ct).ConfigureAwait(false);

    public async Task ChangePasswordAsync(string oldPassword, string newPassword, CancellationToken ct = default)
        => await _rpc.InvokeAsync<ChangedResult>("auth.change_password",
            P(("old_password", oldPassword), ("new_password", newPassword)), ct).ConfigureAwait(false);

    public Task<StatusDto> GetStatusAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<StatusDto>("status.get", null, ct);

    public Task<SecurityOverview> GetSecurityOverviewAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<SecurityOverview>("security.overview", null, ct);

    public Task<List<DeviceDto>> ListDevicesAsync(string? connection = null, CancellationToken ct = default)
        => _rpc.InvokeAsync<List<DeviceDto>>("devices.list", P(("connection", connection)), ct);

    public Task<ScanResult> ScanDevicesAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<ScanResult>("devices.scan", null, ct);

    public Task<DeviceIdentification> IdentifyDeviceAsync(string text, CancellationToken ct = default)
        => _rpc.InvokeAsync<DeviceIdentification>("devices.identify", P(("text", text)), ct);

    public async Task<long> AddDeviceAsync(string kind, string? vendor, string? model, string? serial,
        string? label, CancellationToken ct = default)
    {
        var result = await _rpc.InvokeAsync<IdResult>("devices.add",
            P(("kind", kind), ("vendor", vendor), ("model", model), ("serial", serial), ("label", label)), ct)
            .ConfigureAwait(false);
        return result.Id;
    }

    public Task<List<SessionDto>> RecentSessionsAsync(int limit = 10, CancellationToken ct = default)
        => _rpc.InvokeAsync<List<SessionDto>>("sessions.recent", P(("limit", limit)), ct);

    public Task<List<SessionDto>> OpenSessionsAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<List<SessionDto>>("sessions.open", null, ct);

    public async Task<long> StartSessionAsync(long deviceId, string kind, CancellationToken ct = default)
    {
        var result = await _rpc.InvokeAsync<IdResult>("sessions.start",
            P(("device_id", deviceId), ("kind", kind)), ct).ConfigureAwait(false);
        return result.Id;
    }

    public async Task FinishSessionAsync(long id, string status, string? summary, CancellationToken ct = default)
        => await _rpc.InvokeAsync<OkResult>("sessions.finish",
            P(("id", id), ("status", status), ("summary", summary)), ct).ConfigureAwait(false);

    public Task<List<OperationDto>> ListAuditAsync(int limit = 50, long? sessionId = null, CancellationToken ct = default)
        => _rpc.InvokeAsync<List<OperationDto>>("audit.list", P(("limit", limit), ("session_id", sessionId)), ct);

    public Task<AuditVerify> VerifyAuditAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<AuditVerify>("audit.verify", null, ct);

    public Task<List<ModuleStatusDto>> ListModulesAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<List<ModuleStatusDto>>("modules.list", null, ct);

    public Task<List<MaintenanceCategoryDto>> ListMaintenanceAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<List<MaintenanceCategoryDto>>("maintenance.list", null, ct);

    public Task<ModuleVerify> VerifyModuleAsync(string id, CancellationToken ct = default)
        => _rpc.InvokeAsync<ModuleVerify>("modules.verify", P(("id", id)), ct);

    public async Task RegisterModuleAsync(string id, bool confirmed, CancellationToken ct = default)
        => await _rpc.InvokeAsync<OkResult>("modules.register", P(("id", id), ("confirmed", confirmed)), ct)
            .ConfigureAwait(false);

    public async Task EnableModuleAsync(string id, CancellationToken ct = default)
        => await _rpc.InvokeAsync<OkResult>("modules.enable", P(("id", id)), ct).ConfigureAwait(false);

    public async Task DisableModuleAsync(string id, CancellationToken ct = default)
        => await _rpc.InvokeAsync<OkResult>("modules.disable", P(("id", id)), ct).ConfigureAwait(false);

    public Task<List<BackupDto>> ListBackupsAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<List<BackupDto>>("backups.list", null, ct);

    public async Task<string> CreateBackupAsync(string reason = "manual", CancellationToken ct = default)
    {
        var result = await _rpc.InvokeAsync<NameResult>("backups.create", P(("reason", reason)), ct)
            .ConfigureAwait(false);
        return result.Name;
    }

    public async Task VerifyBackupAsync(string name, CancellationToken ct = default)
        => await _rpc.InvokeAsync<OkResult>("backups.verify", P(("name", name)), ct).ConfigureAwait(false);

    public Task<RestoreResult> RestoreBackupAsync(string name, bool confirmed, CancellationToken ct = default)
        => _rpc.InvokeAsync<RestoreResult>("backups.restore", P(("name", name), ("confirmed", confirmed)), ct);

    public Task<Dictionary<string, JsonElement>> GetSettingsAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<Dictionary<string, JsonElement>>("settings.get_all", null, ct);

    public async Task SetSettingAsync(string key, object value, CancellationToken ct = default)
        => await _rpc.InvokeAsync<OkResult>("settings.set", P(("key", key), ("value", value)), ct)
            .ConfigureAwait(false);

    public Task<List<TechnicianDto>> ListTechniciansAsync(CancellationToken ct = default)
        => _rpc.InvokeAsync<List<TechnicianDto>>("technicians.list", null, ct);

    public async Task<long> AddTechnicianAsync(string name, string role, string password, CancellationToken ct = default)
    {
        var result = await _rpc.InvokeAsync<IdResult>("technicians.add",
            P(("name", name), ("role", role), ("password", password)), ct).ConfigureAwait(false);
        return result.Id;
    }

    public async Task SetTechnicianActiveAsync(string name, bool active, CancellationToken ct = default)
        => await _rpc.InvokeAsync<OkResult>("technicians.set_active", P(("name", name), ("active", active)), ct)
            .ConfigureAwait(false);
}
