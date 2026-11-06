using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using Nexus.CoreClient;

namespace Nexus.Presentation;

/// <summary>Disponível para todos os papéis: troca da própria senha e lista (reduzida) de técnicos.</summary>
public sealed partial class AccountViewModel : PageViewModel
{
    public AccountViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs) : base(api, session, dialogs) { }

    public override string Title => "Minha conta";

    public ObservableCollection<TechnicianRow> Technicians { get; } = new();

    public string ActorText => $"{Session.Actor} · {Labels.Role(Session.Role)}";

    [ObservableProperty] private string? _passwordMessage;

    protected override async Task LoadCoreAsync()
    {
        var technicians = await Api.ListTechniciansAsync();
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
}
