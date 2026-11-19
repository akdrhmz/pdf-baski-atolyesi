; PDF Baski Atolyesi - Inno Setup Kurulum Betigi (Windows)
; Derleme: build_exe.bat once dist\PDF_Baski_Atolyesi\ klasorunu uretir,
; ardindan Inno Setup (iscc.exe) bu betikle tek bir Setup.exe olusturur.

#ifndef AppVersion
  #define AppVersion "2.10.0"
#endif

[Setup]
AppId={{8E9A7B2C-4D1F-4B9E-9A3C-1F2E3D4C5B6A}
AppName=PDF Baski Atolyesi
AppVersion={#AppVersion}
AppPublisher=Abdulkadir Hamza
AppPublisherURL=https://github.com/akdrhmz/pdf-baski-cilt-studyosu
AppSupportURL=mailto:support@kadirhamza.com
DefaultDirName={autopf}\PDF Baski Atolyesi
DefaultGroupName=PDF Baski Atolyesi
AllowNoIcons=yes
OutputDir=..\..\dist
OutputBaseFilename=PDF_Baski_Atolyesi_{#AppVersion}_Setup
SetupIconFile=..\..\assets\icon.ico
UninstallDisplayIcon={app}\PDF_Baski_Atolyesi.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\dist\PDF_Baski_Atolyesi\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PDF Baski Atolyesi"; Filename: "{app}\PDF_Baski_Atolyesi.exe"
Name: "{group}\PDF Baski Atolyesini Kaldir"; Filename: "{uninstallexe}"
Name: "{autodesktop}\PDF Baski Atolyesi"; Filename: "{app}\PDF_Baski_Atolyesi.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PDF_Baski_Atolyesi.exe"; Description: "{cm:LaunchProgram,PDF Baski Atolyesi}"; Flags: nowait postinstall skipifsilent
