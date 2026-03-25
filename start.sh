#!/bin/bash
echo "🚀 Установка зависимостей..."
pip install --upgrade pip
pip install -r requirements.txt
echo "🚀 Запуск бота..."
python bot.py