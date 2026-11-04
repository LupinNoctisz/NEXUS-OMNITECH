using System.Windows;
using Nexus.Presentation;

namespace Nexus.App.Services;

public sealed class DialogService : IDialogService
{
    public Task<bool> ConfirmAsync(string title, string message, string confirmText, string? requiredText = null)
    {
        var dialog = new ConfirmDialog(title, message, confirmText, requiredText)
        {
            Owner = Application.Current.MainWindow,
        };
        return Task.FromResult(dialog.ShowDialog() == true);
    }

    public void ShowInfo(string title, string message)
        => MessageBox.Show(Application.Current.MainWindow, message, title, MessageBoxButton.OK, MessageBoxImage.Information);
}
