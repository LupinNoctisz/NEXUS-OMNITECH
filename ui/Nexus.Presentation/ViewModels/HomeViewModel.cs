using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using Nexus.CoreClient;

namespace Nexus.Presentation;

/// <summary>Tela inicial: somente dados reais de status.get (nada é calculado fora do que o núcleo informou).</summary>
public sealed partial class HomeViewModel : PageViewModel
{
    public HomeViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs) : base(api, session, dialogs) { }

    public override string Title => "Início";

    public ObservableCollection<DeviceRow> ConnectedDevices { get; } = new();
    public ObservableCollection<SessionRow> RecentSessions { get; } = new();
    public ObservableCollection<OperationRow> RecentOperations { get; } = new();
    public ObservableCollection<AlertDto> Alerts { get; } = new();
    public ObservableCollection<ModuleRow> Modules { get; } = new();

    [ObservableProperty] private bool _loaded;
    [ObservableProperty] private string _overallText = "—";
    [ObservableProperty] private string _overallLevel = "info";
    [ObservableProperty] private string _backupText = "—";
    [ObservableProperty] private string _modulesText = "—";
    [ObservableProperty] private string _syncText = "—";
    [ObservableProperty] private string _auditText = "—";
    [ObservableProperty] private string _versionText = "—";
    [ObservableProperty] private string _devicesText = "—";

    protected override async Task LoadCoreAsync()
    {
        var status = await Api.GetStatusAsync();

        Replace(ConnectedDevices, status.DevicesConnected.Select(d => new DeviceRow(d)));
        Replace(RecentSessions, status.RecentSessions.Select(s => new SessionRow(s)));
        Replace(RecentOperations, status.RecentOperations.Select(o => new OperationRow(o)));
        Replace(Alerts, status.Alerts);
        Replace(Modules, status.Modules.Select(m => new ModuleRow(m)));

        var critical = status.Alerts.Count(a => a.Level == "critical");
        var warnings = status.Alerts.Count(a => a.Level == "warning");
        if (critical > 0)
        {
            OverallLevel = "critical";
            OverallText = $"Atenção: {critical} alerta(s) crítico(s)";
        }
        else if (warnings > 0)
        {
            OverallLevel = "warning";
            OverallText = $"{warnings} aviso(s) a verificar";
        }
        else
        {
            OverallLevel = "ok";
            OverallText = "Sem alertas críticos ou avisos";
        }

        DevicesText = status.DevicesConnected.Count == 0
            ? "Nenhum dispositivo conectado identificado. Use 'Dispositivos > Procurar' para atualizar."
            : $"{status.DevicesConnected.Count} dispositivo(s) conectado(s)";

        BackupText = status.Backups.Count == 0
            ? "Nenhum backup criado"
            : $"{status.Backups.Count} backup(s); último em {TimeText.Local(status.Backups.LatestUtc)}";

        var available = status.Modules.Where(m => m.Status == "available").ToList();
        var planned = status.Modules.Count - available.Count;
        var intact = available.Count(m => m.IntegrityOk == true);
        ModulesText = $"{intact} de {available.Count} módulo(s) disponível(is) com integridade OK; {planned} planejado(s), ainda não implementado(s)";

        SyncText = status.Sync.State == "not_configured"
            ? "Não configurada (modo " + status.Mode + ")"
            : status.Sync.State;
        AuditText = status.Audit.Ok
            ? $"Histórico íntegro ({status.Audit.Records} registro(s))"
            : "HISTÓRICO ADULTERADO — verifique em Segurança";
        VersionText = $"Núcleo {status.Version} · banco v{status.SchemaVersion}";
        Loaded = true;
    }

    private static void Replace<T>(ObservableCollection<T> target, IEnumerable<T> source)
    {
        target.Clear();
        foreach (var item in source) target.Add(item);
    }
}
