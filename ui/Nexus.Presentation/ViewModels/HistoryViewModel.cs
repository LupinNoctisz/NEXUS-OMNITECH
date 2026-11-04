using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public sealed partial class HistoryViewModel : PageViewModel
{
    private List<OperationRow> _all = new();

    public HistoryViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs) : base(api, session, dialogs) { }

    public override string Title => "Histórico";

    public ObservableCollection<OperationRow> Operations { get; } = new();

    public IReadOnlyList<int> LimitOptions { get; } = new[] { 50, 100, 200, 500 };

    [ObservableProperty] private int _selectedLimit = 100;
    [ObservableProperty] private string _filterText = "";
    [ObservableProperty] private string _chainText = "";
    [ObservableProperty] private bool? _chainOk;
    [ObservableProperty] private string _countText = "";

    partial void OnFilterTextChanged(string value) => ApplyFilter();

    protected override async Task LoadCoreAsync()
    {
        var list = await Api.ListAuditAsync(SelectedLimit);
        _all = list.Select(o => new OperationRow(o)).ToList();
        ApplyFilter();
    }

    private void ApplyFilter()
    {
        Operations.Clear();
        foreach (var row in _all.Where(r => r.Matches(FilterText))) Operations.Add(row);
        CountText = $"{Operations.Count} de {_all.Count} registro(s) carregado(s)";
    }

    [RelayCommand]
    private Task VerifyAsync() => RunAsync(async () =>
    {
        var result = await Api.VerifyAuditAsync();
        ChainOk = result.Ok;
        ChainText = result.Ok
            ? $"Cadeia íntegra: {result.Records} registro(s) verificado(s)."
            : $"ADULTERAÇÃO detectada a partir do registro {result.FirstBadId}.";
    });
}
