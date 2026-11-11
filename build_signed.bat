@echo off
rem Gera o instalador ja assinado: pergunta a senha do certificado e roda o build na mesma janela.
rem Por padrao usa cert\shotwise-test.pfx; para outro certificado, defina SHOTWISE_SIGN_PFX antes.
setlocal DisableDelayedExpansion
cd /d "%~dp0"
if "%SHOTWISE_SIGN_PFX%"=="" set "SHOTWISE_SIGN_PFX=%~dp0cert\shotwise-test.pfx"
if not exist "%SHOTWISE_SIGN_PFX%" (
    echo Certificado nao encontrado: %SHOTWISE_SIGN_PFX%
    echo Crie um com tools\signing.ps1 -NewTestCert ou defina SHOTWISE_SIGN_PFX.
    pause
    exit /b 1
)
if not defined SHOTWISE_SIGN_PASSWORD set /p "SHOTWISE_SIGN_PASSWORD=Senha do certificado (a digitacao aparece na tela): "
if not defined SHOTWISE_SIGN_PASSWORD (
    echo Senha vazia. Nada foi feito.
    pause
    exit /b 1
)
call "%~dp0build_installer.bat"
