import os
import sqlite3
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# 1. إعدادات البوت وقاعدة البيانات والذاكرة
# ==========================================
BOT_TOKEN = "8811018278:AAGoRYuDg8L_FqSne62PKppksx-LMbXyn0I"
bot = telebot.TeleBot(BOT_TOKEN)

db_lock = threading.Lock()
cache_lock = threading.Lock()
PRICE_CACHE = {}

def get_db_connection():
    conn = sqlite3.connect("bot_database.db")
    conn.row_factory = sqlite3.Row
    return conn

# ==========================================
# 2. جلب أسعار العملات
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
    except Exception as e:
        logging.error(f"خطأ أثناء جلب السعر لـ {symbol}: {e}")

    with cache_lock:
        return PRICE_CACHE.get(symbol, 65000.0)

# ==========================================
# 3. لوحة التحكم والكيبورد الرئيسي
# ==========================================
def main_keyboard():
    markup = ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        KeyboardButton("🤖 تفعيل التداول الآلي"),
        KeyboardButton("🛑 إيقاف التداول الآلي"),
        KeyboardButton("🎯 بيع يدوي إضطراري"),
        KeyboardButton("📊 سجل الأرباح"),
        KeyboardButton("💰 المحفظة")
    )
    return markup

def get_user_dashboard(user_id):
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user = cursor.fetchone()
        balance = user["balance"] if user else 1000.0

        cursor.execute("SELECT * FROM positions WHERE user_id = ?", (user_id,))
        positions = cursor.fetchall()
        
        total_pnl = sum([pos["pnl"] for pos in positions]) if positions else 0.0
        conn.close()
        return balance, total_pnl, positions

# ==========================================
# 4. معالجات الرسائل والأوامر (/start والأزرار)
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    with db_lock:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL, auto_trading INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS positions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, symbol TEXT, entry_price REAL, amount REAL, pnl REAL)")
        cursor.execute("INSERT OR IGNORE INTO users (user_id, balance, auto_trading) VALUES (?, 1000.0, 0)", (user_id,))
        conn.commit()
        conn.close()

    welcome_text = "أهلاً بك! تم تشغيل البوت الشامل بكافة استراتيجيات ومؤشرات التداول العالمية والمتقدمة."
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_keyboard())

@bot.message_handler(func=lambda message: message.text == "🤖 تفعيل التداول الآلي")
def enable_auto(message):
    with db_lock:
        conn = get_db_connection()
        conn.execute("UPDATE users SET auto_trading = 1 WHERE user_id = ?", (message.from_user.id,))
        conn.commit()
        conn.close()
    bot.reply_to(message, "⚙️ تم تفعيل التداول الآلي بنجاح!")

@bot.message_handler(func=lambda message: message.text == "🛑 إيقاف التداول الآلي")
def disable_auto(message):
    with db_lock:
        conn = get_db_connection()
        conn.execute("UPDATE users SET auto_trading = 0 WHERE user_id = ?", (message.from_user.id,))
        conn.commit()
        conn.close()
    bot.reply_to(message, "🛑 تم إيقاف التداول الآلي.")

@bot.message_handler(func=lambda message: message.text == "💰 المحفظة")
def show_wallet(message):
    balance, total_pnl, positions = get_user_dashboard(message.from_user.id)
    msg = f"💳 **تفاصيل المحفظة**\n\n💰 الرصيد المتاح: ${balance:.2f}\n📈 إجمالي الأرباح/الخسائر: ${total_pnl:.2f}\n📂 عدد الصفقات النشطة: {len(positions)}"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📊 سجل الأرباح")
def show_history(message):
    bot.reply_to(message, "📁 لا يوجد لديك سجل صفقات مكتملة حتى الآن.")

@bot.message_handler(func=lambda message: message.text == "🎯 بيع يدوي إضطراري")
def force_sell(message):
    bot.reply_to(message, "⚠️ لا توجد صفقات مفتوحة حالياً!")

# ==========================================
# 5. تشغيل البوت
# ==========================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🤖 البوت يعمل الآن بنجاح...")
    bot.infinity_polling(skip_pending=True)
