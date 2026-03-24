# bot.py - только бот, без Flask
import os
import sys
import logging
import telebot
import json
import time
import requests
from collections import defaultdict
from threading import Lock

# Настройка логирования
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# ================================

# === Глобальный таймер для Gemini ===
last_gemini_request_time = 0
gemini_lock = Lock()
GEMINI_MIN_INTERVAL = 60

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

# === Загрузка базы знаний ===
def load_all_knowledge():
    all_content = []
    try:
        with open('katerina_content.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
            for block in data['content']:
                all_content.append({
                    "text": block['text'],
                    "source": "Основной сайт",
                    "type": block.get('type', 'general')
                })
            logging.info(f"✅ Загружено с основного сайта: {len(data['content'])} блоков")
    except Exception as e:
        logging.error(f"❌ Ошибка загрузки основного сайта: {e}")

    taplink_content = [
        {"text": "Екатерина Храмова — специалист по holistic-подходу к здоровью, наставник по очищению организма.", "source": "Taplink", "type": "about_author"},
        {"text": "Курс построен на мягком очищении без голодания и БАДов.", "source": "Taplink", "type": "about_course"},
        {"text": "Формат: живые онлайн-уроки, закрытый Telegram-чат.", "source": "Taplink", "type": "format"},
        {"text": "Персональное ведение (25 000₽) включает: лекции, практики, консультации, сопровождение.", "source": "Taplink", "type": "tariff_personal"},
        {"text": "Базовый курс (12 200₽) включает: лекции и практики.", "source": "Taplink", "type": "tariff_base"},
        {"text": "VIP (100 000₽) включает: полное сопровождение и приоритетную поддержку.", "source": "Taplink", "type": "tariff_vip"},
        {"text": "Отзывы: участники отмечают снижение веса, улучшение самочувствия, повышение энергии.", "source": "Taplink", "type": "reviews"},
        {"text": "Результаты: улучшение самочувствия, снижение веса, повышение энергии.", "source": "Taplink", "type": "results"},
    ]

    for block in taplink_content:
        all_content.append(block)

    logging.info(f"✅ Всего загружено блоков: {len(all_content)}")
    return all_content

# === Запрос к Gemini ===
def ask_gemini(prompt):
    global last_gemini_request_time
    if not GEMINI_API_KEY:
        return None

    with gemini_lock:
        current_time = time.time()
        time_since_last = current_time - last_gemini_request_time
        if time_since_last < GEMINI_MIN_INTERVAL:
            wait_time = GEMINI_MIN_INTERVAL - time_since_last
            logging.info(f"⏳ Ожидание {wait_time:.1f} сек перед запросом к Gemini...")
            time.sleep(wait_time)
        last_gemini_request_time = time.time()

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for attempt in range(5):
        try:
            response = requests.post(url, json=payload, timeout=60)
            if response.status_code == 200:
                return response.json()['candidates'][0]['content']['parts'][0]['text']
            elif response.status_code in (429, 503):
                wait = 10 * (attempt + 2)
                logging.warning(f"⚠️ Ошибка {response.status_code}, попытка {attempt+1}/5, жду {wait} сек")
                time.sleep(wait)
            else:
                return None
        except Exception as e:
            logging.error(f"❌ Gemini ошибка: {e}")
            time.sleep(10)
    return None

# === Инициализация ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)
knowledge_base = load_all_knowledge()

SYSTEM_PROMPT = """
Ты — дружелюбный помощник Екатерины Храмовой. Отвечай на основе информации с сайта.
Будь теплой, помогай выбрать тариф, рассказывай о результатах.
Учитывай историю диалога. Не здоровайся каждый раз.
Отвечай на русском языке.
"""

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

    greetings = ["привет", "здравствуй", "/start"]
    is_first = len(user_histories.get(user_id, [])) <= 1 and any(g in user_question.lower() for g in greetings)
    if is_first:
        welcome = f"Привет, {user_name}! 👋 Я помощник Екатерины Храмовой. Расскажу о курсе очищения, тарифах и результатах. Чем могу помочь?"
        bot.reply_to(message, welcome)
        add_to_history(user_id, "assistant", welcome)
        return

    history = get_history_context(user_id, last_n=5)
    all_info = [b['text'] for b in knowledge_base][:15]
    full_knowledge = "\n\n---\n\n".join(all_info)

    prompt = f"""{SYSTEM_PROMPT}

{history}

Вот информация с сайта:
{full_knowledge}

Вопрос: {user_question}
Имя: {user_name}

Дай развернутый, теплый ответ."""

    try:
        answer = ask_gemini(prompt)
        if answer:
            bot.reply_to(message, answer)
            add_to_history(user_id, "assistant", answer)
        else:
            fallback = f"{user_name}, у меня временные сложности. Попробуйте спросить позже или напишите в поддержку. 😊"
            bot.reply_to(message, fallback)
            add_to_history(user_id, "assistant", fallback)
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")
        bot.reply_to(message, f"{user_name}, произошла ошибка. Попробуйте позже.")

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
    logging.info("🤖 Бот запущен (без Flask)")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Ошибка polling: {e}. Перезапуск через 10 сек...")
            time.sleep(10)