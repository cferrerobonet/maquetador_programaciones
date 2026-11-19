#define MyAppName "Maquetador de programaciones"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "Carlos Ferrero Bonet"
#define MyAppExeName "MaquetadorProgramaciones.exe"

[Setup]
AppId={{0AE1B171-E74E-4355-9A99-6F10DDACB0BE}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Maquetador de programaciones
DefaultGroupName=Maquetador de programaciones
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
OutputDir=Output
OutputBaseFilename=MaquetadorProgramaciones-{#MyAppVersion}-Windows-Setup
ArchitecturesInstallIn64BitMode=x64compatible
; Sin exigir administrador: en el centro casi nadie lo es.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
SetupIconFile=imagenes\icono.ico

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "dist\MaquetadorProgramaciones\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Maquetador de programaciones"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Maquetador de programaciones"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir el Maquetador de programaciones"; Flags: nowait postinstall skipifsilent

[Code]
{ Se cierra la app antes de copiar (CloseApplications). Los ajustes viven en
  %APPDATA%\MaquetadorProgramaciones, fuera del programa, y desinstalar no los toca. }

function DesinstaladorAnterior(): String;
var
  Clave: String;
  Valor: String;
begin
  Result := '';
  Clave := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
           ExpandConstant('{#SetupSetting("AppId")}') + '_is1';
  if RegQueryStringValue(HKCU, Clave, 'UninstallString', Valor) then
    Result := Valor
  else if RegQueryStringValue(HKLM, Clave, 'UninstallString', Valor) then
    Result := Valor;
  Result := RemoveQuotes(Result);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Desinstalador: String;
  Codigo: Integer;
  Espera: Integer;
begin
  Result := '';
  Desinstalador := DesinstaladorAnterior();
  if (Desinstalador = '') or (not FileExists(Desinstalador)) then
    exit;
  if not Exec(Desinstalador, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
              SW_HIDE, ewWaitUntilTerminated, Codigo) then
    exit;
  Espera := 0;
  while FileExists(Desinstalador) and (Espera < 60) do
  begin
    Sleep(500);
    Espera := Espera + 1;
  end;
end;
