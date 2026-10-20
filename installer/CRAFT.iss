#define MyAppName "CRAFT"
#define MyAppVersion "1.1.1"
#define MyAppPublisher "ABKuznetsov"

[Setup]
AppId={{D09F99C8-FA34-4945-93A8-0DD557156D74}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Sci\apps\craft
DefaultGroupName=CRAFT
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=CRAFT_Setup_{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "setupenv"; Description: "Prepare shared Sci Python environment after install"; GroupDescription: "Environment:"; Flags: checkedonce

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "installer\output\*,.git\*,.agents\*,.codex\*,.superpowers\*,.venv\*,__pycache__\*,*.pyc,*.pyo,.DS_Store,.ruff_cache\*,.pytest_cache\*,build\*,dist\*,*.egg-info\*"

[Icons]
Name: "{group}\CRAFT"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run_craft_silent.vbs"""; WorkingDir: "{app}"
Name: "{group}\Setup Sci Environment"; Filename: "{app}\toolkit\setup_sci_env.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall CRAFT"; Filename: "{uninstallexe}"
Name: "{autodesktop}\CRAFT"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run_craft_silent.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\toolkit\setup_sci_env.bat"; Description: "Prepare Sci environment"; Flags: postinstall runascurrentuser skipifsilent; Tasks: setupenv
Filename: "{sys}\wscript.exe"; Parameters: """{app}\run_craft_silent.vbs"""; Description: "Launch CRAFT"; Flags: postinstall nowait skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
