using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Nexus.Presentation;

namespace Nexus.App.Views;

public partial class SetupView : UserControl
{
    private readonly SetupViewModel _viewModel;
    private readonly Func<Task> _onSuccess;

    public SetupView(SetupViewModel viewModel, Func<Task> onSuccess)
    {
        InitializeComponent();
        _viewModel = viewModel;
        _onSuccess = onSuccess;
        DataContext = viewModel;
        Loaded += (_, _) => NameBox.Focus();
    }

    private async void Create_Click(object sender, RoutedEventArgs e) => await TrySetupAsync();

    private async void ConfirmBox_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) await TrySetupAsync();
    }

    private async Task TrySetupAsync()
    {
        var ok = await _viewModel.TrySetupAsync(PasswordBox.Password, ConfirmBox.Password);
        PasswordBox.Clear();
        ConfirmBox.Clear();
        if (ok) await _onSuccess();
        else PasswordBox.Focus();
    }
}
