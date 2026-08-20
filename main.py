import telebot
from telebot import types

# التوكن الخاص بك مفعل وجاهز
TOKEN = "8811018278:AAHox1l1Xaq5weFW5ScT53lFuvtJeJ_lrR8"

bot = telebot.TeleBot(TOKEN)

# قاعدة بيانات المحفظة
user_wallet = {}

def get_wallet(user_id):
    if user_id not in user_wallet:
        user_wallet[user_id] = {'usdt': 1000.0, 'btc': 0.0}
    return user_wallet[user_id]

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🚀 تنفيذ صفقة محاكاة"),
        types.KeyboardButton("💰 المحفظة"),
        types.KeyboardButton("📊 التحليل والتوقع")
    )
    bot.send_message(message.chat.id, "أهلاً بك! نظام التداول الذكي جاهز والمحاكاة مفعّلة:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🚀 تنفيذ صفقة محاكاة")
def trade(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    price = 65000.0
    amount = 100.0

    if w['usdt'] >= amount:
        btc = amount / price
        w['usdt'] -= amount
        w['btc'] += btc
        msg = (
            f"🚀 **تم تنفيذ صفقة الشراء بنجاح!**\n\n"
            f"🪙 **الزوج:** BTC/USDT\n"
            f"💵 **سعر الدخول:** ${price:.2f}\n"
            f"⚡ **الكمية المشتراة:** {btc:.6f} BTC\n"
            f"💰 **رصيد USDT المتبقي:** ${w['usdt']:.2f}\n\n"
            f"💡 **التحليل:** تم اقتناص فرصة دخول مرنة وسريعة بناءً على حركة السعر."
        )
    else:
        msg = "❌ **الرصيد المتاح غير كافي لتنفيذ الصفقة!**"

    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "💰 المحفظة")
def wallet(message):
    uid = message.from_user.id
    w = get_wallet(uid)
    total = w['usdt'] + (w['btc'] * 65000.0)
    msg = (
        f"💰 **المحفظة**\n\n"
        f"💵 **رصيد الدولار:** ${w['usdt']:.2f}\n"
        f"🪙 **رصيد البيتكوين:** {w['btc']:.6f} BTC\n"
        f"💎 **إجمالي قيمة المحفظة:** ${total:.2f}"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📊 التحليل والتوقع")
def analysis(message):
    msg = (
        "📊 **BTC / USDT**\n\n"
        "💵 **السعر الحالي:** $65000.00\n"
        "📊 **المؤشر العام:** صعود خفيف / محايد\n"
        "🤖 **التوصية:** نظام الدخول السريع والمرن مفعل وجاهز للتنفيذ."
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

if __name__ == '__main__':
    bot.infinity_polling(skip_pending=True)
