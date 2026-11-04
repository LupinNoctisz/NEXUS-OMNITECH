using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public sealed partial class ModulesViewModel : PageViewModel
{
    public ModulesViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs) : base(api, session, dialogs) { }

    public override string Title => "Módulos";

    public ObservableCollection<ModuleRow> Modules { get; } = new();

    public bool CanManage => Session.Can("modules.manage");

    [ObservableProperty] private ModuleRow? _selectedModule;
    [ObservableProperty] private string? _message;

    protected override async Task LoadCoreAsync()
    {
        var selectedId = SelectedModule?.Id;
        var list = await Api.ListModulesAsync();
        Modules.Clear();
        foreach (var module in list) Modules.Add(new ModuleRow(module));
        SelectedModule = selectedId is null ? null : Modules.FirstOrDefault(m => m.Id == selectedId);
    }

    [RelayCommand]
    private Task VerifyAsync() => RunAsync(async () =>
    {
        if (SelectedModule is null) { ErrorMessage = "Selecione um módulo."; return; }
        var result = await Api.VerifyModuleAsync(SelectedModule.Id);
        Message = result.Ok
            ? $"{SelectedModule.Id}: integridade OK."
            : $"{SelectedModule.Id}: FALHOU — " + string.Join("; ", result.Problems);
    });

    [RelayCommand]
    private async Task RegisterAsync()
    {
        var module = SelectedModule;
        if (module is null) { ErrorMessage = "Selecione um módulo."; return; }
        var confirmed = await Dialogs.ConfirmAsync(
            "Registrar módulo",
            $"Registrar o módulo '{module.Id}' (publicador: {module.Publisher})?\n\n" +
            "Somente registre módulos de origem confiável. O registro fixa o conteúdo atual do módulo; " +
            "qualquer alteração posterior bloqueará o carregamento.",
            "Registrar");
        if (!confirmed) return;
        await RunAsync(async () =>
        {
            await Api.RegisterModuleAsync(module.Id, true);
            Message = $"{module.Id} registrado (desativado). Ative para usar.";
            await LoadCoreAsync();
        });
    }

    [RelayCommand]
    private Task EnableAsync() => RunAsync(async () =>
    {
        if (SelectedModule is null) { ErrorMessage = "Selecione um módulo."; return; }
        await Api.EnableModuleAsync(SelectedModule.Id);
        Message = $"{SelectedModule.Id} ativado.";
        await LoadCoreAsync();
    });

    [RelayCommand]
    private Task DisableAsync() => RunAsync(async () =>
    {
        if (SelectedModule is null) { ErrorMessage = "Selecione um módulo."; return; }
        await Api.DisableModuleAsync(SelectedModule.Id);
        Message = $"{SelectedModule.Id} desativado.";
        await LoadCoreAsync();
    });
}
