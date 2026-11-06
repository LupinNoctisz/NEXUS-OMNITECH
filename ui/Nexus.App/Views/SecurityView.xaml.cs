using System.Windows;
using System.Windows.Controls;
using Nexus.Presentation;

namespace Nexus.App.Views;

public partial class SecurityView : UserControl
{
    public SecurityView() => InitializeComponent();

    private SecurityViewModel? Vm => DataContext as SecurityViewModel;

    private async void AddTechnician_Click(object sender, RoutedEventArgs e)
    {
        if (Vm is null) return;
        var ok = await Vm.AddTechnicianAsync(TechPasswordBox.Password, TechConfirmBox.Password);
        if (ok) Clear(TechPasswordBox, TechConfirmBox);
    }

    private static void Clear(params PasswordBox[] boxes)
    {
        foreach (var box in boxes) box.Clear();
    }
}
