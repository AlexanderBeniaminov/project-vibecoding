@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist "venv" (
    echo ОШИБКА: виртуальное окружение не найдено.
    echo Сначала запусти install.bat
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

if "%1"=="--schedule" (
    echo Запуск по расписанию 09:00 МСК ежедневно...
    python main.py --schedule
) else (
    echo Запуск парсера...
    python main.py %*
)

call venv\Scripts\deactivate.bat
pause
