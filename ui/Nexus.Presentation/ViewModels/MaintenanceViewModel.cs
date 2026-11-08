using System.Collections.ObjectModel;
using Nexus.CoreClient;

namespace Nexus.Presentation;

/// <summary>
/// Aba "Manutenção": só lista os módulos de manutenção instalados, por categoria
/// (celular, computador, console, notebook). Não traz conteúdo próprio: o conteúdo vem dos módulos.
/// </summary>
public sealed class MaintenanceViewModel : PageViewModel
{
    public MaintenanceViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs) : base(api, session, dialogs) { }

    public override string Title => "Manutenção";

    public ObservableCollection<MaintenanceCategoryRow> Categories { get; } = new();

    protected override async Task LoadCoreAsync()
    {
        var list = await Api.ListMaintenanceAsync();
        Categories.Clear();
        foreach (var category in list) Categories.Add(new MaintenanceCategoryRow(category));
    }
}
