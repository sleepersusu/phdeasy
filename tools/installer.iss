; 教授研究檔案 Windows 安裝程式（Inno Setup 6）
; 裝在「使用者\AppData\Local\Programs\PhdeasyProfessorFiles」，不用管理員權限
; 教授資料放在「使用者\phdeasy\runs」，從 Google 雲端硬碟同步；更新、重裝、解除安裝都不會動到
#define AppVer GetEnv("APP_VERSION")
#if AppVer == ""
  #define AppVer "0.0.0"
#endif

[Setup]
AppId={{4B7D2C19-6E3A-4F8B-9C1D-2A5E7F9B3C10}
AppName=教授研究檔案
AppVersion={#AppVer}
AppVerName=教授研究檔案 {#AppVer}
AppPublisher=SU
DefaultDirName={localappdata}\Programs\PhdeasyProfessorFiles
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=PhdeasyProfessorFiles-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=教授研究檔案
UninstallDisplayIcon={app}\教授研究檔案.exe
CloseApplications=yes

[Languages]
#ifexist "ChineseTraditional.isl"
Name: "zh"; MessagesFile: "ChineseTraditional.isl"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[Tasks]
Name: "desktopicon"; Description: "在桌面建立捷徑"; GroupDescription: "捷徑："

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\PhdeasyProfessorFiles\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\教授研究檔案"; Filename: "{app}\教授研究檔案.exe"
Name: "{autodesktop}\教授研究檔案"; Filename: "{app}\教授研究檔案.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\教授研究檔案.exe"; Description: "打開教授研究檔案"; Flags: nowait postinstall skipifsilent
; 自動更新（安靜安裝）裝完直接重開
Filename: "{app}\教授研究檔案.exe"; Flags: nowait; Check: IsAutoUpdate

[Code]
function OpenProcess(dwDesiredAccess: Cardinal; bInheritHandle: Boolean; dwProcessId: Cardinal): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(hHandle: THandle; dwMilliseconds: Cardinal): Cardinal;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(hObject: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function IsAutoUpdate(): Boolean;
begin
  Result := ExpandConstant('{param:AUTOUPDATE|0}') = '1';
end;

{ 自動更新：程式帶 /WAITPID=程式編號 叫起安裝程式，先等舊的程式完全關掉（最多 2 分鐘，讓它同步雲端）再開始裝 }
function InitializeSetup(): Boolean;
var
  Pid: Integer;
  H: THandle;
begin
  Pid := StrToIntDef(ExpandConstant('{param:WAITPID|0}'), 0);
  if Pid > 0 then
  begin
    H := OpenProcess($00100000, False, Pid);
    if H <> 0 then
    begin
      WaitForSingleObject(H, 120000);
      CloseHandle(H);
    end;
    Sleep(1500);
  end;
  Result := True;
end;
