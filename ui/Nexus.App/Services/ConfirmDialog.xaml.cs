using System.Windows;
using System.Windows.Controls;

namespace Nexus.App.Services;

public partial class ConfirmDialog : Window
{
    private readonly string? _required;

    public ConfirmDialog(string title, string message, string confirmText, string? requiredText)
    {
        InitializeComponent();
        Title = title;
        MessageText.Text = message;
        ConfirmButton.Content = confirmText;
        _required = requiredText;
        if (_required is not null)
        {
            TypedPanel.Visibility = Visibility.Visible;
            TypedHint.Text = $"Para confirmar, digite {_required}:";
            ConfirmButton.IsEnabled = false;
        }
    }

    private void TypedBox_TextChanged(object sender, TextChangedEventArgs e)
        => ConfirmButton.IsEnabled = _required is null || TypedBox.Text == _required;

    private void Confirm_Click(object sender, RoutedEventArgs e) => DialogResult = true;

    private void Cancel_Click(object sender, RoutedEventArgs e) => DialogResult = false;
}
