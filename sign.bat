@echo off
rem ============================================================================
rem Assinatura de codigo (opcional) - usada pelos scripts de build.
rem
rem Configure por variaveis de ambiente (nada de senha em arquivo ou no repositorio):
rem   SHOTWISE_SIGN_PFX         caminho do certificado .pfx
rem   SHOTWISE_SIGN_PASSWORD    senha do .pfx (evite " e % na senha)
rem   -- ou, para certificado ja instalado no Windows (Meus certificados / token / cartao):
rem   SHOTWISE_SIGN_THUMBPRINT  impressao digital (SHA1) do certificado
rem   SHOTWISE_SIGNTOOL         caminho do signtool.exe (opcional; se vazio, procura em tools\signtool, PATH e Windows SDK)
rem   SHOTWISE_SIGN_TIMESTAMP   servidor de carimbo de tempo (padrao: http://timestamp.digicert.com)
rem                             use o da sua empresa, se houver
rem
rem Uso:
rem   sign.bat /enabled         sai com 0 se ha certificado configurado, 1 se nao
rem   sign.bat arquivo [...]    assina os arquivos
rem   sign.bat /dir pasta       assina todos os .exe/.dll/.pyd da pasta que ainda nao tem assinatura valida
rem Sem certificado configurado, nao faz nada e sai com 0.
rem ============================================================================
setlocal EnableExtensions DisableDelayedExpansion

set "TS=%SHOTWISE_SIGN_TIMESTAMP%"
if "%TS%"=="" set "TS=http://timestamp.digicert.com"
set "THUMB=%SHOTWISE_SIGN_THUMBPRINT%"
if "%THUMB%"=="" set "THUMB=%SHOTWIN_SIGN_THUMBPRINT%"
set "MODE="
if not "%SHOTWISE_SIGN_PFX%"=="" set "MODE=pfx"
if "%MODE%"=="" if not "%THUMB%"=="" set "MODE=store"

if /i "%~1"=="/enabled" goto :check_enabled
if "%MODE%"=="" goto :disabled
if "%~1"=="" goto :usage

if "%MODE%"=="pfx" if not exist "%SHOTWISE_SIGN_PFX%" goto :nopfx
if "%MODE%"=="pfx" if not defined SHOTWISE_SIGN_PASSWORD goto :nopass

rem --- localiza o signtool.exe (PATH ou Windows SDK) ---
set "SIGNTOOL="
if not "%SHOTWISE_SIGNTOOL%"=="" if exist "%SHOTWISE_SIGNTOOL%" set "SIGNTOOL=%SHOTWISE_SIGNTOOL%"
if not defined SIGNTOOL for /f "delims=" %%S in ('dir /b /s "%~dp0tools\signtool\signtool.exe" 2^>nul ^| findstr /i "\\x64\\signtool.exe"') do if not defined SIGNTOOL set "SIGNTOOL=%%S"
if not defined SIGNTOOL for /f "delims=" %%S in ('where signtool.exe 2^>nul') do if not defined SIGNTOOL set "SIGNTOOL=%%S"
if not defined SIGNTOOL for /f "delims=" %%S in ('dir /b /s "%ProgramFiles(x86)%\Windows Kits\10\bin\signtool.exe" 2^>nul ^| findstr /i "\\x64\\signtool.exe" ^| sort /r') do if not defined SIGNTOOL set "SIGNTOOL=%%S"
if not defined SIGNTOOL goto :nosigntool

set /a COUNT=0
set /a FAIL=0
if /i "%~1"=="/dir" goto :sign_dir

:next_file
if "%~1"=="" goto :done
call :sign_one "%~1"
shift
goto :next_file

:sign_dir
for /r "%~2" %%F in (*.exe *.dll *.pyd) do call :sign_if_needed "%%F"
goto :done

:sign_if_needed
"%SIGNTOOL%" verify /pa /q %1 >nul 2>nul
if not errorlevel 1 exit /b 0
call :sign_one %1
exit /b 0

:sign_one
rem tenta o servidor de carimbo configurado e, se ele nao responder, servidores alternativos (2 tentativas cada)
set "SIGNED="
for %%T in ("%TS%" "http://timestamp.digicert.com" "http://timestamp.sectigo.com" "http://timestamp.globalsign.com/tsa/r6advanced1") do (
    if not defined SIGNED call :try_ts %1 %%T
    if not defined SIGNED call :try_ts %1 %%T
)
if not defined SIGNED goto :sign_failed
set /a COUNT+=1
exit /b 0

:try_ts
if "%MODE%"=="pfx" goto :try_pfx
"%SIGNTOOL%" sign /fd SHA256 /tr %2 /td SHA256 /sha1 %THUMB% %1 >nul 2>nul
goto :try_result
:try_pfx
"%SIGNTOOL%" sign /fd SHA256 /tr %2 /td SHA256 /f "%SHOTWISE_SIGN_PFX%" /p "%SHOTWISE_SIGN_PASSWORD%" %1 >nul 2>nul
:try_result
if errorlevel 1 goto :try_again
set "SIGNED=1"
exit /b 0
:try_again
echo [assinatura] servidor de carimbo %~2 nao respondeu; tentando de novo...
ping -n 4 127.0.0.1 >nul
exit /b 1

:sign_failed
set /a FAIL+=1
echo [assinatura] FALHOU: %1
echo   Nenhum servidor de carimbo de tempo respondeu. Confira a internet ou o proxy e rode o build de novo.
exit /b 1

:done
echo [assinatura] arquivos assinados: %COUNT%   falhas: %FAIL%
if %FAIL% gtr 0 exit /b 1
exit /b 0

:check_enabled
if "%MODE%"=="" exit /b 1
exit /b 0

:disabled
echo [assinatura] desativada (defina SHOTWISE_SIGN_PFX e SHOTWISE_SIGN_PASSWORD, ou SHOTWISE_SIGN_THUMBPRINT).
exit /b 0

:usage
echo uso: sign.bat arquivo [arquivo...]   ^|   sign.bat /dir pasta   ^|   sign.bat /enabled
exit /b 1

:nopfx
echo [assinatura] certificado nao encontrado: %SHOTWISE_SIGN_PFX%
exit /b 1

:nopass
echo [assinatura] defina SHOTWISE_SIGN_PASSWORD (senha do .pfx).
exit /b 1

:nosigntool
echo [assinatura] signtool.exe nao encontrado.
echo   Opcao 1: instale o Windows SDK ^(winget install Microsoft.WindowsSDK.10.0.26100^) e marque so "Signing Tools".
echo   Opcao 2: extraia o pacote NuGet Microsoft.Windows.SDK.BuildTools em tools\signtool ^(veja o README^).
echo   Opcao 3: defina SHOTWISE_SIGNTOOL com o caminho do signtool.exe.
exit /b 1
