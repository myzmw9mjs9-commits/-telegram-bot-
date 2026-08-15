import os
import logging
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot import types

# ============================================================
# إعداد السجلات
# ============================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================================
# التوكن المباشر المضمون
# ============================================================
TOKEN = "8811018278:AAF36qLjzSNDz8qxcrk8SPkKerzycIpipv4"

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# ============================================================
# خادم ويب صغير لـ Render
# ============================================================
app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "Trading bot is running smoothly!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host="0.0.0.0", port=port)

# ============================================================
# بيانات المحفظة
# ============================================================
portfolio = {
    "usd": 1000.0,
    "btc": 0.0
}

# ============================================================
# جلب بيانات Binance
# ============================================================
def get_btc_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        res = requests.get(url, timeout=10).json()
        return float(res["price"])
    except Exception as e:
        logger.error(f"Error getting price: {e}")
        return None

# ============================================================
# معالجة أوامر التليجرام
# ============================================================
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

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text.strip()
    price = get_btc_price()

    if text == "📊 التحليل والتوقع":
        if price:
            msg = (
                f"🪙 *BTC / USDT*\n\n"
                f"💵 *السعر الحالي:* `{price:.2f} $` \n"
                f"📊 *المؤشر العام:* صعود خفيف / محايد\n"
                f"🤖 *التوصية:* انتظار فرصة اختراق المقاومة"
            )
        else:
            msg = "❌ تعذر جلب السعر من Binance حالياً."
        bot.reply_to(message, msg)

    elif text == "💰 المحفظة":
        total = portfolio["usd"] + (portfolio["btc"] * (price if price else 0))
        msg = (
            f"💵 *رصيد الدولار:* `{portfolio['usd']:.2f} $` \n"
            f"🪙 *رصيد البيتكوين:* `{portfolio['btc']:.6f} BTC` \n"
            f"💎 *إجمالي المحفظة:* `{total:.2f} $`"
        )
        bot.reply_to(message, msg)

    elif text == "🚀 تنفيذ صفقة محاكاة":
        if price:
            msg = f"🚀 تم تحليل السوق عند `{price:.2f} $`\n💡 النظام يوصي بعدم فتح صفقة جديدة الآن حفاظاً على رأس المال."
        else:
            msg = "❌ تعذر الاتصال ببيانات السوق."
        bot.reply_to(message, msg)

# ============================================================
# بدء التشغيل
# ============================================================
if __name__ == "__main__":
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

    logger.info("Starting TeleBot...")
    bot.infinity_polling(skip_pending=True)

