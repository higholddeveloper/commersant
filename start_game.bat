@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Первый запуск: создаю виртуальное окружение...
    python -m venv .venv || (echo Не найден Python 3.11+. Установите его с python.org и поставьте галочку "Add python.exe to PATH". & pause & exit /b 1)
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || (echo Не удалось установить зависимости. & pause & exit /b 1)
)
".venv\Scripts\python.exe" main.py
