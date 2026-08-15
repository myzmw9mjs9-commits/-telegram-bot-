import os
import time
import threading
import telebot
from flask import Flask

# الاسم الآن مطابق تماماً لما هو موجود في Render
TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

if TOKEN is None:
    raise Exception("❌ لم يتم العثور على TELEGRAM_BOT_TOKEN في متغيرات البيئة")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/')
def index():
    return "البوت يعمل على Render ✅"

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "مرحباً! البوت شغال الآن 🚀")

if __name__ == '__main__':
    # تشغيل Flask في خلفية منفصلة
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)

    threading.Thread(target=run_flask, daemon=True).start()
    print(f"✅ Flask يعمل على المنفذ: {os.environ.get('PORT', 10000)}")

    # إزالة أي Webhook عالق لتجنب خطأ 409
    try:
        bot.remove_webhook()
        print("✅ تم إزالة أي Webhook عالق")
    except Exception as e:
        print(f"⚠️ تنبيه: {e}")

    # تشغيل Polling مع إعادة محاولة تلقائية عند أي خطأ
    print("⏳ بدء تشغيل البوت (Polling)...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"❌ حدث خطأ: {e}")
            print("🔄 إعادة المحاولة بعد 5 ثوانٍ...")
            time.sleep(5)