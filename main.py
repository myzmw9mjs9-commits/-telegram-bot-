import os
import time
import threading
import telebot
from flask import Flask

# 1. التوكن من متغيرات Render
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if TOKEN is None:
    raise Exception("❌ TELEGRAM_BOT_TOKEN غير موجود في المتغيرات")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 2. الصفحة الرئيسية
@app.route('/')
def index():
    return "البوت يعمل ✅"

# 3. أمر /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "مرحباً! البوت شغال الآن 🚀")

# 4. التشغيل الرئيسي
if __name__ == '__main__':
    # تشغيل Flask في خلفية (يحتاجه Render)
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)

    threading.Thread(target=run_flask, daemon=True).start()
    print(f"✅ فلاسك (Flask) يعمل على المنفذ {os.environ.get('PORT', 10000)}")

    # إزالة أي Webhook عالق (يمنع خطأ 409)
    try:
        bot.remove_webhook()
        print("✅ تم إزالة الـ Webhook القديم")
    except Exception as e:
        print(f"⚠️ تنبيه أثناء إزالة الـ Webhook: {e}")

    # تشغيل Polling مع إعادة محاولة دائمة
    print("⏳ بدء تشغيل البوت...")
    while True:
        try:
            # interval=0 يعني استجابة فورية، timeout=20 يعطي مهلة كافية
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"❌ حدث خطأ في البوت (Polling): {e}")
            print("🔄 إعادة المحاولة بعد 5 ثوانٍ...")
            time.sleep(5)