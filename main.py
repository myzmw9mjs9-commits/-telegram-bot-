import telebot
from telebot import types
import requests
import threading
import time
import sqlite3

TOKEN = "8811018278:AAHox1l1Xaq5weFW5ScT53lFuvtJeJ_lrR8"
bot = telebot.TeleBot(TOKEN)

# --- 1. إعداد قاعدة البيانات SQLite ---
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
            sl REAL,
            trailing_step INTEGER DEFAULT 0
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

# --- 2. إدارة قواعد البيانات والمحفظة ---
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

def save_trade(user_id, entry_price, btc_bought, tp, sl, trailing_step=0):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO trades VALUES (?, ?, ?, ?, ?, ?)", (user_id, entry_price, btc_bought, tp, sl, trailing_step))
    conn.commit()
    conn.close()

def update_trade_sl(user_id, new_sl, new_step):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE trades SET sl=?, trailing_step=? WHERE user_id=?", (new_sl, new_step, user_id))
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
    cursor.execute("SELECT entry_price, btc_bought, tp, sl, trailing_step FROM trades WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'entry_price': row[0], 'btc_bought': row[1], 'tp': row[2], 'sl': row[3], 'trailing_step': row[4]}
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

# --- 3. حساب المؤشرات الفنية (RSI, EMA, MACD) ---
def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(abs(diff) if diff < 0 else 0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def calculate_ema(closes, period):
    if len(closes) < period:
        return closes[-1]
    multiplier = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_macd(closes):
    if len(closes) < 26:
        return 0, 0
    ema12 = calculate_ema(closes, 12)
    ema26 = calculate_ema(closes, 26)
    macd_line = ema12 - ema26
    # حساب تقريبي لخط الإشارة
    signal_line = macd_line * 0.8  
    return macd_line, signal_line

# --- 4. التحليل الشامل والكامل لجميع المؤشرات والاستراتيجيات ---
def analyze_all_strategies():
    try:
        url = "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=15m&limit=60"
        res = requests.get(url, timeout=5).json()
        
        opens = [float(k[1]) for k in res]
        highs = [float(k[2]) for k in res]
        lows = [float(k[3]) for k in res]
        closes = [float(k[4]) for k in res]
        current_price = closes[-1]

        # 1. المؤشرات الفنية (RSI, EMA, MACD)
        rsi = calculate_rsi(closes)
        ema20 = calculate_ema(closes, 20)
        ema50 = calculate_ema(closes, 50)
        macd, macd_signal = calculate_macd(closes)

        # شرط الشراء بالمؤشرات الكلاسيكية: RSI متدني + الاتجاه صاعد (EMA20 > EMA50) + MACD إيجابي
        indicator_signal = (rsi <= 40) and (ema20 >= ema50) and (macd > macd_signal)

        # 2. استراتيجية MSS + FVG
        previous_high = max(highs[-12:-2])
        has_mss = current_price > previous_high
        has_fvg = lows[-1] > highs[-3]
        mss_fvg_signal = has_mss and has_fvg

        # 3. استراتيجية Order Block (OB)
        is_explosion = (closes[-2] - opens[-2]) / opens[-2] > 0.012
        is_prev_red = closes[-3] < opens[-3]
        ob_signal = is_explosion and is_prev_red
        ob_bottom = lows[-3]

        # تحديد أي استراتيجية أعطت الإشارة
        if indicator_signal:
            return True, "المؤشرات الفنية (RSI + EMA + MACD)", current_price, current_price * 0.992
        elif mss_fvg_signal:
            return True, "اختراق الهيكل والفجوة (MSS + FVG)", current_price, current_price * 0.990
        elif ob_signal:
            sl_p = ob_bottom if ob_bottom > 0 else current_price * 0.991
            return True, "مناطق الطلب (Order Block)", current_price, sl_p

        return False, None, current_price, 0.0
    except Exception as e:
        return False, None, 0.0, 0.0

def get_live_btc_price():
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        res = requests.get(url, timeout=5).json()
        return float(res['price'])
    except:
        return 65000.0

# --- 5. الماسح الآلي بالسوق الشامل لكل شيء ---
def auto_market_scanner():
    FEE = 0.001

    while True:
        try:
            time.sleep(10)
            current_price = get_live_btc_price()
            has_signal, strat_name, entry_p, stop_sl = analyze_all_strategies()
            auto_users = get_all_auto_users()

            for uid in auto_users:
                w = get_wallet(uid)
                trade = get_trade(uid)
                amount = 100.0

                # فتح صفقة عند تحقق أي شرط من المؤشرات أو الاستراتيجيات
                if not trade and w['usdt'] >= amount and has_signal:
                    usdt_after_fee = amount * (1 - FEE)
                    btc_bought = usdt_after_fee / current_price
                    
                    w['usdt'] -= amount
                    w['btc'] += btc_bought
                    update_wallet(uid, w['usdt'], w['btc'])

                    target_tp = current_price * 1.020 # هدف 2%
                    save_trade(uid, current_price, btc_bought, target_tp, stop_sl, trailing_step=0)
                    
                    msg = (
                        f"🔥 **صفقة جديدة تلقائية!**\n\n"
                        f"📊 **الاستراتيجية:** {strat_name}\n"
                        f"💵 **سعر الشراء:** ${current_price:,.2f}\n"
                        f"🎯 **الهدف (TP +2%):** ${target_tp:,.2f}\n"
                        f"🛡️ **وقف الخسارة (SL):** ${stop_sl:,.2f}\n"
                        f"💰 **المتبقي بالمحفظة:** ${w['usdt']:.2f}"
                    )
                    bot.send_message(uid, msg)

                # متابعة الصفقة + Trailing Stop
                elif trade:
                    entry = trade['entry_price']
                    step = trade['trailing_step']

                    # Trailing Stop: تأمين الأرباح
                    if current_price >= entry * 1.010 and step < 1:
                        update_trade_sl(uid, entry, 1)
                        bot.send_message(uid, f"🛡️ **Trailing Stop:** تم رفع وقف الخسارة إلى سعر الدخول (${entry:,.2f}) لتأمين الصفقة.")
                    elif current_price >= entry * 1.018 and step < 2:
                        new_sl = entry * 1.010
                        update_trade_sl(uid, new_sl, 2)
                        bot.send_message(uid, f"💰 **Trailing Stop:** تم رفع وقف الخسارة لتأمين أرباح +1.0% (${new_sl:,.2f}).")

                    # الخروج عند Target أو Stop Loss
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
                            "🟢 **تم تحقيق هدف الربح (+2%)!**\n\n"
                            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
                            f"📈 **صافي الربح:** +${profit:.2f}\n"
                            f"💰 **رصيد المحفظة:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg)

                    elif current_price <= trade['sl']:
                        gross_returned = trade['btc_bought'] * current_price
                        usdt_returned = gross_returned * (1 - FEE)
                        res_pnl = usdt_returned - 100.0

                        w['usdt'] += usdt_returned
                        w['btc'] = 0.0
                        update_wallet(uid, w['usdt'], w['btc'])
                        record_history(uid, trade['entry_price'], current_price, res_pnl)
                        delete_trade(uid)

                        icon = "🟢" if res_pnl >= 0 else "🔴"
                        msg = (
                            f"{icon} **تم الخروج من الصفقة!**\n\n"
                            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
                            f"📊 **النتيجة:** {icon} ${res_pnl:+.2f}\n"
                            f"💰 **رصيد المحفظة:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg)

        except Exception as e:
            print(f"Scanner error: {e}")

threading.Thread(target=auto_market_scanner, daemon=True).start()

# --- 6. الأوامر في تلجرام ---
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
    bot.send_message(message.chat.id, "أهلاً بك! تم تشغيل البوت الموحد بجميع الاستراتيجيات والمؤشرات (RSI + EMA + MACD + MSS + FVG + Order Block + Trailing Stop).", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def enable_auto(message):
    set_auto_status(message.from_user.id, True)
    bot.send_message(message.chat.id, "✅ **تم تفعيل التداول الآلي بكامل الاستراتيجيات والمؤشرات المدمجة!**")

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
        trade_info = f"صفقة قائمة بسعر ${trade['entry_price']:,.2f}\n🎯 الهدف: ${trade['tp']:,.2f}\n🛡️ الوقف الحالي: ${trade['sl']:,.2f}"

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
