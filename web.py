# web.py - отдельный веб-сервер для пингов
from flask import Flask

app = Flask(__name__)

@app.route('/')
def index():
    return "🤖 Бот работает!"

@app.route('/health')
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)