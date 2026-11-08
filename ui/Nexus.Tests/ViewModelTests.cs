using System.Text.Json;
using Nexus.CoreClient;
using Nexus.Presentation;

namespace Nexus.Tests;

public class HomeAndErrorTests
{
    [Fact]
    public async Task Home_shows_exactly_what_the_core_reported()
    {
        var api = new FakeCoreApi();
        var vm = new HomeViewModel(api, Make.Admin(), new FakeDialogs());

        await vm.LoadAsync();

        Assert.False(vm.HasError);
        Assert.Single(vm.ConnectedDevices);
        Assert.Equal(api.Status.RecentSessions.Count, vm.RecentSessions.Count);
        Assert.Equal(api.Status.RecentOperations.Count, vm.RecentOperations.Count);
        Assert.Contains("1 de 1", vm.ModulesText);
        Assert.Contains("5 planejado", vm.ModulesText);
        Assert.Contains("1 backup", vm.BackupText);
        Assert.Contains("Não configurada", vm.SyncText);
        Assert.Contains("íntegro", vm.AuditText);
        Assert.True(vm.Loaded);
    }

    [Fact]
    public async Task Home_does_not_invent_data_when_core_reports_nothing()
    {
        var api = new FakeCoreApi();
        api.Status = api.Status with
        {
            DevicesConnected = new List<DeviceDto>(),
            RecentSessions = new List<SessionDto>(),
            RecentOperations = new List<OperationDto>(),
            Alerts = new List<AlertDto>(),
            Backups = new BackupSummary(0, null, null),
        };
        var vm = new HomeViewModel(api, Make.Admin(), new FakeDialogs());

        await vm.LoadAsync();

        Assert.Empty(vm.ConnectedDevices);
        Assert.Contains("Nenhum dispositivo", vm.DevicesText);
        Assert.Equal("Nenhum backup criado", vm.BackupText);
        Assert.Equal("ok", vm.OverallLevel);
    }

    [Fact]
    public async Task Home_escalates_level_from_real_alerts()
    {
        var api = new FakeCoreApi();
        api.Status = api.Status with { Alerts = new List<AlertDto> { new("warning", "w"), new("critical", "c") } };
        var vm = new HomeViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();
        Assert.Equal("critical", vm.OverallLevel);
        Assert.Equal(2, vm.Alerts.Count);

        api.Status = api.Status with { Alerts = new List<AlertDto> { new("warning", "w") } };
        await vm.LoadAsync();
        Assert.Equal("warning", vm.OverallLevel);
    }

    [Fact]
    public async Task Core_errors_become_messages_and_never_leave_the_page_busy()
    {
        var api = new FakeCoreApi { FailWith = new RpcException(RpcCodes.PermissionDenied, "PermissionDenied", "negado") };
        var vm = new HomeViewModel(api, Make.Admin(), new FakeDialogs());

        await vm.LoadAsync();

        Assert.True(vm.HasError);
        Assert.Equal("negado", vm.ErrorMessage);
        Assert.False(vm.IsBusy);
    }

    [Fact]
    public async Task Unavailable_core_is_reported_without_crashing()
    {
        var api = new FakeCoreApi { FailWith = new CoreUnavailableException("O núcleo parou") };
        var vm = new HomeViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();
        Assert.Equal("O núcleo parou", vm.ErrorMessage);
    }

    [Fact]
    public async Task Unexpected_exceptions_are_contained()
    {
        var api = new FakeCoreApi { FailWith = new InvalidOperationException("bug") };
        var vm = new HomeViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();
        Assert.Contains("bug", vm.ErrorMessage);
        Assert.False(vm.IsBusy);
    }

    [Fact]
    public async Task Lost_authentication_raises_SessionLost()
    {
        var api = new FakeCoreApi { FailWith = new RpcException(RpcCodes.NotAuthenticated, "AuthenticationError", "Autenticação necessária.") };
        var vm = new HomeViewModel(api, Make.Admin(), new FakeDialogs());
        var lost = false;
        vm.SessionLost += (_, _) => lost = true;

        await vm.LoadAsync();

        Assert.True(lost);
    }

