#ifndef ProductVersion
  #error 請透過 scripts/build.ps1 建置
#endif
[Setup]
AppId={#ProductAppId}
AppName=PokerLens
AppVersion={#ProductVersion}
AppPublisher={#ProductPublisher}
DefaultDirName={localappdata}\Programs\PokerLens
DefaultGroupName=PokerLens
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
OutputDir=..\dist\release
OutputBaseFilename=PokerLens-Setup-{#ProductVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no
RestartApplications=no
UninstallDisplayIcon={app}\Launcher.exe
UninstallDisplayName=PokerLens
SetupIconFile=..\assets\PokerLens.ico
[Languages]
Name: "chinesetraditional"; MessagesFile: "ChineseTraditional.isl"
[Files]
Source: "..\dist\install-root\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "current.json"
Source: "..\dist\install-root\current.json"; DestDir: "{app}"; Flags: onlyifdoesntexist uninsneveruninstall
[Icons]
Name: "{group}\PokerLens"; Filename: "{app}\Launcher.exe"
Name: "{autodesktop}\PokerLens"; Filename: "{app}\Launcher.exe"
[Run]
Filename: "{app}\Launcher.exe"; Description: "啟動 PokerLens"; Flags: nowait postinstall skipifsilent
[UninstallDelete]
Type: filesandordirs; Name: "{app}\versions"
Type: filesandordirs; Name: "{app}\staging"
Type: filesandordirs; Name: "{app}\component-cache"
Type: files; Name: "{app}\current.json"
Type: files; Name: "{app}\previous.json"
Type: files; Name: "{app}\.update.lock"
[Code]
function MoveFileEx(ExistingName, NewName: string; Flags: Cardinal): Boolean;
external 'MoveFileExW@kernel32.dll stdcall';

function ReadVersion(Content: string): string;
var Position, Last: Integer; Tail: string;
begin
  Result := '';
  Position := Pos('"version"', Content);
  if Position = 0 then Exit;
  Tail := Copy(Content, Position + 9, Length(Content));
  Position := Pos(':', Tail);
  if Position = 0 then Exit;
  Tail := Trim(Copy(Tail, Position + 1, Length(Tail)));
  if (Length(Tail) < 2) or (Tail[1] <> '"') then Exit;
  Tail := Copy(Tail, 2, Length(Tail));
  Last := Pos('"', Tail);
  if Last > 0 then Result := Copy(Tail, 1, Last - 1);
end;

function PrepareToInstall(var NeedsRestart: Boolean): string;
var Locator, Service, Processes, Process: Variant; Index: Integer; Path, Root: string;
begin
  Result := '';
  Root := Lowercase(AddBackslash(ExpandConstant('{app}')));
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Processes := Service.ExecQuery('SELECT ExecutablePath FROM Win32_Process WHERE Name=''PokerLens.exe'' OR Name=''Launcher.exe'' OR Name=''Updater.exe''');
    for Index := 0 to Processes.Count - 1 do begin
      Process := Processes.ItemIndex(Index);
      if not VarIsNull(Process.ExecutablePath) then begin
        Path := Process.ExecutablePath;
        Path := Lowercase(Path);
        if Pos(Root, Path) = 1 then begin
          Result := '請先關閉 PokerLens 與更新程式，再繼續安裝。';
          Exit;
        end;
      end;
    end;
  except
    Result := '無法確認程式是否已關閉，請稍後重新執行安裝程式。';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var Content: AnsiString; OldVersion, StatePath, TemporaryPath, NewContent: string;
begin
  if CurStep <> ssPostInstall then Exit;
  StatePath := ExpandConstant('{app}\current.json');
  if not LoadStringFromFile(StatePath, Content) then RaiseException('無法讀取目前版本狀態。');
  OldVersion := ReadVersion(String(Content));
  if OldVersion = '{#ProductVersion}' then Exit;
  if (OldVersion = '') or (Pos('..', OldVersion) > 0) or
     (Pos('\', OldVersion) > 0) or (Pos('/', OldVersion) > 0) or
     not FileExists(ExpandConstant('{app}\versions\') + OldVersion + '\PokerLens.exe') then
    RaiseException('舊版狀態無效，保留目前版本指標，請修復後重試。');
  NewContent := '{"version":"{#ProductVersion}","previous":"' + OldVersion + '","pending":true}';
  TemporaryPath := StatePath + '.new';
  if not SaveStringToFile(TemporaryPath, NewContent, False) then RaiseException('無法儲存新版狀態。');
  if not MoveFileEx(TemporaryPath, StatePath, 9) then RaiseException('無法切換新版，舊版狀態已保留。');
end;
