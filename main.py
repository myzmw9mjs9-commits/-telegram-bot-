import sqlite3
import logging
import threading
import requests
import time
import datetime
from contextlib import closing
from collections import defaultdict
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "8811018278:AAFded7ASv7bNnB6n0X5KiJUmJFw897wddE"
bot = telebot.TeleBot(BOT_TOKEN)

# استخدام RLock لمنع Deadlock وقفل مخصص لكل مستخدم لمنع سباق العمليات
db_lock = threading.RLock()
user_locks = defaultdict(threading.RLock)

user_trading_status = {}
logging.basicConfig(level=logging.INFO)

http_session = requests.Session()

def get_db_connection():
    conn = sqlite3.connect("bot_database.db", timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_lock:
        with closing(get_db_connection()) as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        symbol TEXT,
                        type TEXT,
                        price REAL,
                        amount REAL,
                        fee REAL DEFAULT 0.0,
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
                        take_profit_price REAL DEFAULT 0.0,
                        highest_price_reached REAL DEFAULT 0.0,
                        daily_loss REAL DEFAULT 0.0,
                        last_reset_date TEXT DEFAULT '',
                        trade_open_time TEXT DEFAULT ''
                    )
                ''')

init_db()

def get_user_portfolio(user_id):
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    with db_lock:
        with closing(get_db_connection()) as conn:
            with conn:
                res = conn.execute("SELECT * FROM portfolio WHERE user_id = ?", (user_id,)).fetchone()
                if not res:
                    conn.execute("INSERT INTO portfolio (user_id, usdt_balance, btc_balance, last_buy_price, stop_loss_price, take_profit_price, highest_price_reached, daily_loss, last_reset_date) VALUES (?, 1000.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ?)", (user_id, today_str))
                    res = conn.execute("SELECT * FROM portfolio WHERE user_id = ?", (user_id,)).fetchone()
                else:
                    if res['last_reset_date'] != today_str:
                        conn.execute("UPDATE portfolio SET daily_loss = 0.0, last_reset_date = ? WHERE user_id = ?", (today_str, user_id))
                        res = conn.execute("SELECT * FROM portfolio WHERE user_id = ?", (user_id,)).fetchone()
                return dict(res) if res else None

def fetch_klines_full(symbol="BTCUSDT", interval="15m", limit=1500):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    for attempt in range(3):
        try:
            res = http_session.get(url, timeout=7)
            if res.status_code == 200:
                data = res.json()
                if data and isinstance(data, list):
                    # استبعاد الشمعة الحالية (الأخيرة) غير المغلّقة لتفادي الإشارات الوهمية
                    completed_data = data[:-1] if len(data) > 1 else data
                    opens = [float(item[1]) for item in completed_data]
                    highs = [float(item[2]) for item in completed_data]
                    lows = [float(item[3]) for item in completed_data]
                    closes = [float(item[4]) for item in completed_data]
                    volumes = [float(item[5]) for item in completed_data]
                    return opens, closes, highs, lows, volumes
        except Exception as e:
            logging.error(f"Attempt {attempt+1} - Error fetching klines: {e}")
            time.sleep(1)
    return [], [], [], [], []

def fetch_current_price_live(symbol="BTCUSDT"):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        res = http_session.get(url, timeout=5)
        if res.status_code == 200:
            return float(res.json()['price'])
    except Exception as e:
        logging.error(f"Error fetching live price: {e}")
    return None

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

def adaptive_learning_multiplier(user_id):
    with db_lock:
        with closing(get_db_connection()) as conn:
            with conn:
                trades = conn.execute("SELECT pnl FROM trades WHERE user_id = ? AND status = 'CLOSED' ORDER BY id DESC LIMIT 8", (user_id,)).fetchall()
                if len(trades) >= 4:
                    losses = [t['pnl'] for t in trades if t['pnl'] < 0]
                    if len(losses) >= (len(trades) * 0.6):
                        return 0.15 
    return 0.25 

def full_technical_analysis(symbol="BTCUSDT"):
    _, closes, highs, lows, volumes = fetch_klines_full(symbol, interval="15m", limit=300)
    if not closes or len(closes) < 150:
        return None
    
    current_price = closes[-1]
    rsi = calculate_rsi_standard(closes)
    macd, signal, hist = calculate_macd_standard(closes)
    atr = calculate_atr(closes, highs, lows)
    ema20 = calculate_ema_series(closes, 20)[-1]
    ema50 = calculate_ema_series(closes, 50)[-1]
    ema100 = calculate_ema_series(closes, 100)[-1] if len(closes) >= 100 else ema50
    avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else volumes[-1]
    
    # تحسين شروط الشراء والبيع لتكون أكثر موثوقية وتفادي التسرع
    trend_filter = (current_price > ema100)
    
    buy_condition = (
        trend_filter and 
        current_price >= ema20 and 
        45 < rsi < 65 and 
        hist > 0 and 
        volumes[-1] > (avg_volume * 0.8)
    )
    
    sell_condition = (
        current_price < ema50 or 
        rsi > 78 or 
        (macd < signal and hist < 0)
    )

    if buy_condition:
        recommendation = "شراء متوسط 🟢"
    elif sell_condition:
        recommendation = "بيع متوسط 🔴"
    else:
        recommendation = "محايد / انتظار ⚪"
        
    return {
        "price": current_price,
        "high": highs[-1],
        "low": lows[-1],
        "rsi": rsi,
        "macd": macd,
        "signal": signal,
        "atr": atr,
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema100": round(ema100, 2),
        "recommendation": recommendation
    }

def run_advanced_backtest(symbol="BTCUSDT"):
    opens, closes, highs, lows, volumes = fetch_klines_full(symbol, interval="15m", limit=1500)
    if not closes or len(closes) < 150:
        return "⚠️ تعذر الحصول على بيانات كافية للاختبار حالياً، يرجى المحاولة بعد قليل."
    
    balance = 1000.0
    crypto = 0.0
    winning_trades = 0
    losing_trades = 0
    fee_rate = 0.001  
    entry_price = 0.0
    sl_price = 0.0
    tp_price = 0.0
    highest_price = 0.0
    
    for i in range(100, len(closes) - 1):
        sub_closes = closes[:i]
        sub_highs = highs[:i]
        sub_lows = lows[:i]
        sub_vols = volumes[:i]
        
        next_open = opens[i+1] * 1.0015  # محاكاة الانزلاق السعري في الاختبار الرجعي
        next_high = highs[i+1]
        next_low = lows[i+1]
        
        if crypto > 0:
            if next_high > highest_price:
                highest_price = next_high
                current_atr = calculate_atr(sub_closes, sub_highs, sub_lows)
                trailing_stop = highest_price - (current_atr * 2.2)
                if trailing_stop > sl_price:
                    sl_price = trailing_stop

            if next_low <= sl_price and next_high >= tp_price:
                revenue = crypto * sl_price * (1 - 0.0015)
                fee = revenue * fee_rate
                balance += (revenue - fee)
                losing_trades += 1
                crypto = 0.0
                entry_price = sl_price = tp_price = highest_price = 0.0
                continue
            elif next_high >= tp_price:
                revenue = crypto * tp_price * (1 - 0.0015)
                fee = revenue * fee_rate
                balance += (revenue - fee)
                winning_trades += 1
                crypto = 0.0
                entry_price = sl_price = tp_price = highest_price = 0.0
                continue
            elif next_low <= sl_price:
                revenue = crypto * sl_price * (1 - 0.0015)
                fee = revenue * fee_rate
                balance += (revenue - fee)
                losing_trades += 1
                crypto = 0.0
                entry_price = sl_price = tp_price = highest_price = 0.0
                continue

        rsi = calculate_rsi_standard(sub_closes)
        macd, signal, hist = calculate_macd_standard(sub_closes)
        ema20_val = calculate_ema_series(sub_closes, 20)[-1]
        ema50_val = calculate_ema_series(sub_closes, 50)[-1]
        ema100_val = calculate_ema_series(sub_closes, 100)[-1] if len(sub_closes) >= 100 else ema50_val
        atr_val = calculate_atr(sub_closes, sub_highs, sub_lows)
        avg_vol = sum(sub_vols[-20:]) / 20 if len(sub_vols) >= 20 else sub_vols[-1]
        
        trend_filter = (sub_closes[-1] > ema100_val)
        buy_cond = (
            trend_filter and 
            sub_closes[-1] >= ema20_val and 
            45 < rsi < 65 and 
            hist > 0 and 
            sub_vols[-1] > (avg_vol * 0.8)
        )
        sell_cond = (sub_closes[-1] < ema50_val or rsi > 78 or (macd < signal and hist < 0))

        if buy_cond and balance > 10 and crypto == 0:
            total_equity = balance
            risk_amount = total_equity * 0.015
            stop_dist = atr_val * 2.2
            
            position_size_usdt = (risk_amount / stop_dist) * next_open if stop_dist > 0 else balance * 0.2
            position_size_usdt = min(position_size_usdt, balance * 0.25)
            
            fee = position_size_usdt * fee_rate
            effective_usdt = position_size_usdt - fee
            if effective_usdt <= 0:
                continue
                
            crypto = effective_usdt / next_open
            balance -= position_size_usdt
            entry_price = next_open
            highest_price = next_open
            sl_price = next_open - stop_dist
            tp_price = next_open + (stop_dist * 2.2)
            
        elif crypto > 0 and sell_cond:
            exit_p = next_open * (1 - 0.0015)
            revenue = crypto * exit_p
            fee = revenue * fee_rate
            balance += (revenue - fee)
            
            pnl = (exit_p - entry_price) * crypto - fee
            if pnl > 0:
                winning_trades += 1
            else:
                losing_trades += 1
            crypto = 0.0
            entry_price = sl_price = tp_price = highest_price = 0.0
            
    total_trades = winning_trades + losing_trades
    win_rate = round((winning_trades / total_trades * 100), 2) if total_trades > 0 else 0.0
    final_equity = balance + (crypto * closes[-1])
    profit_pct = round(((final_equity - 1000.0) / 1000.0) * 100, 2)
    
    res = f"🧪 **نتائج الاختبار الرجعي المحسّنة (مع الانزلاق السعري):**\n\n"
    res += f"💵 الرصيد النهائي: `${round(final_equity, 2)}`\n"
    res += f"📈 صافي الأرباح: `{profit_pct}%`\n"
    res += f"🎯 نسبة الصفقات الرابحة: `{win_rate}%`\n"
    res += f"✅ صفقات رابحة: `{winning_trades}` | ❌ صفقات خاسرة: `{losing_trades}`\n"
    res += f"🔄 إجمالي الصفقات: `{total_trades}`"
    return res

def execute_trade_logic(user_id, action, price, atr=0.0):
    with user_locks[user_id]:
        with db_lock:
            with closing(get_db_connection()) as conn:
                with conn:
                    pf = conn.execute("SELECT * FROM portfolio WHERE user_id = ?", (user_id,)).fetchone()
                    if not pf:
                        return
                    pf = dict(pf)
                        
                    usdt = pf['usdt_balance']
                    btc = pf['btc_balance']
                    daily_loss = pf['daily_loss']
                    fee_rate = 0.001
                    
                    if daily_loss >= 50.0 and action == "BUY":
                        return

                    if action == "BUY" and usdt >= 10:
                        dynamic_position_ratio = adaptive_learning_multiplier(user_id)
                        
                        total_equity = usdt + (btc * price)
                        risk_amount = total_equity * 0.015
                        stop_dist = (atr * 2.2) if atr > 0 else (price * 0.025)
                        
                        # حساب المخاطر بحجم مركز ثابت وموحد ومتسق
                        position_size_usdt = (risk_amount / stop_dist) * price if stop_dist > 0 else usdt * 0.2
                        position_size_usdt = min(position_size_usdt, usdt * dynamic_position_ratio)
                        
                        # إضافة هامش الانزلاق السعري (0.15%) عند الشراء الفعلي بالسوق
                        effective_price = price * 1.0015
                        
                        fee = position_size_usdt * fee_rate
                        effective_usdt = position_size_usdt - fee
                        if effective_usdt <= 0:
                            return
                            
                        amount = effective_usdt / effective_price
                        new_usdt = usdt - position_size_usdt
                        new_btc = btc + amount
                        sl_price = effective_price - stop_dist
                        tp_price = effective_price + (stop_dist * 2.2)
                        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        conn.execute("UPDATE portfolio SET usdt_balance = ?, btc_balance = ?, last_buy_price = ?, stop_loss_price = ?, take_profit_price = ?, highest_price_reached = ?, trade_open_time = ? WHERE user_id = ?",
                                     (new_usdt, new_btc, effective_price, sl_price, tp_price, effective_price, now_str, user_id))
                        conn.execute("INSERT INTO trades (user_id, symbol, type, price, amount, fee, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                     (user_id, "BTCUSDT", "BUY", effective_price, amount, fee, "OPEN"))
                        
                    elif action == "SELL" and btc > 0.00001:
                        effective_price = price * (1 - 0.0015) # تطبيق الانزلاق السعري عند البيع
                        gross_revenue = btc * effective_price
                        fee = gross_revenue * fee_rate
                        net_revenue = gross_revenue - fee
                        
                        pnl = (effective_price - pf['last_buy_price']) * btc - fee
                        new_usdt = usdt + net_revenue
                        
                        new_daily_loss = daily_loss
                        if pnl < 0:
                            new_daily_loss += abs(pnl)
                            
                        conn.execute("UPDATE portfolio SET usdt_balance = ?, btc_balance = 0.0, last_buy_price = 0.0, stop_loss_price = 0.0, take_profit_price = 0.0, highest_price_reached = 0.0, daily_loss = ?, trade_open_time = '' WHERE user_id = ?",
                                     (new_usdt, new_daily_loss, user_id))
                        conn.execute("INSERT INTO trades (user_id, symbol, type, price, amount, fee, pnl, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                     (user_id, "BTCUSDT", "SELL", effective_price, btc, fee, pnl, "CLOSED"))

def auto_trading_manager():
    while True:
        try:
            active_users = [u_id for u_id, st in user_trading_status.items() if st is True]
            if active_users:
                data = full_technical_analysis("BTCUSDT")
                if data:
                    price = data['price']
                    high_p = data['high']
                    low_p = data['low']
                    rec = data['recommendation']
                    atr = data['atr']
                    
                    for u_id in active_users:
                        with user_locks[u_id]:
                            pf = get_user_portfolio(u_id)
                            if not pf:
                                continue
                            last_buy = pf['last_buy_price']
                            btc_amt = pf['btc_balance']
                            open_time_str = pf['trade_open_time']
                            
                            # 1. حد زمن أقصى للصفقة (Max Holding Period - مثلاً 48 ساعة)
                            if btc_amt > 0.00001 and open_time_str:
                                try:
                                    open_dt = datetime.datetime.strptime(open_time_str, "%Y-%m-%d %H:%M:%S")
                                    if datetime.datetime.now() - open_dt > datetime.timedelta(hours=48):
                                        execute_trade_logic(u_id, "SELL", price)
                                        continue
                                except Exception:
                                    pass

                            # 2. تقييم وقف الخسارة اليومي
                            if btc_amt > 0.00001 and last_buy > 0:
                                current_unrealized_pnl = (price - last_buy) * btc_amt
                                if current_unrealized_pnl < 0 and abs(current_unrealized_pnl) >= (50.0 - pf['daily_loss']):
                                    execute_trade_logic(u_id, "SELL", price)
                                    continue

                            if pf['daily_loss'] >= 50.0:
                                if btc_amt > 0.00001:
                                    execute_trade_logic(u_id, "SELL", price)
                                continue

                            sl = pf['stop_loss_price']
                            tp = pf['take_profit_price']
                            highest = pf['highest_price_reached']
                            
                            if last_buy > 0:
                                if high_p > highest:
                                    highest = high_p
                                    new_sl = highest - (atr * 2.2)
                                    if new_sl > sl:
                                        sl = new_sl
                                        with db_lock:
                                            with closing(get_db_connection()) as conn:
                                                with conn:
                                                    conn.execute("UPDATE portfolio SET highest_price_reached = ?, stop_loss_price = ? WHERE user_id = ?", (highest, sl, u_id))
                                            
                                if high_p >= tp and tp > 0:
                                    execute_trade_logic(u_id, "SELL", tp)
                                    continue
                                elif low_p <= sl and sl > 0:
                                    execute_trade_logic(u_id, "SELL", sl)
                                    continue
                                    
                            if "شراء" in rec and pf['usdt_balance'] >= 10 and pf['btc_balance'] == 0:
                                execute_trade_logic(u_id, "BUY", price, atr)
                            elif "بيع" in rec and pf['btc_balance'] > 0.00001:
                                execute_trade_logic(u_id, "SELL", price)
        except Exception as e:
            logging.error(f"Auto trading error: {e}")
        time.sleep(15)

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
    bot.reply_to(message, "أهلاً بك! تم تحديث الكود ومعالجة كافة المشاكل (الشموع المغلقة فقط، الانزلاق السعري، حجم المركز الموحد، حد زمن أقصى للصفقة، وتخفيف التسرع في شروط البيع).", reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == "📊 التحليل الفني والمؤشرات")
def show_analysis(message):
    d = full_technical_analysis("BTCUSDT")
    if not d:
        bot.reply_to(message, "⚠️ تعذر الاتصال بالسوق حالياً، يرجى المحاولة بعد ثوانٍ.")
        return
    res = f"📈 **التحليل الفني (شموع مغلقة):**\n\n💵 السعر: `${d['price']}`\n📉 RSI: `{d['rsi']}`\n📊 MACD: `{d['macd']}`\n📉 EMA20: `{d['ema20']}`\n📉 EMA50: `{d['ema50']}`\n📉 EMA100: `{d['ema100']}`\n📏 ATR: `{round(d['atr'], 2)}`\n\n🎯 **التوصية:** {d['recommendation']}"
    bot.reply_to(message, res, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🧪 اختبار رجعي (Backtest)")
def backtest_cmd(message):
    bot.reply_to(message, run_advanced_backtest("BTCUSDT"), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🤖 تفعيل التداول الآلي")
def start_auto(message):
    user_trading_status[message.from_user.id] = True
    bot.reply_to(message, "✅ تم تفعيل التداول الآلي بنجاح مع التعديلات الجديدة لمعالجة الخسائر!")

@bot.message_handler(func=lambda m: m.text == "🛑 إيقاف التداول الآلي")
def stop_auto(message):
    user_trading_status[message.from_user.id] = False
    bot.reply_to(message, "🛑 تم إيقاف التداول الآلي.")

@bot.message_handler(func=lambda m: m.text == "💰 المحفظة")
def show_portfolio(message):
    pf = get_user_portfolio(message.from_user.id)
    if not pf:
        bot.reply_to(message, "⚠️ حدث خطأ في جلب بيانات المحفظة.")
        return
    usdt = round(pf['usdt_balance'], 2)
    btc = round(pf['btc_balance'], 6)
    loss = round(pf['daily_loss'], 2)
    live_price = fetch_current_price_live("BTCUSDT") or 0.0
    res = f"💼 **محفظتك وحالة الحماية:**\n\n💵 USDT: `${usdt}`\n🪙 BTC: `${btc}`\n🛡️ الخسارة اليومية: `${loss} / $50.0`\n📊 القيمة الكلية: `${round(usdt + (btc * live_price), 2)}`"
    bot.reply_to(message, res, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎯 بيع يدوي إضطراري")
def force_sell(message):
    user_id = message.from_user.id
    pf = get_user_portfolio(user_id)
    if not pf or pf['btc_balance'] <= 0.00001:
        bot.reply_to(message, "❌ لا تملك رصيد BTC حالياً للبيع.")
        return
    live_price = fetch_current_price_live("BTCUSDT")
    if live_price:
        execute_trade_logic(user_id, "SELL", live_price)
        bot.reply_to(message, f"✅ تم تنفيذ البيع الإضطراري بالسعر اللحظي الفعلي `${live_price}` وتحديث رصيدك بدقة!")
    else:
        bot.reply_to(message, "⚠️ تعذر جلب السعر الفعلي من السوق، حاول مرة أخرى.")

@bot.message_handler(func=lambda m: m.text == "📊 سجل الأرباح")
def show_trades(message):
    with db_lock:
        with closing(get_db_connection()) as conn:
            with conn:
                trades = conn.execute("SELECT * FROM trades WHERE user_id = ? ORDER BY id DESC LIMIT 5", (message.from_user.id,)).fetchall()
    if not trades:
        bot.reply_to(message, "لا توجد صفقات مسجلة بعد.")
        return
    res = "📜 **سجل آخر الصفقات:**\n\n"
    for t in trades:
        fee_str = f" | عمولة: `${round(t['fee'], 3)}`" if 'fee' in t.keys() and t['fee'] > 0 else ""
        pnl = f" | الربح/الخسارة: `${round(t['pnl'], 2)}`" if t['type'] == "SELL" else ""
        res += f"• {t['type']} | السعر: `${t['price']}`{fee_str}{pnl}\n"
    bot.reply_to(message, res, parse_mode="Markdown")

print("🤖 البوت يعمل بكفاءة مع كافة التصحيحات والتحسينات ضد أسباب الخسارة...")
bot.infinity_polling(skip_pending=True)