    [Fact]
    public async Task A_second_refresh_while_busy_does_not_call_the_core_again()
    {
        var gate = new TaskCompletionSource();
        var api = new FakeCoreApi { StatusGate = gate.Task };
        var vm = new HomeViewModel(api, Make.Admin(), new FakeDialogs());

        var first = vm.LoadAsync();
        await vm.LoadAsync(); // ignorada: já está carregando
        gate.SetResult();
        await first;

        Assert.Equal(1, api.CallCount("status"));
    }
}

public class DevicesAndDiagnosticsTests
{
    [Fact]
    public async Task Devices_list_selection_and_details_come_from_the_core()
    {
        var api = new FakeCoreApi();
        var vm = new DevicesViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();

        Assert.Equal(2, vm.Devices.Count);
        vm.SelectedDevice = vm.Devices.First(d => d.Device.Source == "demo");
        Assert.Contains(vm.Details, d => d.Key == "speed_mbps" && d.Value == "480");
        Assert.Contains(vm.Details, d => d.Key == "Origem" && d.Value == "demo");
    }

    [Fact]
    public async Task Scan_reports_found_devices_and_provider_failures()
    {
        var api = new FakeCoreApi();
        api.Scan = new ScanResult(1, new Dictionary<string, string> { ["usb"] = "não suportado" });
        var vm = new DevicesViewModel(api, Make.Admin(), new FakeDialogs());

        await vm.ScanCommand.ExecuteAsync(null);

        Assert.Contains("1 dispositivo(s) encontrado(s)", vm.Message);
        Assert.Contains("usb: não suportado", vm.Message);
        Assert.Equal(1, api.CallCount("devices.scan"));
        Assert.Equal(1, api.CallCount("devices.list"));
    }

    [Fact]
    public async Task Identify_fills_the_three_fields_as_a_suggestion_without_registering()
    {
        var api = new FakeCoreApi();
        var vm = new DevicesViewModel(api, Make.Admin(), new FakeDialogs()) { IdentifyText = "Dell Inspiron 15 3520 S/N: ABC1234" };

        await vm.IdentifyCommand.ExecuteAsync(null);

        Assert.Equal("Dell", vm.NewVendor);
        Assert.Equal("Inspiron 15 3520", vm.NewModel);
        Assert.Equal("ABC1234", vm.NewSerial);
        Assert.Contains("confira", vm.Message);
        Assert.Equal(1, api.CallCount("devices.identify"));
        Assert.Equal(0, api.CallCount("devices.add"));
    }

    [Fact]
    public async Task Identify_with_empty_text_is_rejected_without_calling_the_core()
    {
        var api = new FakeCoreApi();
        var vm = new DevicesViewModel(api, Make.Admin(), new FakeDialogs());

        await vm.IdentifyCommand.ExecuteAsync(null);

        Assert.True(vm.HasError);
        Assert.Equal(0, api.CallCount("devices.identify"));
    }

    [Fact]
    public async Task Add_with_empty_fields_is_rejected_without_calling_the_core()
    {
        var api = new FakeCoreApi();
        var vm = new DevicesViewModel(api, Make.Admin(), new FakeDialogs());

        await vm.AddCommand.ExecuteAsync(null);

        Assert.True(vm.HasError);
        Assert.Equal(0, api.CallCount("devices.add"));
    }

    [Fact]
    public async Task Add_sends_trimmed_values_and_clears_the_form()
    {
        var api = new FakeCoreApi();
        var vm = new DevicesViewModel(api, Make.Admin(), new FakeDialogs())
        {
            NewKind = "mobile",
            NewModel = "  Aparelho X ",
            NewLabel = "Cliente A",
        };

        await vm.AddCommand.ExecuteAsync(null);

        Assert.Equal(new object?[] { "mobile", null, "Aparelho X", null, "Cliente A" }, api.Args[api.Calls.IndexOf("devices.add")]);
        Assert.Equal("", vm.NewModel);
        Assert.Equal("Dispositivo cadastrado.", vm.Message);
    }

