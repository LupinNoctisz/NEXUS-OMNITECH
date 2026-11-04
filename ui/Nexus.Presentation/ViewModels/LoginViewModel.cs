using CommunityToolkit.Mvvm.ComponentModel;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public sealed partial class LoginViewModel : ObservableObject
{
    private readonly ICoreApi _api;
    private readonly ISessionContext _session;

    public LoginViewModel(ICoreApi api, ISessionContext session)
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

    /// <summary>A senha é passada direto do PasswordBox e nunca é guardada no ViewModel.</summary>
    public async Task<bool> TryLoginAsync(string password)
    {
        if (IsBusy) return false;
        if (string.IsNullOrWhiteSpace(Name) || string.IsNullOrEmpty(password))
        {
            ErrorMessage = "Informe o técnico e a senha.";
            return false;
        }

        IsBusy = true;
        ErrorMessage = null;
        try
        {
            var who = await _api.LoginAsync(Name.Trim(), password);
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
