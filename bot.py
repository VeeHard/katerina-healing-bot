# bot.py - финальная версия
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

# Настройка логирования
logging.basicConfig(stream=sys.stderr, level=logging.INFO)

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# ================================

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
    """Загружает контент с обоих сайтов"""
    all_content = []
    
    # Основной сайт
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
    
    # Taplink (добавляем вручную важную информацию)
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

# === Смысловой поиск ===
def semantic_search(query, knowledge_base, top_k=6):
    """Ищет наиболее релевантные блоки по смыслу"""
    query_lower = query.lower()
    results = []
    
    for block in knowledge_base:
        text = block['text'].lower()
        
        # Базовый подсчет очков
        score = 0
        
        # Прямые совпадения ключевых слов
        important_words = ["персональное", "ведение", "базовый", "vip", "цена", "стоимость", 
                          "результат", "отзыв", "программа", "очищение", "кишечник", "печень",
                          "тариф", "входит", "включено", "катерина", "храмова", "автор"]
        
        for word in important_words:
            if word in query_lower and word in text:
                score += 15
        
        # Совпадение по словам
        words = query_lower.split()
        for word in words:
            if len(word) > 3 and word in text:
                score += 3
        
        # Учитываем тип блока
        if block['type'] == 'tariff_personal' and 'персональное' in query_lower:
            score += 30
        if block['type'] == 'tariff_base' and 'базовый' in query_lower:
            score += 30
        if block['type'] == 'tariff_vip' and 'vip' in query_lower:
            score += 30
        if block['type'] == 'about_author' and ('автор' in query_lower or 'катерина' in query_lower):
            score += 25
        
        if score > 0:
            results.append((score, block))
    
    results.sort(reverse=True, key=lambda x: x[0])
    return [r[1]['text'] for r in results[:top_k]]

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
"""

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "гость"
    user_question = message.text
    
    logging.info(f"📩 ПОЛУЧЕНО СООБЩЕНИЕ от {user_id} ({user_name}): {user_question}")
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
    except:
        pass
    
    # Сохраняем вопрос в историю
    add_to_history(user_id, "user", user_question)
    
    # Проверка на приветствие
    greetings = ["привет", "здравствуй", "добрый день", "здравствуйте", "hello", "hi", "/start"]
    if any(greet in user_question.lower() for greet in greetings):
        welcome_text = f"""Привет, {user_name}! 👋

Я помощник Екатерины Храмовой. Рада познакомиться!

Я здесь, чтобы рассказать вам о курсе по очищению организма, помочь разобраться в тарифах, поделиться результатами и ответить на любые вопросы.

Чем могу быть полезна? Рассказать о программе, ценах или подобрать подходящий тариф? 🤗"""
        bot.reply_to(message, welcome_text)
        add_to_history(user_id, "assistant", welcome_text)
        return
    
    # Ищем релевантную информацию
    relevant_info = semantic_search(user_question, knowledge_base, top_k=6)
    
    # Если ничего не найдено — отправляем в Gemini для генерации ответа
    if not relevant_info:
    logging.info(f"🔍 Ничего не найдено в базе знаний, обращаюсь к Gemini")
    
    # Получаем историю диалога
    history_context = get_history_context(user_id, last_n=5)
    
    prompt = f"""Ты — дружелюбный помощник Екатерины Храмовой, эксперт по курсу очищения организма.

{history_context}

Пользователь {user_name} задал вопрос: "{user_question}"

В базе знаний нет точной информации по этому вопросу.

Твоя задача:
1. Учитывай историю диалога. Если вы уже общались — не здоровайся заново, продолжай разговор
2. Если вопрос не связан с темой курса — мягко скажи, что твоя специализация — это курс очищения организма, и предложи помощь по этой теме
3. Если вопрос связан с темой (здоровье, очищение, питание, энергия, самочувствие) — ответь на него своими словами, используя знания о holistic-подходе
4. После ответа предложи 3-4 конкретные темы, по которым ты можешь помочь
5. Используй имя пользователя {user_name}, но только если это уместно по контексту (не начинай каждый ответ с "Привет, {user_name}!")
6. Будь теплой, дружелюбной, без шаблонных фраз
7. Ответь на русском языке

Сделай ответ естественным, уникальным для этого вопроса."""

    try:
        answer = ask_gemini(prompt)
        if answer:
            bot.reply_to(message, answer)
            add_to_history(user_id, "assistant", answer)
        else:
            fallback = f"{user_name}, я в основном помогаю с вопросами о курсе очищения организма. Я могу рассказать о программе, тарифах, результатах или об авторе. Что вас интересует? 🤗"
            bot.reply_to(message, fallback)
            add_to_history(user_id, "assistant", fallback)
    except Exception as e:
        logging.error(f"❌ Ошибка: {e}")
        fallback = f"Я помогаю с вопросами о курсе очищения организма. Что бы вы хотели узнать: о программе, тарифах или результатах? 😊"
        bot.reply_to(message, fallback)
        add_to_history(user_id, "assistant", fallback)
    
    return
    
    # Если информация найдена — используем её для ответа
    logging.info(f"🔍 Найдено блоков: {len(relevant_info)}")
    context = "\n\n---\n\n".join(relevant_info)
    history_context = get_history_context(user_id, last_n=5)
    
    prompt = f"""{SYSTEM_PROMPT}

{history_context}

Вся информация с сайта и Taplink:
{context}

Вопрос пользователя: {user_question}
Имя пользователя: {user_name}

Дай развернутый, теплый, продающий ответ. Используй ВСЮ информацию, которая есть. Если нужно — предложи варианты, помоги выбрать, расскажи подробнее. Будь как заботливый консультант, который хочет помочь человеку сделать правильный выбор. Ответь на русском языке."""
    
    try:
        logging.info(f"📤 Отправка запроса в Gemini...")
        answer = ask_gemini(prompt)
        
        if answer:
            logging.info(f"✅ Отправляю ответ от Gemini")
            bot.reply_to(message, answer)
            add_to_history(user_id, "assistant", answer)
        else:
            logging.warning(f"⚠️ Gemini не ответил, использую запасной вариант")
            fallback = f"{user_name}, вот что я знаю по вашему вопросу:\n\n" + "\n\n".join(relevant_info[:3])
            bot.reply_to(message, fallback)
            add_to_history(user_id, "assistant", fallback)
            
    except Exception as e:
        logging.error(f"❌ ОШИБКА: {e}")
        fallback = f"{user_name}, вот что я нашла:\n\n" + "\n\n".join(relevant_info[:2])
        bot.reply_to(message, fallback)
        add_to_history(user_id, "assistant", fallback)

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
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return result['candidates'][0]['content']['parts'][0]['text']
        else:
            logging.error(f"❌ Gemini ошибка {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"❌ Gemini исключение: {e}")
        return None

# === Запуск ===
if __name__ == "__main__":
    keep_alive()
    logging.info("⏳ Ожидание 5 секунд...")
    time.sleep(5)
    logging.info("🤖 Бот с RAG-поиском запущен!")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Ошибка polling: {e}. Перезапуск...")
            time.sleep(10)