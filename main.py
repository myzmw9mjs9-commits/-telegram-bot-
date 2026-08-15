import os
import telebot
from flask import Flask
import time

TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/')
def index():
    return "Bot is running with Polling"

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "مرحباً! البوت يعمل بنظام Polling.")

if __name__ == '__main__':
    # تشغيل Flask في خيط منفصل (اختياري)
    import threading
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)

    # إزالة أي ويب هوك قديم لتجنب التعارض
    try:
        bot.remove_webhook()
        print("Webhook removed successfully")
    except Exception as e:
        print(f"Error removing webhook: {e}")

    # تشغيل Flask في الخلفية
    threading.Thread(target=run_flask).start()

    # مع إعادة محاولة تلقائية بدء Polling
    print("Starting Polling...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"Polling error: {e}. Reconnecting in 5 seconds...")
            time.sleep(5)
