@echo off
chcp 65001 >nul
echo.
echo ==================================================
echo   Установка парсера объявлений о продаже бизнеса
echo ==================================================
echo.

:: Проверяем Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ОШИБКА: Python не найден!
    echo.
    echo Скачай и установи Python с сайта: https://python.org/downloads
    echo При установке обязательно поставь галочку "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo Python %PYVER% найден

:: Создаём виртуальное окружение
if not exist "venv" (
    echo Создаём виртуальное окружение venv...
    python -m venv venv
)

:: Активируем и устанавливаем зависимости
call venv\Scripts\activate.bat

echo Устанавливаем зависимости...
pip install --upgrade pip -q
pip install -r requirements.txt -q

:: Playwright
echo Устанавливаем Playwright (Chromium)...
playwright install chromium

:: Создаём .env если нет
if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo ВАЖНО: Создан файл .env - нужно заполнить своими данными!
    echo Открой .env в блокноте и заполни:
    echo   - TELEGRAM_BOT_TOKEN
    echo   - TELEGRAM_CHAT_ID
    echo   - GOOGLE_SPREADSHEET_ID
)

call venv\Scripts\deactivate.bat

echo.
echo ==================================================
echo Установка завершена!
echo.
echo Следующие шаги:
echo   1. Заполни файл .env (двойной клик - открыть в Блокноте)
echo   2. Положи credentials.json рядом с main.py
echo   3. Запусти парсер: дважды кликни run.bat
echo ==================================================
echo.
pause
