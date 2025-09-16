#!/usr/bin/env bash
set -e
echo "=== Скриптолог: запуск ==="
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python3 не найден. Установите Python 3.9+."
  exit 1
fi
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 skriptolog_bot.py
