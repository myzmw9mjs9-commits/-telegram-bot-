import os
import sqlite3
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# 1. إعدادات البوت وقاعدة البيانات والذاكرة
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
bot = telebot.TeleBot(BOT_TOKEN)

db_lock = threading.Lock()
cache_lock = threading.Lock()

PRICE_CACHE = {}

def get_db_connection():
    conn = sqlite3.connect("bot_database.db")
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# 2. جلب أسعار العملات مع الذاكرة المؤقتة
# ==========================================
def get_live_price_fast(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url, timeout=1.5)
        if response.status_code == 200:
            price = float(response.json()["price"])
            with cache_lock:
                PRICE_CACHE[symbol] = price
            return price
        logging.warning(f"فشل جلب سعر {symbol}")
    except Exception as e:
        logging.error(f"خطأ أثناء الاتصال بـ Binance لـ {symbol}: {e}")

    # خيار احتياطي: إرجاع السعر المخزن في الكاش
    with cache_lock:
        return PRICE_CACHE.get(symbol)

def fetch_prices_for_symbols(symbols):
    results = {}
    if not symbols:
        return results

    # تحديد عدد العمال بحيث لا يتجاوز 10 لمنع الضغط
    max_workers = min(10, len(symbols))

    def _fetch(sym):
        try:
            return sym, get_live_price_fast(sym)
        except Exception as e:
            logging.error(f"خطأ غير متوقع أثناء جلب {sym}: {e}")
            return sym, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(_fetch, sym) for sym in symbols]
        for future in futures:
            sym, price = future.result()
            if price is not None:
                results[sym] = price

    return results

# ==========================================
# 3. حساب جميع المؤشرات الفنية المتقدمة
# ==========================================
def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
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
    signal_line = macd_line * 0.8
    return macd_line, signal_line

def calculate_bollinger_bands(closes, period=20, std_dev=2):
    if len(closes) < period:
        return closes[-1], closes[-1]
    slice_c = closes[-period:]
    sma = sum(slice_c) / period
    variance = sum((x - sma) ** 2 for x in slice_c) / period
    std = variance ** 0.5
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return lower, upper

# ==========================================
# 4. منطق إغلاق الصفقات وحساب الأرباح والرسوم
# ==========================================
def close_user_position(pos_id, current_price):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM positions WHERE id = ?", (pos_id,))
        pos = cursor.fetchone()
        
        if not pos:
            conn.close()
            return False

        user_id = pos["user_id"]
        entry_price = pos["entry_price"]
        amount = pos["amount"]

        pnl = (current_price - entry_price) * amount
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount + pnl, user_id))
        cursor.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
        
        conn.commit()
        conn.close()
        return True

def get_user_dashboard(user_id):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        balance = user["balance"] if user else 0.0

        cursor.execute("SELECT * FROM positions WHERE user_id = ?", (user_id,))
        positions = cursor.fetchall()
        
        total_pnl = sum([pos["pnl"] for pos in positions]) if positions else 0.0
        conn.close()
        return balance, total_pnl, positions

def build_dashboard_markup(positions):
    markup = InlineKeyboardMarkup()
    for pos in positions:
        btn_text = f"❌ إغلاق {pos['symbol']} (#{pos['id']})"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"close_{pos['id']}"))
    
    if positions:
        markup.add(InlineKeyboardButton("🔴 إغلاق جميع الصفقات", callback_data="close_all"))
    return markup

# ==========================================
# 5. معالجات الأوامر واستجابة أزرار التليجرام
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    try:
        if call.data.startswith("close_"):
            if call.data == "close_all":
                _, _, positions = get_user_dashboard(call.from_user.id)
                symbols = [pos["symbol"] for pos in positions]
                prices = fetch_prices_for_symbols(symbols)
                
                for pos in positions:
                    live_p = prices.get(pos["symbol"], pos["entry_price"])
                    close_user_position(pos["id"], live_p)
                bot.answer_callback_query(call.id, "تم إغلاق جميع الصفقات بنجاح!")
            else:
                pos_id = int(call.data.split("_")[1])
                with db_lock:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT symbol FROM positions WHERE id = ?", (pos_id,))
                    pos = cursor.fetchone()
                    conn.close()

                if pos:
                    live_price = get_live_price_fast(pos["symbol"])
                    res = close_user_position(pos_id, live_price)
                    if res:
                        bot.answer_callback_query(call.id, f"تم إغلاق الصفقة #{pos_id}")
                    else:
                        bot.answer_callback_query(call.id, "تعذر إغلاق الصفقة!")
                else:
                    bot.answer_callback_query(call.id, "الصفقة غير موجودة أو تم إغلاقها سابقاً.")

            # تحديث اللوحة بعد الإغلاق
            balance, total_pnl, positions = get_user_dashboard(call.from_user.id)
            text = f"📊 **لوحة التحكم**\n\n💰 الرصيد الحالي: ${balance:.2f}\n📈 إجمالي الأرباح/الخسائر: ${total_pnl:.2f}\n📂 عدد الصفقات المفتوحة: {len(positions)}"
            markup = build_dashboard_markup(positions)
            
            try:
                bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                pass

    except Exception as e:
        logging.error(f"خطأ أثناء معالجة زر الإغلاق: {e}")
        bot.answer_callback_query(call.id, "حدث خطأ غير متوقع!")

# ==========================================
# 6. تشغيل البوت
# ==========================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🤖 البوت يعمل الآن بنجاح...")
    bot.infinity_polling()
