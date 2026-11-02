@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto no_python

python -c "import customtkinter, pymupdf, PIL" >nul 2>nul
if errorlevel 1 goto missing_packages

where pythonw >nul 2>nul
if errorlevel 1 (
    start "" python app.py
    exit /b 0
)

start "" pythonw app.py
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
echo Kurmak icin bu klasorde su komutu calistirin:
echo     python -m pip install -r requirements.txt
echo.
pause
exit /b 1
