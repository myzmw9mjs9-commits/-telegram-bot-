import telebot
from telebot import types
import requests
import threading
import time
import sqlite3

TOKEN = "8811018278:AAHox1l1Xaq5weFW5ScT53lFuvtJeJ_lrR8"
bot = telebot.TeleBot(TOKEN)

# --- إعداد قاعدة البيانات SQLite ---
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallets (
            user_id INTEGER PRIMARY KEY,
            usdt REAL,
            btc REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            user_id INTEGER PRIMARY KEY,
            entry_price REAL,
            btc_bought REAL,
            tp REAL,
            sl REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS auto_users (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_wallet(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT usdt, btc FROM wallets WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO wallets VALUES (?, ?, ?)", (user_id, 1000.0, 0.0))
        conn.commit()
        usdt, btc = 1000.0, 0.0
    else:
        usdt, btc = row[0], row[1]
    conn.close()
    return {'usdt': usdt, 'btc': btc}

def update_wallet(user_id, usdt, btc):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE wallets SET usdt=?, btc=? WHERE user_id=?", (usdt, btc, user_id))
    conn.commit()
    conn.close()

def save_trade(user_id, entry_price, btc_bought, tp, sl):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO trades VALUES (?, ?, ?, ?, ?)", (user_id, entry_price, btc_bought, tp, sl))
    conn.commit()
    conn.close()

def delete_trade(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_trade(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT entry_price, btc_bought, tp, sl FROM trades WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'entry_price': row[0], 'btc_bought': row[1], 'tp': row[2], 'sl': row[3]}
    return None

def is_auto_enabled(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM auto_users WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def set_auto_status(user_id, enable):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    if enable:
        cursor.execute("REPLACE INTO auto_users VALUES (?)", (user_id,))
    else:
        cursor.execute("DELETE FROM auto_users WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_all_auto_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM auto_users")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

cached_indicators = {'rsi': 50.0, 'ema': 0.0, 'last_update': 0}

def get_klines_analysis():
    now = time.time()
    if now - cached_indicators['last_update'] < 15 and cached_indicators['ema'] > 0:
        return cached_indicators['rsi'], cached_indicators['ema']
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=5m&limit=30"
        res = requests.get(url, timeout=5).json()
        closes = [float(k[4]) for k in res]
        
        gains, losses = [], []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            gains.append(change if change >= 0 else 0)
            losses.append(abs(change) if change < 0 else 0)
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        rsi = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))
        ema = sum(closes[-5:]) / 5

        cached_indicators['rsi'] = rsi
        cached_indicators['ema'] = ema
        cached_indicators['last_update'] = now
        return rsi, ema
    except:
        return cached_indicators['rsi'], cached_indicators['ema']

def get_live_btc_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        res = requests.get(url, timeout=5).json()
        return float(res['price'])
    except:
        return 65000.0

def auto_market_scanner():
    prev_price = get_live_btc_price()
    FEE = 0.001

    while True:
        try:
            time.sleep(5)
            current_price = get_live_btc_price()
            price_change = ((current_price - prev_price) / prev_price) * 100
            
            rsi, ema = get_klines_analysis()
            auto_users = get_all_auto_users()

            for uid in auto_users:
                w = get_wallet(uid)
                trade = get_trade(uid)
                amount = 100.0

                if not trade and w['usdt'] >= amount:
                    if price_change >= 0.05 and 35 <= rsi <= 60 and current_price >= ema:
                        usdt_after_fee = amount * (1 - FEE)
                        btc_bought = usdt_after_fee / current_price
                        
                        w['usdt'] -= amount
                        w['btc'] += btc_bought
                        update_wallet(uid, w['usdt'], w['btc'])

                        target_tp = current_price * 1.012
                        stop_sl = current_price * 0.995
                        
                        save_trade(uid, current_price, btc_bought, target_tp, stop_sl)
                        
                        msg = (
                            "🤖 صفقة شراء جديدة!\n\n"
                            f"📈 صعود على فريم 5 دقائق: {price_change:.2f}%\n"
                            f"📊 مؤشر RSI: {rsi:.1f}\n"
                            f"💵 سعر الشراء: ${current_price:,.2f}\n"
                            "📉 العمولة: $0.10 USDT\n"
                            f"🎯 هدف الربح: ${target_tp:,.2f}\n"
                            f"🛡️ وقف الخسارة: ${stop_sl:,.2f}\n"
                            f"💰 المتبقي بالمحفظة: ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg)

                elif trade:
                    if current_price >= trade['tp']:
                        gross_returned = trade['btc_bought'] * current_price
                        usdt_returned = gross_returned * (1 - FEE)
                        profit = usdt_returned - 100.0

                        w['usdt'] += usdt_returned
                        w['btc'] = 0.0
                        update_wallet(uid, w['usdt'], w['btc'])
                        delete_trade(uid)

                        msg = (
                            "🟢 تم تحقيق هدف الربح!\n\n"
                            f"💵 سعر البيع: ${current_price:,.2f}\n"
                            f"📈 صافي الربح: +${profit:.2f}\n"
                            f"💰 رصيد المحفظة الحالي: ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg)

                    elif current_price <= trade['sl']:
                        gross_returned = trade['btc_bought'] * current_price
                        usdt_returned = gross_returned * (1 - FEE)
                        loss = usdt_returned - 100.0

                        w['usdt'] += usdt_returned
                        w['btc'] = 0.0
                        update_wallet(uid, w['usdt'], w['btc'])
                        delete_trade(uid)

                        msg = (
                            "🔴 تم تفعيل وقف الخسارة!\n\n"
                            f"💵 سعر البيع: ${current_price:,.2f}\n"
                            f"📉 النتيجة: ${loss:.2f}\n"
                            f"💰 رصيد المحفظة الحالي: ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg)

            prev_price = current_price
        except Exception as e:
            print(f"Scanner error: {e}")

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
    bot.send_message(message.chat.id, "أهلاً بك! تم تشغيل البوت بنجاح.", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def enable_auto(message):
    set_auto_status(message.from_user.id, True)
    bot.send_message(message.chat.id, "✅ تم تفعيل التداول الآلي بنجاح!")

@bot.message_handler(func=lambda m: m.text == "🛑 إيقاف التداول الآلي")
def disable_auto(message):
    set_auto_status(message.from_user.id, False)
    bot.send_message(message.chat.id, "🛑 تم إيقاف التداول الآلي.")

@bot.message_handler(func=lambda m: m.text == "🎯 بيع يدوي إضطراري")
def sell_trade(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    trade = get_trade(uid)

    if trade and w['btc'] > 0:
        current_price = get_live_btc_price()
        gross_returned = w['btc'] * current_price
        usdt_returned = gross_returned * (1 - 0.001)
        profit = usdt_returned - 100.0

        w['usdt'] += usdt_returned
        w['btc'] = 0.0
        update_wallet(uid, w['usdt'], w['btc'])
        delete_trade(uid)

        icon = "🟢" if profit >= 0 else "🔴"
        msg = (
            "⚡ تم البيع اليدوي الإضطراري!\n\n"
            f"💵 سعر البيع: ${current_price:,.2f}\n"
            f"{icon} صافي النتيجة: ${profit:+.2f}\n"
            f"💰 رصيد المحفظة الجديد: ${w['usdt']:.2f}"
        )
    else:
        msg = "❌ لا توجد صفقات مفتوحة حالياً!"

    bot.send_message(message.chat.id, msg)

@bot.message_handler(func=lambda m: m.text == "💰 المحفظة")
def wallet(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    trade = get_trade(uid)
    price = get_live_btc_price()
    total = w['usdt'] + (w['btc'] * price)

    status = "مفعل 🟢" if is_auto_enabled(uid) else "معطل 🔴"
    trade_info = "لا يوجد صفقة قائمة"
    if trade:
        trade_info = f"صفقة قائمة بسعر ${trade['entry_price']:,.2f}\n🎯 الهدف: ${trade['tp']:,.2f}\n🛡️ الوقف: ${trade['sl']:,.2f}"

    msg = (
        "💰 المحفظة\n\n"
        f"💵 الدولار: ${w['usdt']:.2f}\n"
        f"🪙 البيتكوين: {w['btc']:.6f} BTC\n"
        f"💎 الإجمالي الحي: ${total:.2f}\n\n"
        f"🤖 حالة التداول الآلي: {status}\n"
        f"📊 حالة الصفقة:\n{trade_info}"
    )
    bot.send_message(message.chat.id, msg)

if __name__ == '__main__':
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass
    bot.infinity_polling(skip_pending=True)
