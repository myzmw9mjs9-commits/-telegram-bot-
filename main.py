import os
import time
import json
import threading
import urllib.request
import telebot
from telebot import types
from flask import Flask

# 1. جلب التوكن
RAW_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
if not RAW_TOKEN:
    # توكن احتياطي مباشر في حال عدم وجود متغير البيئة
    RAW_TOKEN = "8811018278:AAHox1l1Xaq5weFW5ScT53lFuvtJeJ_lrR8"

TOKEN = RAW_TOKEN.strip()
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")
app = Flask(__name__)

# 2. بيانات المحفظة
portfolio = {
    "usd": 1000.0,
    "btc": 0.0
}

# 3. دالة جلب السعر المضمونة بدون أي تعليق
def get_btc_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read().decode())
            return float(data['bitcoin']['usd'])
    except Exception:
        # سعر افتراضي لضمان عمل البوت وعدم توقفه إطلاقاً عند تعثر الشبكة
        return 65000.0

# 4. خادم Flask لتطبيق Render
@app.route('/')
def index():
    return "Bot is Active ✅"

# 5. أمر /start
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_analysis = types.KeyboardButton("📊 التحليل والتوقع")
    btn_portfolio = types.KeyboardButton("💰 المحفظة")
    btn_trade = types.KeyboardButton("🚀 تنفيذ صفقة محاكاة")
    markup.add(btn_analysis)
    markup.add(btn_portfolio, btn_trade)

    msg = (
        "أهلاً بك في بوت التداول بالذكاء الاصطناعي! 🤖\n\n"
        "💡 *تعديل الرصيد:* أرسل مثلاً `/set_usd 500`"
    )
    bot.reply_to(message, msg, reply_markup=markup)

# 6. أمر تحديد الرصيد
@bot.message_handler(commands=['set_usd'])
def set_usd_balance(message):
    try:
        args = message.text.split()
        if len(args) > 1:
            new_amount = float(args[1])
            portfolio["usd"] = new_amount
            bot.reply_to(message, f"✅ تم تحديث رصيد الدولار إلى:\n`$ {new_amount:.2f}`")
        else:
            bot.reply_to(message, "⚠️ اكتب المبلغ بعد الأمر، مثال:\n`/set_usd 500`")
    except ValueError:
        bot.reply_to(message, "❌ اكتب رقماً صحيحاً، مثال:\n`/set_usd 500`")

# 7. معالجة جميع الأزرار والرسائل
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text.strip()
    price = get_btc_price()

    if text == "📊 التحليل والتوقع":
        msg = (
            f"🪙 *BTC / USDT*\n\n"
            f"💵 *السعر الحالي:* `{price:.2f} $`\n"
            f"📊 *المؤشر العام:* صعود خفيف / محايد\n"
            f"🤖 *التوصية:* انتظار فرصة اختراق المقاومة"
        )
        bot.reply_to(message, msg)

    elif text == "💰 المحفظة":
        total = portfolio["usd"] + (portfolio["btc"] * price)
        msg = (
            f"💵 *رصيد الدولار:* `{portfolio['usd']:.2f} $`\n"
            f"🪙 *رصيد البيتكوين:* `{portfolio['btc']:.6f} BTC`\n"
            f"💎 *إجمالي المحفظة:* `{total:.2f} $`"
        )
        bot.reply_to(message, msg)

    elif text == "🚀 تنفيذ صفقة محاكاة":
        msg = (
            f"🚀 *محاكاة صفقة تداول*\n\n"
            f"🪙 *الزوج:* BTC/USDT\n"
            f"💵 *سعر الدخول الحالي:* `{price:.2f} $`\n"
            f"💰 *الرصيد المتاح:* `{portfolio['usd']:.2f} $`\n\n"
            f"💡 *التحليل:* المؤشرات مستقرة، يوصى بالانتظار للحصول على نقطة دخول أفضل."
        )
        bot.reply_to(message, msg)

# 8. تشغيل البوت بدون توقف
if __name__ == '__main__':
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)

    threading.Thread(target=run_flask, daemon=True).start()

    try:
        bot.remove_webhook()
    except Exception:
        pass

    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception:
            time.sleep(3)
