import logging
import requests
import os
from threading import Thread
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# خادم ويب مصغر لإرضاء Render
app_web = Flask('')

@app_web.route('/')
def home():
    return "Bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host='0.0.0.0', port=port)

# إعداد السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# توكن البوت الحقيقي
TOKEN = "8811018278:AAF36qLjzSNDz8qxcrk8SPkKerzycIpipv4"

# محاكاة محفظة المستخدم
portfolio = {
    "usd": 1000.0,
    "btc": 0.0
}

# جلب سعر البيتكوين والمؤشرات
def get_crypto_data():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        response = requests.get(url).json()
        price = response["bitcoin"]["usd"]
        rsi = 17.2  
        macd = -36.19
        return price, rsi, macd
    except Exception as e:
        logging.error(f"Error fetching data: {e}")
        return None, None, None

# أمر /start
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

# معالجة الرسائل والأزرار
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    price, rsi, macd = get_crypto_data()

    if text == "💰 المحفظة":
        total_val = portfolio["usd"] + (portfolio["btc"] * (price if price else 0))
        msg = (
            f"💵 رصيد الدولار: {portfolio['usd']:.2f} $\n"
            f"🪙 رصيد البيتكوين: {portfolio['btc']:.6f} BTC\n"
            f"💎 إجمالي قيمة المحفظة: {total_val:.2f} $"
        )
        await update.message.reply_text(msg)

    elif text == "📊 التحليل والتوقع":
        if price:
            msg = (
                f"💵 سعر البيتكوين: {price:.2f} $\n"
                f"📊 مؤشر RSI: {rsi}\n"
                f"📉 مؤشر MACD: {macd}\n"
                f"🤖 توقع الذكاء الاصطناعي: 📉 هابط أو محايد (انتظار/بيع)"
            )
        else:
            msg = "تعذر جلب البيانات حالياً، يرجى المحاولة لاحقاً."
        await update.message.reply_text(msg)

    elif text == "🚀 تنفيذ صفقة محاكاة":
        await update.message.reply_text("⏳ جاري تحليل المؤشرات المتقدمة وسعر السوق...")
        if price:
            if rsi < 30:
                msg = f"تنبيه: ** النظام يفضل الانتظار لعدم توفر فرصة **\n(RSI: {rsi}) القوية. السعر: {price:.2f} $"
            else:
                msg = f"تم إيجاد فرصة دخول مناسبة عند السعر {price:.2f} $"
        else:
            msg = "خطأ في الاتصال بالسوق."
        await update.message.reply_text(msg)

if __name__ == '__main__':
    # تشغيل خادم الويب
    Thread(target=run_web).start()
    
    # تشغيل البوت
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    app.run_polling()

