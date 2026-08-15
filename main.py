from flask import Flask, request
import telebot

TOKEN = "توكن_البوت"
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
    bot.process_new_updates([update])
    return "ok", 200

# عند تشغيل السيرفر، عيّن الويب هوك (يُنفّذ مرّة واحدة)
bot.remove_webhook()
bot.set_webhook(url='https://اسم-تطبيقك.onrender.com/webhook')