    [Fact]
    public void Viewer_cannot_manage_devices()
    {
        var vm = new DevicesViewModel(new FakeCoreApi(), Make.Viewer(), new FakeDialogs());
        Assert.False(vm.CanManage);
        Assert.True(new DevicesViewModel(new FakeCoreApi(), Make.Admin(), new FakeDialogs()).CanManage);
    }

    [Fact]
    public async Task Starting_a_session_requires_a_device_and_uses_the_chosen_kind()
    {
        var api = new FakeCoreApi();
        var vm = new DiagnosticsViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();

        await vm.StartCommand.ExecuteAsync(null);
        Assert.True(vm.HasError);
        Assert.Equal(0, api.CallCount("sessions.start"));

        vm.SelectedDevice = vm.Devices.First();
        vm.SelectedKind = "pc_diagnostics";
        await vm.StartCommand.ExecuteAsync(null);

        var args = api.Args[api.Calls.IndexOf("sessions.start")];
        Assert.Equal(new object?[] { vm.Devices.First().Id, "pc_diagnostics" }, args);
    }

    [Fact]
    public async Task Finishing_requires_an_open_session()
    {
        var api = new FakeCoreApi();
        var vm = new DiagnosticsViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();

        vm.SelectedSession = vm.Sessions.First(s => !s.IsOpen);
        await vm.FinishCommand.ExecuteAsync("completed");
        Assert.True(vm.HasError);
        Assert.Equal(0, api.CallCount("sessions.finish"));

        vm.SelectedSession = vm.Sessions.First(s => s.IsOpen);
        vm.FinishSummary = " Cancelada pelo cliente ";
        await vm.FinishCommand.ExecuteAsync("aborted");

        var args = api.Args[api.Calls.IndexOf("sessions.finish")];
        Assert.Equal("aborted", args[1]);
        Assert.Equal("Cancelada pelo cliente", args[2]);
    }

    [Fact]
    public async Task Not_implemented_notice_depends_on_real_module_availability()
    {
        var api = new FakeCoreApi();
        var vm = new DiagnosticsViewModel(api, Make.Admin(), new FakeDialogs());

        await vm.LoadAsync();
        Assert.False(vm.ShowNotImplementedNotice); // a fixture tem um módulo disponível

        api.Modules = api.Modules.Where(m => m.Status == "planned").ToList();
        await vm.LoadAsync();
        Assert.True(vm.ShowNotImplementedNotice);
    }
}

public class HistoryModulesBackupsTests
{
    [Fact]
    public async Task History_filters_loaded_records_locally()
    {
        var api = new FakeCoreApi();
        var vm = new HistoryViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();
        var total = vm.Operations.Count;
        Assert.True(total > 0);

        vm.FilterText = "backup.create";
        Assert.Single(vm.Operations);
        Assert.Equal("backup.create", vm.Operations[0].Action);
        Assert.Contains($"de {total}", vm.CountText);

        vm.FilterText = "texto-que-nao-existe-xyz";
        Assert.Empty(vm.Operations);

        vm.FilterText = "";
        Assert.Equal(total, vm.Operations.Count);
    }

    [Fact]
    public async Task History_verify_reports_tampering()
    {
        var api = new FakeCoreApi { AuditResult = new AuditVerify(false, 3, 2) };
        var vm = new HistoryViewModel(api, Make.Admin(), new FakeDialogs());

        await vm.VerifyCommand.ExecuteAsync(null);

        Assert.False(vm.ChainOk);
        Assert.Contains("ADULTERAÇÃO", vm.ChainText);
        Assert.Contains("2", vm.ChainText);
    }

    [Fact]
    public async Task Register_module_needs_confirmation()
    {
        var api = new FakeCoreApi();
        var dialogs = new FakeDialogs { Answer = false };
        var vm = new ModulesViewModel(api, Make.Admin(), dialogs);
        await vm.LoadAsync();
        vm.SelectedModule = vm.Modules.First(m => m.Id == "nexus.demo");

        await vm.RegisterCommand.ExecuteAsync(null);
        Assert.Equal(1, dialogs.ConfirmCalls);
        Assert.Equal(0, api.CallCount("modules.register"));

        dialogs.Answer = true;
        await vm.RegisterCommand.ExecuteAsync(null);
        Assert.Equal(new object?[] { "nexus.demo", true }, api.Args[api.Calls.IndexOf("modules.register")]);
    }

