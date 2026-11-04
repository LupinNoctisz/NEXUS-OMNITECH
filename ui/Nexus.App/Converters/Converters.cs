using System.Globalization;
using System.Windows;
using System.Windows.Data;
using System.Windows.Media;

namespace Nexus.App.Converters;

/// <summary>"ok" / "warning" / "critical" / outro → pincel do tema atual.</summary>
public sealed class LevelBrushConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var key = (value as string) switch
        {
            "ok" => "OkBrush",
            "warning" => "WarnBrush",
            "critical" => "CritBrush",
            _ => "MutedBrush",
        };
        return Application.Current.TryFindResource(key) as Brush ?? Brushes.Gray;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => throw new NotSupportedException();
}

/// <summary>true → verde, false → vermelho, null → cinza.</summary>
public sealed class BoolBrushConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
    {
        var key = value is bool b ? (b ? "OkBrush" : "CritBrush") : "MutedBrush";
        return Application.Current.TryFindResource(key) as Brush ?? Brushes.Gray;
    }

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => throw new NotSupportedException();
}

public sealed class InverseBoolConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture) => value is bool b && !b;
    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => value is bool b && !b;
}

/// <summary>Texto não vazio → visível; vazio/nulo → recolhido.</summary>
public sealed class TextVisibilityConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => string.IsNullOrEmpty(value as string) ? Visibility.Collapsed : Visibility.Visible;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => throw new NotSupportedException();
}

/// <summary>Número &gt; 0 → visível.</summary>
public sealed class CountVisibleConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => value is int n && n > 0 ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => throw new NotSupportedException();
}

/// <summary>Nulo → visível (placeholder "nada selecionado"); com valor → recolhido.</summary>
public sealed class NullVisibleConverter : IValueConverter
{
    public object Convert(object value, Type targetType, object parameter, CultureInfo culture)
        => value is null ? Visibility.Visible : Visibility.Collapsed;

    public object ConvertBack(object value, Type targetType, object parameter, CultureInfo culture) => throw new NotSupportedException();
}
