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

# دالة الفحص الآلي المستمر وإدارة الصفقات (الشراء والبيع التلقائي)
def auto_market_scanner():
    prev_price = get_live_btc_price()
    
    while True:
        try:
            time.sleep(10) # فحص كل 10 ثوانٍ
            current_price = get_live_btc_price()
            
            # حساب نسبة التغير السريعة
            price_change = ((current_price - prev_price) / prev_price) * 100
            
            for uid in list(auto_trading_users):
                w = get_wallet(uid)
                amount = 100.0
                
                # 1. حالة الدخول الآلي (الشراء) عند رصد صعود
                if uid not in open_trades and w['usdt'] >= amount:
                    if price_change >= 0.05:
                        btc_bought = amount / current_price
                        w['usdt'] -= amount
                        w['btc'] += btc_bought
                        
                        # تحديد أهداف الربح والخسارة تلقائياً
                        target_tp = current_price * 1.01  # هدف ربح +1%
                        stop_sl = current_price * 0.995  # وقف خسارة -0.5%
                        
                        open_trades[uid] = {
                            'entry_price': current_price,
                            'btc_bought': btc_bought,
                            'tp': target_tp,
                            'sl': stop_sl
                        }
                        
                        msg = (
                            f"🤖 **صفقة شراء آلية جديدة!**\n\n"
                            f"📈 **السبب:** رصد صعود مفاجئ (+{price_change:.2f}%)\n"
                            f"🪙 **الزوج:** BTC/USDT\n"
                            f"💵 **سعر الشراء:** ${current_price:,.2f}\n"
                            f"🎯 **هدف الربح (TP):** ${target_tp:,.2f} (+1%)\n"
                            f"🛡️ **وقف الخسارة (SL):** ${stop_sl:,.2f} (-0.5%)\n"
                            f"💰 **المتبقي في المحفظة:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")

                # 2. حالة التخارج الآلي (البيع) عند تحقق هدف الربح أو وقف الخسارة
                elif uid in open_trades:
                    trade = open_trades[uid]
                    
                    # تحقق هدف الربح (Take Profit)
                    if current_price >= trade['tp']:
                        usdt_returned = trade['btc_bought'] * current_price
                        profit = usdt_returned - 100.0
                        w['usdt'] += usdt_returned
                        w['btc'] = 0.0
                        del open_trades[uid]
                        
                        msg = (
                            f"🟢 **تم جني الأرباح أوتوماتيكياً!**\n\n"
                            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
                            f"📉 **سعر الدخول:** ${trade['entry_price']:,.2f}\n"
                            f"📈 **الربح الصافي:** +${profit:.2f}\n"
                            f"💰 **رصيد المحفظة الحالي:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")

                    # تحقق وقف الخسارة (Stop Loss)
                    elif current_price <= trade['sl']:
                        usdt_returned = trade['btc_bought'] * current_price
                        loss = usdt_returned - 100.0
                        w['usdt'] += usdt_returned
                        w['btc'] = 0.0
                        del open_trades[uid]
                        
                        msg = (
                            f"🔴 **تم تفعيل وقف الخسارة تلقائياً لحماية حسابك!**\n\n"
                            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
                            f"📉 **سعر الدخول:** ${trade['entry_price']:,.2f}\n"
                            f"📉 **الخسارة:** ${loss:.2f}\n"
                            f"💰 **رصيد المحفظة الحالي:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")

            prev_price = current_price
        except Exception as e:
            print(f"Error in scanner: {e}")

# تشغيل الفحص والبيع/الشراء الآلي في الخلفية
threading.Thread(target=auto_market_scanner, daemon=True).start()

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🤖 تفعيل التداول الآلي"),
        types.KeyboardButton("🛑 إيقاف التداول الآلي"),
        types.KeyboardButton("🎯 بيع يدوي إضطراري"),
        types.KeyboardButton("💰 المحفظة")
    )
    bot.send_message(message.chat.id, "أهلاً بك! تم تفعيل نظام التداول الآلي الكامل (شراء وبيع تلقائي مع Take Profit و Stop Loss):", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def enable_auto(message):
    uid = message.from_user.id
    auto_trading_users.add(uid)
    bot.send_message(message.chat.id, "✅ **تم تفعيل الرصد والتداول الآلي!**\nالبوت يشتري ويبيع تلقائياً بحدد أرباح (+1%) ووقف خسارة (-0.5%).", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🛑 إيقاف التداول الآلي")
def disable_auto(message):
    uid = message.from_user.id
    auto_trading_users.discard(uid)
    bot.send_message(message.chat.id, "🛑 **تم إيقاف التداول الآلي.**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎯 بيع يدوي إضطراري")
def sell_trade(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    
    if uid in open_trades and w['btc'] > 0:
        current_price = get_live_btc_price()
        trade = open_trades.pop(uid)
        
        usdt_returned = w['btc'] * current_price
        profit = usdt_returned - 100.0
        
        w['usdt'] += usdt_returned
        w['btc'] = 0.0
        
        icon = "🟢" if profit >= 0 else "🔴"
        msg = (
            f"⚡ **تم البيع اليدوي الإضطراري!**\n\n"
            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
            f"📉 **سعر الدخول:** ${trade['entry_price']:,.2f}\n"
            f"{icon} **النتيجة:** ${profit:+.2f}\n"
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
    trade_info = "لا يوجد صفقة قائمة"
    if uid in open_trades:
        t = open_trades[uid]
        trade_info = f"صفقة مفتوحة بسعر ${t['entry_price']:,.2f}\n🎯 الهدف: ${t['tp']:,.2f}\n🛡️ الوقف: ${t['sl']:,.2f}"

    msg = (
        f"💰 **المحفظة**\n\n"
        f"💵 **الدولار:** ${w['usdt']:.2f}\n"
        f"🪙 **البيتكوين:** {w['btc']:.6f} BTC\n"
        f"💎 **الإجمالي الحي:** ${total:.2f}\n\n"
        f"🤖 **حالة النظام الآلي:** {status}\n"
        f"📊 **حالة الصفقة:** {trade_info}"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    bot.infinity_polling(skip_pending=True)
