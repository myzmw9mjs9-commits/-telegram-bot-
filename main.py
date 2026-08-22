import logging
import sqlite3
import requests
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# 1. الإعدادات الأساسية والتكوين (Configuration)
# ==========================================
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
DB_PATH = "trading_bot.db"
FEE = 0.001  # رسوم التداول 0.1%

bot = TeleBot(BOT_TOKEN)

# أقفال التزامن للسلامة (Thread Safety)
db_lock = Lock()
cache_lock = Lock()

# كاش الأسعار المحلي
PRICE_CACHE = {}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# ==========================================
# 2. إدارة قاعدة البيانات (SQLite Setup)
# ==========================================
def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        # جدول المستخدمين
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance REAL DEFAULT 1000.0
            )
        """)
        # جدول الصفقات
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                symbol TEXT,
                type TEXT,
                entry_price REAL,
                amount REAL,
                margin REAL
            )
        """)
        conn.commit()
        conn.close()

# ==========================================
# 3. جلب الأسعار والاتصال بـ Binance API
# ==========================================
def get_live_price_fast(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        response = requests.get(url, timeout=1.5)
        if response.status_code == 200:
            price = float(response.json()["price"])
            with cache_lock:
                PRICE_CACHE[symbol] = price
            return price
        logging.warning(f"فشل جلب سعر {symbol} من API (رمز الحالة: {response.status_code})")
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
# 4. منطق إغلاق الصفقات وحساب الأرباح والرسوم
# ==========================================
def close_user_position(pos_id, current_price):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # جلب تفاصيل الصفقة
        cursor.execute("SELECT * FROM positions WHERE id = ?", (pos_id,))
        pos = cursor.fetchone()
        if not pos:
            conn.close()
            return None
        
        user_id = pos["user_id"]
        
        # جلب رصيد المستخدم
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            logging.warning(f"المستخدم {user_id} غير موجود في قاعدة البيانات.")
            return None
            
        current_balance = user["balance"]
        
        # حساب PnL
        entry = pos["entry_price"]
        amount = pos["amount"]
        is_long = pos["type"].upper() == "LONG"
        
        pnl = (current_price - entry) * amount if is_long else (entry - current_price) * amount
        
        # خصم الرسوم من المبلغ العائد
        gross_return = pos["margin"] + pnl
        net_return = max(0.0, gross_return * (1 - FEE))
        
        new_balance = current_balance + net_return
        
        # تحديث الرصيد وحذف الصفقة
        cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
        cursor.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
        conn.commit()
        conn.close()
        
        return {
            "symbol": pos["symbol"],
            "pnl": pnl,
            "net_return": net_return,
            "fee_deducted": gross_return * FEE,
            "new_balance": new_balance
        }

# ==========================================
# 5. بناء لوحة التحكم وأزرار التليجرام (UI)
# ==========================================
def get_user_dashboard_data(user_id):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # ضمان وجود المستخدم
        cursor.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 1000.0)", (user_id,))
        conn.commit()
        
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        balance = cursor.fetchone()["balance"]
        
        cursor.execute("SELECT * FROM positions WHERE user_id = ?", (user_id,))
        positions = cursor.fetchall()
        conn.close()
        
    symbols = list(set([p["symbol"] for p in positions]))
    prices = fetch_prices_for_symbols(symbols)
    
    pos_data_list = []
    total_pnl = 0.0
    
    for p in positions:
        sym = p["symbol"]
        curr_p = prices.get(sym, p["entry_price"])
        is_long = p["type"].upper() == "LONG"
        pnl = (curr_p - p["entry_price"]) * p["amount"] if is_long else (p["entry_price"] - curr_p) * p["amount"]
        total_pnl += pnl
        
        pos_data_list.append({
            "id": p["id"],
            "symbol": sym,
            "type": p["type"],
            "pnl": pnl,
            "current_price": curr_p
        })
        
    return balance, total_pnl, pos_data_list

