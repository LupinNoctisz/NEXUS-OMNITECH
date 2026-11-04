using System.Windows;
using Nexus.CoreClient;
using Nexus.Presentation;

namespace Nexus.App.Services;

/// <summary>
/// Troca o dicionário de cores (Dark/Light). A preferência "oficial" fica no núcleo; aqui só se guarda uma cópia
/// local para a tela de login já abrir no tema certo.
/// </summary>
public sealed class ThemeService : IThemeService
{
    private const int ThemeSlot = 0; // posição do dicionário de tema em App.xaml
    private readonly UiSettingsStore? _store;

    public ThemeService(UiSettingsStore? store = null) => _store = store;

    public string Current { get; private set; } = "dark";

    public void Apply(string theme)
    {
        var name = theme == "light" ? "light" : "dark";
        var uri = new Uri($"pack://application:,,,/Themes/{(name == "light" ? "Light" : "Dark")}.xaml", UriKind.Absolute);
        Application.Current.Resources.MergedDictionaries[ThemeSlot] = new ResourceDictionary { Source = uri };
        if (_store is not null && name != Current) _store.Update(s => s with { Theme = name });
        Current = name;
    }
}
