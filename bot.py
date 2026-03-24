# bot.py - финальная версия с очередью сообщений
import os
import sys
import logging
import telebot
import json
import time
import requests
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
        {"text": "Екатерина Храмова — специалист по holistic-подходу к здоровью, наставник по очищению организма. Ее подход объединяет знания о теле, эмоциях и энергетике.", "source": "Taplink", "type": "about_author"},
        {"text": "Курс построен на мягком очищении без голодания и БАДов. Екатерина передает знания и практики, которые остаются с вами навсегда.", "source": "Taplink", "type": "about_course"},
        {"text": "Формат: живые онлайн-уроки, закрытый Telegram-чат, поддержка единомышленников, ответы на вопросы в реальном времени.", "source": "Taplink", "type": "format"},
        {"text": "Персональное ведение (25 000₽) включает: лекции об основах функционирования организма, ежедневные практики для работы с жидкостями и системами, индивидуальные консультации, личное сопровождение на весь период программы.", "source": "Taplink", "type": "tariff_personal"},
        {"text": "Базовый курс (12 200₽) включает: лекции об основах функционирования организма, ежедневные практики для работы с жидкостями и системами.", "source": "Taplink", "type": "tariff_base"},
        {"text": "VIP (100 000₽) включает: все возможности базового и персонального тарифов, плюс полное сопровождение, дополнительные индивидуальные сессии и приоритетную поддержку.", "source": "Taplink", "type": "tariff_vip"},
        {"text": "Отзывы: участники отмечают снижение веса, улучшение самочувствия, повышение энергии, очищение кожи, восстановление микрофлоры кишечника.", "source": "Taplink", "type": "reviews"},
        {"text": "Результаты программы: улучшение самочувствия, снижение веса, повышение энергии, регенерация организма, улучшение работы ЖКТ, нормализация сна, снижение тревожности.", "source": "Taplink", "type": "results"},
        {"text": "Как проходит курс: рекомендованный протокол подготовки, 4 урока в живом онлайн формате с записью, закрытая группа в Telegram, поддержка единомышленников.", "source": "Taplink", "type": "how_it_works"},
    ]

    for block in taplink_content:
        all_content.append(block)

    logging.info(f"✅ Всего загружено блоков: {len(all_content)}")
    return all_content

# === Веб-сервер ===
app = Flask(__name__)

@app.route('/')
def index():
    return "🤖 Бот с Gemini работает!"

@app.route('/health')
def health():
    return "OK", 200

def run_web():
    app.run(host='0.0.0.0', port=8080, threaded=True)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# === Запрос к Gemini ===
