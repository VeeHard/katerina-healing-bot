# bot.py - полная версия с Gemini
import telebot
import json
import time
import requests
from flask import Flask
from threading import Thread

# ========== НАСТРОЙКИ ==========
TELEGRAM_TOKEN = "8704823023:AAGQgsQ6isAm7Da4EasFhQ3p8c2nW4sM02w"
GEMINI_API_KEY = "AIzaSyBDTN-5avqFIOng-sW9PF0Srv2f9L7wtIU"
# ================================

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
            print(f"✅ Загружено блоков: {len(data['content'])}")
            return data['content']
    except Exception as e:
        print(f"❌ Ошибка загрузки: {e}")
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
            return result['candidates'][0]['content']['parts'][0]['text']
        else:
            print(f"Gemini ошибка: {response.status_code}")
            return None
    except Exception as e:
        print(f"Gemini исключение: {e}")
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
    
    try:
        bot.send_chat_action(message.chat.id, 'typing')
    except:
        pass
    
    # Ищем в базе знаний
    relevant_info = search_knowledge(user_question, knowledge_base)
    
    if not relevant_info:
        answer = "Извините, я не нашла информации по вашему вопросу. Напишите в поддержку!"
        bot.reply_to(message, answer)
        return
    
    context = "\n\n---\n\n".join(relevant_info)
    
    # Формируем запрос к Gemini
    prompt = f"""{SYSTEM_PROMPT}

Контекст с сайта:
{context}

Вопрос пользователя: {user_question}

Дай ответ на русском языке, используя ТОЛЬКО информацию из контекста. Будь дружелюбной и полезной."""
    
    try:
        print(f"📤 Отправка запроса в Gemini...")
        answer = ask_gemini(prompt)
        
        if answer:
            print(f"✅ Gemini ответил")
            bot.reply_to(message, answer)
        else:
            # Если Gemini не ответил, используем запасной вариант
            print(f"⚠️ Использую запасной вариант")
            bot.reply_to(message, f"📌 {relevant_info[0]}")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        bot.reply_to(message, f"📌 Вот что я нашла:\n\n{relevant_info[0]}")

# === Запуск бота ===
if __name__ == "__main__":
    keep_alive()
    print("🤖 Бот с Gemini запущен!")
    print("🌐 Веб-сервер для пингов работает на порту 8080")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Ошибка: {e}. Перезапуск через 10 секунд...")
            time.sleep(10)