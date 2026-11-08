using System.Collections.ObjectModel;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public sealed partial class DevicesViewModel : PageViewModel
{
    public DevicesViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs) : base(api, session, dialogs) { }

    public override string Title => "Dispositivos";

    public ObservableCollection<DeviceRow> Devices { get; } = new();
    public ObservableCollection<KeyValueRow> Details { get; } = new();

    public IReadOnlyList<Option> KindOptions { get; } = new List<Option>
    {
        new("pc", "Computador"), new("usb", "USB"), new("mobile", "Móvel"), new("console", "Console"), new("other", "Outro"),
    };

    public bool CanManage => Session.Can("devices.manage");

    [ObservableProperty] private DeviceRow? _selectedDevice;
    [ObservableProperty] private string? _message;
    [ObservableProperty] private string _newKind = "pc";
    [ObservableProperty] private string _newVendor = "";
    [ObservableProperty] private string _newModel = "";
    [ObservableProperty] private string _newSerial = "";
    [ObservableProperty] private string _newLabel = "";
    [ObservableProperty] private string _identifyText = "";

    partial void OnSelectedDeviceChanged(DeviceRow? value)
    {
        Details.Clear();
        if (value is null) return;
        Details.Add(new KeyValueRow("Identificador interno", value.Device.Uid));
        Details.Add(new KeyValueRow("Origem", value.SourceText));
        Details.Add(new KeyValueRow("Primeira vez visto", value.FirstSeen));
        Details.Add(new KeyValueRow("Última vez visto", value.LastSeen));
        foreach (var pair in value.Device.Properties.OrderBy(p => p.Key))
        {
            Details.Add(new KeyValueRow(pair.Key, Labels.Describe(pair.Value)));
        }
    }

    protected override async Task LoadCoreAsync()
    {
        var selectedId = SelectedDevice?.Id;
        var list = await Api.ListDevicesAsync();
        Devices.Clear();
        foreach (var device in list) Devices.Add(new DeviceRow(device));
        SelectedDevice = selectedId is null ? null : Devices.FirstOrDefault(d => d.Id == selectedId);
    }

    [RelayCommand]
    private Task ScanAsync() => RunAsync(async () =>
    {
        var result = await Api.ScanDevicesAsync();
        Message = $"{result.Found} dispositivo(s) encontrado(s)."
            + (result.Errors.Count == 0
                ? ""
                : " Falhas: " + string.Join("; ", result.Errors.Select(e => $"{e.Key}: {e.Value}")));
        await LoadCoreAsync();
    });

    // Separa o texto colado (etiqueta, caixa, OS) em fabricante/modelo/serial. É só uma SUGESTÃO:
    // os campos são preenchidos para o técnico conferir e nada é gravado até clicar em "Cadastrar".
    [RelayCommand]
    private Task IdentifyAsync() => RunAsync(async () =>
    {
        if (string.IsNullOrWhiteSpace(IdentifyText))
        {
            ErrorMessage = "Cole ou digite o texto da etiqueta (fabricante, modelo, S/N).";
            return;
        }
        var result = await Api.IdentifyDeviceAsync(IdentifyText.Trim());
        if (result.Kind is not null) NewKind = result.Kind;
        NewVendor = result.Vendor ?? "";
        NewModel = result.Model ?? "";
        NewSerial = result.Serial ?? "";
        var notes = new List<string>(result.Warnings);
        foreach (var pair in result.Alternatives.Where(p => p.Key == "serial"))
        {
            notes.Add("Seriais possíveis: " + string.Join(", ", pair.Value));
        }
        Message = "Sugestão preenchida; confira antes de cadastrar."
            + (notes.Count == 0 ? "" : " " + string.Join(" ", notes));
    });

    [RelayCommand]
    private Task AddAsync() => RunAsync(async () =>
    {
        static string? Clean(string value) => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

        var vendor = Clean(NewVendor);
        var model = Clean(NewModel);
        var serial = Clean(NewSerial);
        var label = Clean(NewLabel);
        if (vendor is null && model is null && serial is null && label is null)
        {
            ErrorMessage = "Informe ao menos fabricante, modelo, serial ou identificação.";
            return;
        }
        await Api.AddDeviceAsync(NewKind, vendor, model, serial, label);
        NewVendor = NewModel = NewSerial = NewLabel = IdentifyText = "";
        Message = "Dispositivo cadastrado.";
        await LoadCoreAsync();
    });
}
