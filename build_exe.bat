@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================================
echo   PDF Baski Atolyesi - Windows Derleme (Setup + Portable EXE)
echo   Gelistirici: Abdulkadir Hamza (support@kadirhamza.com)
echo ================================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi. https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

echo [1/5] Gerekli paketler kontrol ediliyor...
python -c "import PySide6, pymupdf, PIL" >nul 2>nul
if errorlevel 1 (
    echo Eksik paketler kuruluyor...
    python -m pip install -r requirements.txt
    if errorlevel 1 goto fail
)

python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo PyInstaller kuruluyor...
    python -m pip install "pyinstaller>=6"
    if errorlevel 1 goto fail
)

echo.
echo [2/5] Surum ve simge hazirlaniyor...
for /f "delims=" %%V in ('python -c "from core import version; print(version.VERSION)"') do set "APPVER=%%V"
if "%APPVER%"=="" set "APPVER=0.0.0"
echo Surum: %APPVER%
if not exist "assets\icon.ico" (
    python tools\make_icon.py
    if errorlevel 1 goto fail
)

echo.
echo [3/5] Testler calistiriliyor...
python -m pytest tests -q
if errorlevel 1 (
    echo HATA: Testler gecmedi; derleme durduruldu.
    pause
    exit /b 1
)

set "PI_EXCLUDES=--exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets --exclude-module PySide6.Qt3DCore --exclude-module PySide6.Qt3DRender --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtCharts --exclude-module PySide6.QtDataVisualization --exclude-module tkinter"
set "PI_HIDDEN=--hidden-import core.gutter_engine --hidden-import core.pdf_tools --hidden-import core.page_layout_model --hidden-import core.settings_store --hidden-import core.diagnostics --hidden-import core.version"

echo.
echo [4/5] Kurulum icin hizli klasor (onedir) ve Portable EXE derleniyor...
python -m PyInstaller --noconfirm --clean --noconsole --onedir ^
    %PI_EXCLUDES% %PI_HIDDEN% ^
    --add-data "assets;assets" --add-data "locales;locales" ^
    --icon "assets\icon.ico" --name "PDF_Baski_Atolyesi" app.py
if errorlevel 1 goto fail

python -m PyInstaller --noconfirm --noconsole --onefile ^
    %PI_EXCLUDES% %PI_HIDDEN% ^
    --add-data "assets;assets" --add-data "locales;locales" ^
    --icon "assets\icon.ico" --name "PDF_Baski_Atolyesi_%APPVER%_Portable" app.py
if errorlevel 1 goto fail

echo.
echo [5/5] Inno Setup ile Setup.exe olusturuluyor (varsa)...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not "%ISCC%"=="" (
    "%ISCC%" /DAppVersion=%APPVER% "packaging\windows\installer.iss"
    if errorlevel 1 goto fail
    echo Setup EXE hazir: %~dp0dist\PDF_Baski_Atolyesi_%APPVER%_Setup.exe
) else (
    echo NOT: Inno Setup 6 bulunamadi; Setup.exe atlandi.
    echo      Inno Setup kuruluysa packaging\windows\installer.iss ile Setup.exe uretilebilir.
)

echo.
echo ================================================================
echo   Portable EXE: %~dp0dist\PDF_Baski_Atolyesi_%APPVER%_Portable.exe
echo ================================================================
explorer "%~dp0dist"
exit /b 0

:fail
echo.
echo Derleme basarisiz oldu.
pause
exit /b 1
