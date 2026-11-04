using System.Windows;
using Nexus.Presentation;

namespace Nexus.App.Services;

/// <summary>Troca o dicionário de cores (Dark/Light). A preferência é gravada pelo núcleo, não aqui.</summary>
public sealed class ThemeService : IThemeService
{
    private const int ThemeSlot = 0; // posição do dicionário de tema em App.xaml

    public string Current { get; private set; } = "dark";

    public void Apply(string theme)
    {
        var name = theme == "light" ? "light" : "dark";
        var uri = new Uri($"pack://application:,,,/Themes/{(name == "light" ? "Light" : "Dark")}.xaml", UriKind.Absolute);
        Application.Current.Resources.MergedDictionaries[ThemeSlot] = new ResourceDictionary { Source = uri };
        Current = name;
    }
}