    [Fact]
    public async Task Planned_modules_are_shown_as_not_implemented_and_cannot_be_managed()
    {
        var vm = new ModulesViewModel(new FakeCoreApi(), Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();

        var planned = vm.Modules.First(m => m.Module.Status == "planned");
        Assert.Equal("Não implementado", planned.StateText);
        Assert.False(planned.CanRegister);
        Assert.False(planned.CanEnable);
        Assert.Equal("—", planned.IntegrityText);

        var demo = vm.Modules.First(m => m.Id == "nexus.demo");
        Assert.Equal("Íntegro", demo.IntegrityText);
        Assert.True(demo.CanDisable);
    }

    [Fact]
    public async Task Failed_integrity_is_visible()
    {
        var api = new FakeCoreApi();
        api.Modules = new List<ModuleStatusDto>
        {
            new("nexus.demo", "Demo", "1.0.0", "LMF Informática", "available", true, true, false, false,
                new List<string> { "module.py: hash diverge do manifesto" }),
        };
        var vm = new ModulesViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();

        var row = vm.Modules.Single();
        Assert.True(row.IntegrityFailed);
        Assert.Equal("FALHOU", row.IntegrityText);
        Assert.Contains("hash diverge", row.Problems);
    }

    [Fact]
    public async Task Restore_requires_typed_confirmation_and_does_nothing_if_declined()
    {
        var api = new FakeCoreApi();
        var dialogs = new FakeDialogs { Answer = false };
        var vm = new BackupsViewModel(api, Make.Admin(), dialogs);
        await vm.LoadAsync();
        vm.SelectedBackup = vm.Backups.First();

        await vm.RestoreCommand.ExecuteAsync(null);

        Assert.Equal(BackupsViewModel.RestoreWord, dialogs.LastRequiredText);
        Assert.Equal(0, api.CallCount("backups.restore"));
    }

    [Fact]
    public async Task Restore_sends_confirmed_and_name_only()
    {
        var api = new FakeCoreApi();
        var vm = new BackupsViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.LoadAsync();
        vm.SelectedBackup = vm.Backups.First();

        await vm.RestoreCommand.ExecuteAsync(null);

        Assert.Equal(new object?[] { vm.Backups.First().Name, true }, api.Args[api.Calls.IndexOf("backups.restore")]);
        Assert.Contains("preservado", vm.Message);
    }

    [Fact]
    public async Task Restore_that_removes_the_current_technician_forces_login()
    {
        var api = new FakeCoreApi();
        api.RestoreResultValue = new RestoreResult("nexus-x-pre-restore.db", false);
        var vm = new BackupsViewModel(api, Make.Admin(), new FakeDialogs());
        var lost = false;
        vm.SessionLost += (_, _) => lost = true;
        await vm.LoadAsync();
        vm.SelectedBackup = vm.Backups.First();

        await vm.RestoreCommand.ExecuteAsync(null);

        Assert.True(lost);
    }

    [Fact]
    public async Task Backup_actions_without_selection_show_an_error()
    {
        var api = new FakeCoreApi();
        var vm = new BackupsViewModel(api, Make.Admin(), new FakeDialogs());
        await vm.VerifyCommand.ExecuteAsync(null);
        Assert.True(vm.HasError);
        await vm.RestoreCommand.ExecuteAsync(null);
        Assert.Equal(0, api.CallCount("backups.verify") + api.CallCount("backups.restore"));
    }

    [Fact]
    public void Backup_row_formats_sizes()
    {
        Assert.Equal("512 B", new BackupRow(new BackupDto("a.db", 512, "2026-11-04T00:00:00+00:00", true)).SizeText);
        Assert.Equal("2,0 KB", new BackupRow(new BackupDto("a.db", 2048, "2026-11-04T00:00:00+00:00", true)).SizeText.Replace('.', ','));
        Assert.Equal("Não", new BackupRow(new BackupDto("a.db", 1, "2026-11-04T00:00:00+00:00", false)).ChecksumText);
    }
}

public class SecuritySettingsLoginShellTests
{
    [Fact]
    public async Task Security_page_lists_real_findings()
    {
        var api = new FakeCoreApi();
        api.Security = api.Security with
        {
            Technicians = new TechnicianSummary(3, 3, 1, 0),
            Modules = new List<SecurityModule> { new("nexus.demo", "available", false, new List<string> { "módulo adulterado" }) },
        };
        var vm = new SecurityViewModel(api, Make.Admin(), new FakeDialogs());

        await vm.LoadAsync();

        Assert.Contains(vm.Findings, f => f.Contains("nexus.demo") && f.Contains("módulo adulterado"));
        Assert.Contains(vm.Findings, f => f.Contains("sem senha"));
        Assert.Equal(api.Technicians.Count, vm.Technicians.Count);
        Assert.Equal(api.Security.Permissions.Count, vm.Permissions.Count);
    }

