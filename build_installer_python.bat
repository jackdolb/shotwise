@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo === Shotwise: gerando o instalador "modo Python" ===
echo Para computadores que bloqueiam executaveis sem assinatura. Nao gera .exe do programa:
echo o Shotwise abre pelo pythonw.exe do Python instalado, como no run.bat.
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

python tools\make_icon.py
for /f %%V in ('python -c "import shotwise; print(shotwise.__version__)"') do set VER=%%V
echo Versao: %VER%

set SIGN_ON=
call "%~dp0sign.bat" /enabled
if not errorlevel 1 set SIGN_ON=1
if defined SIGN_ON (
    "%ISCC%" /DMyAppVersion=%VER% /DSignEnabled=1 "/Sshotwise=cmd /c $q$q%~dp0sign.bat$q $f$q" installer\Shotwise-Python.iss
) else (
    "%ISCC%" /DMyAppVersion=%VER% installer\Shotwise-Python.iss
)
if errorlevel 1 goto :erro
if defined SIGN_ON (
    call "%~dp0sign.bat" dist_installer\Shotwise-Python-Setup-%VER%.exe
    if errorlevel 1 goto :erro
) else (
    echo AVISO: o instalador NAO esta assinado ^(veja README, secao Assinatura^).
)

rem --- arquivo .sha256 ao lado do instalador (o Shotwise exige o hash para atualizar) ---
python tools\write_sha256.py "dist_installer\Shotwise-Python-Setup-%VER%.exe"
if errorlevel 1 (
    echo ERRO: nao consegui gerar o arquivo .sha256 - o atualizador recusaria esta versao.
    pause
    exit /b 1
)
if errorlevel 1 goto :erro

echo.
echo Pronto! Instalador em: dist_installer\Shotwise-Python-Setup-%VER%.exe
echo O computador de destino precisa de Python 3.11+ e de internet (ou proxy) para baixar PySide6, numpy e Pillow.
pause
exit /b 0

:erro
echo.
echo Ocorreu um erro durante a geracao. Verifique as mensagens acima.
pause
exit /b 1
