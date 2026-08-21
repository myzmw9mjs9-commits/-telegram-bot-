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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            entry_price REAL,
            exit_price REAL,
            pnl REAL,
            timestamp TEXT
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

def record_history(user_id, entry_price, exit_price, pnl):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    date_str = time.strftime("%Y-%m-%d %H:%M")
    cursor.execute("INSERT INTO history (user_id, entry_price, exit_price, pnl, timestamp) VALUES (?, ?, ?, ?, ?)", 
                   (user_id, entry_price, exit_price, pnl, date_str))
    conn.commit()
    conn.close()

def get_user_history(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT entry_price, exit_price, pnl, timestamp FROM history WHERE user_id=? ORDER BY id DESC LIMIT 5", (user_id,))
    rows = cursor.fetchall()
    cursor.execute("SELECT SUM(pnl) FROM history WHERE user_id=?", (user_id,))
    total_pnl = cursor.fetchone()[0] or 0.0
    conn.close()
    return rows, total_pnl

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

# --- تحليل هيكل السوق الذكي (MSS + FVG) ---
cached_smart_reading = {'signal': False, 'entry_price': 0.0, 'prev_high': 0.0, 'last_update': 0}

def get_smart_market_reading():
    now = time.time()
    if now - cached_smart_reading['last_update'] < 15 and cached_smart_reading['entry_price'] > 0:
        return cached_smart_reading['signal'], cached_smart_reading['entry_price'], cached_smart_reading['prev_high']
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=30"
        res = requests.get(url, timeout=5).json()
        
        highs = [float(k[2]) for k in res]
        lows = [float(k[3]) for k in res]
        closes = [float(k[4]) for k in res]
        
        # 1. كشف اختراق الهيكل (MSS)
        previous_high = max(highs[-12:-2])
        current_close = closes[-1]
        has_mss = current_close > previous_high

        # 2. كشف الفجوة السعرية (FVG)
        candle1_high = highs[-3]
        candle3_low = lows[-1]
        has_fvg = candle3_low > candle1_high

        smart_signal = has_mss and has_fvg

        cached_smart_reading['signal'] = smart_signal
        cached_smart_reading['entry_price'] = current_close
        cached_smart_reading['prev_high'] = previous_high
        cached_smart_reading['last_update'] = now
        return smart_signal, current_close, previous_high
    except:
        return False, 0.0, 0.0

def get_live_btc_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        res = requests.get(url, timeout=5).json()
        return float(res['price'])
    except:
        return 65000.0

def auto_market_scanner():
    FEE = 0.001

    while True:
        try:
            time.sleep(10)
            current_price = get_live_btc_price()
            smart_signal, entry_p, prev_h = get_smart_market_reading()
            auto_users = get_all_auto_users()

            for uid in auto_users:
                w = get_wallet(uid)
                trade = get_trade(uid)
                amount = 100.0

                if not trade and w['usdt'] >= amount:
                    if smart_signal:
                        usdt_after_fee = amount * (1 - FEE)
                        btc_bought = usdt_after_fee / current_price
                        
                        w['usdt'] -= amount
                        w['btc'] += btc_bought
                        update_wallet(uid, w['usdt'], w['btc'])

                        target_tp = current_price * 1.020 # هدف 2.0%
                        stop_sl = current_price * 0.990  # وقف 1.0%
                        
                        save_trade(uid, current_price, btc_bought, target_tp, stop_sl)
                        
                        msg = (
                            "🔥 **صفقة جديدة بناءً على هيكل السوق (SMC)!**\n\n"
                            f"📈 **تم كسر الهيكل (MSS):** اخترق القمة ${prev_h:,.2f}\n"
                            "⚡ **تأكيد الفجوة (FVG):** سيولة شراء مؤسسية عالية\n"
                            f"💵 **سعر الشراء:** ${current_price:,.2f}\n"
                            f"🎯 **هدف الربح (TP +2%):** ${target_tp:,.2f}\n"
                            f"🛡️ **وقف الخسارة (SL -1%):** ${stop_sl:,.2f}\n"
                            f"💰 **المتبقي بالمحفظة:** ${w['usdt']:.2f}"
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
                        record_history(uid, trade['entry_price'], current_price, profit)
                        delete_trade(uid)

                        msg = (
                            "🟢 **تم تحقيق هدف الربح المؤسسي (+2%)!**\n\n"
                            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
                            f"📈 **صافي الربح:** +${profit:.2f}\n"
                            f"💰 **رصيد المحفظة الحالي:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg)

                    elif current_price <= trade['sl']:
                        gross_returned = trade['btc_bought'] * current_price
                        usdt_returned = gross_returned * (1 - FEE)
                        loss = usdt_returned - 100.0

                        w['usdt'] += usdt_returned
                        w['btc'] = 0.0
                        update_wallet(uid, w['usdt'], w['btc'])
                        record_history(uid, trade['entry_price'], current_price, loss)
                        delete_trade(uid)

                        msg = (
                            "🔴 **تم ضرب وقف الخسارة الاحترازي!**\n\n"
                            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
                            f"📉 **النتيجة:** ${loss:.2f}\n"
                            f"💰 **رصيد المحفظة الحالي:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg)

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
        types.KeyboardButton("📊 سجل الأرباح"),
        types.KeyboardButton("💰 المحفظة")
    )
    bot.send_message(message.chat.id, "أهلاً بك! تم تشغيل البوت بالاستراتيجية الذكية (MSS + FVG).", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def enable_auto(message):
    set_auto_status(message.from_user.id, True)
    bot.send_message(message.chat.id, "✅ **تم تفعيل التداول الذكي القائم على هيكل السوق!**")

@bot.message_handler(func=lambda m: m.text == "🛑 إيقاف التداول الآلي")
def disable_auto(message):
    set_auto_status(message.from_user.id, False)
    bot.send_message(message.chat.id, "🛑 **تم إيقاف التداول الآلي.**")

@bot.message_handler(func=lambda m: m.text == "📊 سجل الأرباح")
def history(message):
    uid = message.from_user.id
    rows, total_pnl = get_user_history(uid)
    
    if not rows:
        bot.send_message(message.chat.id, "📂 لا يوجد لديك سجل صفقات مكتملة حتى الآن.")
        return

    msg = "📊 **سجل الصفقات المكتملة:**\n\n"
    for r in rows:
        entry, exit_p, pnl, dt = r
        icon = "🟢" if pnl >= 0 else "🔴"
        msg += f"🗓️ {dt}\n💵 دخول: ${entry:,.2f} | خروج: ${exit_p:,.2f}\n{icon} النتيجة: ${pnl:+.2f}\n--------------------\n"
    
    total_icon = "🟢" if total_pnl >= 0 else "🔴"
    msg += f"\n💰 **إجمالي الأرباح/الخسائر:** {total_icon} ${total_pnl:+.2f}"
    bot.send_message(message.chat.id, msg)

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
        record_history(uid, trade['entry_price'], current_price, profit)
        delete_trade(uid)

        icon = "🟢" if profit >= 0 else "🔴"
        msg = (
            "⚡ **تم البيع اليدوي الإضطراري!**\n\n"
            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
            f"{icon} **صافي النتيجة:** ${profit:+.2f}\n"
            f"💰 **رصيد المحفظة الجديد:** ${w['usdt']:.2f}"
        )
    else:
        msg = "❌ **لا توجد صفقات مفتوحة حالياً!**"

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
        "💰 **المحفظة**\n\n"
        f"💵 **الدولار:** ${w['usdt']:.2f}\n"
        f"🪙 **البيتكوين:** {w['btc']:.6f} BTC\n"
        f"💎 **الإجمالي الحي:** ${total:.2f}\n\n"
        f"🤖 **حالة التداول الآلي:** {status}\n"
        f"📊 **حالة الصفقة:**\n{trade_info}"
    )
    bot.send_message(message.chat.id, msg)

if __name__ == '__main__':
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass
    bot.infinity_polling(skip_pending=True)