def ask_gemini(prompt):
    if not GEMINI_API_KEY:
        logging.error("❌ Нет API ключа Gemini")
        return None

    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"

    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    max_retries = 3
    retry_delay = 10

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                return result['candidates'][0]['content']['parts'][0]['text']
            elif response.status_code == 429:
                logging.warning(f"⚠️ Лимит запросов Gemini (429), попытка {attempt + 1} из {max_retries}")
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (attempt + 2)
                    logging.info(f"⏳ Ожидание {wait_time} секунд...")
                    time.sleep(wait_time)
                continue
            else:
                logging.error(f"❌ Gemini ошибка {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"❌ Gemini исключение: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None

    logging.error("❌ Превышено количество попыток запроса к Gemini")
    return None

# === Инициализация ===
bot = telebot.TeleBot(TELEGRAM_TOKEN)
knowledge_base = load_all_knowledge()

SYSTEM_PROMPT = """
Ты — дружелюбный, теплый и заботливый помощник Екатерины Храмовой. Твоя задача — продавать курс по очищению организма и помогать людям принять решение.

Важные правила:
1. Ты — ассистент, который знает ВСЮ информацию с сайта и Taplink
2. Отвечай развернуто, с душой, как живой человек
3. Используй всю доступную информацию, чтобы дать полный ответ
4. Если спрашивают о тарифах — подробно расскажи, что входит в каждый, и помоги выбрать
5. Если спрашивают об авторе — расскажи о Екатерине Храмовой и ее подходе
6. Если спрашивают о результатах — приведи конкретные результаты из отзывов
7. Предлагай помощь, уточняй, что хочет узнать человек
8. Используй теплые слова, эмодзи, будь поддерживающей
9. Если вопрос не совсем понятен — уточни, а не говори "не нашла информации"
10. Отвечай ТОЛЬКО на русском языке
11. Учитывай историю диалога. Если вы уже общались — не здоровайся заново, продолжай разговор
"""

# === Основная логика обработки сообщения ===
def process_message_sync(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "гость"
    user_question = message.text

    logging.info(f"📩 ОБРАБОТКА сообщения от {user_id} ({user_name}): {user_question}")

    try:
        bot.send_chat_action(message.chat.id, 'typing')
    except:
        pass

    add_to_history(user_id, "user", user_question)

    greetings = ["привет", "здравствуй", "добрый день", "здравствуйте", "hello", "hi", "/start"]
    is_first_greeting = len(user_histories.get(user_id, [])) <= 1 and any(greet in user_question.lower() for greet in greetings)

    if is_first_greeting:
        welcome_text = f"""Привет, {user_name}! 👋

Я помощник Екатерины Храмовой. Рада познакомиться!

Я здесь, чтобы рассказать вам о курсе по очищению организма, помочь разобраться в тарифах, поделиться результатами и ответить на любые вопросы.

Чем могу быть полезна? Рассказать о программе, ценах или подобрать подходящий тариф? 🤗"""
        bot.reply_to(message, welcome_text)
        add_to_history(user_id, "assistant", welcome_text)
        return

    history_context = get_history_context(user_id, last_n=5)

    all_info = []
    for block in knowledge_base:
        all_info.append(block['text'])
    full_knowledge = "\n\n---\n\n".join(all_info)

    prompt = f"""{SYSTEM_PROMPT}

{history_context}

Вот ВСЯ информация с сайта и Taplink:
{full_knowledge}

Вопрос пользователя: {user_question}
Имя пользователя: {user_name}

Найди в этой информации ответ на вопрос.
- Если в информации есть точный ответ — дай его развернуто, с душой
- Если информации недостаточно — скажи об этом и предложи помощь
- Используй ВСЮ информацию, которая есть
- Ответь на русском языке, будь теплой и заботливой"""

    try:
        logging.info(f"📤 Отправка запроса в Gemini...")
        answer = ask_gemini(prompt)

        if answer:
            logging.info(f"✅ Отправляю ответ от Gemini")
            bot.reply_to(message, answer)
            add_to_history(user_id, "assistant", answer)

            logging.info(f"⏳ Пауза 5 секунд перед следующим запросом...")
            time.sleep(5)

        else:
            logging.warning(f"⚠️ Gemini не ответил, использую запасной вариант")
            fallback_info = []
            for block in knowledge_base:
                if any(word in user_question.lower() for word in ["цена", "стоимость", "тариф", "курс", "сколько"]):
                    if block['type'] in ['tariff_personal', 'tariff_base', 'tariff_vip']:
                        fallback_info.append(block['text'])
                elif "автор" in user_question.lower() and block['type'] == 'about_author':
                    fallback_info.append(block['text'])
                elif "результат" in user_question.lower() and block['type'] == 'results':
                    fallback_info.append(block['text'])
                elif "отзыв" in user_question.lower() and block['type'] == 'reviews':
                    fallback_info.append(block['text'])
                elif "как проходит" in user_question.lower() and block['type'] == 'how_it_works':
                    fallback_info.append(block['text'])

            if fallback_info:
                fallback = f"{user_name}, вот что я знаю по вашему вопросу:\n\n" + "\n\n".join(fallback_info[:3])
            else:
                fallback = f"{user_name}, у меня временные сложности с обработкой запроса. Попробуйте спросить позже или напишите в поддержку. 😊"

            bot.reply_to(message, fallback)
            add_to_history(user_id, "assistant", fallback)

    except Exception as e:
        logging.error(f"❌ ОШИБКА: {e}")
        fallback = f"{user_name}, произошла ошибка. Попробуйте спросить по-другому или напишите позже. 😊"
        bot.reply_to(message, fallback)
        add_to_history(user_id, "assistant", fallback)

# === Обработка очереди сообщений ===
def process_queue(user_id):
    with queue_lock:
        if processing[user_id] or not message_queue[user_id]:
            return
        processing[user_id] = True
        next_message = message_queue[user_id].pop(0)

    try:
        process_message_sync(next_message)
    finally:
        with queue_lock:
            processing[user_id] = False
        process_queue(user_id)

# === Получение сообщений (добавление в очередь) ===
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    with queue_lock:
        message_queue[user_id].append(message)
    process_queue(user_id)

# === Запуск ===
if __name__ == "__main__":
    keep_alive()
    logging.info("⏳ Ожидание 5 секунд...")
    time.sleep(5)
    logging.info("🤖 Бот запущен!")

    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Ошибка polling: {e}. Перезапуск...")
            time.sleep(10)