@echo off
rem Publica a versao atual no GitHub Releases (e o Shotwise instalado passa a enxergar a atualizacao).
rem Requisitos: GitHub CLI (gh) instalado e logado (gh auth login), e os instaladores ja gerados em dist_installer.
rem Uso: publicar_release.bat            (publica a versao de shotwise\__init__.py)
setlocal
cd /d "%~dp0"
for /f %%v in ('python -c "from shotwise import __version__ as v; print(v)"') do set VER=%%v
if "%VER%"=="" (
    echo Nao consegui ler a versao em shotwise\__init__.py.
    goto :fim
)
where gh >nul 2>nul
if errorlevel 1 (
    echo GitHub CLI nao encontrado. Instale em https://cli.github.com e rode: gh auth login
    echo Ou publique pelo site: Releases ^> Draft a new release ^> tag v%VER% ^> anexe os arquivos de dist_installer.
    goto :fim
)
setlocal enabledelayedexpansion
set ASSETS=
for %%f in ("dist_installer\Shotwise-Setup-%VER%.exe" "dist_installer\Shotwise-Setup-%VER%.exe.sha256" "dist_installer\Shotwise-Python-Setup-%VER%.exe" "dist_installer\Shotwise-Python-Setup-%VER%.exe.sha256") do (
    if exist %%f set ASSETS=!ASSETS! %%f
)
if "!ASSETS!"=="" (
    echo Nenhum instalador da versao %VER% em dist_installer. Rode build_signed.bat primeiro.
    goto :fim
)
echo Versao %VER% - arquivos:!ASSETS!
rem O Shotwise recusa atualizar sem o .sha256 e sem assinatura valida: confira se os arquivos .sha256 aparecem acima.
set /p OK=Publicar agora? (S/N): 
if /i not "!OK!"=="S" goto :fim
gh release create v%VER% !ASSETS! --title "Shotwise %VER%" --generate-notes
if errorlevel 1 (
    echo Falha ao publicar. Confira o login ^(gh auth status^) e se a tag v%VER% ja existe.
    goto :fim
)
echo Pronto: a versao %VER% foi publicada.
:fim
echo.
pause
