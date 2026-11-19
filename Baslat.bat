@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" app.py %*
    exit /b 0
)
if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" app.py %*
    exit /b 0
)

where python >nul 2>nul
if errorlevel 1 goto no_python

python -c "import PySide6, pymupdf, PIL" >nul 2>nul
if errorlevel 1 goto missing_packages

where pythonw >nul 2>nul
if errorlevel 1 (
    start "" python app.py %*
    exit /b 0
)

start "" pythonw app.py %*
exit /b 0

:no_python
echo.
echo Python bulunamadi.
echo Python 3.10 veya daha yenisini kurun: https://www.python.org/downloads/windows/
echo Kurulum sirasinda "Add python.exe to PATH" secenegini isaretleyin.
echo.
pause
exit /b 1

:missing_packages
echo.
echo Gerekli Python paketleri eksik.
echo Kurmak icin install_windows.bat dosyasini calistirin veya su komutu girin:
echo     python -m pip install -r requirements.txt
echo.
pause
exit /b 1
