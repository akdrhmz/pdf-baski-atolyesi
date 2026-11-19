@echo off
setlocal
chcp 65001 >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$desktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PDF Baski Atolyesi.lnk'; " ^
    "$startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'PDF Baski Atolyesi.lnk'; " ^
    "Remove-Item -Force -ErrorAction SilentlyContinue $desktop, $startMenu"

echo PDF Baski Atolyesi Masaustu ve Baslat Menusu kisayollari kaldirildi.
pause
