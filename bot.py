# bot.py - с прямыми HTTP-запросами к Gemini API и Grounding
import os
import sys
import logging
import telebot
import time
import random
import requests
import json
from flask import Flask
from threading import Thread
from collections import defaultdict
from threading import Lock

# Настройка логирования
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# ================================

# === Проверка ключей ===
if not TELEGRAM_TOKEN:
    logging.error("❌ TELEGRAM_TOKEN не задан!")
if not GEMINI_API_KEY:
    logging.error("❌ GEMINI_API_KEY не задан!")

# === Инициализация бота (В НАЧАЛЕ!) ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === Глобальный таймер для Gemini ===
last_gemini_request_time = 0
gemini_lock = Lock()
GEMINI_MIN_INTERVAL = 5

# === Очередь сообщений ===
message_queue = defaultdict(list)
queue_lock = Lock()
processing = defaultdict(bool)

# === Память диалогов ===
user_histories = defaultdict(list)

def add_to_history(user_id, role, content):
    user_histories[user_id].append({"role": role, "content": content})
    if len(user_histories[user_id]) > 20:
        user_histories[user_id] = user_histories[user_id][-20:]

def get_history_context(user_id, last_n=5):
    history = user_histories.get(user_id, [])
    if not history:
        return ""
    recent = history[-last_n:]
    context = "История нашего диалога:\n"
    for msg in recent:
        context += f"{'Пользователь' if msg['role'] == 'user' else 'Помощник'}: {msg['content']}\n"
    return context

# === Системный промпт ===
SYSTEM_PROMPT = """
Ты — дружелюбный, теплый и заботливый помощник Катерины Храмовой.

Твоя специализация — курс по очищению организма. У тебя есть доступ к интернету, чтобы находить актуальную информацию.

ВАЖНО: Имя автора курса — Катерина (не Екатерина). Всегда используй имя Катерина.

При любом вопросе о курсе очищения организма, ценах, тарифах, результатах — ОБЯЗАТЕЛЬНО используй поиск в интернете и обращайся к сайтам:
- https://katerinakhramova.tilda.ws/katerinahealing
- https://taplink.cc/katerinahealing

Не используй свои знания о курсе, если они не подтверждены этими источниками.

Правила:
1. Если вопрос о курсе — ищи информацию на указанных сайтах.
2. Если вопрос о ценах — найди актуальные тарифы на сайте.
3. Если вопрос о результатах — найди отзывы на сайте.
4. Если вопрос о здоровье, питании, очищении — отвечай, используя holistic-подход.
5. Если вопрос требует актуальной информации (курс валют, погода, новости) — используй поиск в интернете.
6. Если вопрос не связан с темой здоровья и курса — мягко перенаправь к теме.
7. Отвечай на русском языке, будь теплой и заботливой.
"""

# === Веб-сервер для keep-alive ===
app = Flask(__name__)

