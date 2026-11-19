@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo === PDF Baski Atolyesi - Windows Kurulumu ===
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo HATA: Python 3.10+ bulunamadi. https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Sanal ortam (.venv) olusturuluyor...
    python -m venv .venv
    if errorlevel 1 goto fail
)

echo [2/3] Bagimliliklar kuruluyor...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 goto fail

echo [3/3] Baslat Menusu ve Masaustu kisayollari olusturuluyor...
set "APP_DIR=%~dp0"
if "%APP_DIR:~-1%"=="\" set "APP_DIR=%APP_DIR:~0,-1%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$desktop = [Environment]::GetFolderPath('Desktop'); " ^
    "$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'PDF Baski Atolyesi.lnk'; " ^
    "foreach ($lnkPath in @((Join-Path $desktop 'PDF Baski Atolyesi.lnk'), $startMenu)) { " ^
    "  $s = $ws.CreateShortcut($lnkPath); " ^
    "  $s.TargetPath = '%APP_DIR%\Baslat.bat'; " ^
    "  $s.WorkingDirectory = '%APP_DIR%'; " ^
    "  $s.IconLocation = '%APP_DIR%\assets\icon.ico'; " ^
    "  $s.WindowStyle = 7; " ^
    "  $s.Save() " ^
    "}"
if errorlevel 1 goto fail

echo.
echo Kurulum tamamlandi! Masaustu ve Baslat Menusunden 'PDF Baski Atolyesi' ile baslatabilirsiniz.
pause
exit /b 0

:fail
echo.
echo HATA: Kurulum tamamlanamadi.
pause
exit /b 1
