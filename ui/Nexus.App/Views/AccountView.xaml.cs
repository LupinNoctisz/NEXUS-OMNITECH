using System.Windows;
using System.Windows.Controls;
using Nexus.Presentation;

namespace Nexus.App.Views;

public partial class AccountView : UserControl
{
    public AccountView() => InitializeComponent();

    private async void ChangePassword_Click(object sender, RoutedEventArgs e)
    {
        if (DataContext is not AccountViewModel vm) return;
        var ok = await vm.ChangePasswordAsync(OldBox.Password, NewBox.Password, NewConfirmBox.Password);
        if (ok)
        {
            OldBox.Clear();
            NewBox.Clear();
            NewConfirmBox.Clear();
        }
    }
}