@app.route('/')
def index():
    return "🤖 Бот Катерины Храмовой работает!"

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    app.run(host='0.0.0.0', port=8080, threaded=True)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# === Запрос к Gemini с Grounding через REST API ===
def ask_gemini_with_search(prompt):
    global last_gemini_request_time
    
    with gemini_lock:
        current_time = time.time()
        time_since_last = current_time - last_gemini_request_time
        if time_since_last < GEMINI_MIN_INTERVAL:
            wait_time = GEMINI_MIN_INTERVAL - time_since_last
            logging.info(f"⏳ Ожидание {wait_time:.1f} сек перед запросом к Gemini...")
            time.sleep(wait_time)
        last_gemini_request_time = time.time()
    
    try:
        full_prompt = f"{SYSTEM_PROMPT}\n\n{prompt}"
        
        # Формируем запрос к Gemini API с включённым поиском
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        
        payload = {
            "contents": [{
                "parts": [{"text": full_prompt}]
            }],
            "tools": [{
                "googleSearch": {}  # Включаем Google Search Grounding
            }]
        }
        
        response = requests.post(url, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            # Извлекаем текст ответа
            answer = result['candidates'][0]['content']['parts'][0]['text']
            
            # Если есть ссылки на источники, добавляем их
            if 'groundingMetadata' in result['candidates'][0]:
                sources = result['candidates'][0]['groundingMetadata'].get('groundingChunks', [])
                if sources:
                    links = []
                    for chunk in sources[:3]:
                        if 'web' in chunk:
                            links.append(chunk['web']['uri'])
                    if links:
                        answer += f"\n\n🔗 Источники: " + ", ".join(links)
            
            return answer
        else:
            logging.error(f"❌ Gemini ошибка {response.status_code}: {response.text[:200]}")
            return None
            
    except Exception as e:
        logging.error(f"❌ Gemini исключение: {e}")
        return None

# === Обработка сообщений ===
def process_message_sync(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "гость"
    user_question = message.text
    
    logging.info(f"📩 ОБРАБОТКА: {user_name}: {user_question}")
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
    except:
        pass
    
    add_to_history(user_id, "user", user_question)
    
    # Имитация человеческой задержки (3-8 секунд)
    delay = random.uniform(3, 8)
    logging.info(f"⏳ Имитация задержки {delay:.1f} секунд...")
    time.sleep(delay)
    
    # Проверка на приветствие (для первого сообщения)
    greetings = ["привет", "здравствуй", "/start"]
    is_first = len(user_histories.get(user_id, [])) <= 1 and any(g in user_question.lower() for g in greetings)
    
    if is_first:
        welcome = f"Привет, {user_name}! 👋 Я помощник Катерины Храмовой. Расскажу о курсе очищения, тарифах и результатах. Чем могу помочь?"
        bot.reply_to(message, welcome)
        add_to_history(user_id, "assistant", welcome)
        return
    
    # Получаем историю диалога
    history_context = get_history_context(user_id, last_n=5)
    
    # Формируем промпт
    prompt = f"""
{history_context}

Вопрос пользователя: {user_question}
Имя пользователя: {user_name}

Дай развернутый, теплый ответ. Если нужно найти актуальную информацию — используй поиск в интернете. Если вопрос о курсе — обязательно ищи на сайтах Катерины Храмовой.
"""
    
    try:
        answer = ask_gemini_with_search(prompt)
        
        if answer:
            bot.reply_to(message, answer)
            add_to_history(user_id, "assistant", answer)
        else:
            fallback = f"{user_name}, у меня временные технические сложности 😔\n\nВы также можете связаться с Катериной напрямую: @KaterinaHealing\n\nПопробуйте спросить позже или напишите в Telegram Катерине, она обязательно поможет! 💫"
            bot.reply_to(message, fallback)
            add_to_history(user_id, "assistant", fallback)
            
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")
        fallback = f"{user_name}, у меня временные технические сложности 😔\n\nВы также можете связаться с Катериной напрямую: @KaterinaHealing\n\nПопробуйте спросить позже или напишите в Telegram Катерине, она обязательно поможет! 💫"
        bot.reply_to(message, fallback)
        add_to_history(user_id, "assistant", fallback)

# === Обработка очереди ===
def process_queue(user_id):
    with queue_lock:
        if processing[user_id] or not message_queue[user_id]:
            return
        processing[user_id] = True
        msg = message_queue[user_id].pop(0)
    
    try:
        process_message_sync(msg)
    finally:
        with queue_lock:
            processing[user_id] = False
        process_queue(user_id)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    with queue_lock:
        message_queue[message.from_user.id].append(message)
    process_queue(message.from_user.id)

# === Запуск ===
if __name__ == "__main__":
    keep_alive()
    logging.info("⏳ Ожидание 5 секунд...")
    time.sleep(5)
    logging.info("🤖 Бот Катерины Храмовой с Gemini Grounding запущен!")
    logging.info("🌐 Поддерживает поиск в интернете")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Ошибка polling: {e}. Перезапуск через 10 сек...")
            time.sleep(10)