    [Fact]
    public async Task Change_password_validates_confirmation_before_calling_the_core()
    {
        var api = new FakeCoreApi();
        var vm = new AccountViewModel(api, Make.Admin(), new FakeDialogs());

        Assert.False(await vm.ChangePasswordAsync("antiga", "nova-senha-1", "diferente"));
        Assert.Equal(0, api.CallCount("change_password"));
        Assert.True(vm.HasError);

        Assert.True(await vm.ChangePasswordAsync("antiga", "nova-senha-1", "nova-senha-1"));
        Assert.Equal(1, api.CallCount("change_password"));
        Assert.Equal("Senha alterada.", vm.PasswordMessage);
    }

    [Fact]
    public async Task Add_technician_validates_name_and_password_confirmation()
    {
        var api = new FakeCoreApi();
        var vm = new SecurityViewModel(api, Make.Admin(), new FakeDialogs());

        Assert.False(await vm.AddTechnicianAsync("senha-forte-1", "senha-forte-1")); // sem nome
        vm.NewTechnicianName = "carla";
        Assert.False(await vm.AddTechnicianAsync("senha-forte-1", "outra"));
        Assert.Equal(0, api.CallCount("technicians.add"));

        Assert.True(await vm.AddTechnicianAsync("senha-forte-1", "senha-forte-1"));
        Assert.Equal(new object?[] { "carla", "technician" }, api.Args[api.Calls.IndexOf("technicians.add")]);
        Assert.Equal("", vm.NewTechnicianName);
    }

    [Fact]
    public async Task Settings_reject_invalid_values_without_calling_the_core()
    {
        var api = new FakeCoreApi();
        var vm = new SettingsViewModel(api, Make.Admin(), new FakeDialogs(), new FakeTheme(), new FakeRuntime());
        await vm.LoadAsync();

        vm.BackupKeepText = "0";
        await vm.SaveCommand.ExecuteAsync(null);
        Assert.True(vm.HasError);
        vm.BackupKeepText = "abc";
        await vm.SaveCommand.ExecuteAsync(null);
        Assert.Equal(0, api.CallCount("settings.set"));
    }

    [Fact]
    public async Task Settings_save_only_what_changed_and_apply_the_theme()
    {
        var api = new FakeCoreApi();
        var theme = new FakeTheme();
        var vm = new SettingsViewModel(api, Make.Admin(), new FakeDialogs(), theme, new FakeRuntime());
        await vm.LoadAsync();

        await vm.SaveCommand.ExecuteAsync(null);
        Assert.Equal("Nenhuma alteração.", vm.Message);
        Assert.Equal(0, api.CallCount("settings.set"));

        vm.SelectedTheme = "light";
        vm.BackupKeepText = "20";
        await vm.SaveCommand.ExecuteAsync(null);

        Assert.Equal(2, api.CallCount("settings.set"));
        Assert.Equal("light", theme.Current);
        Assert.Contains(api.Args, a => a.Length == 2 && Equals(a[0], "backup.keep") && Equals(a[1], 20));
        Assert.Contains("Núcleo", vm.CoreText);
        Assert.Equal("Local (offline)", vm.ModeText);
    }

