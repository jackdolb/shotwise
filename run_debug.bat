@echo off
setlocal
cd /d "%~dp0"
rem Roda o Shotwise COM console: mostra os erros na tela e grava o log detalhado.
if not exist .venv (
    echo Ambiente nao encontrado. Rode run.bat uma vez primeiro.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat
set SHOTWIN_DEBUG=1
python main.py
echo.
echo O Shotwise foi encerrado. Log: %APPDATA%\Shotwise\logs\shotwise.log
pause
