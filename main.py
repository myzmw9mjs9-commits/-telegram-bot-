import os
import time
import threading
import telebot
from flask import Flask

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if TOKEN is None:
    raise Exception("❌ TELEGRAM_BOT_TOKEN غير موجود")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/')
def index():
    return "البوت يعمل ✅"

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "مرحباً! البوت شغال الآن 🚀")

# ---- أضف هذا القسم الجديد ----
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if message.text == "المحفظة":
        bot.reply_to(message, "💰 محفظتك: 1000$ (رصيد تجريبي)")
    elif message.text == "التحليل والتوقع":
        bot.reply_to(message, "📊 التوقع: السعر سيصعد 2% خلال ساعة")
    elif message.text == "تنفيذ صفقة محاكاة":
        bot.reply_to(message, "✅ تم تنفيذ صفقة شراء وهمية")
    else:
        bot.reply_to(message, f"أرسلت: {message.text}\nاستخدم الأزرار المتاحة")
# ---------------------------------

if __name__ == '__main__':
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)

    threading.Thread(target=run_flask, daemon=True).start()
    print(f"✅ Flask يعمل على المنفذ {os.environ.get('PORT', 10000)}")

    try:
        bot.remove_webhook()
        print("✅ تم إزالة الـ Webhook")
    except Exception as e:
        print(f"⚠️ تنبيه: {e}")

    print("⏳ بدء تشغيل البوت...")
    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            print(f"❌ خطأ: {e}")
            time.sleep(5)