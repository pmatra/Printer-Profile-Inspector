; Compile after build.ps1. One stable AppId upgrades existing installations.
#ifndef AppVersion
  #error AppVersion must be provided by build-installer.ps1
#endif
#define AppName "ICC Profile Inspector"
#define AppExe "ICC Gamut Inspector.exe"

[Setup]
AppId={{6650BC65-5B27-4C12-897C-987F6C378E37}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Peter Matra
AppPublisherURL=https://github.com/pmatra/Printer-Profile-Inspector
AppUpdatesURL=https://github.com/pmatra/Printer-Profile-Inspector/releases
DefaultDirName={autopf}\ICC Profile Inspector
DisableDirPage=no
DisableProgramGroupPage=yes
DisableWelcomePage=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=commandline
MinVersion=10.0
OutputDir=..\dist\installer
OutputBaseFilename=ICC-Profile-Inspector-Setup-v{#AppVersion}-x64
UninstallDisplayIcon={app}\{#AppExe}
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}.0
LicenseFile=..\LICENSE

[Files]
Source: "..\dist\ICC Gamut Inspector\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "INNO_SETUP_LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Description: "Open ICC Profile Inspector"; Flags: postinstall nowait skipifsilent runasoriginaluser unchecked

[UninstallDelete]
Type: files; Name: "{autoprograms}\ICC Profile Inspector.lnk"; Check: DeleteStartMenuShortcut
Type: files; Name: "{autodesktop}\ICC Profile Inspector.lnk"; Check: DeleteDesktopShortcut
Type: files; Name: "{app}\installer-shortcuts.ini"
; Settings and categories in each user's AppData are deliberately preserved.

[Code]
var
  ShortcutPage: TInputOptionWizardPage;
  ShortcutsCreated: Boolean;
  OwnStartMenuShortcut, OwnDesktopShortcut: Boolean;

function InitializeUninstall: Boolean;
begin
  OwnStartMenuShortcut := GetIniBool('Shortcuts', 'StartMenu', False,
    ExpandConstant('{app}\installer-shortcuts.ini'));
  OwnDesktopShortcut := GetIniBool('Shortcuts', 'Desktop', False,
    ExpandConstant('{app}\installer-shortcuts.ini'));
  Result := True;
end;

function DeleteStartMenuShortcut: Boolean;
begin
  Result := OwnStartMenuShortcut;
end;

function DeleteDesktopShortcut: Boolean;
begin
  Result := OwnDesktopShortcut;
end;

procedure InitializeWizard;
begin
  { These choices are shown after file installation, before the launch offer. }
  ShortcutPage := CreateInputOptionPage(wpInfoAfter, 'Create shortcuts',
    'ICC Profile Inspector is installed.',
    'Choose the shortcuts you want to create, then click Next.', False, False);
  ShortcutPage.Add('Create a Start menu shortcut');
  ShortcutPage.Add('Create a Desktop shortcut');
  ShortcutPage.Values[0] := ExpandConstant('{param:STARTMENU|1}') = '1';
  ShortcutPage.Values[1] := ExpandConstant('{param:DESKTOP|0}') = '1';
end;

procedure CreateChosenShortcuts;
var
  Link: String;
begin
  if ShortcutsCreated then Exit;
  if ShortcutPage.Values[0] then begin
    Link := ExpandConstant('{autoprograms}\ICC Profile Inspector.lnk');
    CreateShellLink(Link, 'Inspect ICC profiles and 3D printer gamuts',
      ExpandConstant('{app}\{#AppExe}'), '', ExpandConstant('{app}'),
      ExpandConstant('{app}\{#AppExe}'), 0, SW_SHOWNORMAL);
    SetIniBool('Shortcuts', 'StartMenu', True, ExpandConstant('{app}\installer-shortcuts.ini'));
  end;
  if ShortcutPage.Values[1] then begin
    Link := ExpandConstant('{autodesktop}\ICC Profile Inspector.lnk');
    CreateShellLink(Link, 'ICC Profile Inspector',
      ExpandConstant('{app}\{#AppExe}'), '', ExpandConstant('{app}'),
      ExpandConstant('{app}\{#AppExe}'), 0, SW_SHOWNORMAL);
    SetIniBool('Shortcuts', 'Desktop', True, ExpandConstant('{app}\installer-shortcuts.ini'));
  end;
  ShortcutsCreated := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ShortcutPage.ID then begin
    try
      CreateChosenShortcuts;
    except
      MsgBox('The program was installed, but a shortcut could not be created: ' +
        GetExceptionMessage, mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssDone) and WizardSilent then CreateChosenShortcuts;
end;
