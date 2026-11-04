using System.Text.Json;
using Nexus.CoreClient;
using Nexus.Presentation;

namespace Nexus.Tests;

/// <summary>ICoreApi em memória. Os dados padrão são as respostas REAIS do núcleo (Fixtures).</summary>
public sealed class FakeCoreApi : ICoreApi
{
    public event EventHandler? Disconnected;

    public StatusDto Status = Fixture.Result<StatusDto>("status");
    public SecurityOverview Security = Fixture.Result<SecurityOverview>("security_overview");
    public List<DeviceDto> Devices = Fixture.Result<List<DeviceDto>>("devices_list");
    public List<SessionDto> Sessions = Fixture.Result<List<SessionDto>>("sessions_recent");
    public List<OperationDto> Audit = Fixture.Result<List<OperationDto>>("audit_list");
    public AuditVerify AuditResult = Fixture.Result<AuditVerify>("audit_verify");
    public List<ModuleStatusDto> Modules = Fixture.Result<List<ModuleStatusDto>>("modules_list");
    public ModuleVerify ModuleVerifyResult = Fixture.Result<ModuleVerify>("module_verify");
    public List<BackupDto> Backups = Fixture.Result<List<BackupDto>>("backups_list");
    public RestoreResult RestoreResultValue = Fixture.Result<RestoreResult>("restore_result");
    public ScanResult Scan = Fixture.Result<ScanResult>("scan_result");
    public Dictionary<string, JsonElement> Settings = Fixture.Result<Dictionary<string, JsonElement>>("settings_all");
    public List<TechnicianDto> Technicians = Fixture.Result<List<TechnicianDto>>("technicians_list");
    public HelloInfo HelloValue = Fixture.Result<HelloInfo>("hello");
    public SetupStatus SetupStatusValue = Fixture.Result<SetupStatus>("setup_status");
    public SystemPaths PathsValue = Fixture.Result<SystemPaths>("system_paths");
    public WhoAmI LoginResult = Fixture.Result<WhoAmI>("login");

    /// <summary>Quando definida, TODA chamada lança esta exceção.</summary>
    public Exception? FailWith;

    /// <summary>Quando definida, GetStatusAsync aguarda esta tarefa (simula chamada lenta).</summary>
    public Task? StatusGate;

    public List<string> Calls = new();
    public List<object?[]> Args = new();

    public int CallCount(string name) => Calls.Count(c => c == name);

    public void RaiseDisconnected() => Disconnected?.Invoke(this, EventArgs.Empty);

    private void Record(string name, params object?[] args)
    {
        Calls.Add(name);
        Args.Add(args);
        if (FailWith is not null) throw FailWith;
    }

    public Task<HelloInfo> HelloAsync(CancellationToken ct = default) { Record("hello"); return Task.FromResult(HelloValue); }

    public Task<SetupStatus> GetSetupStatusAsync(CancellationToken ct = default)
    {
        Record("setup.status");
        return Task.FromResult(SetupStatusValue);
    }

    public Task<WhoAmI> CreateAdminAsync(string name, string password, CancellationToken ct = default)
    {
        Record("setup.create_admin", name);
        return Task.FromResult(LoginResult);
    }

    public Task<SystemPaths> GetSystemPathsAsync(CancellationToken ct = default)
    {
        Record("system.paths");
        return Task.FromResult(PathsValue);
    }

    public Task<WhoAmI> LoginAsync(string name, string password, CancellationToken ct = default)
    {
        Record("login", name);
        return Task.FromResult(LoginResult);
    }

    public Task LogoutAsync(CancellationToken ct = default) { Record("logout"); return Task.CompletedTask; }

    public Task ChangePasswordAsync(string oldPassword, string newPassword, CancellationToken ct = default)
    {
        Record("change_password");
        return Task.CompletedTask;
    }

    public async Task<StatusDto> GetStatusAsync(CancellationToken ct = default)
    {
        Record("status");
        if (StatusGate is not null) await StatusGate;
        return Status;
    }

    public Task<SecurityOverview> GetSecurityOverviewAsync(CancellationToken ct = default)
    {
        Record("security");
        return Task.FromResult(Security);
    }

    public Task<List<DeviceDto>> ListDevicesAsync(string? connection = null, CancellationToken ct = default)
    {
        Record("devices.list");
        return Task.FromResult(Devices);
    }

    public Task<ScanResult> ScanDevicesAsync(CancellationToken ct = default) { Record("devices.scan"); return Task.FromResult(Scan); }

    public Task<long> AddDeviceAsync(string kind, string? vendor, string? model, string? serial, string? label,
        CancellationToken ct = default)
    {
        Record("devices.add", kind, vendor, model, serial, label);
        return Task.FromResult(99L);
    }

    public Task<List<SessionDto>> RecentSessionsAsync(int limit = 10, CancellationToken ct = default)
    {
        Record("sessions.recent");
        return Task.FromResult(Sessions);
    }

