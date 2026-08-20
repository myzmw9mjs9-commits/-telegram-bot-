import telebot
from telebot import types
import requests

TOKEN = "8811018278:AAHox1l1Xaq5weFW5ScT53lFuvtJeJ_lrR8"
bot = telebot.TeleBot(TOKEN)

user_wallet = {}
open_trades = {}  # لمتابعة الصفقات المفتوحة

# دالة جلب السعر الحي للبيتكوين من Binance
def get_live_btc_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        response = requests.get(url).json()
        return float(response['price'])
    except:
        return 65000.0

def get_wallet(user_id):
    if user_id not in user_wallet:
        user_wallet[user_id] = {'usdt': 1000.0, 'btc': 0.0}
    return user_wallet[user_id]

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🚀 شراء (سعر حي)"),
        types.KeyboardButton("🎯 بيع وجني الأرباح"),
        types.KeyboardButton("💰 المحفظة"),
        types.KeyboardButton("📊 السعر الحالي")
    )
    bot.send_message(message.chat.id, "أهلاً بك! تم ربط البوت بأسعار Binance الحية:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🚀 شراء (سعر حي)")
def buy_trade(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    current_price = get_live_btc_price()
    amount = 100.0

    if w['usdt'] >= amount:
        btc_bought = amount / current_price
        w['usdt'] -= amount
        w['btc'] += btc_bought
        open_trades[uid] = current_price # حفظ سعر الدخول

        msg = (
            f"🚀 **تم فتح صفقة شراء بالسعر الحي!**\n\n"
            f"🪙 **الزوج:** BTC/USDT\n"
            f"📈 **سعر الدخول المباشر:** ${current_price:,.2f}\n"
            f"⚡ **الكمية:** {btc_bought:.6f} BTC\n"
            f"💰 **المتبقي:** ${w['usdt']:.2f}"
        )
    else:
        msg = "❌ **الرصيد غير كافي!**"

    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎯 بيع وجني الأرباح")
def sell_trade(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    
    if w['btc'] > 0:
        current_price = get_live_btc_price()
        entry_price = open_trades.get(uid, current_price)
        
        usdt_returned = w['btc'] * current_price
        profit = usdt_returned - (w['btc'] * entry_price)
        
        w['usdt'] += usdt_returned
        w['btc'] = 0.0
        
        status_icon = "🟢" if profit >= 0 else "🔴"
        
        msg = (
            f"✅ **تم إغلاق الصفقة بالسعر الحي!**\n\n"
            f"💵 **سعر البيع الحالي:** ${current_price:,.2f}\n"
            f"📉 **سعر الدخول:** ${entry_price:,.2f}\n"
            f"{status_icon} **الربح/الخسارة:** ${profit:+.2f}\n"
            f"💰 **رصيد المحفظة:** ${w['usdt']:.2f}"
        )
    else:
        msg = "❌ **لا توجد صفقات مفتوحة حالياً!**"

    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 السعر الحالي")
def live_price(message):
    price = get_live_btc_price()
    bot.send_message(message.chat.id, f"📊 **سعر BTC/USDT الحقيقي الآن:**\n\n💵 **${price:,.2f}**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💰 المحفظة")
def wallet(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    price = get_live_btc_price()
    total = w['usdt'] + (w['btc'] * price)
    msg = (
        f"💰 **المحفظة (تقييم حي)**\n\n"
        f"💵 **الدولار:** ${w['usdt']:.2f}\n"
        f"🪙 **البيتكوين:** {w['btc']:.6f} BTC\n"
        f"💎 **الإجمالي بالسعر الحالي:** ${total:.2f}"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    bot.infinity_polling(skip_pending=True)
