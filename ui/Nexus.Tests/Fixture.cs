using System.Text.Json;
using Nexus.CoreClient;

namespace Nexus.Tests;

/// <summary>Respostas reais do núcleo (geradas por scripts/dump_rpc_fixtures.py, com dados fictícios).</summary>
internal static class Fixture
{
    private static string PathOf(string name) => Path.Combine(AppContext.BaseDirectory, "Fixtures", name + ".json");

    public static T Result<T>(string name)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(PathOf(name)));
        return document.RootElement.GetProperty("result").Deserialize<T>(CoreJson.Options)!;
    }

    public static (int Code, string Message, string Type) Error(string name)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(PathOf(name)));
        var error = document.RootElement.GetProperty("error");
        return (error.GetProperty("code").GetInt32(),
                error.GetProperty("message").GetString()!,
                error.GetProperty("data").GetProperty("type").GetString()!);
    }
}
