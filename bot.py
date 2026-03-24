# bot.py - исправленная версия
import os
import sys
import logging
import telebot
import json
import time
import requests
from flask import Flask
from threading import Thread

# Настройка логирования
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# ================================

# === Проверка наличия ключей ===
if not TELEGRAM_TOKEN:
    logging.error("❌ TELEGRAM_TOKEN не задан в переменных окружения!")
if not GEMINI_API_KEY:
    logging.error("❌ GEMINI_API_KEY не задан в переменных окружения!")

# === Веб-сервер для keep-alive ===
app = Flask(__name__)

@app.route('/')
def index():
    return "🤖 Бот с Gemini работает!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# === Загрузка базы знаний ===
def load_knowledge_base():
    try:
        with open('katerina_content.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            logging.info(f"✅ Загружено блоков: {len(data['content'])}")
            return data['content']
    except Exception as e:
        logging.error(f"❌ Ошибка загрузки: {e}")
        return []

# === Поиск по базе знаний ===
def search_knowledge(query, knowledge_base):
    query_lower = query.lower()
    results = []
    
    for block in knowledge_base:
        text = block.get('text', '').lower()
        keywords = [kw.lower() for kw in block.get('keywords', [])]
        
        score = 0
        for kw in keywords:
            if kw in query_lower:
                score += 10
        words = query_lower.split()
        for word in words:
            if len(word) > 3 and word in text:
                score += 2
        
        if score > 0:
            results.append((score, block['text']))
    
    results.sort(reverse=True)
    return [text for score, text in results[:3]]

# === Запрос к Gemini ===
def ask_gemini(prompt):
    if not GEMINI_API_KEY:
        logging.error("❌ Нет API ключа Gemini")
        return None
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            text = result['candidates'][0]['content']['parts'][0]['text']
            logging.info(f"✅ Gemini ответ получен, длина: {len(text)}")
            return text
        else:
            logging.error(f"❌ Gemini ошибка {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        logging.error(f"❌ Gemini исключение: {e}")
        return None

# === Инициализация бота ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)
knowledge_base = load_knowledge_base()

SYSTEM_PROMPT = """
Ты — дружелюбный помощник Екатерины Храмовой. Отвечай на вопросы о курсе по очищению организма.

Правила:
1. Отвечай ТОЛЬКО на основе информации, которая дана в контексте
2. Будь теплой, заботливой, но профессиональной
3. Если точного ответа нет, предложи написать на почту или в поддержку
4. Если спрашивают о ценах, указывай тарифы: Базовый (12 200₽), Персональное ведение (25 000₽), VIP (100 000₽)
5. Отвечай кратко и по делу, но с душой
"""

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_question = message.text
    
    logging.info(f"📩 ПОЛУЧЕНО СООБЩЕНИЕ от {message.from_user.id}: {user_question}")
    
    # Показываем, что бот печатает
    try:
        bot.send_chat_action(message.chat.id, 'typing')
    except:
        pass
    
    # Ищем в базе знаний
    relevant_info = search_knowledge(user_question, knowledge_base)
    
    if not relevant_info:
        logging.info(f"🔍 Ничего не найдено в базе знаний")
        answer = "Извините, я не нашла информации по вашему вопросу. Напишите в поддержку!"
        bot.reply_to(message, answer)
        return
    
    logging.info(f"🔍 Найдено блоков: {len(relevant_info)}")
    context = "\n\n---\n\n".join(relevant_info)
    
    # Формируем запрос к Gemini
    prompt = f"""{SYSTEM_PROMPT}

Контекст с сайта:
{context}

Вопрос пользователя: {user_question}

Дай ответ на русском языке, используя ТОЛЬКО информацию из контекста. Будь дружелюбной и полезной."""
    
    # Пробуем получить ответ от Gemini
    try:
        logging.info(f"📤 Отправка запроса в Gemini...")
        answer = ask_gemini(prompt)
        
        if answer:
            logging.info(f"✅ Отправляю ответ от Gemini")
            bot.reply_to(message, answer)
        else:
            logging.warning(f"⚠️ Gemini не ответил, использую запасной вариант")
            bot.reply_to(message, f"📌 {relevant_info[0]}")
            
    except Exception as e:
        logging.error(f"❌ ОШИБКА в handle_message: {e}")
        bot.reply_to(message, f"📌 Вот что я нашла:\n\n{relevant_info[0]}")

# === Запуск бота ===
if __name__ == "__main__":
    keep_alive()
    
    # Небольшая задержка перед запуском polling
    logging.info("⏳ Ожидание 5 секунд перед подключением к Telegram...")
    time.sleep(5)
    
    logging.info("🤖 Бот с Gemini запущен!")
    logging.info("🌐 Веб-сервер для пингов работает на порту 8080")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Ошибка polling: {e}. Перезапуск через 10 секунд...")
            time.sleep(10)