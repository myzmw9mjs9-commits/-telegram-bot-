import telebot
from telebot import types
import requests
import threading
import time

TOKEN = "8811018278:AAHox1l1Xaq5weFW5ScT53lFuvtJeJ_lrR8"
bot = telebot.TeleBot(TOKEN)

user_wallet = {}
open_trades = {}
auto_trading_users = set()

# جلب أسعار الشموع لحساب RSI
def get_rsi():
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=15"
        res = requests.get(url, timeout=5).json()
        closes = [float(candle[4]) for candle in res]
        
        gains, losses = [], []
        for i in range(1, len(closes)):
            diff = closes[i] - closes[i-1]
            if diff >= 0:
                gains.append(diff)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(diff))
                
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        
        if avg_loss == 0: return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    except:
        return 50.0

def get_live_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        return float(requests.get(url, timeout=5).json()['price'])
    except:
        return 65000.0

def get_wallet(user_id):
    if user_id not in user_wallet:
        user_wallet[user_id] = {'usdt': 1000.0, 'btc': 0.0}
    return user_wallet[user_id]

# خوارزمية الفحص الذاتي وإدارة الصفقات
def smart_trading_engine():
    while True:
        try:
            time.sleep(5)
            price = get_live_price()
            rsi = get_rsi()
            
            for uid in list(auto_trading_users):
                w = get_wallet(uid)
                
                # 1. إستراتيجية الشراء الذكي (RSI تحت 35 = القاع)
                if uid not in open_trades and w['usdt'] >= 100.0:
                    if rsi <= 35:
                        btc_bought = 100.0 / price
                        w['usdt'] -= 100.0
                        w['btc'] += btc_bought
                        
                        open_trades[uid] = {
                            'entry': price,
                            'amount_btc': btc_bought,
                            'tp': price * 1.015, # هدف ربح +1.5%
                            'sl': price * 0.992  # وقف خسارة -0.8%
                        }
                        
                        bot.send_message(uid, f"🤖 **صفقة شراء آلية!**\n\n🪙 **السعر:** ${price:,.2f}\n📊 **مؤشر RSI:** {rsi:.1f} (تشبع بيعي)\n🎯 **هدف الربح:** ${price*1.015:,.2f}\n🛡️ **وقف الخسارة:** ${price*0.992:,.2f}", parse_mode="Markdown")

                # 2. إدارة الصفقة المفتوحة (البيع الآلي)
                elif uid in open_trades:
                    trade = open_trades[uid]
                    
                    # جني أرباح تلقائي
                    if price >= trade['tp']:
                        returned = trade['amount_btc'] * price
                        profit = returned - 100.0
                        w['usdt'] += returned
                        w['btc'] = 0.0
                        del open_trades[uid]
                        bot.send_message(uid, f"🟢 **تم جني الأرباح تلقائياً!**\n\n💵 **سعر البيع:** ${price:,.2f}\n📈 **الربح الصافي:** +${profit:.2f}", parse_mode="Markdown")
                        
                    # إيقاف خسارة تلقائي
                    elif price <= trade['sl']:
                        returned = trade['amount_btc'] * price
                        loss = returned - 100.0
                        w['usdt'] += returned
                        w['btc'] = 0.0
                        del open_trades[uid]
                        bot.send_message(uid, f"🔴 **تم تفعيل إيقاف الخسارة لحماية محفظتك!**\n\n💵 **سعر البيع:** ${price:,.2f}\n📉 **الخسارة:** ${loss:.2f}", parse_mode="Markdown")
                        
        except Exception as e:
            print(f"Error: {e}")

threading.Thread(target=smart_trading_engine, daemon=True).start()

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🤖 تشغيل النظام الذكي"),
        types.KeyboardButton("🛑 إيقاف النظام"),
        types.KeyboardButton("💰 المحفظة"),
        types.KeyboardButton("📊 حالة المؤشر")
    )
    bot.send_message(message.chat.id, "أهلاً بك! تم إطلاق محرك التداول الذكي بـ RSI و Stop-Loss:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🤖 تشغيل النظام الذكي")
def enable(m):
    auto_trading_users.add(m.from_user.id)
    bot.send_message(m.chat.id, "✅ **تم التفعيل!** البوت يراقب مؤشر RSI وسيشتري عند القاع ويبيع عند الهدف أوتوماتيكياً.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🛑 إيقاف النظام")
def disable(m):
    auto_trading_users.discard(m.from_user.id)
    bot.send_message(m.chat.id, "🛑 **تم الإيقاف.**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 حالة المؤشر")
def rsi_status(m):
    p = get_live_price()
    r = get_rsi()
    bot.send_message(m.chat.id, f"📊 **BTC/USDT**\n\n💵 **السعر:** ${p:,.2f}\n📉 **مؤشر RSI:** {r:.1f}\n\n*(الدخول الآلي يحدث عندما ينزل RSI تحت 35)*", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💰 المحفظة")
def wallet(m):
    w = get_wallet(m.from_user.id)
    p = get_live_price()
    total = w['usdt'] + (w['btc'] * p)
    bot.send_message(m.chat.id, f"💰 **المحفظة**\n\n💵 **USDT:** ${w['usdt']:.2f}\n🪙 **BTC:** {w['btc']:.6f}\n💎 **الإجمالي:** ${total:.2f}", parse_mode="Markdown")

if __name__ == '__main__':
    bot.infinity_polling(skip_pending=True)
