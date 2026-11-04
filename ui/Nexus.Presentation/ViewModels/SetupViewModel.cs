using CommunityToolkit.Mvvm.ComponentModel;
using Nexus.CoreClient;

namespace Nexus.Presentation;

/// <summary>Primeiro uso: cria o administrador inicial (o núcleo só aceita enquanto não existir nenhum técnico).</summary>
public sealed partial class SetupViewModel : ObservableObject
{
    private readonly ICoreApi _api;
    private readonly ISessionContext _session;

    public SetupViewModel(ICoreApi api, ISessionContext session)
    {
        _api = api;
        _session = session;
    }

    [ObservableProperty]
    private string _name = "";

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasError))]
    private string? _errorMessage;

    [ObservableProperty]
    private bool _isBusy;

    public bool HasError => !string.IsNullOrEmpty(ErrorMessage);

    /// <summary>As senhas vêm direto dos PasswordBox e nunca são guardadas aqui.</summary>
    public async Task<bool> TrySetupAsync(string password, string confirmation)
    {
        if (IsBusy) return false;
        if (string.IsNullOrWhiteSpace(Name))
        {
            ErrorMessage = "Informe o nome do administrador.";
            return false;
        }
        if (password != confirmation)
        {
            ErrorMessage = "A confirmação não confere com a senha.";
            return false;
        }

        IsBusy = true;
        ErrorMessage = null;
        try
        {
            var who = await _api.CreateAdminAsync(Name.Trim(), password);
            _session.Set(who);
            return true;
        }
        catch (CoreException ex)
        {
            ErrorMessage = ex.Message;
            return false;
        }
        finally
        {
            IsBusy = false;
        }
    }
}