    public Task<List<SessionDto>> OpenSessionsAsync(CancellationToken ct = default)
    {
        Record("sessions.open");
        return Task.FromResult(Sessions.Where(s => s.Status == "open").ToList());
    }

    public Task<long> StartSessionAsync(long deviceId, string kind, CancellationToken ct = default)
    {
        Record("sessions.start", deviceId, kind);
        return Task.FromResult(42L);
    }

    public Task FinishSessionAsync(long id, string status, string? summary, CancellationToken ct = default)
    {
        Record("sessions.finish", id, status, summary);
        return Task.CompletedTask;
    }

    public Task<List<OperationDto>> ListAuditAsync(int limit = 50, long? sessionId = null, CancellationToken ct = default)
    {
        Record("audit.list", limit);
        return Task.FromResult(Audit);
    }

    public Task<AuditVerify> VerifyAuditAsync(CancellationToken ct = default) { Record("audit.verify"); return Task.FromResult(AuditResult); }

    public Task<List<ModuleStatusDto>> ListModulesAsync(CancellationToken ct = default)
    {
        Record("modules.list");
        return Task.FromResult(Modules);
    }

    public Task<ModuleVerify> VerifyModuleAsync(string id, CancellationToken ct = default)
    {
        Record("modules.verify", id);
        return Task.FromResult(ModuleVerifyResult);
    }

    public Task RegisterModuleAsync(string id, bool confirmed, CancellationToken ct = default)
    {
        Record("modules.register", id, confirmed);
        return Task.CompletedTask;
    }

    public Task EnableModuleAsync(string id, CancellationToken ct = default) { Record("modules.enable", id); return Task.CompletedTask; }
    public Task DisableModuleAsync(string id, CancellationToken ct = default) { Record("modules.disable", id); return Task.CompletedTask; }

    public Task<List<BackupDto>> ListBackupsAsync(CancellationToken ct = default)
    {
        Record("backups.list");
        return Task.FromResult(Backups);
    }

    public Task<string> CreateBackupAsync(string reason = "manual", CancellationToken ct = default)
    {
        Record("backups.create");
        return Task.FromResult("nexus-20261104-000000-manual.db");
    }

    public Task VerifyBackupAsync(string name, CancellationToken ct = default) { Record("backups.verify", name); return Task.CompletedTask; }

    public Task<RestoreResult> RestoreBackupAsync(string name, bool confirmed, CancellationToken ct = default)
    {
        Record("backups.restore", name, confirmed);
        return Task.FromResult(RestoreResultValue);
    }

    public Task<Dictionary<string, JsonElement>> GetSettingsAsync(CancellationToken ct = default)
    {
        Record("settings.get");
        return Task.FromResult(Settings);
    }

    public Task SetSettingAsync(string key, object value, CancellationToken ct = default)
    {
        Record("settings.set", key, value);
        return Task.CompletedTask;
    }

    public Task<List<TechnicianDto>> ListTechniciansAsync(CancellationToken ct = default)
    {
        Record("technicians.list");
        return Task.FromResult(Technicians);
    }

    public Task<long> AddTechnicianAsync(string name, string role, string password, CancellationToken ct = default)
    {
        Record("technicians.add", name, role);
        return Task.FromResult(7L);
    }

    public Task SetTechnicianActiveAsync(string name, bool active, CancellationToken ct = default)
    {
        Record("technicians.set_active", name, active);
        return Task.CompletedTask;
    }
}

public sealed class FakeDialogs : IDialogService
{
    public bool Answer = true;
    public int ConfirmCalls;
    public string? LastRequiredText;
    public string? LastMessage;

    public Task<bool> ConfirmAsync(string title, string message, string confirmText, string? requiredText = null)
    {
        ConfirmCalls++;
        LastRequiredText = requiredText;
        LastMessage = message;
        return Task.FromResult(Answer);
    }

    public void ShowInfo(string title, string message) { }
}

public sealed class FakeRuntime : IRuntimeInfo
{
    public string AppVersion => "0.1.0";
    public string PythonPath => @"C:\Python312\python.exe";
    public string PythonVersion => "3.12.10";
    public string CorePath => @"C:\NEXUS\core";
    public string? ChooseResult = "Python alterado.";
    public int ChooseCalls;

    public Task<string?> ChoosePythonAsync()
    {
        ChooseCalls++;
        return Task.FromResult(ChooseResult);
    }
}

public sealed class FakeTheme : IThemeService
{
    public string Current { get; private set; } = "dark";
    public void Apply(string theme) => Current = theme;
}

public static class Make
{
    public static SessionContext Admin()
    {
        var session = new SessionContext();
        session.Set(Fixture.Result<WhoAmI>("login"));
        return session;
    }

    public static SessionContext Viewer()
    {
        var session = new SessionContext();
        session.Set(new WhoAmI("leitor.demo", "viewer", new List<string> { "devices.read", "audit.read" }, true));
        return session;
    }
}
