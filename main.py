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
auto_trading_users = set()

# دالة جلب أسعار الإغلاق لحساب مؤشر RSI و EMA
def get_klines_data():
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=30"
        response = requests.get(url, timeout=5).json()
        closes = [float(k[4]) for k in response]
        return closes
    except:
        return []

# دالة حساب مؤشر RSI (Relative Strength Index)
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        if change >= 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
            
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

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

# دالة الفحص الآلي المتقدم (12 قراءة في الدقيقة + تحليل RSI و EMA)
def auto_market_scanner():
    prev_price = get_live_btc_price()
    
    while True:
        try:
            time.sleep(5)  # قراءة كل 5 ثوانٍ (12 قراءة في الدقيقة)
            current_price = get_live_btc_price()
            price_change = ((current_price - prev_price) / prev_price) * 100
            
            # جلب البيانات لحساب RSI والمتوسط
            prices = get_klines_data()
            rsi = calculate_rsi(prices) if prices else 50.0
            ema_short = sum(prices[-5:]) / 5 if len(prices) >= 5 else current_price

            for uid in list(auto_trading_users):
                w = get_wallet(uid)
                amount = 100.0
                
                # شرط دخول الصفقة الدقيق: صعود مفاجئ + RSI ممتاز (بين 35 و 65) + السعر فوق المتوسط Short EMA
                if uid not in open_trades and w['usdt'] >= amount:
                    if price_change >= 0.04 and 35 <= rsi <= 65 and current_price >= ema_short:
                        btc_bought = amount / current_price
                        w['usdt'] -= amount
                        w['btc'] += btc_bought
                        
                        target_tp = current_price * 1.01   # هدف ربح +1%
                        stop_sl = current_price * 0.995   # وقف خسارة -0.5%
                        
                        open_trades[uid] = {
                            'entry_price': current_price,
                            'btc_bought': btc_bought,
                            'tp': target_tp,
                            'sl': stop_sl
                        }
                        
                        msg = (
                            f"🤖 **صفقة شراء آلية مسبقة الفحص!**\n\n"
                            f"📈 **السبب:** رصد صعود (+{price_change:.2f}%)\n"
                            f"📊 **مؤشر RSI:** {rsi:.1f} (منطقة آمنة)\n"
                            f"🪙 **الزوج:** BTC/USDT\n"
                            f"💵 **سعر الشراء:** ${current_price:,.2f}\n"
                            f"🎯 **هدف الربح (TP):** ${target_tp:,.2f} (+1%)\n"
                            f"🛡️ **وقف الخسارة (SL):** ${stop_sl:,.2f} (-0.5%)\n"
                            f"💰 **المتبقي في المحفظة:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")

                # حالة التخارج والبيع الأوتوماتيكي
                elif uid in open_trades:
                    trade = open_trades[uid]
                    
                    # جني الأرباح
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

                    # وقف الخسارة
                    elif current_price <= trade['sl']:
                        usdt_returned = trade['btc_bought'] * current_price
                        loss = usdt_returned - 100.0
                        w['usdt'] += usdt_returned
                        w['btc'] = 0.0
                        del open_trades[uid]
                        
                        msg = (
                            f"🔴 **تم تفعيل وقف الخسارة تلقائياً!**\n\n"
                            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
                            f"📉 **سعر الدخول:** ${trade['entry_price']:,.2f}\n"
                            f"📉 **الخسارة:** ${loss:.2f}\n"
                            f"💰 **رصيد المحفظة الحالي:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")

            prev_price = current_price
        except Exception as e:
            print(f"Error in scanner: {e}")

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
    bot.send_message(message.chat.id, "أهلاً بك! تم تفعيل نظام التداول الآلي المطور بحساب مؤشر RSI و EMA:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def enable_auto(message):
    uid = message.from_user.id
    auto_trading_users.add(uid)
    bot.send_message(message.chat.id, "✅ **تم تفعيل التداول الآلي الذكي!**\nالبوت يحلل 12 مرة بالدقيقة مع دمج مؤشرات RSI و EMA.", parse_mode="Markdown")

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
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass
    bot.infinity_polling(skip_pending=True)
