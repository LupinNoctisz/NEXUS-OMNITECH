<#
.SYNOPSIS
  Gera o instalador do NEXUS OMNITECH (publicação .NET + núcleo Python + Inno Setup).
.EXAMPLE
  ./installer/build.ps1 -Version 0.1.1
.NOTES
  Requer: .NET 8 SDK e Inno Setup 6 (ISCC.exe). Saída: build\installer\NexusOmnitech-Setup-<versão>.exe (+ .sha256).
  -SkipPublish reaproveita build\stage (usado nos testes de atualização, só para mudar o número da versão do instalador).
#>
param(
    [string]$Version = "0.1.1",
    [switch]$SkipPublish
)
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$build = Join-Path $root "build"
$publish = Join-Path $build "publish"
$stage = Join-Path $build "stage"
$out = Join-Path $build "installer"

function Find-Iscc {
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($path in @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
            "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
        if (Test-Path $path) { return $path }
    }
    throw "Inno Setup 6 (ISCC.exe) não encontrado. Instale com: winget install JRSoftware.InnoSetup"
}

if (-not $SkipPublish) {
    if (Test-Path $build) { Remove-Item $build -Recurse -Force }
    New-Item -ItemType Directory -Force $publish, $stage, $out | Out-Null

    Write-Host "== Publicando a interface (self-contained, win-x64) =="
    dotnet publish (Join-Path $root "ui\Nexus.App\Nexus.App.csproj") -c Release -r win-x64 --self-contained true `
        -p:Version=$Version -p:PublishSingleFile=false -o $publish
    if ($LASTEXITCODE -ne 0) { throw "dotnet publish falhou ($LASTEXITCODE)" }

    Write-Host "== Montando a pasta de instalação =="
    Copy-Item (Join-Path $publish "*") $stage -Recurse -Force
    $core = Join-Path $stage "core\nexus"
    New-Item -ItemType Directory -Force $core | Out-Null
    robocopy (Join-Path $root "src\nexus") $core /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy do núcleo falhou ($LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
    $modules = Join-Path $stage "modules"
    New-Item -ItemType Directory -Force $modules | Out-Null
    robocopy (Join-Path $root "modules") $modules /E /XD __pycache__ /XF *.pyc /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy dos módulos falhou ($LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
    Copy-Item (Join-Path $root "LICENSE") $stage -Force
}
New-Item -ItemType Directory -Force $out | Out-Null

Write-Host "== Compilando o instalador (Inno Setup) =="
$iscc = Find-Iscc
& $iscc "/DAppVersion=$Version" "/DStageDir=$stage" "/DOutDir=$out" (Join-Path $PSScriptRoot "nexus.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou ($LASTEXITCODE)" }

$installer = Join-Path $out "NexusOmnitech-Setup-$Version.exe"
$hash = (Get-FileHash $installer -Algorithm SHA256).Hash.ToLower()
"$hash  $(Split-Path $installer -Leaf)" | Set-Content -Encoding ascii "$installer.sha256"
Write-Host "Instalador: $installer"
Write-Host "SHA-256:    $hash"
