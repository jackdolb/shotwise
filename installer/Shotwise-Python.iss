; Shotwise - instalador "modo Python" (Inno Setup 6)
; Para computadores com politica de Controle de Aplicativo (WDAC / Device Guard) que bloqueia executaveis
; sem assinatura. Nao instala nenhum .exe novo: o programa abre pelo pythonw.exe do Python ja instalado
; (assinado pela Python Software Foundation, como no run.bat). Gere com build_installer_python.bat.
; Usa o mesmo AppId do instalador comum: instalar um sobre o outro atualiza no mesmo lugar.

#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif
#define MyAppName "Shotwise"

[Setup]
ShowLanguageDialog=yes
UsePreviousLanguage=no
; NAO altere o AppId.
AppId={{B6B1A7E2-5C1F-4B9E-9C6D-7E0B6F3A2D41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Jackson Araujo
AppPublisherURL=https://jacksonti.com
AppSupportURL=https://github.com/jackdolb/shotwise
AppUpdatesURL=https://github.com/jackdolb/shotwise/releases
LicenseFile=..\LICENSE
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no
OutputDir=..\dist_installer
OutputBaseFilename=Shotwise-Python-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
#ifdef SignEnabled
; assina o instalador e o desinstalador (comando definido por /Sshotwise=... no ISCC; veja sign.bat)
SignTool=shotwise
SignedUninstaller=yes
#endif

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "startup"; Description: "Iniciar o Shotwise com o Windows"; Flags: unchecked
Name: "desktopicon"; Description: "Criar atalho na area de trabalho"; Flags: unchecked

[InstallDelete]
; limpa restos da instalacao com executavel (versao PyInstaller) e codigo antigo
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\Shotwise.exe"
Type: files; Name: "{app}\ShotWin.exe"
Type: files; Name: "{autoprograms}\ShotWin.lnk"
Type: files; Name: "{autodesktop}\ShotWin.lnk"
Type: filesandordirs; Name: "{app}\shotwin"
Type: filesandordirs; Name: "{app}\shotwise"

[Files]
Source: "..\main.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-ocr.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements-audio.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\shotwise\*.py"; DestDir: "{app}\shotwise"; Flags: ignoreversion
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{code:GetPythonW}"; Parameters: """{app}\main.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{code:GetPythonW}"; Parameters: """{app}\main.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\icon.ico"; Tasks: desktopicon

[Registry]
; --- limpeza do nome antigo (ShotWin, ate a versao 1.7): remove entradas antigas ---
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "ShotWin"; Flags: deletevalue
Root: HKCU; Subkey: "Software\Classes\Applications\ShotWin.exe"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\ShotWin.Image"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\ShotWinEdit"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.png\OpenWithList\ShotWin.exe"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: none; ValueName: "ShotWin.Image"; Flags: deletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\ShotWinEdit"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.jpg\OpenWithList\ShotWin.exe"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: none; ValueName: "ShotWin.Image"; Flags: deletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\ShotWinEdit"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.jpeg\OpenWithList\ShotWin.exe"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: none; ValueName: "ShotWin.Image"; Flags: deletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\ShotWinEdit"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.bmp\OpenWithList\ShotWin.exe"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.bmp\OpenWithProgids"; ValueType: none; ValueName: "ShotWin.Image"; Flags: deletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\ShotWinEdit"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.webp\OpenWithList\ShotWin.exe"; ValueType: none; Flags: deletekey
Root: HKCU; Subkey: "Software\Classes\.webp\OpenWithProgids"; ValueType: none; ValueName: "ShotWin.Image"; Flags: deletevalue

Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Shotwise"; ValueData: """{code:GetPythonW}"" ""{app}\main.py"""; Tasks: startup; Flags: uninsdeletevalue

; "Abrir com" e menu de contexto para imagens (somente para o usuario atual)
Root: HKCU; Subkey: "Software\Classes\Shotwise.Image"; ValueType: string; ValueData: "Shotwise (editar imagem e vídeo)"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Shotwise.Image"; ValueType: string; ValueName: "FriendlyTypeName"; ValueData: "Shotwise"
Root: HKCU; Subkey: "Software\Classes\Shotwise.Image\DefaultIcon"; ValueType: string; ValueData: "{app}\assets\icon.ico"
Root: HKCU; Subkey: "Software\Classes\Shotwise.Image\shell\open"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"
Root: HKCU; Subkey: "Software\Classes\Shotwise.Image\shell\open\command"; ValueType: string; ValueData: """{code:GetPythonW}"" ""{app}\main.py"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.png\OpenWithProgids"; ValueType: none; ValueName: "Shotwise.Image"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{code:GetPythonW}"" ""{app}\main.py"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.jpg\OpenWithProgids"; ValueType: none; ValueName: "Shotwise.Image"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{code:GetPythonW}"" ""{app}\main.py"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: none; ValueName: "Shotwise.Image"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{code:GetPythonW}"" ""{app}\main.py"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.bmp\OpenWithProgids"; ValueType: none; ValueName: "Shotwise.Image"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{code:GetPythonW}"" ""{app}\main.py"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.webp\OpenWithProgids"; ValueType: none; ValueName: "Shotwise.Image"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{code:GetPythonW}"" ""{app}\main.py"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: none; ValueName: "Shotwise.Image"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{code:GetPythonW}"" ""{app}\main.py"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.gif\OpenWithProgids"; ValueType: none; ValueName: "Shotwise.Image"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{code:GetPythonW}"" ""{app}\main.py"" ""%1"""

[Run]
Filename: "{code:GetPythonW}"; Parameters: """{app}\main.py"""; WorkingDir: "{app}"; Description: "Abrir o Shotwise agora"; Flags: nowait postinstall skipifsilent
; atualizacao feita pelo proprio Shotwise (/RELAUNCH=1): reabre o programa ao terminar
Filename: "{code:GetPythonW}"; Parameters: """{app}\main.py"""; WorkingDir: "{app}"; Flags: nowait; Check: RelaunchAfterUpdate

[UninstallDelete]
Type: filesandordirs; Name: "{app}\libs"
Type: filesandordirs; Name: "{app}\shotwin"
Type: filesandordirs; Name: "{app}\shotwise"
Type: files; Name: "{app}\pip-install.log"

[Code]
function RelaunchAfterUpdate: Boolean;
begin
  Result := ExpandConstant('{param:RELAUNCH|0}') = '1';
end;

function OpenEventW(Access: Cardinal; Inherit: Integer; Name: String): Cardinal; external 'OpenEventW@kernel32.dll stdcall';
function SetEvent(Handle: Cardinal): Integer; external 'SetEvent@kernel32.dll stdcall';
function CloseHandle(Handle: Cardinal): Integer; external 'CloseHandle@kernel32.dll stdcall';

function ShotwiseRunning: Boolean;
begin
  Result := CheckForMutexes('ShotwiseSingleInstance') or CheckForMutexes('ShotWinSingleInstance');
end;

{ Pede ao Shotwise que se encerre sozinho (evento nomeado) e espera ate ~10 s. }
procedure AskShotwiseToQuit;
var
  H: Cardinal;
  I: Integer;
begin
  if not ShotwiseRunning then Exit;
  H := OpenEventW($0002, 0, 'Local\ShotwiseQuit');
  if H <> 0 then
  begin
    SetEvent(H);
    CloseHandle(H);
  end;
  H := OpenEventW($0002, 0, 'Local\ShotWinQuit');   { versao antiga (ShotWin) }
  if H <> 0 then
  begin
    SetEvent(H);
    CloseHandle(H);
  end;
  for I := 1 to 40 do
  begin
    if not ShotwiseRunning then Exit;
    Sleep(250);
  end;
end;

{ Fecha o Shotwise em execucao antes de instalar/desinstalar. Retorna False se o usuario cancelar. }
function EnsureShotwiseClosed(Silent: Boolean): Boolean;
var
  Rc, Tries: Integer;
begin
  AskShotwiseToQuit;
  
  Tries := 0;
  while ShotwiseRunning do
  begin
    Tries := Tries + 1;
    if (Tries > 3) or Silent then
    begin
      Result := False;
      Exit;
    end;
    if MsgBox('O Shotwise ainda esta em execucao e nao fechou sozinho.' + #13#10 +
              'Clique com o botao direito no icone dele na bandeja do Windows, escolha "Sair" e depois "Tentar novamente".',
              mbError, MB_RETRYCANCEL) = IDCANCEL then
    begin
      Result := False;
      Exit;
    end;
  end;
  Result := True;
end;

function InitializeUninstall: Boolean;
begin
  Result := EnsureShotwiseClosed(UninstallSilent);
end;

var
  PyExe: String;

function TryPythonDir(Dir: String): Boolean;
begin
  Result := FileExists(AddBackslash(Dir) + 'python.exe') and FileExists(AddBackslash(Dir) + 'pythonw.exe');
  if Result then
    PyExe := AddBackslash(Dir) + 'python.exe';
end;

function PyVersionOk(V: String): Boolean;
var
  P, Minor: Integer;
begin
  Result := False;
  if Copy(V, 1, 2) <> '3.' then Exit;
  V := Copy(V, 3, Length(V));
  P := Pos('-', V);
  if P > 0 then V := Copy(V, 1, P - 1);
  Minor := StrToIntDef(V, 0);
  Result := Minor >= 11;
end;

function FindInRegistry(Root: Integer; SubKey: String): Boolean;
var
  Versions: TArrayOfString;
  I: Integer;
  Dir: String;
begin
  Result := False;
  if RegGetSubkeyNames(Root, SubKey, Versions) then
    for I := GetArrayLength(Versions) - 1 downto 0 do
      if PyVersionOk(Versions[I]) then
       if RegQueryStringValue(Root, SubKey + '\' + Versions[I] + '\InstallPath', '', Dir) then
        if TryPythonDir(Dir) then
        begin
          Result := True;
          Exit;
        end;
end;

function FindPython: Boolean;
var
  P: String;
begin
  Result := FindInRegistry(HKEY_CURRENT_USER, 'Software\Python\PythonCore')
         or FindInRegistry(HKEY_LOCAL_MACHINE, 'Software\Python\PythonCore');
  if not Result then
  begin
    P := FileSearch('python.exe', GetEnv('PATH'));
    { o python.exe de WindowsApps e so um atalho da Microsoft Store, nao o Python de verdade }
    if (P <> '') and (Pos('WindowsApps', P) = 0) then
      Result := TryPythonDir(ExtractFileDir(P));
  end;
end;

function GetPythonW(Param: String): String;
begin
  Result := ExtractFilePath(PyExe) + 'pythonw.exe';
end;

function InitializeSetup: Boolean;
begin
  Result := FindPython;
  if Result then
  begin
    Result := EnsureShotwiseClosed(WizardSilent);
    Exit;
  end;
  if not Result then
    MsgBox('Este instalador precisa do Python 3.11 ou superior (python.org) instalado neste computador, ' +
           'e nao o encontrou.' + #13#10#13#10 +
           'Instale o Python, marque "Add python.exe to PATH" se quiser, e execute o instalador de novo.',
           mbError, MB_OK);
end;

{ Grava o idioma escolhido no instalador como idioma inicial do Shotwise (so em instalacao nova). }
procedure WriteInitialLanguage;
var
  Code, Cfg: String;
begin
  Cfg := ExpandConstant('{userappdata}\Shotwise\config.json');
  if FileExists(Cfg) then Exit;
  if ActiveLanguage = 'english' then Code := 'en'
  else if ActiveLanguage = 'spanish' then Code := 'es'
  else Code := 'pt';
  ForceDirectories(ExpandConstant('{userappdata}\Shotwise'));
  SaveStringToFile(Cfg, '{"language": "' + Code + '"}', False);
end;

{ ---- Pagina "Atualizacoes": de onde o Shotwise busca novas versoes ---- }
var
  UpdPage: TInputOptionWizardPage;
  UpdEdit: TNewEdit;
  UpdBrowse: TNewButton;
  UpdChosen: Boolean;

procedure UpdRadioClick(Sender: TObject);
begin
  UpdEdit.Enabled := UpdPage.Values[1];
  UpdBrowse.Enabled := UpdPage.Values[1];
end;

procedure UpdBrowseClick(Sender: TObject);
var
  Dir: String;
begin
  Dir := UpdEdit.Text;
  if BrowseForFolder('Selecione a pasta com os instaladores do Shotwise', Dir, False) then
    UpdEdit.Text := Dir;
end;

procedure InitializeWizard;
begin
  UpdPage := CreateInputOptionPage(wpSelectTasks, 'Atualizacoes',
    'De onde o Shotwise deve buscar novas versoes?',
    'Voce pode mudar isso depois em Configuracoes > Sobre.', True, True);
  UpdPage.Add('Repositorio web (padrao)');
  UpdPage.Add('Pasta local ou de rede (repositorio interno da empresa):');
  UpdPage.Values[0] := True;
  UpdPage.CheckListBox.Height := ScaleY(64);
  UpdEdit := TNewEdit.Create(UpdPage);
  UpdEdit.Parent := UpdPage.Surface;
  UpdEdit.Left := ScaleX(20);
  UpdEdit.Top := UpdPage.CheckListBox.Top + UpdPage.CheckListBox.Height + ScaleY(8);
  UpdEdit.Width := UpdPage.SurfaceWidth - ScaleX(20) - ScaleX(96);
  UpdEdit.Enabled := False;
  UpdBrowse := TNewButton.Create(UpdPage);
  UpdBrowse.Parent := UpdPage.Surface;
  UpdBrowse.Left := UpdEdit.Left + UpdEdit.Width + ScaleX(8);
  UpdBrowse.Top := UpdEdit.Top - ScaleY(1);
  UpdBrowse.Width := ScaleX(88);
  UpdBrowse.Height := UpdEdit.Height + ScaleY(2);
  UpdBrowse.Caption := 'Procurar...';
  UpdBrowse.Enabled := False;
  UpdBrowse.OnClick := @UpdBrowseClick;
  UpdPage.CheckListBox.OnClickCheck := @UpdRadioClick;
end;

{ Em instalacao silenciosa (ou com /UPDATEFOLDER="\\servidor\pasta") a pagina nao aparece. }
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  if (UpdPage <> nil) and (PageID = UpdPage.ID) then
    Result := WizardSilent or (ExpandConstant('{param:UPDATEFOLDER|}') <> '');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (UpdPage <> nil) and (CurPageID = UpdPage.ID) then
  begin
    if UpdPage.Values[1] and (Trim(UpdEdit.Text) = '') then
    begin
      MsgBox('Informe a pasta de atualizacao ou escolha o repositorio web.', mbError, MB_OK);
      Result := False;
    end
    else
      UpdChosen := True;
  end;
end;

{ Grava a escolha em install_defaults.json; o Shotwise le o arquivo na primeira abertura e o apaga. }
procedure WriteUpdateDefaults;
var
  Folder, Json, Dir: String;
begin
  Folder := ExpandConstant('{param:UPDATEFOLDER|}');
  if Folder <> '' then
    UpdChosen := True
  else if UpdChosen and UpdPage.Values[1] then
    Folder := Trim(UpdEdit.Text);
  if not UpdChosen then Exit;
  StringChangeEx(Folder, '\', '\\', True);
  if Folder <> '' then
    Json := '{"update_source": "folder", "update_folder": "' + Folder + '"}'
  else
    Json := '{"update_source": "repo"}';
  Dir := ExpandConstant('{userappdata}\Shotwise');
  ForceDirectories(Dir);
  SaveStringToFile(Dir + '\install_defaults.json', Json, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Rc: Integer;
  Libs, Log, Cmd: String;
begin
  if CurStep = ssPostInstall then
  begin
    WriteInitialLanguage;
    WriteUpdateDefaults;
    Libs := ExpandConstant('{app}\libs');
    Log := ExpandConstant('{app}\pip-install.log');
    WizardForm.StatusLabel.Caption := 'Baixando e instalando os componentes (PySide6, numpy, Pillow). Pode levar alguns minutos...';
    WizardForm.Refresh;
    Cmd := '/C ""' + PyExe + '" -m pip install --disable-pip-version-check --upgrade --target "' + Libs +
           '" -r "' + ExpandConstant('{app}\requirements.txt') + '" > "' + Log + '" 2>&1"';
    if (not Exec(ExpandConstant('{cmd}'), Cmd, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Rc)) or (Rc <> 0) then
      MsgBox('Nao foi possivel instalar os componentes (PySide6, numpy e Pillow). Verifique a conexao com a internet ' +
             'ou o proxy da empresa e execute o instalador de novo.' + #13#10#13#10 +
             'Detalhes em: ' + Log, mbError, MB_OK)
    else
    begin
      { OCR e opcional: se falhar, so o reconhecimento de texto fica indisponivel }
      Cmd := '/C ""' + PyExe + '" -m pip install --disable-pip-version-check --upgrade --target "' + Libs +
             '" -r "' + ExpandConstant('{app}\requirements-ocr.txt') + '" >> "' + Log + '" 2>&1"';
      Exec(ExpandConstant('{cmd}'), Cmd, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Rc);
      { som do sistema no video: tambem opcional }
      Cmd := '/C ""' + PyExe + '" -m pip install --disable-pip-version-check --upgrade --target "' + Libs +
             '" -r "' + ExpandConstant('{app}\requirements-audio.txt') + '" >> "' + Log + '" 2>&1"';
      Exec(ExpandConstant('{cmd}'), Cmd, ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Rc);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Shotwise');
    DataDir := ExpandConstant('{userappdata}\Shotwise');
    if (not UninstallSilent) and DirExists(DataDir) then
    begin
      if MsgBox('Excluir tambem as configuracoes e as capturas editaveis guardadas pelo Shotwise?' + #13#10 +
                'Pasta: ' + DataDir + #13#10#13#10 +
                'As capturas editaveis guardam a imagem original, sem as tarjas. ' +
                'Os PNGs salvos em Documentos\Shotwise nao serao apagados.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
