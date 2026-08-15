import os
import time
import threading
import requests
import telebot
from telebot import types
from flask import Flask

# 1. جلب التوكن
RAW_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not RAW_TOKEN:
    raise Exception("❌ TELEGRAM_BOT_TOKEN غير موجود")

TOKEN = RAW_TOKEN.strip()
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")
app = Flask(__name__)

# 2. بيانات المحفظة
portfolio = {
    "usd": 1000.0,
    "btc": 0.0
}

# 3. دالة جلب السعر المضمونة
def get_btc_price():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url = "https://api.coindesk.com/v1/bpi/currentprice.json"
        res = requests.get(url, headers=headers, timeout=5).json()
        return float(res["bpi"]["USD"]["rate_float"])
    except Exception:
        pass

    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        res = requests.get(url, headers=headers, timeout=5).json()
        return float(res["bitcoin"]["usd"])
    except Exception:
        return None

# 4. خدمة Render
@app.route('/')
def index():
    return "البوت يعمل بنجاح ✅"

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
            bot.reply_to(message, f"✅ تم تحديث رصيد الدولار في محفظتك إلى:\n`$ {new_amount:.2f}`")
        else:
            bot.reply_to(message, "⚠️ اكتب المبلغ بعد الأمر، مثال:\n`/set_usd 500`")
    except ValueError:
        bot.reply_to(message, "❌ اكتب رقماً صحيحاً، مثال:\n`/set_usd 500`")

# 7. معالجة جميع الأزرار (تم إصلاح زر الصفقة هنا)
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text.strip()
    price = get_btc_price()

    if text == "📊 التحليل والتوقع":
        if price:
            msg = (
                f"🪙 *BTC / USDT*\n\n"
                f"💵 *السعر الحالي:* `{price:.2f} $`\n"
                f"📊 *المؤشر العام:* صعود خفيف / محايد\n"
                f"🤖 *التوصية:* انتظار فرصة اختراق المقاومة"
            )
        else:
            msg = "❌ تعذر جلب السعر حالياً."
        bot.reply_to(message, msg)

    elif text == "💰 المحفظة":
        total = portfolio["usd"] + (portfolio["btc"] * (price if price else 0))
        msg = (
            f"💵 *رصيد الدولار:* `{portfolio['usd']:.2f} $`\n"
            f"🪙 *رصيد البيتكوين:* `{portfolio['btc']:.6f} BTC`\n"
            f"💎 *إجمالي المحفظة:* `{total:.2f} $`"
        )
        bot.reply_to(message, msg)

    elif text == "🚀 تنفيذ صفقة محاكاة":
        if price:
            msg = (
                f"🚀 *محاكاة صفقة تداول*\n\n"
                f"🪙 *الزوج:* BTC/USDT\n"
                f"💵 *سعر الدخول الحالي:* `{price:.2f} $`\n"
                f"💰 *الرصيد المتاح:* `{portfolio['usd']:.2f} $`\n\n"
                f"💡 *التحليل:* المؤشرات مستقرة، يوصى بالانتظار للحصول على نقطة دخول أفضل."
            )
        else:
            msg = "❌ تعذر الاتصال ببيانات السوق حالياً."
        bot.reply_to(message, msg)

# 8. التشغيل
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
            time.sleep(5)