def build_dashboard_markup(positions_data):
    markup = InlineKeyboardMarkup(row_width=1)
    
    for pos in positions_data:
        btn_text = f"❌ إغلاق {pos['symbol']} ({pos['type']}) | PnL: {pos['pnl']:.2f}$"
        markup.add(InlineKeyboardButton(text=btn_text, callback_data=f"close_{pos['id']}"))
    
    markup.add(
        InlineKeyboardButton(text="🔄 تحديث اللوحة", callback_data="refresh_dashboard"),
        InlineKeyboardButton(text="⚠️ إغلاق كافة الصفقات", callback_data="close_all")
    )
    return markup

# ==========================================
# 6. معالجات أوامر التليجرام (Telegram Handlers)
# ==========================================
@bot.message_handler(commands=['start', 'dashboard'])
def send_dashboard(message):
    user_id = message.from_user.id
    balance, total_pnl, positions = get_user_dashboard_data(user_id)
    
    text = f"📊 **لوحة تحكم التداول**\n\n"
    text += f"💰 **الرصيد المتاح:** `${balance:.2f}`\n"
    text += f"📈 **إجمالي الأرباح/الخسائر:** `${total_pnl:.2f}`\n"
    text += f"🔓 **عدد الصفقات المفتوحة:** `{len(positions)}`"
    
    markup = build_dashboard_markup(positions)
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    
    if call.data == "refresh_dashboard":
        balance, total_pnl, positions = get_user_dashboard_data(user_id)
        text = f"📊 **لوحة تحكم التداول**\n\n"
        text += f"💰 **الرصيد المتاح:** `${balance:.2f}`\n"
        text += f"📈 **إجمالي الأرباح/الخسائر:** `${total_pnl:.2f}`\n"
        text += f"🔓 **عدد الصفقات المفتوحة:** `{len(positions)}`"
        
        markup = build_dashboard_markup(positions)
        try:
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "تم تحديث البيانات!")
        except Exception:
            bot.answer_callback_query(call.id, "البيانات محدثة بالفعل.")

    elif call.data.startswith("close_"):
        if call.data == "close_all":
            _, _, positions = get_user_dashboard_data(user_id)
            for pos in positions:
                close_user_position(pos["id"], pos["current_price"])
            bot.answer_callback_query(call.id, "تم إغلاق جميع الصفقات بنجاح!")
        else:
            pos_id = int(call.data.split("_")[1])
            # جلب السعر الحالي
            with db_lock:
                conn = get_db_connection()
                pos = conn.execute("SELECT symbol FROM positions WHERE id = ?", (pos_id,)).fetchone()
                conn.close()
            
            if pos:
                live_price = get_live_price_fast(pos["symbol"])
                res = close_user_position(pos_id, live_price)
                if res:
                    bot.answer_callback_query(call.id, f"تم إغلاق {res['symbol']} بنجاح! PnL: {res['pnl']:.2f}$")
            else:
                bot.answer_callback_query(call.id, "الصفقة مغلقة بالفعل!")
        
        # تحديث اللوحة بعد الإغلاق
        balance, total_pnl, positions = get_user_dashboard_data(user_id)
        text = f"📊 **لوحة تحكم التداول**\n\n"
        text += f"💰 **الرصيد المتاح:** `${balance:.2f}`\n"
        text += f"📈 **إجمالي الأرباح/الخسائر:** `${total_pnl:.2f}`\n"
        text += f"🔓 **عدد الصفقات المفتوحة:** `{len(positions)}`"
        
        markup = build_dashboard_markup(positions)
        bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# ==========================================
# 7. نقطة التشغيل الرئيسية (Main)
# ==========================================
if __name__ == "__main__":
    init_db()
    logging.info("تم تشغيل البوت بنجاح وهو جاهز لاستقبال الأوامر...")
    bot.infinity_polling()
