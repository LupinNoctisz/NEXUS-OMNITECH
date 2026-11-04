using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Nexus.Presentation;

namespace Nexus.App.Views;

public partial class LoginView : UserControl
{
    private readonly LoginViewModel _viewModel;
    private readonly Func<Task> _onSuccess;

    public LoginView(LoginViewModel viewModel, Func<Task> onSuccess)
    {
        InitializeComponent();
        _viewModel = viewModel;
        _onSuccess = onSuccess;
        DataContext = viewModel;
        Loaded += (_, _) => NameBox.Focus();
    }

    private async void Login_Click(object sender, RoutedEventArgs e) => await TryLoginAsync();

    private async void PasswordBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) await TryLoginAsync();
    }

    private async Task TryLoginAsync()
    {
        var ok = await _viewModel.TryLoginAsync(PasswordBox.Password);
        PasswordBox.Clear(); // a senha não permanece na tela nem na memória da interface
        if (ok) await _onSuccess();
        else PasswordBox.Focus();
    }
}
