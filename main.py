import os
import time
import threading
import telebot
from flask import Flask

# جلب التوكن من متغيرات Render باسم TELEGRAM_BOT_TOKEN
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

if TOKEN is None:
    raise Exception("❌ لم يتم العثور على TELEGRAM_BOT_TOKEN في متغيرات البيئة")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# الصفحة الرئيسية (يفحصها Render للتأكد أن السيرفر شغال)
@app.route('/')
def index():
    return "البوت يعمل على Render ✅"

# أمر /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "مرحباً! البوت شغال الآن 🚀")

# تشغيل البرنامج
if __name__ == '__main__':
    # 1. تشغيل Flask في خلفية منفصلة (لأن Render يحتاجها)
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)

    threading.Thread(target=run_flask, daemon=True).start()
    print(f"✅ Flask يعمل على المنفذ: {os.environ.get('PORT', 10000)}")

    # 2. إزالة أي Webhook عالق (لمنع خطأ 409)
    try:
        bot.remove_webhook()
        print("✅ تم إزالة أي Webhook عالق")
    except Exception as e:
        print(f"⚠️ تنبيه أثناء إزالة الـ Webhook: {e}")

    # 3. تشغيل البوت بطريقة Polling مع إعادة محاولة تلقائية عند أي خطأ
    print("⏳ بدء تشغيل البوت (Polling)...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"❌ حدث خطأ في البوت: {e}")
            print("🔄 إعادة المحاولة بعد 5 ثوانٍ...")
            time.sleep(5)