#!/bin/bash
echo "🚀 Запуск бота на Render..."
gunicorn bot:app --bind 0.0.0.0:8080 --daemon
python bot.py