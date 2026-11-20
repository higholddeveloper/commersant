@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" python -m venv .venv
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt || exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --windowed --name Commersant ^
    --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick main.py || exit /b 1
if exist dist\Commersant\saves rmdir /s /q dist\Commersant\saves
copy /y commercial.man dist\Commersant\commercial.man >nul
copy /y README.md dist\Commersant\README.md >nul
".venv\Scripts\python.exe" -c "from core.version import VERSION; print(VERSION)" > builder.txt
set /p VER=<builder.txt
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Commersant' -DestinationPath 'dist\Commersant-v%VER%-win64.zip' -Force"
echo.
echo Готово: dist\Commersant-v%VER%-win64.zip
