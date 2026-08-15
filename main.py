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

# 2. بيانات المحفظة الافتراضية
portfolio = {
    "usd": 1000.0,
    "btc": 0.0
}

# 3. جلب سعر البيتكوين (Binance + CoinGecko احتياطي)
def get_btc_price():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        res = requests.get(url, headers=headers, timeout=5).json()
        if "price" in res:
            return float(res["price"])
    except Exception:
        pass

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

    bot.reply_to(
        message,
        "أهلاً بك في بوت التداول بالذكاء الاصطناعي! 🤖\nاختر خياراً من القائمة أدناه:",
        reply_markup=markup
    )

# 6. معالجة الضغط على الأزرار
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

# 7. التشغيل الرئيسي
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
