using System.Diagnostics;
using System.Text;
using Nexus.CoreClient;

namespace Nexus.Tests;

/// <summary>
/// Teste de ponta a ponta REAL: inicia o núcleo Python como processo filho (como o aplicativo faz) numa pasta
/// temporária e conversa com ele pelo CoreApi. Se Python/núcleo não estiverem disponíveis, o teste é ignorado
/// (passa sem executar) — a menos que NEXUS_REQUIRE_E2E=1 (usado no CI), quando a ausência vira falha.
/// </summary>
public class EndToEndTests
{
    private const string Admin = "ci.admin";
    private const string Password = "senha-ficticia-123"; // nexus:allow-secret (valor fictício de teste)

    private static bool Required => Environment.GetEnvironmentVariable("NEXUS_REQUIRE_E2E") == "1";

    private static CoreLaunchOptions? TryOptions()
    {
        try
        {
            var options = CoreLaunchOptions.FromEnvironment();
            return options;
        }
        catch (CoreException) when (!Required)
        {
            return null;
        }
    }

    private static void InitAdmin(CoreLaunchOptions options, string home)
    {
        var info = new ProcessStartInfo
        {
            FileName = options.PythonPath,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var arg in new[] { "-m", "nexus", "--home", home, "--password-stdin", "init", "--admin", Admin })
        {
            info.ArgumentList.Add(arg);
        }
        info.Environment["PYTHONPATH"] = options.CorePath;
        info.Environment["PYTHONUTF8"] = "1";

        using var process = Process.Start(info)!;
        process.StandardInput.Write(Password + "\n");
        process.StandardInput.Close();
        var stderr = process.StandardError.ReadToEnd();
        process.StandardOutput.ReadToEnd();
        Assert.True(process.WaitForExit(60_000), "init não terminou");
        Assert.True(process.ExitCode == 0, "init falhou: " + stderr);
    }

    [Fact]
    public async Task Real_core_full_session()
    {
        var options = TryOptions();
        if (options is null) return;

        var home = Path.Combine(Path.GetTempPath(), "nexus-e2e-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(home);
        try
        {
            InitAdmin(options, home);

            await using var transport = ProcessTransport.Start(options with { HomePath = home });
            await using var connection = new JsonRpcConnection(transport, TimeSpan.FromSeconds(60));
            connection.Start();
            var api = new CoreApi(connection);

            var hello = await api.HelloAsync();
            Assert.Equal("1.0", hello.Protocol);
            Assert.False(hello.Authenticated);

            var denied = await Assert.ThrowsAsync<RpcException>(() => api.GetStatusAsync());
            Assert.Equal(RpcCodes.NotAuthenticated, denied.Code);

            var wrong = await Assert.ThrowsAsync<RpcException>(() => api.LoginAsync(Admin, "senha-errada-123"));
            Assert.Equal(RpcCodes.NotAuthenticated, wrong.Code);

            var who = await api.LoginAsync(Admin, Password);
            Assert.True(who.Authenticated);
            Assert.Equal("admin", who.Role);

            var status = await api.GetStatusAsync();
            Assert.True(status.Audit.Ok);
            Assert.Contains(status.Modules, m => m.Status == "planned"); // módulos ainda não implementados aparecem como tal

            Assert.True((await api.GetSecurityOverviewAsync()).DatabaseIntegrity);
            Assert.NotNull(await api.ListDevicesAsync());

            var backup = await api.CreateBackupAsync("e2e");
            await api.VerifyBackupAsync(backup);
            Assert.Contains(await api.ListBackupsAsync(), b => b.Name == backup);

            var denyRestore = await Assert.ThrowsAsync<RpcException>(() => api.RestoreBackupAsync(backup, false));
            Assert.Equal(RpcCodes.ConfirmationRequired, denyRestore.Code);

            await api.LogoutAsync();
            var afterLogout = await Assert.ThrowsAsync<RpcException>(() => api.GetStatusAsync());
            Assert.Equal(RpcCodes.NotAuthenticated, afterLogout.Code);
        }
        finally
        {
            try { Directory.Delete(home, recursive: true); } catch (IOException) { }
        }
    }

    [Fact]
    public async Task Missing_python_is_reported_as_unavailable_not_as_a_crash()
    {
        var options = new CoreLaunchOptions("python-que-nao-existe-xyz", Path.GetTempPath(), null);
        var ex = Assert.Throws<CoreUnavailableException>(() => ProcessTransport.Start(options));
        Assert.Contains("Python", ex.Message);
        await Task.CompletedTask;
    }
}