    [Fact]
    public async Task Login_requires_both_fields()
    {
        var api = new FakeCoreApi();
        var session = new SessionContext();
        var vm = new LoginViewModel(api, session);

        Assert.False(await vm.TryLoginAsync("senha"));
        vm.Name = "tecnico.demo";
        Assert.False(await vm.TryLoginAsync(""));
        Assert.Equal(0, api.CallCount("login"));
        Assert.False(session.IsAuthenticated);
    }

    [Fact]
    public async Task Login_failure_shows_the_core_message_and_keeps_the_user_out()
    {
        var api = new FakeCoreApi { FailWith = new RpcException(RpcCodes.NotAuthenticated, "AuthenticationError", "Credenciais inválidas ou conta temporariamente bloqueada.") };
        var session = new SessionContext();
        var vm = new LoginViewModel(api, session) { Name = "tecnico.demo" };

        Assert.False(await vm.TryLoginAsync("senha-errada"));

        Assert.True(vm.HasError);
        Assert.StartsWith("Credenciais inválidas", vm.ErrorMessage);
        Assert.False(session.IsAuthenticated);
        Assert.False(vm.IsBusy);
    }

    [Fact]
    public async Task Login_success_sets_the_session_from_the_core_response()
    {
        var api = new FakeCoreApi();
        var session = new SessionContext();
        var vm = new LoginViewModel(api, session) { Name = " tecnico.demo " };

        Assert.True(await vm.TryLoginAsync("senha"));

        Assert.True(session.IsAuthenticated);
        Assert.Equal("tecnico.demo", session.Actor);
        Assert.True(session.Can("devices.manage"));
        Assert.False(session.Can("permissao.inexistente"));
        Assert.Equal(new object?[] { "tecnico.demo" }, api.Args[api.Calls.IndexOf("login")]);
    }

    [Fact]
    public void Shell_exposes_the_sections_in_order_for_admin()
    {
        var shell = new ShellViewModel(new FakeCoreApi(), Make.Admin(), new FakeDialogs(), new FakeTheme(), new FakeRuntime());
        Assert.Equal(
            new[] { "Início", "Dispositivos", "Diagnósticos", "Histórico", "Módulos", "Backups", "Segurança", "Configurações", "Minha conta" },
            shell.Items.Select(i => i.Title).ToArray());
    }

    [Fact]
    public async Task Shell_applies_saved_theme_and_opens_home_with_real_data()
    {
        var api = new FakeCoreApi();
        api.Settings["ui.theme"] = JsonSerializer.SerializeToElement("light");
        var theme = new FakeTheme();
        var shell = new ShellViewModel(api, Make.Admin(), new FakeDialogs(), theme, new FakeRuntime());

        await shell.InitializeAsync();
        await Task.Delay(100); // a carga da página é disparada em segundo plano

        Assert.Equal("light", theme.Current);
        Assert.IsType<HomeViewModel>(shell.CurrentPage);
        Assert.Equal(1, api.CallCount("status"));
    }

    [Fact]
    public async Task Shell_navigation_creates_each_page_once_and_loads_it()
    {
        var api = new FakeCoreApi();
        var shell = new ShellViewModel(api, Make.Admin(), new FakeDialogs(), new FakeTheme(), new FakeRuntime());

        shell.SelectedItem = shell.Items[1];
        var first = shell.CurrentPage;
        shell.SelectedItem = shell.Items[0];
        shell.SelectedItem = shell.Items[1];
        await Task.Delay(100);

        Assert.IsType<DevicesViewModel>(first);
        Assert.Same(first, shell.CurrentPage);
    }

    [Fact]
    public async Task Shell_logout_clears_session_and_requests_login()
    {
        var api = new FakeCoreApi();
        var session = Make.Admin();
        var shell = new ShellViewModel(api, session, new FakeDialogs(), new FakeTheme(), new FakeRuntime());
        var requested = false;
        shell.LogoutRequested += (_, _) => requested = true;

        await shell.LogoutCommand.ExecuteAsync(null);

        Assert.True(requested);
        Assert.False(session.IsAuthenticated);
        Assert.Equal(1, api.CallCount("logout"));
    }

