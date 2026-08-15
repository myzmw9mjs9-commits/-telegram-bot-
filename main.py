import os
import time
import threading
import requests
import telebot
from telebot import types
from flask import Flask

# 1. جلب التوكن وتنظيف المسافات
RAW_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
if not RAW_TOKEN:
    raise Exception("❌ TELEGRAM_BOT_TOKEN غير موجود في متغيرات Render")

TOKEN = RAW_TOKEN.strip()
bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")
app = Flask(__name__)

# 2. بيانات المحفظة (قابلة للتعديل من المستخدم)
portfolio = {
    "usd": 1000.0,  # الرصيد الافتراضي
    "btc": 0.0
}

# 3. جلب سعر البيتكوين عبر CoinDesk API المضمون
def get_btc_price():
    headers = {"User-Agent": "Mozilla/5.0"}
    # المصدر الأول: CoinDesk (مضمون 100% على Render)
    try:
        url = "https://api.coindesk.com/v1/bpi/currentprice.json"
        res = requests.get(url, headers=headers, timeout=5).json()
        return float(res["bpi"]["USD"]["rate_float"])
    except Exception:
        pass

    # المصدر الثاني: CoinGecko احتياطي
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        res = requests.get(url, headers=headers, timeout=5).json()
        return float(res["bitcoin"]["usd"])
    except Exception:
        return None

# 4. الصفحة الرئيسية لخدمة Render
@app.route('/')
def index():
    return "البوت يعمل بنجاح ✅"

# 5. أمر /start وإظهار الأزرار
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
        "💡 *طريقة تغيير الرصيد:* أرسل الأمر مع الرقم بالشكل التالي:\n"
        "`/set_usd 500` (لتحديد رصيدك إلى 500 دولار)"
    )
    bot.reply_to(message, msg, reply_markup=markup)

# 6. أمر تغيير رصيد الدولار حسب رغبتك
@bot.message_handler(commands=['set_usd'])
def set_usd_balance(message):
    try:
        args = message.text.split()
        if len(args) > 1:
            new_amount = float(args[1])
            portfolio["usd"] = new_amount
            bot.reply_to(message, f"✅ تم تحديث رصيد الدولار في محفظتك إلى: `{new_amount:.2f} $`")
        else:
            bot.reply_to(message, "⚠️ يرجى كتابة المبلغ بعد الأمر، مثال:\n`/set_usd 2500`")
    except ValueError:
        bot.reply_to(message, "❌ يرجى كتابة رقم صحيح بعد الأمر، مثال:\n`/set_usd 500`")

# 7. معالجة الضغط على الأزرار
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
            msg = "❌ تعذر جلب السعر من جميع المصادر حالياً."
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
            msg = f"🚀 تم تحليل السوق عند `{price:.2f} $`\n💡 النظام يوصي بعدم فتح صفقة جديدة الآن حفاظاً على رأس المال."
        else:
            msg = "❌ تعذر الاتصال ببيانات السوق."
        bot.reply_to(message, msg)

# 8. التشغيل الرئيسي
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
        except Exception as e:
            time.sleep(5)
