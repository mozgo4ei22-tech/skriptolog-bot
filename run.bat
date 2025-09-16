@echo off
SETLOCAL
echo === Скриптолог: запуск ===
where python >nul 2>nul
IF %ERRORLEVEL% NEQ 0 (
  echo Python не найден. Установите Python 3.9+ с python.org и повторите.
  pause
  exit /b 1
)
echo Устанавливаю зависимости...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo Запускаю бота...
python skriptolog_bot.py
pause
