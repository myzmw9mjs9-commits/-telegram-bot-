import telebot
from telebot import types
import requests
import threading
import time

TOKEN = "8811018278:AAHox1l1Xaq5weFW5ScT53lFuvtJeJ_lrR8"
bot = telebot.TeleBot(TOKEN)

# بيانات المحفظة والصفقات
user_wallet = {}
open_trades = {}
auto_trading_users = set()  # قائمة المستخدمين المفعلين للتداول الآلي

def get_live_btc_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        response = requests.get(url, timeout=5).json()
        return float(response['price'])
    except:
        return 65000.0

def get_wallet(user_id):
    if user_id not in user_wallet:
        user_wallet[user_id] = {'usdt': 1000.0, 'btc': 0.0}
    return user_wallet[user_id]

# دالة الفحص الآلي المستمر في الخلفية
def auto_market_scanner():
    prev_price = get_live_btc_price()
    
    while True:
        try:
            time.sleep(10) # فحص كل 10 ثوانٍ
            current_price = get_live_btc_price()
            
            # حساب نسبة التغير السريعة
            price_change = ((current_price - prev_price) / prev_price) * 100
            
            # شرط الدخول التلقائي: إذا رصد صعود سريع بأكثر من 0.05%
            if price_change >= 0.05:
                for uid in list(auto_trading_users):
                    w = get_wallet(uid)
                    amount = 100.0
                    
                    # الدخول تلقائياً إذا لم تكن هناك صفقة مفتوحة والرصيد كافي
                    if uid not in open_trades and w['usdt'] >= amount:
                        btc_bought = amount / current_price
                        w['usdt'] -= amount
                        w['btc'] += btc_bought
                        open_trades[uid] = current_price
                        
                        msg = (
                            f"🤖 **إشعار دخول تلقائي!**\n\n"
                            f"📈 **السبب:** رصد مؤشر صعود مفاجئ بنسبة (+{price_change:.2f}%)\n"
                            f"🪙 **الزوج:** BTC/USDT\n"
                            f"💵 **سعر الشراء:** ${current_price:,.2f}\n"
                            f"⚡ **الكمية:** {btc_bought:.6f} BTC\n"
                            f"💰 **المتبقي في المحفظة:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")
            
            prev_price = current_price
        except Exception as e:
            print(f"Error in scanner: {e}")

# تشغيل الفحص الآلي في خيط مستقل (Thread)
threading.Thread(target=auto_market_scanner, daemon=True).start()

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🤖 تفعيل التداول الآلي"),
        types.KeyboardButton("🛑 إيقاف التداول الآلي"),
        types.KeyboardButton("🎯 بيع وجني الأرباح"),
        types.KeyboardButton("💰 المحفظة")
    )
    bot.send_message(message.chat.id, "أهلاً بك! تم إضافة نظام الرصد والدخول الآلي عند الصعود:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def enable_auto(message):
    uid = message.from_user.id
    auto_trading_users.add(uid)
    bot.send_message(message.chat.id, "✅ **تم تفعيل الرصد الآلي!**\nسيقوم البوت الآن بفحص السوق والدخول تلقائياً فور رصد أي إشارة صعود.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🛑 إيقاف التداول الآلي")
def disable_auto(message):
    uid = message.from_user.id
    auto_trading_users.discard(uid)
    bot.send_message(message.chat.id, "🛑 **تم إيقاف الرصد الآلي.**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎯 بيع وجني الأرباح")
def sell_trade(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    
    if uid in open_trades and w['btc'] > 0:
        current_price = get_live_btc_price()
        entry_price = open_trades.pop(uid)
        
        usdt_returned = w['btc'] * current_price
        profit = usdt_returned - 100.0
        
        w['usdt'] += usdt_returned
        w['btc'] = 0.0
        
        icon = "🟢" if profit >= 0 else "🔴"
        msg = (
            f"✅ **تم إغلاق الصفقة بنجاح!**\n\n"
            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
            f"📉 **سعر الدخول:** ${entry_price:,.2f}\n"
            f"{icon} **الربح/الخسارة:** ${profit:+.2f}\n"
            f"💰 **رصيد المحفظة الجديد:** ${w['usdt']:.2f}"
        )
    else:
        msg = "❌ **لا توجد صفقات مفتوحة حالياً!**"

    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💰 المحفظة")
def wallet(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    price = get_live_btc_price()
    total = w['usdt'] + (w['btc'] * price)
    
    status = "مفعل 🟢" if uid in auto_trading_users else "معطل 🔴"
    
    msg = (
        f"💰 **المحفظة**\n\n"
        f"💵 **الدولار:** ${w['usdt']:.2f}\n"
        f"🪙 **البيتكوين:** {w['btc']:.6f} BTC\n"
        f"💎 **الإجمالي الحي:** ${total:.2f}\n\n"
        f"🤖 **حالة الرصد الآلي:** {status}"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    bot.infinity_polling(skip_pending=True)
