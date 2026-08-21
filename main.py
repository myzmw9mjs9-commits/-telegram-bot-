import telebot
from telebot import types
import requests
import threading
import time
import sqlite3

TOKEN = "8811018278:AAHox1l1Xaq5weFW5ScT53lFuvtJeJ_lrR8"
bot = telebot.TeleBot(TOKEN)

# العملة المستهدفة: Solana (أسهل وأوضح في الربح)
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
    if not row:
        cursor.execute("INSERT INTO wallets VALUES (?, ?, ?)", (user_id, 1000.0, 0.0))
        conn.commit()
        usdt, coin = 1000.0, 0.0
    else:
        usdt, coin = row[0], row[1]
    conn.close()
    return {'usdt': usdt, 'coin': coin}

def update_wallet(user_id, usdt, coin):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE wallets SET usdt=?, coin=? WHERE user_id=?", (usdt, coin, user_id))
    conn.commit()
    conn.close()

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

def get_trade(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT entry_price, coin_bought, tp, sl FROM trades WHERE user_id=?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {'entry_price': row[0], 'coin_bought': row[1], 'tp': row[2], 'sl': row[3]}
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

def get_live_price():
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={SYMBOL}"
        res = requests.get(url, timeout=5).json()
        return float(res['price'])
    except:
        return 140.0

# جلب مؤشر RSI سريع وبسيط
def get_rsi():
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval=15m&limit=20"
        res = requests.get(url, timeout=5).json()
        closes = [float(k[4]) for k in res]
        gains, losses = [], []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            gains.append(change if change >= 0 else 0)
            losses.append(abs(change) if change < 0 else 0)
        avg_gain = sum(gains[-14:]) / 14
        avg_loss = sum(losses[-14:]) / 14
        if avg_loss == 0:
            return 100.0
        return 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))
    except:
        return 50.0

# حلقة الفحص السهل (استراتيجية الارتداد المضمون)
def auto_market_scanner():
    while True:
        try:
            time.sleep(10)
            current_price = get_live_price()
            rsi = get_rsi()
            auto_users = get_all_auto_users()

            for uid in auto_users:
                w = get_wallet(uid)
                trade = get_trade(uid)
                amount = 50.0  # تداول بمبلغ بسيط وسهل

                # الشراء عند القاع (عندما يكون RSI أقل من 35 أي السعر رخيص جداً ومستعد للارتداد)
                if not trade and w['usdt'] >= amount:
                    if rsi <= 38:
                        coin_bought = (amount * 0.999) / current_price
                        w['usdt'] -= amount
                        w['btc'] = coin_bought  # التخزين في خانة العملة
                        update_wallet(uid, w['usdt'], w['btc'])

                        target_tp = current_price * 1.015  # هدف ربح +1.5% سهولة تحقيقه عالية
                        stop_sl = current_price * 0.985   # وقف خسارة -1.5%

                        save_trade(uid, current_price, coin_bought, target_tp, stop_sl)

                        msg = (
                            f"🚀 **صفقة سهلة على عملة Solana (SOL)!**\n\n"
                            f"📉 **السبب:** وصول السعر لقاع ممتاز (RSI: {rsi:.1f})\n"
                            f"💵 **سعر الشراء:** ${current_price:,.2f}\n"
                            f"🎯 **هدف الربح (+1.5%):** ${target_tp:,.2f}\n"
                            f"🛡️ **وقف الخسارة:** ${stop_sl:,.2f}\n"
                            f"💰 **المتبقي بالمحفظة:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")

                # التخارج عند الربح
                elif trade:
                    if current_price >= trade['tp']:
                        usdt_returned = (trade['coin_bought'] * current_price) * 0.999
                        profit = usdt_returned - 50.0

                        w['usdt'] += usdt_returned
                        w['btc'] = 0.0
                        update_wallet(uid, w['usdt'], w['btc'])
                        delete_trade(uid)

                        msg = (
                            f"🟢 **تم تحقيق هدف الربح بسهولة!**\n\n"
                            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
                            f"📈 **الربح الصافي:** +${profit:.2f}\n"
                            f"💰 **رصيد المحفظة الحالي:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")

                    elif current_price <= trade['sl']:
                        usdt_returned = (trade['coin_bought'] * current_price) * 0.999
                        loss = usdt_returned - 50.0

                        w['usdt'] += usdt_returned
                        w['btc'] = 0.0
                        update_wallet(uid, w['usdt'], w['btc'])
                        delete_trade(uid)

                        msg = (
                            f"🔴 **تم الخروج بوقف الخسارة لحماية الحساب.**\n\n"
                            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
                            f"📉 **الخسارة:** ${loss:.2f}\n"
                            f"💰 **رصيد المحفظة الحالي:** ${w['usdt']:.2f}"
                        )
                        bot.send_message(uid, msg, parse_mode="Markdown")

        except Exception as e:
            print(f"Error: {e}")

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
    bot.send_message(message.chat.id, "أهلاً بك! تم تفعيل بوت التداول المباشر السهل على عملة Solana (SOL):", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def enable_auto(message):
    set_auto_status(message.from_user.id, True)
    bot.send_message(message.chat.id, "✅ **تم تفعيل استراتيجية الشراء من القاع على SOL!**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🛑 إيقاف التداول الآلي")
def disable_auto(message):
    set_auto_status(message.from_user.id, False)
    bot.send_message(message.chat.id, "🛑 **تم إيقاف التداول الآلي.**", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎯 بيع يدوي إضطراري")
def sell_trade(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    trade = get_trade(uid)

    if trade and w['btc'] > 0:
        current_price = get_live_price()
        usdt_returned = (w['btc'] * current_price) * 0.999
        profit = usdt_returned - 50.0

        w['usdt'] += usdt_returned
        w['btc'] = 0.0
        update_wallet(uid, w['usdt'], w['btc'])
        delete_trade(uid)

        icon = "🟢" if profit >= 0 else "🔴"
        msg = (
            f"⚡ **تم البيع اليدوي!**\n\n"
            f"💵 **سعر البيع:** ${current_price:,.2f}\n"
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
    trade = get_trade(uid)
    price = get_live_price()
    total = w['usdt'] + (w['btc'] * price)

    status = "مفعل 🟢" if is_auto_enabled(uid) else "معطل 🔴"
    trade_info = "لا يوجد صفقة قائمة"
    if trade:
        trade_info = f"صفقة SOL بسعر ${trade['entry_price']:,.2f}\n🎯 الهدف: ${trade['tp']:,.2f}\n🛡️ الوقف: ${trade['sl']:,.2f}"

    msg = (
        f"💰 **المحفظة**\n\n"
        f"💵 **الدولار:** ${w['usdt']:.2f}\n"
        f"🪙 **عملة SOL:** {w['btc']:.4f}\n"
        f"💎 **الإجمالي الحي:** ${total:.2f}\n\n"
        f"🤖 **حالة التداول الآلي:** {status}\n"
        f"📊 **حالة الصفقة:**\n{trade_info}"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass
    bot.infinity_polling(skip_pending=True)
