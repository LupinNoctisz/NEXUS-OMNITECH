using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public sealed partial class BackupsViewModel : PageViewModel
{
    public const string RestoreWord = "RESTAURAR";

    public BackupsViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs) : base(api, session, dialogs) { }

    public override string Title => "Backups";

    public ObservableCollection<BackupRow> Backups { get; } = new();

    public bool CanManage => Session.Can("backup.manage");
    public bool CanRestore => Session.Can("backup.restore");

    [ObservableProperty] private BackupRow? _selectedBackup;
    [ObservableProperty] private string? _message;

    protected override async Task LoadCoreAsync()
    {
        var selectedName = SelectedBackup?.Name;
        var list = await Api.ListBackupsAsync();
        Backups.Clear();
        foreach (var backup in list) Backups.Add(new BackupRow(backup));
        SelectedBackup = selectedName is null ? null : Backups.FirstOrDefault(b => b.Name == selectedName);
    }

    [RelayCommand]
    private Task CreateAsync() => RunAsync(async () =>
    {
        var name = await Api.CreateBackupAsync("manual");
        Message = $"Backup criado: {name}";
        await LoadCoreAsync();
    });

    [RelayCommand]
    private Task VerifyAsync() => RunAsync(async () =>
    {
        if (SelectedBackup is null) { ErrorMessage = "Selecione um backup."; return; }
        await Api.VerifyBackupAsync(SelectedBackup.Name);
        Message = $"{SelectedBackup.Name}: checksum e integridade do banco conferem.";
    });

    [RelayCommand]
    private async Task RestoreAsync()
    {
        var backup = SelectedBackup;
        if (backup is null) { ErrorMessage = "Selecione um backup."; return; }
        var confirmed = await Dialogs.ConfirmAsync(
            "Restaurar backup",
            $"Restaurar '{backup.Name}' SUBSTITUI todos os dados locais atuais (técnicos, dispositivos, sessões, histórico).\n\n" +
            "O NEXUS cria antes um backup do estado atual. Se o seu usuário não existir no backup restaurado, " +
            "você será desconectado.",
            "Restaurar",
            RestoreWord);
        if (!confirmed) return;

        var sessionActive = true;
        var ok = await RunAsync(async () =>
        {
            var result = await Api.RestoreBackupAsync(backup.Name, true);
            sessionActive = result.SessionActive;
            Message = $"Backup restaurado. Estado anterior preservado em {result.SafetyBackup}.";
            if (sessionActive) await LoadCoreAsync();
        });
        if (ok && !sessionActive) RaiseSessionLost();
    }
}
