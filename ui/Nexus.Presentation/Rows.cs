using Nexus.CoreClient;

namespace Nexus.Presentation;

public sealed class DeviceRow
{
    public DeviceRow(DeviceDto device) { Device = device; }

    public DeviceDto Device { get; }
    public long Id => Device.Id;
    public string Title => Device.Label ?? Device.Model ?? Device.Uid;
    public string KindText => Labels.Kind(Device.Kind);
    public string Vendor => Device.Vendor ?? "—";
    public string Model => Device.Model ?? "—";
    public string Serial => Device.Serial ?? "—";
    public string ConnectionText => Labels.Connection(Device.Connection);
    public bool IsConnected => Device.Connection == "connected";
    public string SourceText => Device.Source;
    public string LastSeen => TimeText.Local(Device.LastSeen);
    public string FirstSeen => TimeText.Local(Device.FirstSeen);
}

public sealed class SessionRow
{
    public SessionRow(SessionDto session) { Session = session; }

    public SessionDto Session { get; }
    public long Id => Session.Id;
    public string DeviceText => Session.DeviceLabel ?? Session.DeviceModel ?? $"Dispositivo #{Session.DeviceId}";
    public string KindText => Labels.SessionKind(Session.Kind);
    public string StatusText => Labels.SessionStatus(Session.Status);
    public bool IsOpen => Session.Status == "open";
    public string Technician => Session.Technician;
    public string Started => TimeText.Local(Session.StartedAt);
    public string Ended => TimeText.Local(Session.EndedAt);
    public string Summary => Session.Summary ?? "";
}

public sealed class OperationRow
{
    public OperationRow(OperationDto operation) { Operation = operation; }

    public OperationDto Operation { get; }
    public long Id => Operation.Id;
    public string When => TimeText.Local(Operation.Ts);
    public string Technician => Operation.Technician;
    public string Action => Operation.Action;
    public string Target => Operation.Target ?? "";
    public string Outcome => Operation.Outcome;
    public string Details => Operation.Details == "{}" ? "" : Operation.Details;
    public string HashShort => Operation.Hash.Length >= 12 ? Operation.Hash[..12] : Operation.Hash;

    public bool Matches(string filter)
    {
        if (string.IsNullOrWhiteSpace(filter)) return true;
        var text = filter.Trim();
        return Action.Contains(text, StringComparison.OrdinalIgnoreCase)
            || Technician.Contains(text, StringComparison.OrdinalIgnoreCase)
            || Target.Contains(text, StringComparison.OrdinalIgnoreCase)
            || Outcome.Contains(text, StringComparison.OrdinalIgnoreCase)
            || Details.Contains(text, StringComparison.OrdinalIgnoreCase);
    }
}

public sealed class ModuleRow
{
    public ModuleRow(ModuleStatusDto module) { Module = module; }

    public ModuleStatusDto Module { get; }
    public string Id => Module.Id;
    public string Name => Module.Name;
    public string Version => Module.Version;
    public string Publisher => Module.Publisher;
    public bool IsAvailable => Module.Status == "available";
    public string StatusText => Labels.ModuleStatus(Module.Status);

    public string StateText
    {
        get
        {
            if (!IsAvailable) return "Não implementado";
            if (!Module.Registered) return "Não registrado";
            if (!Module.Enabled) return "Registrado (desativado)";
            return Module.Loaded ? "Ativo e carregado" : "Ativo (não carregado)";
        }
    }

    public string IntegrityText => Module.IntegrityOk switch
    {
        null => "—",
        true => "Íntegro",
        false => "FALHOU",
    };

    public bool IntegrityFailed => Module.IntegrityOk == false;
    public string Problems => string.Join(Environment.NewLine, Module.Problems);
    public bool CanRegister => IsAvailable && !Module.Registered;
    public bool CanEnable => IsAvailable && Module.Registered && !Module.Enabled;
    public bool CanDisable => Module.Registered && Module.Enabled;
}

public sealed class BackupRow
{
    public BackupRow(BackupDto backup) { Backup = backup; }

    public BackupDto Backup { get; }
    public string Name => Backup.Name;
    public string Modified => TimeText.Local(Backup.ModifiedUtc);
    public string ChecksumText => Backup.HasChecksum ? "Sim" : "Não";

    public string SizeText
    {
        get
        {
            var size = Backup.SizeBytes;
            if (size >= 1024 * 1024) return $"{size / (1024.0 * 1024.0):0.0} MB";
            if (size >= 1024) return $"{size / 1024.0:0.0} KB";
            return $"{size} B";
        }
    }
}

public sealed class TechnicianRow
{
    public TechnicianRow(TechnicianDto technician) { Technician = technician; }

    public TechnicianDto Technician { get; }
    public string Name => Technician.Name;
    public string RoleText => Labels.Role(Technician.Role);
    public bool Active => Technician.Active;
    public string ActiveText => Technician.Active ? "Ativo" : "Inativo";
    public string PasswordText => Technician.HasPassword ? "Definida" : "SEM SENHA";
    public string LockText => string.IsNullOrEmpty(Technician.LockedUntil) ? "" : "Bloqueado até " + TimeText.Local(Technician.LockedUntil);
}
