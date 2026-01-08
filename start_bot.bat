@echo off
cd /d "%~dp0"

REM Включаем UTF-8 в cmd
chcp 65001 >nul

echo Текущая папка:
cd
echo.

REM Путь к Python
set "PY=C:\Users\serda\AppData\Local\Programs\Python\Python311\python.exe"

echo Запуск бота (отдельное окно)...
start "Telegram Bot" cmd /k ""%PY%" bot.py"

echo.
echo Запуск admin web панели (отдельное окно)...
start "Admin Web" cmd /k ""%PY%" start_admin_ui.py"

echo.
echo Оба процесса запущены. Эти окна можно не закрывать.
pause
