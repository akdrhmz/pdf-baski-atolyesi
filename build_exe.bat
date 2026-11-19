@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================================
echo   PDF Baski Atolyesi - Tasinabilir EXE Yapici
echo   Gelistirici: Abdulkadir Hamza (support@kadirhamza.com)
echo ================================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python bulunamadi. https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

echo [1/4] Gerekli paketler kontrol ediliyor...
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
echo [2/4] Surum ve simge hazirlaniyor...
for /f "delims=" %%V in ('python -c "from core import version; print(version.VERSION)"') do set "APPVER=%%V"
if "%APPVER%"=="" set "APPVER=0.0.0"
echo Surum: %APPVER%
if not exist "assets\icon.ico" (
    echo Simge uretiliyor...
    python tools\make_icon.py
    if errorlevel 1 goto fail
)

echo.
echo [3/4] Testler calistiriliyor...
python -m pytest -q
if errorlevel 1 (
    echo.
    echo HATA: Testler gecmedi; derleme durduruldu.
    echo Once "python -m pytest -q" ciktisindaki hatayi duzeltin.
    pause
    exit /b 1
)

echo.
echo [4/4] Tek dosya EXE derleniyor...
python -m PyInstaller ^
    --noconfirm --clean --noconsole --onefile ^
    --exclude-module PySide6.QtWebEngineCore ^
    --exclude-module PySide6.QtWebEngineWidgets ^
    --exclude-module PySide6.Qt3DCore ^
    --exclude-module PySide6.Qt3DRender ^
    --exclude-module PySide6.QtQuick ^
    --exclude-module PySide6.QtQml ^
    --exclude-module PySide6.QtMultimedia ^
    --exclude-module PySide6.QtCharts ^
    --exclude-module PySide6.QtDataVisualization ^
    --exclude-module tkinter ^
    --add-data "assets;assets" ^
    --add-data "locales;locales" ^
    --hidden-import "core.gutter_engine" ^
    --hidden-import "core.pdf_tools" ^
    --hidden-import "core.page_layout_model" ^
    --hidden-import "core.settings_store" ^
    --hidden-import "core.diagnostics" ^
    --hidden-import "core.version" ^
    --icon "assets\icon.ico" ^
    --name "PDF_Baski_Atolyesi_%APPVER%" ^
    app.py
if errorlevel 1 goto fail

echo.
echo ================================================================
echo   EXE hazir: %~dp0dist\PDF_Baski_Atolyesi_%APPVER%.exe
echo ================================================================
echo.
explorer "%~dp0dist"
exit /b 0

:fail
echo.
echo Derleme basarisiz oldu. Yukaridaki konsol ciktisini kontrol edin.
pause
exit /b 1
