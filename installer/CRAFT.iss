#define MyAppName "CRAFT"
#define MyAppVersion "1.1.2"
#define MyAppPublisher "ABKuznetsov"

[Setup]
AppId={{D09F99C8-FA34-4945-93A8-0DD557156D74}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\XRD Craft
DefaultGroupName=XRD Craft
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=admin
OutputDir=output
OutputBaseFilename=CRAFT_Windows_{#MyAppVersion}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\assets\craft.ico
SetupIconFile=..\assets\craft.ico
VersionInfoVersion={#MyAppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Dirs]
Name: "{commonappdata}\Sci"; Permissions: users-modify

[Files]
Source: "..\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "installer\output\*,.git\*,.agents\*,.codex\*,.superpowers\*,.venv\*,__pycache__\*,*.pyc,*.pyo,.DS_Store,.ruff_cache\*,.pytest_cache\*,build\*,dist\*,docs\*,tests\*,assets\craft-presentation.png,*.egg-info\*"

[Icons]
Name: "{group}\CRAFT"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run_craft_silent.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\craft.ico"
Name: "{group}\Setup Sci Environment"; Filename: "{app}\toolkit\setup_sci_env.bat"; WorkingDir: "{app}"
Name: "{group}\Uninstall CRAFT"; Filename: "{uninstallexe}"
Name: "{commondesktop}\CRAFT"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\run_craft_silent.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\craft.ico"

[Run]
Filename: "{cmd}"; Parameters: "/D /C ""{app}\toolkit\setup_sci_env.bat"""; Description: "Prepare shared Sci environment"; WorkingDir: "{app}"; StatusMsg: "Preparing shared Sci environment in ProgramData..."; Flags: waituntilterminated
Filename: "{sys}\wscript.exe"; Parameters: """{app}\run_craft_silent.vbs"""; Description: "Launch CRAFT"; Flags: postinstall nowait skipifsilent unchecked runasoriginaluser

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
