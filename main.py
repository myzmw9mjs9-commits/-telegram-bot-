import telebot
from telebot import types

# ضع التوكن الخاص بك هنا
TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'
bot = telebot.TeleBot(TOKEN)

# قاعدة بيانات وهمية للمحفظة
user_wallet = {}

def get_user_wallet(user_id):
    if user_id not in user_wallet:
        user_wallet[user_id] = {'usdt': 1000.0, 'btc': 0.0}
    return user_wallet[user_id]

# دالة اتخاذ القرار المرنة (تسمح بالدخول في كافة الحالات تقريباً)
def smart_trade_decision(market_status):
    # المرونة: يسمح بالشراء إذا كان المؤشر صاعد، محايد، أو حتى خفيف
    allowed_statuses = ["صعود خفيف / محايد", "صعود خفيف", "محايد", "مستقرة", "صعود"]
    if any(status in market_status for status in allowed_statuses):
        return True, "تم الكشف عن فرصة مرنة (صعود خفيف/محايد)، تم تنفيذ الصفقة بنجاح!"
    return False, "السوق في حالة هبوط حاد، تم إلغاء الصفقة لحماية المحفظة."

@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton("🚀 تنفيذ صفقة محاكاة")
    btn2 = types.KeyboardButton("💰 المحفظة")
    btn3 = types.KeyboardButton("📊 التحليل والتوقع")
    markup.add(btn1, btn2, btn3)
    
    bot.send_message(message.chat.id, "أهلاً بك في بوت التداول الذكي! اختر من القائمة:", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "🚀 تنفيذ صفقة محاكاة")
def simulate_trade(message):
    user_id = message.from_user.id
    wallet = get_user_wallet(user_id)
    
    # محاكاة حالة السوق الحالية
    market_status = "صعود خفيف / محايد"
    current_price = 65000.0
    trade_amount = 100.0  # مبلغ دخول الصفقة (100 دولار)

    can_trade, reason = smart_trade_decision(market_status)

    if can_trade:
        if wallet['usdt'] >= trade_amount:
            btc_bought = trade_amount / current_price
            wallet['usdt'] -= trade_amount
            wallet['btc'] += btc_bought

            msg = (
                f"🚀 **محاكاة صفقة تداول**\n\n"
                f"🪙 **الزوج:** BTC/USDT\n"
                f"💵 **سعر الدخول الحالي:** ${current_price:.2f}\n"
                f"⚡ **الكمية المشتراة:** {btc_bought:.6f} BTC\n"
                f"💰 **الرصيد المتاح:** ${wallet['usdt']:.2f}\n\n"
                f"💡 **التحليل:** {reason}"
            )
        else:
            msg = "❌ **الرصيد المتاح غير كافي لتنفيذ الصفقة!**"
    else:
        msg = f"💡 **التحليل:** {reason}"

    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "💰 المحفظة")
def show_wallet(message):
    user_id = message.from_user.id
    wallet = get_user_wallet(user_id)
    total_val = wallet['usdt'] + (wallet['btc'] * 65000.0)
    
    msg = (
        f"💰 **المحفظة**\n\n"
        f"💵 **رصيد الدولار:** ${wallet['usdt']:.2f}\n"
        f"🪙 **رصيد البيتكوين:** {wallet['btc']:.6f} BTC\n"
        f"💎 **إجمالي المحفظة:** ${total_val:.2f}"
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📊 التحليل والتوقع")
def show_analysis(message):
    msg = (
        f"📊 **BTC / USDT**\n\n"
        f"💵 **السعر الحالي:** $65000.00\n"
        f"📊 **المؤشر العام:** صعود خفيف / محايد\n"
        f"🤖 **التوصية:** نظام التفكير المرن مفعل، جاهز للدخول الفوري."
    )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

bot.polling(none_stop=True)
