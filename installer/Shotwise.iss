; Shotwise - instalador (Inno Setup 6)
; Gere com build_installer.bat (ele define MyAppVersion a partir de shotwise/__init__.py).
; Reexecutar o instalador de uma versao nova ATUALIZA a instalacao existente no mesmo lugar:
; mesmo AppId, programa fechado automaticamente, configuracoes e capturas do usuario preservadas.

#ifndef MyAppVersion
  #define MyAppVersion "1.1.0"
#endif
#define MyAppName "Shotwise"
#define MyAppExe "Shotwise.exe"

[Setup]
ShowLanguageDialog=yes
UsePreviousLanguage=no
; NAO altere o AppId: e ele que faz as novas versoes atualizarem a instalacao anterior.
AppId={{B6B1A7E2-5C1F-4B9E-9C6D-7E0B6F3A2D41}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Jackson Araujo
VersionInfoVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
UsePreviousTasks=yes
; instala so para o usuario atual, sem precisar de administrador (use o dialogo para instalar para todos)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; o Shotwise em execucao e fechado pelo proprio instalador (veja [Code]: evento ShotwiseQuit)
CloseApplications=yes
RestartApplications=no
OutputDir=..\dist_installer
OutputBaseFilename=Shotwise-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
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
; limpa arquivos de versoes anteriores (bibliotecas antigas do PyInstaller) antes de copiar os novos
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\ShotWin.exe"
Type: files; Name: "{autoprograms}\ShotWin.lnk"
Type: files; Name: "{autodesktop}\ShotWin.lnk"

[Files]
Source: "..\dist\Shotwise\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

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

Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Shotwise"; ValueData: """{app}\{#MyAppExe}"""; Tasks: startup; Flags: uninsdeletevalue

; "Abrir com" e menu de contexto para imagens (somente para o usuario atual)
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExe}"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Shotwise (editar imagem e vídeo)"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes"; ValueType: string; ValueName: ".png"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\.png\OpenWithList\{#MyAppExe}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.png\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes"; ValueType: string; ValueName: ".jpg"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\.jpg\OpenWithList\{#MyAppExe}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpg\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes"; ValueType: string; ValueName: ".jpeg"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\.jpeg\OpenWithList\{#MyAppExe}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.jpeg\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes"; ValueType: string; ValueName: ".bmp"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\.bmp\OpenWithList\{#MyAppExe}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.bmp\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes"; ValueType: string; ValueName: ".webp"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\.webp\OpenWithList\{#MyAppExe}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.webp\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes"; ValueType: string; ValueName: ".mp4"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\.mp4\OpenWithList\{#MyAppExe}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.mp4\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\Applications\{#MyAppExe}\SupportedTypes"; ValueType: string; ValueName: ".gif"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\.gif\OpenWithList\{#MyAppExe}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\ShotwiseEdit"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Editar no Shotwise"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\SystemFileAssociations\.gif\shell\ShotwiseEdit\command"; ValueType: string; ValueData: """{app}\{#MyAppExe}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Abrir o Shotwise agora"; Flags: nowait postinstall skipifsilent
; atualizacao feita pelo proprio Shotwise (/RELAUNCH=1): reabre o programa ao terminar
Filename: "{app}\{#MyAppExe}"; Flags: nowait; Check: RelaunchAfterUpdate

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
  if ShotwiseRunning then
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM Shotwise.exe', '', SW_HIDE, ewWaitUntilTerminated, Rc);
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM ShotWin.exe', '', SW_HIDE, ewWaitUntilTerminated, Rc);
  if ShotwiseRunning then Sleep(1500);
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
begin
  if CurStep = ssPostInstall then
  begin
    WriteInitialLanguage;
    WriteUpdateDefaults;
  end;
end;

function InitializeSetup: Boolean;
begin
  Result := EnsureShotwiseClosed(WizardSilent);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { remove a inicializacao automatica, mesmo que tenha sido ligada pelas Configuracoes do app }
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
