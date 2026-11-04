using System.Text.Json;

namespace Nexus.CoreClient;

/// <summary>Contrato tipado do núcleo. Cada método corresponde a um método de docs/PROTOCOL.md.</summary>
public interface ICoreApi
{
    /// <summary>Disparado quando o processo do núcleo encerra ou a conexão cai.</summary>
    event EventHandler? Disconnected;

    Task<HelloInfo> HelloAsync(CancellationToken ct = default);
    Task<SetupStatus> GetSetupStatusAsync(CancellationToken ct = default);
    /// <summary>Cria o PRIMEIRO administrador (o núcleo recusa se já existir algum técnico) e entra com ele.</summary>
    Task<WhoAmI> CreateAdminAsync(string name, string password, CancellationToken ct = default);
    Task<SystemPaths> GetSystemPathsAsync(CancellationToken ct = default);
    Task<WhoAmI> LoginAsync(string name, string password, CancellationToken ct = default);
    Task LogoutAsync(CancellationToken ct = default);
    Task ChangePasswordAsync(string oldPassword, string newPassword, CancellationToken ct = default);

    Task<StatusDto> GetStatusAsync(CancellationToken ct = default);
    Task<SecurityOverview> GetSecurityOverviewAsync(CancellationToken ct = default);

    Task<List<DeviceDto>> ListDevicesAsync(string? connection = null, CancellationToken ct = default);
    Task<ScanResult> ScanDevicesAsync(CancellationToken ct = default);
    Task<long> AddDeviceAsync(string kind, string? vendor, string? model, string? serial, string? label,
        CancellationToken ct = default);

    Task<List<SessionDto>> RecentSessionsAsync(int limit = 10, CancellationToken ct = default);
    Task<List<SessionDto>> OpenSessionsAsync(CancellationToken ct = default);
    Task<long> StartSessionAsync(long deviceId, string kind, CancellationToken ct = default);
    Task FinishSessionAsync(long id, string status, string? summary, CancellationToken ct = default);

    Task<List<OperationDto>> ListAuditAsync(int limit = 50, long? sessionId = null, CancellationToken ct = default);
    Task<AuditVerify> VerifyAuditAsync(CancellationToken ct = default);

    Task<List<ModuleStatusDto>> ListModulesAsync(CancellationToken ct = default);
    Task<ModuleVerify> VerifyModuleAsync(string id, CancellationToken ct = default);
    Task RegisterModuleAsync(string id, bool confirmed, CancellationToken ct = default);
    Task EnableModuleAsync(string id, CancellationToken ct = default);
    Task DisableModuleAsync(string id, CancellationToken ct = default);

    Task<List<BackupDto>> ListBackupsAsync(CancellationToken ct = default);
    Task<string> CreateBackupAsync(string reason = "manual", CancellationToken ct = default);
    Task VerifyBackupAsync(string name, CancellationToken ct = default);
    Task<RestoreResult> RestoreBackupAsync(string name, bool confirmed, CancellationToken ct = default);

    Task<Dictionary<string, JsonElement>> GetSettingsAsync(CancellationToken ct = default);
    Task SetSettingAsync(string key, object value, CancellationToken ct = default);

    Task<List<TechnicianDto>> ListTechniciansAsync(CancellationToken ct = default);
    Task<long> AddTechnicianAsync(string name, string role, string password, CancellationToken ct = default);
    Task SetTechnicianActiveAsync(string name, bool active, CancellationToken ct = default);
}
