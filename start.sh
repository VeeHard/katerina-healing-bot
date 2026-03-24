#!/bin/bash
echo "🚀 Запуск веб-сервера на порту 8080..."
gunicorn web:app --bind 0.0.0.0:8080 --daemon

echo "🚀 Запуск бота..."
python bot.py