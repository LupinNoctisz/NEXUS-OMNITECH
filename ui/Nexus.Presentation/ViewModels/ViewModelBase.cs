using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Nexus.CoreClient;

namespace Nexus.Presentation;

public abstract partial class ViewModelBase : ObservableObject
{
    [ObservableProperty]
    private bool _isBusy;

    [ObservableProperty]
    [NotifyPropertyChangedFor(nameof(HasError))]
    private string? _errorMessage;

    public bool HasError => !string.IsNullOrEmpty(ErrorMessage);

    /// <summary>O núcleo informou que não há sessão autenticada (ex.: backup restaurado sem o técnico).</summary>
    public event EventHandler? SessionLost;

    protected void RaiseSessionLost() => SessionLost?.Invoke(this, EventArgs.Empty);

    /// <summary>
    /// Executa uma operação do núcleo sem travar a interface: marca ocupado, limpa/mostra o erro
    /// e converte falhas esperadas em mensagem. Ignora chamadas enquanto outra está em andamento.
    /// </summary>
    protected async Task<bool> RunAsync(Func<Task> action)
    {
        if (IsBusy) return false;
        IsBusy = true;
        ErrorMessage = null;
        try
        {
            await action();
            return true;
        }
        catch (RpcException ex) when (ex.Code == RpcCodes.NotAuthenticated)
        {
            ErrorMessage = ex.Message;
            RaiseSessionLost();
            return false;
        }
        catch (CoreException ex)
        {
            ErrorMessage = ex.Message;
            return false;
        }
        catch (Exception ex)
        {
            ErrorMessage = "Erro inesperado: " + ex.Message;
            return false;
        }
        finally
        {
            IsBusy = false;
        }
    }
}

public abstract partial class PageViewModel : ViewModelBase
{
    protected PageViewModel(ICoreApi api, ISessionContext session, IDialogService dialogs)
    {
        Api = api;
        Session = session;
        Dialogs = dialogs;
    }

    protected ICoreApi Api { get; }
    protected ISessionContext Session { get; }
    protected IDialogService Dialogs { get; }

    public abstract string Title { get; }

    /// <summary>Carrega os dados reais da página a partir do núcleo.</summary>
    protected abstract Task LoadCoreAsync();

    public Task LoadAsync() => RunAsync(LoadCoreAsync);

    [RelayCommand]
    private Task RefreshAsync() => LoadAsync();
}
