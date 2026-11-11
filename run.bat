@echo off
setlocal
cd /d "%~dp0"

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
    echo Primeira execucao: criando ambiente e instalando dependencias...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Falha ao instalar dependencias.
        pause
        exit /b 1
    )
) else (
    call .venv\Scripts\activate.bat
)

rem OCR (opcional): instala os pacotes do Windows OCR se ainda nao existirem
python -c "import winrt.windows.media.ocr" >nul 2>nul
if errorlevel 1 (
    echo Instalando componentes de OCR - opcional...
    python -m pip install -r requirements-ocr.txt
    if errorlevel 1 echo Aviso: OCR indisponivel. O restante do Shotwise funciona normalmente.
)

rem Som do sistema no video (opcional)
python -c "import pyaudiowpatch" >nul 2>nul
if errorlevel 1 python -m pip install -r requirements-audio.txt >nul 2>nul

rem pythonw nao abre janela de console; erros ficam em %APPDATA%\Shotwise\logs\shotwise.log
start "" pythonw main.py
