; NEXUS OMNITECH — instalador (Inno Setup 6). Compile com installer\build.ps1.
; Instala POR USUÁRIO por padrão (sem administrador); o diálogo permite instalar para todos.
; Dados do usuário (banco, backups, logs) ficam em %LOCALAPPDATA%\NexusOmnitech e NUNCA são tocados
; por instalação/atualização; a desinstalação só os remove se o usuário confirmar explicitamente.

#ifndef AppVersion
  #define AppVersion "0.1.3"
#endif
#ifndef StageDir
  #define StageDir "..\build\stage"
#endif
#ifndef OutDir
  #define OutDir "..\build\installer"
#endif

#define AppName "NEXUS OMNITECH"
#define AppExe "NexusOmnitech.exe"

[Setup]
AppId={{6F0B6B52-7C1E-4D55-9B1A-4E2C8E3A9D10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=LMF Informática
VersionInfoVersion={#AppVersion}
VersionInfoCompany=LMF Informática
VersionInfoProductName={#AppName}
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutDir}
OutputBaseFilename=NexusOmnitech-Setup-{#AppVersion}
SetupIconFile=..\ui\Nexus.App\Assets\nexus.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
AppMutex=NexusOmnitech.SingleInstance
CloseApplications=no

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; limpa o núcleo e os módulos embutidos da versão anterior (arquivos removidos não podem sobrar).
; Isto NÃO inclui dados do usuário: eles ficam em %LOCALAPPDATA%\NexusOmnitech.
Type: filesandordirs; Name: "{app}\core"
Type: filesandordirs; Name: "{app}\modules"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; arquivos gerados em tempo de execução dentro da pasta do programa (ex.: __pycache__)
Type: filesandordirs; Name: "{app}\core"

[Code]
function PythonKeyExists(const Root: Integer; const Minor: Integer): Boolean;
var
  Key: String;
begin
  Key := 'SOFTWARE\Python\PythonCore\3.' + IntToStr(Minor);
  Result := RegKeyExists(Root, Key) or RegKeyExists(Root, 'SOFTWARE\WOW6432Node\Python\PythonCore\3.' + IntToStr(Minor));
end;

function UvPythonExists(const Base: String): Boolean;
var
  FindRec: TFindRec;
begin
  Result := False;
  if FindFirst(Base + '\uv\python\cpython-3.*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
        begin
          if FileExists(Base + '\uv\python\' + FindRec.Name + '\python.exe') then
          begin
            Result := True;
            Break;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

{ Verificação aproximada (o aplicativo faz a verificação definitiva ao abrir). Não bloqueia em instalação silenciosa. }
function PythonLooksInstalled(): Boolean;
var
  Minor: Integer;
begin
  Result := FileExists(ExpandConstant('{win}\py.exe'));
  for Minor := 12 to 20 do
  begin
    if PythonKeyExists(HKEY_CURRENT_USER, Minor) or PythonKeyExists(HKEY_LOCAL_MACHINE, Minor) then
      Result := True;
  end;
  if UvPythonExists(ExpandConstant('{userappdata}')) or UvPythonExists(ExpandConstant('{localappdata}')) then
    Result := True;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if (not WizardSilent()) and (not PythonLooksInstalled()) then
  begin
    Result := MsgBox(
      'Não foi detectado o Python 3.12 (ou mais novo) neste computador.' + #13#10#13#10 +
      'O NEXUS OMNITECH precisa dele para abrir. Você pode instalar o Python agora ou depois ' +
      '(por exemplo: winget install Python.Python.3.12) e, se necessário, indicar o python.exe ao abrir o NEXUS.' + #13#10#13#10 +
      'Deseja continuar a instalação mesmo assim?', mbConfirmation, MB_YESNO) = IDYES;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir, ConfigDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\NexusOmnitech');
    ConfigDir := ExpandConstant('{userappdata}\NexusOmnitech');
    { Desinstalação silenciosa NUNCA apaga dados. }
    if (not UninstallSilent()) and (DirExists(DataDir) or DirExists(ConfigDir)) then
    begin
      if MsgBox(
        'O NEXUS OMNITECH foi removido.' + #13#10#13#10 +
        'Deseja também APAGAR os dados do usuário (banco de dados, backups, logs e configurações)?' + #13#10 +
        DataDir + #13#10#13#10 +
        'Esta ação NÃO pode ser desfeita. Se tiver dúvida, responda Não: os dados serão mantidos e reaproveitados numa futura instalação.',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      begin
        DelTree(DataDir, True, True, True);
        DelTree(ConfigDir, True, True, True);
      end;
    end;
  end;
end;
