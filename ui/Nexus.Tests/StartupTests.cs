using Nexus.CoreClient;
using Nexus.Presentation;

namespace Nexus.Tests;

public class FakeProbe : IPythonProbe
{
    private readonly Dictionary<string, PythonProbeResult> _results = new(StringComparer.OrdinalIgnoreCase);
    public List<string> Probed = new();

    public FakeProbe Add(string path, string? version, string? problem = null)
    {
        _results[path] = version is null
            ? new PythonProbeResult(false, null, problem ?? "falhou")
            : new PythonProbeResult(true, Version.Parse(version), null);
        return this;
    }

    public Task<PythonProbeResult> ProbeAsync(string path, CancellationToken ct)
    {
        Probed.Add(path);
        return Task.FromResult(_results.TryGetValue(path, out var r) ? r : new PythonProbeResult(false, null, "não encontrado"));
    }
}

public class PythonLocatorTests
{
    private static PythonCandidate C(string path, string source = "teste", bool explicitChoice = false) => new(path, source, explicitChoice);

    [Fact]
    public async Task First_valid_candidate_in_priority_order_wins_even_if_an_older_one_comes_first_on_PATH()
    {
        var probe = new FakeProbe().Add("a", "3.11.9").Add("b", "3.12.10").Add("c", "3.13.1");
        var result = await new PythonLocator(probe).ResolveAsync(new[] { C("a"), C("b"), C("c") });

        Assert.True(result.Found);
        Assert.Equal("b", result.Selected!.Path);
        Assert.Equal(new Version(3, 12, 10), result.Version);
        Assert.Single(result.Rejected);
        Assert.Contains("3.11.9", result.Rejected[0]);
        Assert.DoesNotContain("c", probe.Probed); // nem executa os que vêm depois do escolhido
    }

    [Fact]
    public async Task Python_older_than_3_12_is_never_accepted()
    {
        var probe = new FakeProbe().Add("old", "3.11.9").Add("older", "3.8.10");
        var result = await new PythonLocator(probe).ResolveAsync(new[] { C("old"), C("older") });

        Assert.False(result.Found);
        Assert.False(result.ExplicitFailure);
        Assert.Equal(2, result.Rejected.Count);
    }

    [Fact]
    public async Task Broken_candidates_are_skipped_with_their_reason()
    {
        var probe = new FakeProbe().Add("broken", null, "ModuleNotFoundError: sqlite3").Add("ok", "3.12.0");
        var result = await new PythonLocator(probe).ResolveAsync(new[] { C("broken"), C("ok") });

        Assert.Equal("ok", result.Selected!.Path);
        Assert.Contains("sqlite3", result.Rejected.Single());
    }

    [Fact]
    public async Task Explicit_choice_that_is_invalid_stops_without_falling_back()
    {
        var probe = new FakeProbe().Add("mine", "3.10.0").Add("path-python", "3.12.5");
        var result = await new PythonLocator(probe).ResolveAsync(
            new[] { C("mine", "variável NEXUS_PYTHON", true), C("path-python", "PATH") });

        Assert.False(result.Found);
        Assert.True(result.ExplicitFailure);
        Assert.DoesNotContain("path-python", probe.Probed);
    }

    [Fact]
    public async Task Explicit_choice_that_is_valid_wins_over_everything()
    {
        var probe = new FakeProbe().Add("mine", "3.12.1").Add("other", "3.13.0");
        var result = await new PythonLocator(probe).ResolveAsync(new[] { C("mine", "config", true), C("other") });
        Assert.Equal("mine", result.Selected!.Path);
    }

    [Fact]
    public async Task Duplicates_and_blank_paths_are_probed_once()
    {
        var probe = new FakeProbe().Add(@"C:\Py\python.exe", "3.11.0");
        var result = await new PythonLocator(probe).ResolveAsync(
            new[] { C(@"C:\Py\python.exe"), C(@"c:\py\PYTHON.EXE"), C("  ") });
        Assert.False(result.Found);
        Assert.Single(probe.Probed);
    }

