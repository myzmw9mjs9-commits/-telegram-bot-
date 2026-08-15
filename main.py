import os
import time
import threading
import telebot
from flask import Flask

# التوكن من متغيرات Render
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if TOKEN is None:
    raise Exception("❌ TELEGRAM_BOT_TOKEN غير موجود في المتغيرات")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/')
def index():
    return "البوت يعمل ✅"

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "مرحباً! البوت شغال الآن 🚀")

if __name__ == '__main__':
    # تشغيل Flask في الخلفية (يحتاجه Render)
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)

    threading.Thread(target=run_flask, daemon=True).start()
    print(f"✅ Flask يعمل على المنفذ {os.environ.get('PORT', 10000)}")

    # إزالة أي Webhook عالق لتفادي خطأ 409
    try:
        bot.remove_webhook()
        print("✅ تم إزالة الـ Webhook القديم")
    except Exception as e:
        print(f"⚠️ تنبيه: {e}")

    # تشغيل البوت مع إعادة محاولة تلقائية
    print("⏳ بدء تشغيل البوت...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"❌ خطأ في البوت: {e}")
            print("🔄 إعادة المحاولة بعد 5 ثوانٍ...")
            time.sleep(5)