    [Fact]
    public async Task Shell_requests_login_when_a_page_loses_the_session()
    {
        var api = new FakeCoreApi { FailWith = new RpcException(RpcCodes.NotAuthenticated, "AuthenticationError", "Autenticação necessária.") };
        var shell = new ShellViewModel(api, Make.Admin(), new FakeDialogs(), new FakeTheme(), new FakeRuntime());
        var requested = false;
        shell.LogoutRequested += (_, _) => requested = true;

        shell.SelectedItem = shell.Items[1];
        await Task.Delay(200);

        Assert.True(requested);
    }

    [Fact]
    public void Shell_hides_security_and_settings_from_non_admins_but_keeps_account()
    {
        var shell = new ShellViewModel(new FakeCoreApi(), Make.Viewer(), new FakeDialogs(), new FakeTheme(), new FakeRuntime());
        var titles = shell.Items.Select(i => i.Title).ToArray();
        Assert.DoesNotContain("Segurança", titles);
        Assert.DoesNotContain("Configurações", titles);
        Assert.Contains("Minha conta", titles);
        Assert.Contains("Início", titles);
    }

    [Fact]
    public async Task Shell_does_not_request_settings_when_the_user_lacks_settings_read()
    {
        var api = new FakeCoreApi();
        var shell = new ShellViewModel(api, Make.Viewer(), new FakeDialogs(), new FakeTheme(), new FakeRuntime());
        await shell.InitializeAsync();
        Assert.Equal(0, api.CallCount("settings.get"));

        var adminApi = new FakeCoreApi();
        await new ShellViewModel(adminApi, Make.Admin(), new FakeDialogs(), new FakeTheme(), new FakeRuntime()).InitializeAsync();
        Assert.Equal(1, adminApi.CallCount("settings.get"));
    }

    [Fact]
    public async Task Account_page_lists_technicians_for_a_viewer_and_changes_own_password()
    {
        var api = new FakeCoreApi();
        var vm = new AccountViewModel(api, Make.Viewer(), new FakeDialogs());
        await vm.LoadAsync();
        Assert.Equal(api.Technicians.Count, vm.Technicians.Count);
        Assert.True(await vm.ChangePasswordAsync("antiga-123", "nova-senha-1", "nova-senha-1"));
        Assert.Equal(1, api.CallCount("change_password"));
    }

    [Fact]
    public async Task Theme_toggle_persists_only_with_permission()
    {
        var api = new FakeCoreApi();
        var theme = new FakeTheme();
        var admin = new ShellViewModel(api, Make.Admin(), new FakeDialogs(), theme, new FakeRuntime());
        await admin.ToggleThemeCommand.ExecuteAsync(null);
        Assert.Equal("light", theme.Current);
        Assert.Equal(1, api.CallCount("settings.set"));

        var viewerApi = new FakeCoreApi();
        var viewer = new ShellViewModel(viewerApi, Make.Viewer(), new FakeDialogs(), new FakeTheme(), new FakeRuntime());
        await viewer.ToggleThemeCommand.ExecuteAsync(null);
        Assert.Equal(0, viewerApi.CallCount("settings.set"));
    }
}

public class FormattingTests
{
    [Fact]
    public void Utc_timestamps_are_shown_in_local_time()
    {
        var utc = "2026-11-04T01:25:33+00:00";
        var expected = DateTimeOffset.Parse(utc).ToLocalTime().ToString("dd/MM/yyyy HH:mm:ss", System.Globalization.CultureInfo.GetCultureInfo("pt-BR"));
        Assert.Equal(expected, TimeText.Local(utc));
    }

    [Fact]
    public void Missing_or_invalid_timestamps_do_not_crash()
    {
        Assert.Equal("—", TimeText.Local(null));
        Assert.Equal("—", TimeText.Local(" "));
        Assert.Equal("não-é-data", TimeText.Local("não-é-data"));
    }

    [Fact]
    public void Unknown_technical_values_are_shown_as_received()
    {
        Assert.Equal("Computador", Labels.Kind("pc"));
        Assert.Equal("novo-tipo", Labels.Kind("novo-tipo"));
        Assert.Equal("Planejado (não implementado)", Labels.ModuleStatus("planned"));
    }
}