    [Fact]
    public async Task Failure_message_tells_how_to_fix_and_lists_what_was_checked()
    {
        var probe = new FakeProbe().Add("x", "3.9.0");
        var result = await new PythonLocator(probe).ResolveAsync(new[] { C("x", "PATH") });
        var message = CoreStartup.DescribeFailure(result);

        Assert.Contains("3.12", message);
        Assert.Contains("winget install Python.Python.3.12", message);
        Assert.Contains("PATH: x", message);

        var explicitMessage = CoreStartup.DescribeFailure(new PythonResolution(null, null, new[] { "a" }, true));
        Assert.Contains("indicado", explicitMessage);
    }

    [Theory]
    [InlineData(@"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe", true)]
    [InlineData(@"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python3.exe", true)]
    [InlineData(@"C:\Users\x\AppData\Local\Programs\Python\Python312\python.exe", false)]
    [InlineData(@"C:\Users\x\AppData\Local\Microsoft\WindowsApps\PythonSoftwareFoundation.Python.3.12_abc\python.exe", false)]
    public void Microsoft_Store_alias_is_recognised_but_real_store_installs_are_not(string path, bool isAlias)
        => Assert.Equal(isAlias, ProcessPythonProbe.IsStoreAlias(path));

    [Fact]
    public async Task Real_probe_rejects_missing_file_and_accepts_nothing_without_running_it()
    {
        var result = await new ProcessPythonProbe().ProbeAsync(Path.Combine(Path.GetTempPath(), "nao-existe", "python.exe"), default);
        Assert.False(result.Ok);
        Assert.Contains("não encontrado", result.Problem);
    }
}

public class VersionAndSettingsTests
{
    [Theory]
    [InlineData("0.1.0", "0.1.0", true)]
    [InlineData("0.1.5", "0.1.0", true)]
    [InlineData("0.1.0", "0.1.0+abcdef", true)]
    [InlineData("0.1.0", "0.2.0", false)]
    [InlineData("1.0.0", "0.1.0", false)]
    [InlineData("lixo", "0.1.0", false)]
    [InlineData(null, "0.1.0", false)]
    public void Core_and_interface_must_share_major_and_minor(string? core, string app, bool expected)
        => Assert.Equal(expected, VersionCompat.IsCompatible(core, app));

    private static string TempDir() => Path.Combine(Path.GetTempPath(), "nexus-ui-" + Guid.NewGuid().ToString("N"));

