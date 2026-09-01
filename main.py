import os
import telebot

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
  raise ValueError("⚠️ خطأ: متغير البيئة BOT_TOKEN غير موجود!")

bot = telebot.TeleBot(TOKEN)


@bot.message_handler(commands=["start"])
def send_welcome(message):
  bot.reply_to(message, "أهلاً بك! البوت يعمل بنجاح 24/7 على Railway 🚀")


# تشغيل البوت بالطريقة المباشرة
print("Bot is starting...")
bot.infinity_polling()
