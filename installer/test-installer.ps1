<#
.SYNOPSIS
  Testa o instalador de verdade (silencioso): instala, valida atalhos e arquivos, executa o autoteste do app,
  abre a janela, confere instância única, fecha e confere que o núcleo Python encerrou, atualiza para uma versão
  nova preservando os dados e desinstala. Falha (exit != 0) no primeiro problema.
.EXAMPLE
  ./installer/test-installer.ps1 -Version 0.1.2 -NewVersion 0.1.3
#>
param(
    [string]$Version = "0.1.2",
    [string]$NewVersion = "0.1.3"
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$temp = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { $env:TEMP }
$work = Join-Path $temp ("nexus-install-test-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$app = Join-Path $work "app"
$dataHome = Join-Path $work "data"
New-Item -ItemType Directory -Force $work | Out-Null
$results = [System.Collections.Generic.List[string]]::new()
$password = "senha-ficticia-123"   # nexus:allow-secret (valor fictício de teste)

function Step([string]$name, [scriptblock]$body) {
    Write-Host "`n=== $name ==="
    & $body
    $results.Add("OK  $name")
    Write-Host "OK  $name"
}
function Assert([bool]$condition, [string]$message) {
    if (-not $condition) { throw "FALHOU: $message" }
}
function Run-Installer([string]$path, [string]$log) {
    $p = Start-Process $path -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
        "/DIR=`"$app`"", "/TASKS=desktopicon", "/LOG=`"$log`"") -Wait -PassThru
    Assert ($p.ExitCode -eq 0) "instalador terminou com código $($p.ExitCode) (log: $log)"
}
function Nexus-Processes { Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "nexus.* serve --stdio" } }
function Selftest([string]$tag) {
    $out = Join-Path $work "selftest-$tag.json"
    $env:NEXUS_HOME = $dataHome
    $p = Start-Process (Join-Path $app "NexusOmnitech.exe") -ArgumentList @("--selftest", "`"$out`"") -Wait -PassThru
    Assert (Test-Path $out) "autoteste não gerou o relatório"
    $report = Get-Content $out -Raw | ConvertFrom-Json
    Write-Host ($report | ConvertTo-Json)
    Assert ($p.ExitCode -eq 0) "autoteste terminou com código $($p.ExitCode): $($report.error)"
    Assert ($report.ok -eq $true) "autoteste não OK: $($report.error)"
    Assert ([version]$report.python_version -ge [version]"3.12") "Python < 3.12 ($($report.python_version))"
    Assert ($report.protocol -eq "1.0") "protocolo inesperado"
    Assert ($report.core_path -like "$app*") "o núcleo não veio da pasta instalada ($($report.core_path))"
    Assert ($report.core_killed_on_exit -eq $false) "o núcleo precisou ser finalizado à força"
    Assert ($report.core_exit_code -eq 0) "o núcleo saiu com código $($report.core_exit_code)"
    Assert ((Nexus-Processes).Count -eq 0) "sobrou processo do núcleo depois do autoteste"
    return $report
}

try {
    $installerV1 = Join-Path $root "build\installer\NexusOmnitech-Setup-$Version.exe"
    Assert (Test-Path $installerV1) "instalador não encontrado: $installerV1"
    $expectedHash = (Get-Content "$installerV1.sha256" -Raw).Split(" ")[0].Trim()

    Step "Integridade do instalador (SHA-256)" {
        $actual = (Get-FileHash $installerV1 -Algorithm SHA256).Hash.ToLower()
        Assert ($actual -eq $expectedHash) "SHA-256 diverge ($actual != $expectedHash)"
        $sig = (Get-Item $installerV1).Length
        Assert ($sig -gt 5MB) "instalador pequeno demais ($sig bytes)"
    }

    Step "Instalação silenciosa" {
        Run-Installer $installerV1 (Join-Path $work "install-v1.log")
        foreach ($rel in "NexusOmnitech.exe", "core\nexus\__init__.py", "core\nexus\core\app.py", "core\nexus\api\server.py",
            "modules\nexus.pc_diagnostics\manifest.json", "LICENSE") {
            Assert (Test-Path (Join-Path $app $rel)) "arquivo ausente após instalar: $rel"
        }
        Assert (-not (Test-Path (Join-Path $app "core\nexus\__pycache__"))) "__pycache__ foi empacotado"
    }

    Step "Atalhos e registro de desinstalação" {
        $shell = New-Object -ComObject WScript.Shell
        $start = Join-Path ([Environment]::GetFolderPath("Programs")) "NEXUS OMNITECH.lnk"
        $desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "NEXUS OMNITECH.lnk"
        Assert (Test-Path $start) "atalho do menu Iniciar ausente ($start)"
        Assert (Test-Path $desktop) "atalho da área de trabalho ausente ($desktop)"
        foreach ($lnk in $start, $desktop) {
            $target = $shell.CreateShortcut($lnk).TargetPath
            Assert ($target -eq (Join-Path $app "NexusOmnitech.exe")) "atalho $lnk aponta para $target"
        }
        $key = Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" | Where-Object { $_.PSChildName -like "{6F0B6B52-7C1E-4D55-9B1A-4E2C8E3A9D10}*" }
        Assert ($null -ne $key) "entrada de desinstalação ausente no registro"
        Assert ((Get-ItemProperty $key.PSPath).DisplayVersion -eq $Version) "versão registrada incorreta"
        Assert (Test-Path (Join-Path $app "unins000.exe")) "desinstalador ausente"
    }

    Step "Autoteste do aplicativo instalado (Python, núcleo, JSON-RPC, encerramento)" {
        $report = Selftest "v1"
        Assert ($report.initialized -eq $false) "banco novo deveria estar sem administrador"
    }

    Step "Criar dados reais (administrador + backup) com o núcleo instalado" {
        $env:PYTHONPATH = Join-Path $app "core"
        $env:PYTHONUTF8 = "1"
        "$password`n" | & python -m nexus --home $dataHome --password-stdin init --admin ci.admin
        Assert ($LASTEXITCODE -eq 0) "nexus init falhou"
        "$password`n" | & python -m nexus --home $dataHome --as ci.admin --password-stdin backup create
        Assert ($LASTEXITCODE -eq 0) "nexus backup create falhou"
        Remove-Item Env:PYTHONPATH
        Assert (Test-Path (Join-Path $dataHome "nexus.db")) "banco não foi criado"
        $script:dbHash = (Get-FileHash (Join-Path $dataHome "nexus.db") -Algorithm SHA256).Hash
        $script:backupNames = (Get-ChildItem (Join-Path $dataHome "backups") -Filter "nexus-*.db").Name -join ","
        Assert ($script:backupNames.Length -gt 0) "backup não foi criado"
    }

    Step "Abrir a janela, instância única, sem terminal e encerramento limpo" {
        $env:NEXUS_HOME = $dataHome
        $exe = Join-Path $app "NexusOmnitech.exe"
        $p = Start-Process $exe -PassThru
        $deadline = (Get-Date).AddSeconds(45)
        while ((Get-Date) -lt $deadline -and -not $p.HasExited) {
            $p.Refresh()
            if ($p.MainWindowHandle -ne 0 -and $p.MainWindowTitle -like "*NEXUS*") { break }
            Start-Sleep -Milliseconds 500
        }
        Assert (-not $p.HasExited) "o aplicativo fechou sozinho (código $($p.ExitCode)); veja $dataHome\logs\ui.log"
        $p.Refresh()
        Assert ($p.MainWindowHandle -ne 0) "a janela principal não apareceu em 45 s"
        Assert ($p.MainWindowTitle -like "*NEXUS OMNITECH*") "título inesperado: $($p.MainWindowTitle)"

        $children = @(Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $p.Id })
        Assert ($children.Count -ge 1) "o núcleo Python não foi iniciado pelo aplicativo"
        $names = ($children | ForEach-Object { $_.Name }) -join ","
        Assert (-not ($children | Where-Object { $_.Name -in @("cmd.exe", "conhost.exe", "powershell.exe", "pwsh.exe") })) "janela de terminal criada: $names"
        Assert ((Nexus-Processes).Count -eq 1) "deveria haver exatamente 1 núcleo em execução"

        $second = Start-Process $exe -PassThru
        Assert ($second.WaitForExit(20000)) "a segunda instância não encerrou sozinha"
        Assert (@(Get-Process -Name NexusOmnitech -ErrorAction SilentlyContinue).Count -eq 1) "há mais de uma instância do aplicativo"

        $null = $p.CloseMainWindow()
        Assert ($p.WaitForExit(20000)) "o aplicativo não fechou após fechar a janela"
        Start-Sleep -Seconds 1
        Assert ((Nexus-Processes).Count -eq 0) "o núcleo Python continuou em execução após fechar o aplicativo"
        Assert (Test-Path (Join-Path $env:APPDATA "NexusOmnitech\ui-settings.json")) "as preferências da janela não foram salvas"
        Assert (Test-Path (Join-Path $dataHome "logs")) "pasta de logs não existe"
    }

    Step "Atualização para $NewVersion preservando dados" {
        & (Join-Path $PSScriptRoot "build.ps1") -Version $NewVersion -SkipPublish
        $installerV2 = Join-Path $root "build\installer\NexusOmnitech-Setup-$NewVersion.exe"
        Assert (Test-Path $installerV2) "instalador novo não gerado"

        $stale = Join-Path $app "core\nexus\arquivo_obsoleto.py"
        "x = 1" | Set-Content $stale

        Run-Installer $installerV2 (Join-Path $work "install-v2.log")
        Assert (-not (Test-Path $stale)) "arquivo obsoleto do núcleo antigo não foi removido na atualização"
        Assert (Test-Path (Join-Path $app "core\nexus\core\app.py")) "núcleo ausente após atualizar"
        $key = Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" | Where-Object { $_.PSChildName -like "{6F0B6B52-7C1E-4D55-9B1A-4E2C8E3A9D10}*" }
        Assert ((Get-ItemProperty $key.PSPath).DisplayVersion -eq $NewVersion) "versão registrada não foi atualizada"

        Assert ((Get-FileHash (Join-Path $dataHome "nexus.db") -Algorithm SHA256).Hash -eq $script:dbHash) "o banco de dados foi alterado pela atualização"
        $backupsNow = (Get-ChildItem (Join-Path $dataHome "backups") -Filter "nexus-*.db").Name -join ","
        Assert ($backupsNow -eq $script:backupNames) "os backups mudaram na atualização"

        $report = Selftest "v2"
        Assert ($report.initialized -eq $true) "após atualizar, o administrador criado antes não foi encontrado"
        # (o instalador novo reaproveita os binários da pasta stage, então só o número do instalador/registro muda)
    }

    Step "Desinstalação silenciosa (dados preservados)" {
        $unins = Join-Path $app "unins000.exe"
        $p = Start-Process $unins -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
        Assert ($p.ExitCode -eq 0) "desinstalador terminou com código $($p.ExitCode)"
        $deadline = (Get-Date).AddSeconds(30)
        while ((Test-Path (Join-Path $app "NexusOmnitech.exe")) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
        Assert (-not (Test-Path (Join-Path $app "NexusOmnitech.exe"))) "o executável continua instalado"
        Assert (-not (Test-Path (Join-Path $app "core"))) "a pasta do núcleo continua instalada"
        Assert (-not (Test-Path (Join-Path ([Environment]::GetFolderPath("Programs")) "NEXUS OMNITECH.lnk"))) "atalho do menu Iniciar não foi removido"
        Assert (-not (Test-Path (Join-Path ([Environment]::GetFolderPath("Desktop")) "NEXUS OMNITECH.lnk"))) "atalho da área de trabalho não foi removido"
        $key = Get-ChildItem "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall" -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -like "{6F0B6B52-7C1E-4D55-9B1A-4E2C8E3A9D10}*" }
        Assert ($null -eq $key) "entrada de desinstalação continua no registro"
        Assert ((Get-FileHash (Join-Path $dataHome "nexus.db") -Algorithm SHA256).Hash -eq $script:dbHash) "desinstalação silenciosa alterou/removeu o banco de dados"
    }

    Write-Host "`n===== RESULTADO ====="
    $results | ForEach-Object { Write-Host $_ }
    Write-Host "Todos os passos passaram."
    exit 0
}
catch {
    Write-Host "`n===== FALHA =====" -ForegroundColor Red
    $results | ForEach-Object { Write-Host $_ }
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host $_.ScriptStackTrace
    foreach ($log in (Get-ChildItem $work -Filter "*.log" -ErrorAction SilentlyContinue)) { Write-Host "--- $($log.Name) (final) ---"; Get-Content $log.FullName -Tail 30 }
    $uiLog = Join-Path $dataHome "logs\ui.log"
    if (Test-Path $uiLog) { Write-Host "--- ui.log ---"; Get-Content $uiLog -Tail 40 }
    Get-Process -Name NexusOmnitech -ErrorAction SilentlyContinue | Stop-Process -Force
    exit 1
}
finally {
    Remove-Item Env:NEXUS_HOME -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
}
