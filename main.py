import os
import time
import threading
import telebot
from flask import Flask

# 1. جلب التوكن مع إزالة أي مسافات زائدة تلقائياً (.strip())
RAW_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not RAW_TOKEN:
    raise Exception("❌ TELEGRAM_BOT_TOKEN غير موجود في متغيرات Render")

TOKEN = RAW_TOKEN.strip()

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# 2. الصفحة الرئيسية لخدمة Render
@app.route('/')
def index():
    return "البوت يعمل بنجاح ✅"

# 3. أمر /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "مرحباً! البوت شغال الآن 🚀")

# 4. التشغيل الرئيسي
if __name__ == '__main__':
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)

    threading.Thread(target=run_flask, daemon=True).start()
    print(f"✅ Flask يعمل على المنفذ {os.environ.get('PORT', 10000)}")

    # إزالة أي Webhook قديم لتجنب تعارض 409
    try:
        bot.remove_webhook()
        print("✅ تم إزالة Webhook القديم")
    except Exception as e:
        print(f"⚠️ تنبيه أثناء مسح Webhook: {e}")

    # تشغيل Polling مع مستمع دائم
    print("⏳ بدء تشغيل البوت...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"❌ حدث خطأ: {e}، إعادة المحاولة خلال 5 ثوانٍ...")
            time.sleep(5)
