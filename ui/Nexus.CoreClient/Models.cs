using System.Text.Json;

namespace Nexus.CoreClient;

// DTOs espelham exatamente o JSON do núcleo (snake_case). Ver docs/PROTOCOL.md.

public sealed record HelloInfo(string Protocol, string CoreVersion, int SchemaVersion, List<string> Methods,
    string Actor, string Role, List<string> Permissions, bool Authenticated);

public sealed record SetupStatus(bool Initialized);
public sealed record SystemPaths(string Home, string Database, string Logs, string Backups, string Modules);

public sealed record WhoAmI(string Actor, string Role, List<string> Permissions, bool Authenticated);

public sealed record OkResult(bool Ok);
public sealed record ChangedResult(string Changed);
public sealed record IdResult(long Id);
public sealed record NameResult(string Name);

public sealed record DeviceDto(long Id, string Uid, string Kind, string Source, string? Vendor, string? Model,
    string? Serial, string? Label, string Connection, string FirstSeen, string LastSeen,
    Dictionary<string, JsonElement> Properties);

public sealed record SessionDto(long Id, long DeviceId, string Kind, string Technician, string Status,
    string StartedAt, string? EndedAt, string? Summary, string? DeviceLabel, string? DeviceModel);

public sealed record OperationDto(long Id, string Ts, string Technician, string Action, string? Target,
    long? SessionId, string Details, string Outcome, string PrevHash, string Hash);

public sealed record ModuleStatusDto(string Id, string Name, string Version, string Publisher, string Status,
    bool Registered, bool Enabled, bool Loaded, bool? IntegrityOk, List<string> Problems);

public sealed record BackupDto(string Name, long SizeBytes, string ModifiedUtc, bool HasChecksum);

public sealed record BackupSummary(int Count, string? Latest, string? LatestUtc);
public sealed record AlertDto(string Level, string Message);
public sealed record AuditSummary(bool Ok, int Records);
public sealed record SyncState(string State, string Detail);

public sealed record StatusDto(string Version, int SchemaVersion, int ExpectedSchemaVersion, string Mode,
    string Actor, string Role, List<DeviceDto> DevicesConnected, List<SessionDto> RecentSessions,
    List<OperationDto> RecentOperations, List<ModuleStatusDto> Modules, BackupSummary Backups,
    SyncState Sync, AuditSummary Audit, List<AlertDto> Alerts);

public sealed record AuditVerify(bool Ok, int Records, long? FirstBadId);
public sealed record TechnicianSummary(int Total, int Active, int WithoutPassword, int Locked);
public sealed record SecurityModule(string Id, string Status, bool? IntegrityOk, List<string> Problems);

public sealed record SecurityOverview(string Actor, string Role, List<string> Permissions, AuditVerify Audit,
    bool DatabaseIntegrity, TechnicianSummary Technicians, List<string> TrustedPublishers,
    List<SecurityModule> Modules);

public sealed record TechnicianDto(long Id, string Name, string Role, bool Active, string CreatedAt,
    int FailedAttempts, string? LockedUntil, bool HasPassword);

public sealed record ScanResult(int Found, Dictionary<string, string> Errors);
public sealed record RestoreResult(string SafetyBackup, bool SessionActive);
public sealed record ModuleVerify(bool Ok, List<string> Problems);
