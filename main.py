import os
import telebot

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
  raise ValueError("BOT_TOKEN environment variable is missing!")

bot = telebot.TeleBot(TOKEN)


@bot.message_handler(commands=["start"])
def send_welcome(message):
  bot.reply_to(message, "أهلاً بك! البوت يعمل بنجاح 24/7 على Railway 🚀")


# تشغيل البوت بالطريقة المباشرة
print("Bot is starting...")
bot.infinity_polling()
