using Nexus.CoreClient;

namespace Nexus.Tests;

/// <summary>Os DTOs da interface precisam bater com o que o núcleo realmente devolve.</summary>
public class ContractTests
{
    [Fact]
    public void Hello_matches_core_output()
    {
        var hello = Fixture.Result<HelloInfo>("hello");
        Assert.Equal("1.0", hello.Protocol);
        Assert.False(hello.Authenticated);
        Assert.Contains("status.get", hello.Methods);
        Assert.Contains("backups.restore", hello.Methods);
    }

    [Fact]
    public void Login_matches_core_output()
    {
        var who = Fixture.Result<WhoAmI>("login");
        Assert.Equal("tecnico.demo", who.Actor);
        Assert.Equal("admin", who.Role);
        Assert.True(who.Authenticated);
        Assert.Contains("devices.manage", who.Permissions);
    }

    [Fact]
    public void Status_matches_core_output()
    {
        var status = Fixture.Result<StatusDto>("status");
        Assert.Equal(status.SchemaVersion, status.ExpectedSchemaVersion);
        Assert.Equal("local", status.Mode);
        Assert.Equal("not_configured", status.Sync.State);
        Assert.True(status.Audit.Ok);

        var device = Assert.Single(status.DevicesConnected);
        Assert.Equal("connected", device.Connection);
        Assert.Equal("Demo Phone", device.Model);
        Assert.Null(device.Label);
        Assert.Equal("480", device.Properties["speed_mbps"].GetString());

        Assert.Equal(2, status.RecentSessions.Count);
        Assert.Contains(status.RecentSessions, s => s.Status == "open" && s.EndedAt is null);
        Assert.Equal(1, status.Backups.Count);
        Assert.NotNull(status.Backups.Latest);
        Assert.NotEmpty(status.RecentOperations);
        Assert.All(status.RecentOperations, o => Assert.Equal(64, o.Hash.Length));
        Assert.Contains(status.Modules, m => m.Id == "nexus.demo" && m.Status == "available" && m.IntegrityOk == true);
        Assert.Equal(5, status.Modules.Count(m => m.Status == "planned" && m.IntegrityOk is null));
    }

    [Fact]
    public void Security_overview_matches_core_output()
    {
        var overview = Fixture.Result<SecurityOverview>("security_overview");
        Assert.Equal("admin", overview.Role);
        Assert.True(overview.Audit.Ok);
        Assert.Null(overview.Audit.FirstBadId);
        Assert.True(overview.DatabaseIntegrity);
        Assert.Equal(2, overview.Technicians.Total);
        Assert.Equal(0, overview.Technicians.WithoutPassword);
        Assert.Contains("LMF Informática", overview.TrustedPublishers);
    }

    [Fact]
    public void Lists_match_core_output()
    {
        var devices = Fixture.Result<List<DeviceDto>>("devices_list");
        Assert.Equal(2, devices.Count);
        Assert.Contains(devices, d => d.Source == "manual" && d.Connection == "unknown" && d.Label == "Cliente Demo A");

        var sessions = Fixture.Result<List<SessionDto>>("sessions_recent");
        Assert.Contains(sessions, s => s.Kind == "pc_diagnostics" && s.Status == "completed" && s.Summary == "Sessão de demonstração");
        Assert.All(Fixture.Result<List<SessionDto>>("sessions_open"), s => Assert.Equal("open", s.Status));

        var audit = Fixture.Result<List<OperationDto>>("audit_list");
        Assert.Equal(5, audit.Count);
        Assert.True(audit[0].Id > audit[1].Id);

        var technicians = Fixture.Result<List<TechnicianDto>>("technicians_list");
        Assert.Equal(2, technicians.Count);
        Assert.All(technicians, t => Assert.True(t.HasPassword));
    }

    [Fact]
    public void Modules_and_backups_match_core_output()
    {
        var modules = Fixture.Result<List<ModuleStatusDto>>("modules_list");
        var demo = Assert.Single(modules, m => m.Id == "nexus.demo");
        Assert.True(demo.Registered);
        Assert.True(demo.Enabled);
        Assert.Equal(true, demo.IntegrityOk);
        Assert.Empty(demo.Problems);

        var verify = Fixture.Result<ModuleVerify>("module_verify");
        Assert.True(verify.Ok);

        var backups = Fixture.Result<List<BackupDto>>("backups_list");
        var backup = Assert.Single(backups);
        Assert.StartsWith("nexus-", backup.Name);
        Assert.True(backup.HasChecksum);
        Assert.True(backup.SizeBytes > 0);
    }

    [Fact]
    public void Operations_results_match_core_output()
    {
        var scan = Fixture.Result<ScanResult>("scan_result");
        Assert.Equal(1, scan.Found);
        Assert.Empty(scan.Errors);

        var restore = Fixture.Result<RestoreResult>("restore_result");
        Assert.True(restore.SessionActive);
        Assert.EndsWith(".db", restore.SafetyBackup);

        var audit = Fixture.Result<AuditVerify>("audit_verify");
        Assert.True(audit.Ok);

        var settings = Fixture.Result<Dictionary<string, System.Text.Json.JsonElement>>("settings_all");
        Assert.Equal("dark", settings["ui.theme"].GetString());
        Assert.Equal(10, settings["backup.keep"].GetInt32());
    }

    [Theory]
    [InlineData("error_not_authenticated", RpcCodes.NotAuthenticated, "AuthenticationError")]
    [InlineData("error_permission", RpcCodes.PermissionDenied, "PermissionDenied")]
    [InlineData("error_confirmation", RpcCodes.ConfirmationRequired, "ConfirmationRequired")]
    [InlineData("error_validation", RpcCodes.ValidationError, "ValidationError")]
    [InlineData("error_invalid_params", -32602, "InvalidParams")]
    public void Errors_match_core_output(string fixture, int code, string type)
    {
        var error = Fixture.Error(fixture);
        Assert.Equal(code, error.Code);
        Assert.Equal(type, error.Type);
        Assert.False(string.IsNullOrWhiteSpace(error.Message));
    }
}
