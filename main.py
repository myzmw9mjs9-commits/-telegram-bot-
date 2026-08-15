import logging
import os
from threading import Thread
import requests
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# إعداد السجلات
# ============================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# الإعدادات (توكن آمن)
# ============================================================
# اقرأ التوكن من البيئة، وإذا لم يوجد استخدم الاحتياطي (لتشغيله محلياً)
TOKEN = os.environ.get("BOT_TOKEN", "8811018278:AAF36qLjzSNDz8qxcrk8SPkKerzycIpipv4")

# ============================================================
# خادم ويب صغير لإرضاء Render
# ============================================================
app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    # إضافة use_reloader=False و debug=False لتجنب مشاكل التشغيل
    app_web.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ============================================================
# محفظة تجريبية
# ============================================================
portfolio = {
    "usd": 1000.0,
    "btc": 0.0,
}

# ============================================================
# جلب بيانات السوق من Binance
# ============================================================
def get_btc_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        res = requests.get(url, timeout=10).json()
        return float(res["price"])
    except Exception as e:
        logger.error(f"Error fetching price: {e}")
        return None

# ============================================================
# أوامر التليجرام
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📊 التحليل والتوقع"],
        ["💰 المحفظة", "🚀 تنفيذ صفقة محاكاة"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "أهلاً بك في بوت التداول بالذكاء الاصطناعي! 🤖\nاختر خياراً من القائمة أدناه:",
        reply_markup=reply_markup
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    price = get_btc_price()

    if text == "📊 التحليل والتوقع":
        if price:
            # استخدام HTML بدلاً من Markdown
            msg = (
                f"🪙 <b>BTC/USDT</b>\n"
                f"💵 السعر الحالي: {price:.2f} $\n"
                f"📊 المؤشر العام: محايد / صعود خفيف\n"
                f"🤖 التوصية التجريبية: انتظار فرصة أفضل"
            )
            await update.message.reply_text(msg, parse_mode='HTML')
        else:
            await update.message.reply_text("❌ تعذر جلب السعر حالياً من Binance.")

    elif text == "💰 المحفظة":
        # حساب المجموع بأمان (إذا كان السعر None يعتبر 0)
        total = portfolio["usd"] + (portfolio["btc"] * (price if price else 0))
        msg = (
            f"💵 رصيد الدولار: {portfolio['usd']:.2f} $\n"
            f"🪙 رصيد البيتكوين: {portfolio['btc']:.6f} BTC\n"
            f"💎 إجمالي المحفظة: {total:.2f} $"
        )
        await update.message.reply_text(msg)

    elif text == "🚀 تنفيذ صفقة محاكاة":
        if price:
            msg = f"🚀 تم فحص السوق عند السعر {price:.2f} $\n💡 النظام ينصح بالانتظار وعدم المخاطرة الآن."
        else:
            msg = "❌ خطأ في الاتصال ببيانات السوق."
        await update.message.reply_text(msg)

# ============================================================
# التشغيل الرئيسي
# ============================================================
if __name__ == "__main__":
    # تشغيل خادم الويب
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

    # تشغيل بوت التليجرام
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Starting Telegram Bot...")
    app.run_polling()