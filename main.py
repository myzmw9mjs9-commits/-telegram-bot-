import sqlite3
import logging
import threading
import requests
import time
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "8811018278:AAFded7ASv7bNnB6n0X5KiJUmJFw897wddE"
bot = telebot.TeleBot(BOT_TOKEN)

db_lock = threading.Lock()
user_trading_status = {}
logging.basicConfig(level=logging.INFO)

def get_db_connection():
    conn = sqlite3.connect("bot_database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT,
                type TEXT,
                price REAL,
                amount REAL,
                pnl REAL DEFAULT 0.0,
                status TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfolio (
                user_id INTEGER PRIMARY KEY,
                usdt_balance REAL DEFAULT 1000.0,
                btc_balance REAL DEFAULT 0.0,
                last_buy_price REAL DEFAULT 0.0,
                stop_loss_price REAL DEFAULT 0.0,
                take_profit_price REAL DEFAULT 0.0
            )
        ''')
        conn.commit()
        conn.close()

init_db()

def get_user_portfolio(user_id):
    with db_lock:
        conn = get_db_connection()
        res = conn.execute("SELECT * FROM portfolio WHERE user_id = ?", (user_id,)).fetchone()
        if not res:
            conn.execute("INSERT INTO portfolio (user_id, usdt_balance, btc_balance, last_buy_price, stop_loss_price, take_profit_price) VALUES (?, 1000.0, 0.0, 0.0, 0.0, 0.0)", (user_id,))
            conn.commit()
            res = conn.execute("SELECT * FROM portfolio WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        return res

def fetch_klines_full(symbol="BTCUSDT", interval="5m", limit=300):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            highs = [float(item[2]) for item in data]
            lows = [float(item[3]) for item in data]
            closes = [float(item[4]) for item in data]
            volumes = [float(item[5]) for item in data]
            return closes, highs, lows, volumes
    except Exception as e:
        logging.error(f"Error fetching klines: {e}")
    return [], [], [], []

def calculate_ema_series(prices, period):
    if len(prices) < period:
        return []
    k = 2 / (period + 1)
    ema_list = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema_list.append((p * k) + (ema_list[-1] * (1 - k)))
    return ema_list

def calculate_rsi_standard(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(prices)):
        delta = prices[i] - prices[i-1]
        gains.append(delta if delta > 0 else 0.0)
        losses.append(abs(delta) if delta < 0 else 0.0)
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0: return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def calculate_macd_standard(prices):
    if len(prices) < 35:
        return 0.0, 0.0, 0.0
    ema12_list = calculate_ema_series(prices, 12)
    ema26_list = calculate_ema_series(prices, 26)
    diff = len(ema12_list) - len(ema26_list)
    ema12_aligned = ema12_list[diff:]
    macd_line = [e12 - e26 for e12, e26 in zip(ema12_aligned, ema26_list)]
    signal_line_list = calculate_ema_series(macd_line, 9)
    current_macd = macd_line[-1]
    current_signal = signal_line_list[-1] if signal_line_list else current_macd
    return round(current_macd, 2), round(current_signal, 2), round(current_macd - current_signal, 2)

def calculate_atr(closes, highs, lows, period=14):
    if len(closes) < period + 1:
        return closes[-1] * 0.01
    tr_list = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        tr_list.append(tr)
    return sum(tr_list[-period:]) / period

def full_technical_analysis(symbol="BTCUSDT"):
    closes, highs, lows, volumes = fetch_klines_full(symbol, interval="5m", limit=300)
    if not closes or len(closes) < 50:
        return None
    
    current_price = closes[-1]
    rsi = calculate_rsi_standard(closes)
    macd, signal, _ = calculate_macd_standard(closes)
    atr = calculate_atr(closes, highs, lows)
    ema20 = calculate_ema_series(closes, 20)[-1] if len(closes) >= 20 else current_price
    
    # شروط ذكية ومعدلة لتضمن الدخول في الصفقات وعدم التوقف
    if rsi < 55 and macd >= signal:
        recommendation = "شراء قوي 🟢"
    elif rsi > 55 or macd < signal:
        recommendation = "بيع قوي 🔴"
    else:
        recommendation = "محايد / انتظار ⚪"
        
    return {
        "price": current_price,
        "rsi": rsi,
        "macd": macd,
        "signal": signal,
        "atr": atr,
        "ema20": round(ema20, 2),
        "recommendation": recommendation
    }

def run_advanced_backtest(symbol="BTCUSDT"):
    closes, highs, lows, _ = fetch_klines_full(symbol, interval="5m", limit=300)
    if not closes or len(closes) < 50:
        return "تعذر الحصول على البيانات للاختبار."
    
    balance = 1000.0
    crypto = 0.0
    winning_trades = 0
    losing_trades = 0
    fee_rate = 0.001
    entry_price = 0.0
    
    for i in range(30, len(closes)):
        sub_closes = closes[:i]
        rsi = calculate_rsi_standard(sub_closes)
        macd, signal, _ = calculate_macd_standard(sub_closes)
        p = sub_closes[-1]
        
        if rsi < 55 and macd >= signal and balance > 10 and crypto == 0:
            trade_vol = (balance * 0.3) / p
            cost = trade_vol * p
            balance -= cost * (1 + fee_rate)
            crypto = trade_vol
            entry_price = p
        elif (rsi > 55 or macd < signal) and crypto > 0:
            revenue = (crypto * p) * (1 - fee_rate)
            balance += revenue
            if p > entry_price:
                winning_trades += 1
            else:
                losing_trades += 1
            crypto = 0.0
            
    total_trades = winning_trades + losing_trades
    win_rate = round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0.0
    final_equity = balance + (crypto * closes[-1])
    profit_pct = round(((final_equity - 1000.0) / 1000.0) * 100, 2)
    
    res = f"🧪 **نتائج الاختبار الرجعي والـ Win Rate:**\n\n"
    res += f"💵 الرصيد النهائي: `${round(final_equity, 2)}`\n"
    res += f"📈 صافي الأرباح: `{profit_pct}%`\n"
    res += f"🎯 نسبة الصفقات الرابحة (Win Rate): `{win_rate}%`\n"
    res += f"✅ صفقات رابحة: `{winning_trades}` | ❌ صفقات خاسرة: `{losing_trades}`\n"
    res += f"🔄 إجمالي الصفقات: `{total_trades}`"
    return res

def execute_trade_logic(user_id, action, price, atr=0.0):
    with db_lock:
        conn = get_db_connection()
        pf = conn.execute("SELECT * FROM portfolio WHERE user_id = ?", (user_id,)).fetchone()
        if not pf:
            conn.close()
            return
            
        usdt = pf['usdt_balance']
        btc = pf['btc_balance']
        
        if action == "BUY" and usdt >= 10:
            risk_amount = usdt * 0.02
            stop_dist = (atr * 1.5) if atr > 0 else (price * 0.02)
            position_size_usdt = min(usdt * 0.5, (risk_amount / stop_dist) * price) if stop_dist > 0 else usdt * 0.3
            
            amount = position_size_usdt / price
            new_usdt = usdt - position_size_usdt
            new_btc = btc + amount
            sl_price = price - stop_dist
            tp_price = price + (stop_dist * 2)
            
            conn.execute("UPDATE portfolio SET usdt_balance = ?, btc_balance = ?, last_buy_price = ?, stop_loss_price = ?, take_profit_price = ? WHERE user_id = ?",
                         (new_usdt, new_btc, price, sl_price, tp_price, user_id))
            conn.execute("INSERT INTO trades (user_id, symbol, type, price, amount, status) VALUES (?, ?, ?, ?, ?, ?)",
                         (user_id, "BTCUSDT", "BUY", price, amount, "OPEN"))
            conn.commit()
            
        elif action == "SELL" and btc > 0.00001:
            pnl = (price - pf['last_buy_price']) * btc
            new_usdt = usdt + (btc * price)
            
            conn.execute("UPDATE portfolio SET usdt_balance = ?, btc_balance = 0.0, last_buy_price = 0.0, stop_loss_price = 0.0, take_profit_price = 0.0 WHERE user_id = ?",
                         (new_usdt, user_id))
            conn.execute("INSERT INTO trades (user_id, symbol, type, price, amount, pnl, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (user_id, "BTCUSDT", "SELL", price, btc, pnl, "CLOSED"))
            conn.commit()
            
        conn.close()

def auto_trading_manager():
    while True:
        try:
            active_users = [u_id for u_id, st in user_trading_status.items() if st is True]
            if active_users:
                data = full_technical_analysis("BTCUSDT")
                if data:
                    price = data['price']
                    rec = data['recommendation']
                    atr = data['atr']
                    
                    for u_id in active_users:
                        pf = get_user_portfolio(u_id)
                        last_price = pf['last_buy_price']
                        sl = pf['stop_loss_price']
                        tp = pf['take_profit_price']
                        
                        if last_price > 0:
                            if (price <= sl and sl > 0) or (price >= tp and tp > 0):
                                execute_trade_logic(u_id, "SELL", price)
                                continue
                                
                        if "شراء" in rec and pf['usdt_balance'] >= 10 and pf['btc_balance'] == 0:
                            execute_trade_logic(u_id, "BUY", price, atr)
                        elif "بيع" in rec and pf['btc_balance'] > 0.00001:
                            execute_trade_logic(u_id, "SELL", price)
        except Exception as e:
            logging.error(f"Auto trading error: {e}")
        time.sleep(10)

threading.Thread(target=auto_trading_manager, daemon=True).start()

def main_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🤖 تفعيل التداول الآلي"), KeyboardButton("🛑 إيقاف التداول الآلي"))
    markup.row(KeyboardButton("📊 التحليل الفني والمؤشرات"), KeyboardButton("🧪 اختبار رجعي (Backtest)"))
    markup.row(KeyboardButton("🎯 بيع يدوي إضطراري"), KeyboardButton("💰 المحفظة"))
    markup.row(KeyboardButton("📊 سجل الأرباح"))
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    get_user_portfolio(message.from_user.id)
    bot.reply_to(message, "أهلاً بك! النسخة الشاملة والمطورة تعمل الآن بكافة مميزات إدارة المخاطر، الـ Win Rate، والـ ATR.", reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == "📊 التحليل الفني والمؤشرات")
def show_analysis(message):
    d = full_technical_analysis("BTCUSDT")
    if not d:
        bot.reply_to(message, "خطأ في الاتصال بالشبكة، حاول مجدداً.")
        return
    res = f"📈 **التحليل المتقدم (BTC/USDT):**\n\n💵 السعر: `${d['price']}`\n📉 RSI: `{d['rsi']}`\n📊 MACD: `{d['macd']}`\n📏 ATR: `{round(d['atr'], 2)}`\n\n🎯 **التوصية:** {d['recommendation']}"
    bot.reply_to(message, res, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🧪 اختبار رجعي (Backtest)")
def backtest_cmd(message):
    bot.reply_to(message, run_advanced_backtest("BTCUSDT"), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def start_auto(message):
    user_trading_status[message.from_user.id] = True
    bot.reply_to(message, "✅ تم تفعيل التداول الآلي بنجاح وسيبدأ الدخول في الصفقات بناءً على المؤشرات!")

@bot.message_handler(func=lambda m: m.text == "🛑 إيقاف التداول الآلي")
def stop_auto(message):
    user_trading_status[message.from_user.id] = False
    bot.reply_to(message, "🛑 تم إيقاف التداول الآلي.")

@bot.message_handler(func=lambda m: m.text == "💰 المحفظة")
def show_portfolio(message):
    pf = get_user_portfolio(message.from_user.id)
    usdt = round(pf['usdt_balance'], 2)
    btc = round(pf['btc_balance'], 6)
    closes, _, _, _ = fetch_klines_full("BTCUSDT", limit=5)
    cp = closes[-1] if closes else 0.0
    res = f"💼 **محفظتك المباشرة:**\n\n💵 USDT: `${usdt}`\n🪙 BTC: `{btc}`\n📊 القيمة الإجمالية: `${round(usdt + (btc * cp), 2)}`"
    bot.reply_to(message, res, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎯 بيع يدوي إضطراري")
def force_sell(message):
    user_id = message.from_user.id
    pf = get_user_portfolio(user_id)
    if pf['btc_balance'] <= 0.00001:
        bot.reply_to(message, "❌ لا تملك أي رصيد BTC للبيع.")
        return
    closes, _, _, _ = fetch_klines_full("BTCUSDT", limit=5)
    if closes:
        execute_trade_logic(user_id, "SELL", closes[-1])
        bot.reply_to(message, f"✅ تم البيع الفوري بسعر `${closes[-1]}` وتحديث محفظتك!")

@bot.message_handler(func=lambda m: m.text == "📊 سجل الأرباح")
def show_trades(message):
    with db_lock:
        conn = get_db_connection()
        trades = conn.execute("SELECT * FROM trades WHERE user_id = ? ORDER BY id DESC LIMIT 5", (message.from_user.id,)).fetchall()
        conn.close()
    if not trades:
        bot.reply_to(message, "لا توجد صفقات مسجلة بعد.")
        return
    res = "📜 **سجل الصفقات والأرباح:**\n\n"
    for t in trades:
        pnl = f" | الربح: `${round(t['pnl'], 2)}`" if t['type'] == "SELL" else ""
        res += f"• {t['type']} | السعر: `${t['price']}`{pnl}\n"
    bot.reply_to(message, res, parse_mode="Markdown")

print("🤖 البوت الشامل يعمل الآن بكافة المميزات...")
bot.infinity_polling(skip_pending=True)
