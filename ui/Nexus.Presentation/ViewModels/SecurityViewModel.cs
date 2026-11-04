using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public sealed partial class SecurityViewModel : PageViewModel
{
    public SecurityViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs) : base(api, session, dialogs) { }

    public override string Title => "Segurança";

    public ObservableCollection<string> Permissions { get; } = new();
    public ObservableCollection<string> Findings { get; } = new();
    public ObservableCollection<TechnicianRow> Technicians { get; } = new();

    public IReadOnlyList<Option> RoleOptions { get; } = new List<Option>
    {
        new("technician", "Técnico"), new("viewer", "Somente leitura"), new("admin", "Administrador"),
    };

    public bool CanManageTechnicians => Session.Can("technicians.manage");

    [ObservableProperty] private string _actorText = "—";
    [ObservableProperty] private string _roleText = "—";
    [ObservableProperty] private string _auditText = "—";
    [ObservableProperty] private bool _auditOk = true;
    [ObservableProperty] private string _databaseText = "—";
    [ObservableProperty] private bool _databaseOk = true;
    [ObservableProperty] private string _techniciansText = "—";
    [ObservableProperty] private string _publishersText = "—";
    [ObservableProperty] private string _newTechnicianName = "";
    [ObservableProperty] private string _newTechnicianRole = "technician";
    [ObservableProperty] private string? _passwordMessage;
    [ObservableProperty] private string? _technicianMessage;

    protected override async Task LoadCoreAsync()
    {
        var overview = await Api.GetSecurityOverviewAsync();
        var technicians = await Api.ListTechniciansAsync();

        ActorText = overview.Actor;
        RoleText = Labels.Role(overview.Role);
        AuditOk = overview.Audit.Ok;
        AuditText = overview.Audit.Ok
            ? $"Íntegro ({overview.Audit.Records} registro(s))"
            : $"ADULTERADO a partir do registro {overview.Audit.FirstBadId}";
        DatabaseOk = overview.DatabaseIntegrity;
        DatabaseText = overview.DatabaseIntegrity ? "Íntegro" : "FALHOU na verificação";
        var t = overview.Technicians;
        TechniciansText = $"{t.Active} ativo(s) de {t.Total}; {t.WithoutPassword} sem senha; {t.Locked} bloqueado(s)";
        PublishersText = overview.TrustedPublishers.Count == 0 ? "Nenhum" : string.Join(", ", overview.TrustedPublishers);

        Permissions.Clear();
        foreach (var permission in overview.Permissions) Permissions.Add(permission);

        Findings.Clear();
        foreach (var module in overview.Modules.Where(m => m.IntegrityOk == false))
        {
            Findings.Add($"Módulo {module.Id}: " + string.Join("; ", module.Problems));
        }
        if (t.WithoutPassword > 0) Findings.Add($"{t.WithoutPassword} técnico(s) ativo(s) sem senha (não conseguem entrar).");

        Technicians.Clear();
        foreach (var technician in technicians) Technicians.Add(new TechnicianRow(technician));
    }

    /// <summary>Chamado pela view com os textos dos PasswordBox (as senhas não ficam guardadas no ViewModel).</summary>
    public async Task<bool> ChangePasswordAsync(string oldPassword, string newPassword, string confirmation)
    {
        PasswordMessage = null;
        if (newPassword != confirmation)
        {
            ErrorMessage = "A confirmação não confere com a nova senha.";
            return false;
        }
        return await RunAsync(async () =>
        {
            await Api.ChangePasswordAsync(oldPassword, newPassword);
            PasswordMessage = "Senha alterada.";
        });
    }

    public async Task<bool> AddTechnicianAsync(string password, string confirmation)
    {
        TechnicianMessage = null;
        if (string.IsNullOrWhiteSpace(NewTechnicianName))
        {
            ErrorMessage = "Informe o nome do técnico.";
            return false;
        }
        if (password != confirmation)
        {
            ErrorMessage = "A confirmação não confere com a senha.";
            return false;
        }
        var name = NewTechnicianName.Trim();
        return await RunAsync(async () =>
        {
            await Api.AddTechnicianAsync(name, NewTechnicianRole, password);
            NewTechnicianName = "";
            TechnicianMessage = $"Técnico '{name}' adicionado.";
            await LoadCoreAsync();
        });
    }

    [RelayCommand]
    private Task ToggleActiveAsync(TechnicianRow? row) => RunAsync(async () =>
    {
        if (row is null) return;
        await Api.SetTechnicianActiveAsync(row.Name, !row.Active);
        TechnicianMessage = row.Active ? $"'{row.Name}' desativado." : $"'{row.Name}' ativado.";
        await LoadCoreAsync();
    });
}