    [Fact]
    public void Settings_roundtrip_and_missing_file_gives_defaults()
    {
        var dir = TempDir();
        try
        {
            var store = new UiSettingsStore(dir);
            Assert.Null(store.Load().PythonPath);

            Assert.True(store.Save(new UiSettings { PythonPath = @"C:\Py\python.exe", Theme = "light", WindowWidth = 1000, WindowHeight = 700, WindowMaximized = true }));
            var loaded = new UiSettingsStore(dir).Load();
            Assert.Equal(@"C:\Py\python.exe", loaded.PythonPath);
            Assert.Equal("light", loaded.Theme);
            Assert.Equal(1000, loaded.WindowWidth);
            Assert.True(loaded.WindowMaximized);
            Assert.False(File.Exists(store.FilePath + ".tmp")); // gravação atômica não deixa lixo
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public void Corrupted_settings_file_never_blocks_startup()
    {
        var dir = TempDir();
        Directory.CreateDirectory(dir);
        try
        {
            var store = new UiSettingsStore(dir);
            File.WriteAllText(store.FilePath, "{ isto não é json");
            Assert.Null(store.Load().PythonPath);

            File.WriteAllText(store.FilePath, "{\"theme\":\"neon\",\"window_width\":1,\"window_height\":99999,\"python_path\":\"  \"}");
            var loaded = store.Load();
            Assert.Null(loaded.Theme);
            Assert.Null(loaded.WindowWidth);
            Assert.Null(loaded.WindowHeight);
            Assert.Null(loaded.PythonPath);
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public void Update_changes_only_what_it_is_told_to()
    {
        var dir = TempDir();
        try
        {
            var store = new UiSettingsStore(dir);
            store.Save(new UiSettings { Theme = "dark", PythonPath = "p" });
            store.Update(s => s with { Theme = "light" });
            var loaded = store.Load();
            Assert.Equal("light", loaded.Theme);
            Assert.Equal("p", loaded.PythonPath);
        }
        finally { Directory.Delete(dir, true); }
    }

    [Fact]
    public void Ui_log_writes_to_the_given_folder_without_throwing_on_failure()
    {
        var dir = TempDir();
        try
        {
            UiLog.Directory = dir;
            UiLog.Info("olá");
            Assert.Contains("olá", File.ReadAllText(Path.Combine(dir, "ui.log")));
        }
        finally
        {
            UiLog.Directory = null;
            Directory.Delete(dir, true);
        }
        UiLog.Directory = Path.Combine("\0invalid", "x"); // caminho inválido: não pode lançar exceção
        UiLog.Info("não deve falhar");
        UiLog.Directory = null;
    }
}

public class SetupAndSettingsTests
{
    [Fact]
    public async Task Setup_requires_name_and_matching_passwords_before_calling_the_core()
    {
        var api = new FakeCoreApi();
        var session = new SessionContext();
        var vm = new SetupViewModel(api, session);

        Assert.False(await vm.TrySetupAsync("senha-forte-1", "senha-forte-1")); // sem nome
        vm.Name = "Maria";
        Assert.False(await vm.TrySetupAsync("senha-forte-1", "outra"));
        Assert.Equal(0, api.CallCount("setup.create_admin"));
        Assert.False(session.IsAuthenticated);
    }

    [Fact]
    public async Task Setup_success_logs_the_new_admin_in()
    {
        var api = new FakeCoreApi();
        var session = new SessionContext();
        var vm = new SetupViewModel(api, session) { Name = " Maria " };

        Assert.True(await vm.TrySetupAsync("senha-forte-1", "senha-forte-1"));
        Assert.True(session.IsAuthenticated);
        Assert.Equal(new object?[] { "Maria" }, api.Args[api.Calls.IndexOf("setup.create_admin")]);
    }

    [Fact]
    public async Task Setup_shows_the_core_error_for_weak_password()
    {
        var api = new FakeCoreApi { FailWith = new RpcException(RpcCodes.ValidationError, "ValidationError", "Senha fraca.") };
        var vm = new SetupViewModel(api, new SessionContext()) { Name = "Maria" };

        Assert.False(await vm.TrySetupAsync("curta", "curta"));
        Assert.Equal("Senha fraca.", vm.ErrorMessage);
        Assert.False(vm.IsBusy);
    }

    [Fact]
    public async Task Settings_page_shows_real_runtime_and_data_locations()
    {
        var api = new FakeCoreApi();
        var vm = new SettingsViewModel(api, Make.Admin(), new FakeDialogs(), new FakeTheme(), new FakeRuntime());

        await vm.LoadAsync();

        Assert.Contains("3.12.10", vm.PythonText);
        Assert.Contains(@"C:\Python312\python.exe", vm.PythonText);
        Assert.Equal(api.PathsValue.Home, vm.DataText);
        Assert.Equal(api.PathsValue.Backups, vm.BackupsPathText);
        Assert.Contains("0.1.0", vm.AppText);
    }

    [Fact]
    public async Task Choosing_python_shows_the_message_and_ignores_cancel()
    {
        var runtime = new FakeRuntime();
        var vm = new SettingsViewModel(new FakeCoreApi(), Make.Admin(), new FakeDialogs(), new FakeTheme(), runtime);

        await vm.ChoosePythonCommand.ExecuteAsync(null);
        Assert.Equal("Python alterado.", vm.Message);

        runtime.ChooseResult = null;
        vm.Message = null;
        await vm.ChoosePythonCommand.ExecuteAsync(null);
        Assert.Null(vm.Message);
        Assert.Equal(2, runtime.ChooseCalls);
    }
}

public class NewContractTests
{
    [Fact]
    public void Setup_status_and_system_paths_match_the_real_core_responses()
    {
        var status = Fixture.Result<SetupStatus>("setup_status");
        Assert.True(status.Initialized); // o gerador já criou os técnicos de demonstração

        var paths = Fixture.Result<SystemPaths>("system_paths");
        Assert.False(string.IsNullOrWhiteSpace(paths.Home));
        Assert.EndsWith("nexus.db", paths.Database);
        Assert.Contains("backups", paths.Backups);
    }

    [Fact]
    public void Creating_a_second_admin_is_refused_by_the_core()
    {
        var (code, message, type) = Fixture.Error("error_already_initialized");
        Assert.Equal(-32000, code);
        Assert.Contains("já foi inicializado", message);
        Assert.Equal("NexusError", type);
    }
}
