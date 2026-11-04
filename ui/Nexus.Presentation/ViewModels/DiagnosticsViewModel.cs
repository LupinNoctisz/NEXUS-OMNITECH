using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Nexus.CoreClient;

namespace Nexus.Presentation;

/// <summary>
/// Sessões de diagnóstico e disponibilidade dos módulos. Os módulos de diagnóstico ainda não existem:
/// a tela mostra isso explicitamente e não gera nenhum resultado de teste.
/// </summary>
public sealed partial class DiagnosticsViewModel : PageViewModel
{
    public DiagnosticsViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs) : base(api, session, dialogs) { }

    public override string Title => "Diagnósticos";

    public ObservableCollection<DeviceRow> Devices { get; } = new();
    public ObservableCollection<SessionRow> Sessions { get; } = new();
    public ObservableCollection<ModuleRow> Modules { get; } = new();

    public IReadOnlyList<Option> KindOptions { get; } = new List<Option>
    {
        new("general", "Geral"), new("pc_diagnostics", "Diagnóstico de PC"), new("mobile", "Mobile"),
        new("console", "Console"), new("electronics", "Eletrônica"),
    };

    public bool CanRun => Session.Can("sessions.run");

    [ObservableProperty] private DeviceRow? _selectedDevice;
    [ObservableProperty] private SessionRow? _selectedSession;
    [ObservableProperty] private string _selectedKind = "general";
    [ObservableProperty] private string _finishSummary = "";
    [ObservableProperty] private string? _message;
    [ObservableProperty] private bool _showNotImplementedNotice = true;

    protected override async Task LoadCoreAsync()
    {
        var devices = await Api.ListDevicesAsync();
        var sessions = await Api.RecentSessionsAsync(50);
        var modules = await Api.ListModulesAsync();

        var deviceId = SelectedDevice?.Id;
        var sessionId = SelectedSession?.Id;
        Devices.Clear();
        foreach (var device in devices) Devices.Add(new DeviceRow(device));
        Sessions.Clear();
        foreach (var session in sessions) Sessions.Add(new SessionRow(session));
        Modules.Clear();
        foreach (var module in modules) Modules.Add(new ModuleRow(module));

        SelectedDevice = deviceId is null ? null : Devices.FirstOrDefault(d => d.Id == deviceId);
        SelectedSession = sessionId is null ? null : Sessions.FirstOrDefault(s => s.Id == sessionId);
        ShowNotImplementedNotice = !modules.Any(m => m.Status == "available");
    }

    [RelayCommand]
    private Task StartAsync() => RunAsync(async () =>
    {
        if (SelectedDevice is null)
        {
            ErrorMessage = "Selecione um dispositivo.";
            return;
        }
        var id = await Api.StartSessionAsync(SelectedDevice.Id, SelectedKind);
        Message = $"Sessão {id} iniciada.";
        await LoadCoreAsync();
    });

    [RelayCommand]
    private Task FinishAsync(string? status) => RunAsync(async () =>
    {
        if (SelectedSession is null || !SelectedSession.IsOpen)
        {
            ErrorMessage = "Selecione uma sessão aberta.";
            return;
        }
        var finalStatus = status == "aborted" ? "aborted" : "completed";
        var summary = string.IsNullOrWhiteSpace(FinishSummary) ? null : FinishSummary.Trim();
        await Api.FinishSessionAsync(SelectedSession.Id, finalStatus, summary);
        FinishSummary = "";
        Message = $"Sessão {SelectedSession.Id} encerrada.";
        await LoadCoreAsync();
    });
}
