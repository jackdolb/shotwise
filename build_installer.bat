@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo === Shotwise: gerando o instalador ===
echo.

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo Python 3.11 ou superior nao encontrado. O atalho "python" da Microsoft Store nao conta.
    echo Instale o Python de verdade: https://www.python.org/downloads/  ^(marque "Add python.exe to PATH"^)
    echo ou execute:  winget install --id Python.Python.3.12 -e
    echo Depois feche esta janela, abra outra e rode este arquivo de novo.
    pause
    exit /b 1
)

rem --- assinatura: avisa logo (antes de compilar) se faltar a senha nesta janela ---
if defined SHOTWISE_SIGN_PFX if not defined SHOTWISE_SIGN_PASSWORD (
    echo SHOTWISE_SIGN_PFX esta definido, mas SHOTWISE_SIGN_PASSWORD nao esta definido NESTA janela.
    echo Use build_signed.bat ^(pergunta a senha^) ou defina as duas variaveis na mesma janela do CMD.
    pause
    exit /b 1
)

rem --- localiza o compilador do Inno Setup (ISCC.exe) ---
set ISCC=
for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do (
    if exist %%P set ISCC=%%~P
)
if "%ISCC%"=="" (
    echo Inno Setup 6 nao encontrado.
    echo Instale com:  winget install --id JRSoftware.InnoSetup -e
    echo ou baixe em https://jrsoftware.org/isdl.php  e execute este arquivo de novo.
    pause
    exit /b 1
)

if not exist .venv (
    echo Criando ambiente virtual...
    python -m venv .venv
    if errorlevel 1 goto :erro
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :erro
python -m pip install -r requirements-ocr.txt
if errorlevel 1 echo Aviso: pacotes de OCR nao instalados; o OCR ficara indisponivel no executavel.
python -m pip install -r requirements-audio.txt
if errorlevel 1 echo Aviso: PyAudioWPatch nao instalado; o video nao gravara o som do sistema.
set AUDIO_ARGS=
python -c "import pyaudiowpatch" >nul 2>nul
if not errorlevel 1 set AUDIO_ARGS=--hidden-import pyaudiowpatch --hidden-import _portaudiowpatch
set OCR_ARGS=
python -c "import winrt.windows.media.ocr" >nul 2>nul
if not errorlevel 1 set OCR_ARGS=--collect-submodules winrt --hidden-import winrt.windows.media.ocr --hidden-import winrt.windows.globalization --hidden-import winrt.windows.graphics.imaging --hidden-import winrt.windows.storage.streams

python tools\make_icon.py

for /f %%V in ('python -c "import shotwise; print(shotwise.__version__)"') do set VER=%%V
echo Versao: %VER%

rem --- 1) aplicativo em pasta (onedir: abre mais rapido e atualiza melhor que onefile) ---
if exist dist\Shotwise rmdir /s /q dist\Shotwise
python -m PyInstaller --noconfirm --clean --onedir --noconsole --name Shotwise --icon assets\icon.ico %OCR_ARGS% %AUDIO_ARGS% main.py
if errorlevel 1 goto :erro

rem --- 2) assinatura opcional dos binarios (veja sign.bat e a secao "Assinatura" do README) ---
set SIGN_ON=
call "%~dp0sign.bat" /enabled
if not errorlevel 1 set SIGN_ON=1
if defined SIGN_ON (
    echo Assinando os arquivos do aplicativo...
    call "%~dp0sign.bat" /dir dist\Shotwise
    if errorlevel 1 goto :erro
)

rem --- 3) instalador ---
if defined SIGN_ON (
    "%ISCC%" /DMyAppVersion=%VER% /DSignEnabled=1 "/Sshotwise=cmd /c $q$q%~dp0sign.bat$q $f$q" installer\Shotwise.iss
) else (
    "%ISCC%" /DMyAppVersion=%VER% installer\Shotwise.iss
)
if errorlevel 1 goto :erro

if defined SIGN_ON (
    call "%~dp0sign.bat" dist_installer\Shotwise-Setup-%VER%.exe
    if errorlevel 1 goto :erro
) else (
    echo.
    echo AVISO: o instalador NAO esta assinado. Com App Control / Controle de Aplicativo Inteligente a execucao
    echo pode ser bloqueada. Defina SHOTWISE_SIGN_PFX e SHOTWISE_SIGN_PASSWORD ^(veja o README, secao Assinatura^).
)

rem --- arquivo .sha256 ao lado do instalador (o Shotwise exige o hash para atualizar) ---
python tools\write_sha256.py "dist_installer\Shotwise-Setup-%VER%.exe"
if errorlevel 1 (
    echo ERRO: nao consegui gerar o arquivo .sha256 - o atualizador recusaria esta versao.
    pause
    exit /b 1
)
if errorlevel 1 goto :erro

echo.
echo Pronto! Instalador em: dist_installer\Shotwise-Setup-%VER%.exe
echo.
echo Impressoes digitais (SHA256) para pedir liberacao ao suporte de TI:
certutil -hashfile dist\Shotwise\Shotwise.exe SHA256 | findstr /v "hash CertUtil"
certutil -hashfile dist_installer\Shotwise-Setup-%VER%.exe SHA256 | findstr /v "hash CertUtil"
pause
exit /b 0

:erro
echo.
echo Ocorreu um erro durante a geracao. Verifique as mensagens acima.
echo Se aparecer "bloqueado pela politica do Device Guard / App Control", a politica da empresa nao deixa
echo executar programas sem assinatura nesta maquina. Gere o instalador em outro computador ou peca ao
echo suporte para liberar. Veja a secao "Ambiente corporativo" do README.
pause
exit /b 1
