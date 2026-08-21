import telebot
from telebot import types
import requests
import threading
import time
import sqlite3

TOKEN = "8811018278:AAHox1l1Xaq5weFW5ScT53lFuvtJeJ_lrR8"
bot = telebot.TeleBot(TOKEN)

SYMBOL = "SOLUSDT"

def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS wallets (user_id INTEGER PRIMARY KEY, usdt REAL, coin REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS trades (user_id INTEGER PRIMARY KEY, entry_price REAL, coin_bought REAL, tp REAL, sl REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS auto_users (user_id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

init_db()

def get_wallet(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT usdt, coin FROM wallets WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return {'usdt': row[0], 'coin': row[1]} if row else {'usdt': 1000.0, 'coin': 0.0}

def update_wallet(user_id, usdt, coin):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO wallets VALUES (?, ?, ?)", (user_id, usdt, coin))
    conn.commit()
    conn.close()

def get_trade(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT entry_price, coin_bought, tp, sl FROM trades WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return {'entry_price': row[0], 'coin_bought': row[1], 'tp': row[2], 'sl': row[3]} if row else None

def save_trade(user_id, entry_price, coin_bought, tp, sl):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("REPLACE INTO trades VALUES (?, ?, ?, ?, ?)", (user_id, entry_price, coin_bought, tp, sl))
    conn.commit()
    conn.close()

def delete_trade(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def get_all_auto_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM auto_users")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

# --- محرك التحليل الشامل والمؤشرات المتقدمة ---
def analyze_market():
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval=5m&limit=50"
        res = requests.get(url, timeout=5).json()
        
        closes = [float(k[4]) for k in res]
        volumes = [float(k[5]) for k in res]
        current_price = closes[-1]

        # 1. حساب RSI
        gains, losses = [], []
        for i in range(1, len(closes)):
            chg = closes[i] - closes[i-1]
            gains.append(chg if chg >= 0 else 0)
            losses.append(abs(chg) if chg < 0 else 0)
        avg_g = sum(gains[-14:]) / 14
        avg_l = sum(losses[-14:]) / 14
        rsi = 100.0 if avg_l == 0 else 100.0 - (100.0 / (1.0 + (avg_g / avg_l)))

        # 2. حساب المتوسطات الاتجاهية (EMA Short & Long)
        ema_short = sum(closes[-9:]) / 9
        ema_long = sum(closes[-21:]) / 21

        # 3. حساب حدود بولينجر (Bollinger Bands)
        sma20 = sum(closes[-20:]) / 20
        variance = sum([((x - sma20) ** 2) for x in closes[-20:]]) / 20
        std_dev = variance ** 0.5
        lower_band = sma20 - (std_dev * 2)

        # 4. حساب حجم السيولة (Volume Filter)
        avg_volume = sum(volumes[-10:]) / 10
        current_volume = volumes[-1]

        # --- نظام تقييم نقاط القوة (Scoring) ---
        score = 0
        details = []

        if rsi <= 42:
            score += 1
            details.append("RSI في منطقة قاع")
        if current_price >= ema_short and ema_short > ema_long:
            score += 1
            details.append("الاتجاه العام صاعد (EMA Cross)")
        if current_price <= lower_band * 1.005:
            score += 1
            details.append("السعر قريب من الحد السفلي لبولينجر")
        if current_volume > avg_volume * 1.2:
            score += 1
            details.append("سيولة تداول عالية (Volume Surge)")

        return {
            'price': current_price,
            'score': score,
            'rsi': rsi,
            'details': details
        }
    except Exception as e:
        return None

# --- حلقة الفحص واتخاذ القرار ---
def auto_scanner():
    while True:
        try:
            time.sleep(7)
            analysis = analyze_market()
            if not analysis:
                continue

            price = analysis['price']
            score = analysis['score']
            auto_users = get_all_auto_users()

            for uid in auto_users:
                w = get_wallet(uid)
                trade = get_trade(uid)
                amount = 50.0

                # دخول الصفقة فقط إذا كانت نقاط القوة 3 أو أكثر من 4
                if not trade and w['usdt'] >= amount:
                    if score >= 3:
                        coin_bought = (amount * 0.999) / price
                        w['usdt'] -= amount
                        w['coin'] += coin_bought
                        update_wallet(uid, w['usdt'], w['coin'])

                        tp = price * 1.012  # هدف +1.2%
                        sl = price * 0.991  # وقف خسارة -0.9%
                        save_trade(uid, price, coin_bought, tp, sl)

                        reasons = "\n• ".join(analysis['details'])
                        msg = (
                            f"🧠 **دخول صفقة بناءً على تحليل شامل!**\n\n"
                            f"🪙 **العملة:** {SYMBOL}\n"
                            f"💵 **سعر الشراء:** ${price:,.2f}\n"
                            f"📊 **معدل قوة الإشارة:** {score}/4\n\n"
                            f"🔍 **الأسباب المؤكدة:**\n• {reasons}\n\n"
                            f"🎯 **الهدف:** ${tp:,.2f}\n"
                            f"🛡️ **الوقف:** ${sl:,.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")

                # الخروج
                elif trade:
                    if price >= trade['tp']:
                        usdt_ret = (trade['coin_bought'] * price) * 0.999
                        profit = usdt_ret - 50.0
                        w['usdt'] += usdt_ret
                        w['coin'] = 0.0
                        update_wallet(uid, w['usdt'], w['coin'])
                        delete_trade(uid)
                        bot.send_message(uid, f"🟢 **تم جني الأرباح بناءً على التحليل!**\nالربح: +${profit:.2f}")

                    elif price <= trade['sl']:
                        usdt_ret = (trade['coin_bought'] * price) * 0.999
                        loss = usdt_ret - 50.0
                        w['usdt'] += usdt_ret
                        w['coin'] = 0.0
                        update_wallet(uid, w['usdt'], w['coin'])
                        delete_trade(uid)
                        bot.send_message(uid, f"🔴 **تم تفعيل الوقف.**\nالخسارة: ${loss:.2f}")

        except Exception as e:
            print(f"Error: {e}")

threading.Thread(target=auto_scanner, daemon=True).start()

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("🤖 تفعيل التداول الآلي", "🛑 إيقاف التداول الآلي", "💰 المحفظة")
    bot.send_message(message.chat.id, "أهلاً بك! تم تفعيل نظام التحليل الشامل القائم على تقييم المؤشرات المجمعة.", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def enable_auto(message):
    conn = sqlite3.connect("bot_database.db")
    conn.cursor().execute("REPLACE INTO auto_users VALUES (?)", (message.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "✅ **تم تفعيل النظام الواعي بالتحليل المجمع.**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🛑 إيقاف التداول الآلي")
def disable_auto(message):
    conn = sqlite3.connect("bot_database.db")
    conn.cursor().execute("DELETE FROM auto_users WHERE user_id=?", (message.from_user.id,))
    conn.commit()
    conn.close()
    bot.send_message(message.chat.id, "🛑 **تم الإيقاف.**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💰 المحفظة")
def wallet(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    bot.send_message(message.chat.id, f"💰 **رصيدك:** ${w['usdt']:.2f} USDT")

if __name__ == '__main__':
    bot.infinity_polling(skip_pending=True)
