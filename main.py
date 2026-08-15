import os
import time
import threading
import logging

import telebot
from flask import Flask

# ============================================================
# الإعدادات
# ============================================================

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "❌ TELEGRAM_BOT_TOKEN غير موجود في Environment Variables"
    )

PORT = int(os.environ.get("PORT", "10000"))

# ============================================================
# Logging
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

# ============================================================
# Telegram Bot
# threaded=True يسمح بمعالجة أكثر من رسالة في نفس الوقت
# ============================================================

bot = telebot.TeleBot(
    TOKEN,
    threaded=True,
    num_threads=8
)

# ============================================================
# Flask
# ============================================================

app = Flask(__name__)


@app.route("/")
def index():
    return "البوت يعمل ✅", 200


@app.route("/health")
def health():
    return "OK", 200


# ============================================================
# Telegram Commands
# ============================================================

@bot.message_handler(commands=["start"])
def start(message):
    bot.reply_to(
        message,
        "مرحباً! البوت شغال الآن 🚀"
    )


@bot.message_handler(commands=["ping"])
def ping(message):
    bot.reply_to(
        message,
        "🏓 البوت سريع ويعمل بشكل طبيعي ⚡"
    )


# ============================================================
# Flask Server
# ============================================================

def run_flask():
    try:
        logger.info(
            "🌐 Flask يعمل على المنفذ %s",
            PORT
        )

        app.run(
            host="0.0.0.0",
            port=PORT,
            debug=False,
            use_reloader=False,
            threaded=True
        )

    except Exception as e:
        logger.exception(
            "❌ خطأ في Flask: %s",
            e
        )


# ============================================================
# Main
# ============================================================

def main():

    # تشغيل Flask في الخلفية
    flask_thread = threading.Thread(
        target=run_flask,
        daemon=True
    )

    flask_thread.start()

    # إزالة Webhook قديم
    try:
        bot.remove_webhook()
        logger.info(
            "✅ تم إزالة الـ Webhook القديم"
        )

    except Exception as e:
        logger.warning(
            "⚠️ تعذر إزالة Webhook: %s",
            e
        )

    logger.info(
        "🚀 بدء تشغيل Telegram Bot..."
    )

    # ========================================================
    # تشغيل مستمر وسريع
    # لا يوجد sleep بين الرسائل
    # ========================================================

    while True:

        try:

            bot.infinity_polling(
                timeout=20,
                long_polling_timeout=20,
                skip_pending=False,
                allowed_updates=None
            )

        except Exception as e:

            logger.exception(
                "❌ خطأ في Telegram Bot: %s",
                e
            )

            logger.info(
                "🔄 إعادة الاتصال خلال 2 ثانية..."
            )

            time.sleep(2)


# ============================================================
# تشغيل البرنامج
# ============================================================

if __name__ == "__main__":
    main()