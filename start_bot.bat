@echo off
cd /d "%~dp0"

echo Текущая папка:
cd

echo.
echo Запуск бота...
"C:\Users\serda\AppData\Local\Programs\Python\Python311\python.exe" bot.py

if errorlevel 1 (
    echo.
    echo ОШИБКА при запуске бота!
    echo Проверьте:
    echo 1. Установлены ли зависимости (pip install -r requirements.txt)
    echo 2. Создан ли .env и указан BOT_TOKEN
    echo 3. Логи выше на наличие ошибок
)

echo.
pause
