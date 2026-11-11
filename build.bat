@echo off
setlocal
cd /d "%~dp0"

echo === Shotwise: gerando executavel ===

python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 (
    echo Python 3.11 ou superior nao encontrado. O atalho "python" da Microsoft Store nao conta.
    echo Instale o Python de verdade: https://www.python.org/downloads/  ^(marque "Add python.exe to PATH"^)
    echo ou execute:  winget install --id Python.Python.3.12 -e
    echo Depois feche esta janela, abra outra e rode este arquivo de novo.
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

set ICON_ARG=
if exist assets\icon.ico set ICON_ARG=--icon assets\icon.ico

python -m PyInstaller --noconfirm --clean --onefile --noconsole --name Shotwise %ICON_ARG% %OCR_ARGS% %AUDIO_ARGS% main.py
if errorlevel 1 goto :erro

call "%~dp0sign.bat" /enabled
if not errorlevel 1 (
    call "%~dp0sign.bat" dist\Shotwise.exe
    if errorlevel 1 goto :erro
)

echo.
echo Pronto! Executavel em: dist\Shotwise.exe
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
