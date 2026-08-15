import logging
import math
import os
from datetime import datetime, timezone
from threading import Thread

import requests
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ============================================================
# إعداد السجلات
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# الإعدادات - ضعها في Environment Variables
# ============================================================

TOKEN = "8811018278:AAF36qLjzSNDz8qxcrk8SPkKerzycIpipv4"

STARTING_BALANCE = float(os.getenv("STARTING_BALANCE", "1000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))  # 1%
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "0.03"))  # 3%

# اختياري: لمتابعة الأخبار
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "").strip()

# ============================================================
# خادم ويب صغير لـ Render
# ============================================================

app_web = Flask(__name__)


@app_web.route("/")
def home():
    return "Trading bot is alive!"


def run_web():
    port = int(os.environ.get("PORT", "8080"))
    app_web.run(host="0.0.0.0", port=port)


# ============================================================
# محفظة Paper Trading
# ============================================================

portfolio = {
    "usd": STARTING_BALANCE,
    "btc": 0.0,
    "daily_start_balance": STARTING_BALANCE,
    "consecutive_losses": 0,
}


# ============================================================
# أدوات حساب المؤشرات
# ============================================================

def ema(values, period):
    """حساب EMA بدون مكتبات إضافية."""
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)
    result = sum(values[:period]) / period

    for price in values[period:]:
        result = (price - result) * multiplier + result

    return result


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def rsi(values, period=14):
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(candles, period=14):
    if len(candles) < period + 1:
        return None

    true_ranges = []

    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        previous_close = candles[i - 1]["close"]

        tr = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close),
        )
        true_ranges.append(tr)

    return sum(true_ranges[-period:]) / period


def macd(values):
    if len(values) < 35:
        return None, None, None

    # EMA كامل حتى نحصل على MACD قريب من الحساب المعتاد
    ema12_series = []
    ema26_series = []

    def build_ema_series(data, period):
        if len(data) < period:
            return []

        multiplier = 2 / (period + 1)
        current = sum(data[:period]) / period
        series = [None] * (period - 1) + [current]

        for price in data[period:]:
            current = (price - current) * multiplier + current
            series.append(current)

        return series

    ema12_series = build_ema_series(values, 12)
    ema26_series = build_ema_series(values, 26)

    macd_values = []
    for i in range(len(values)):
        if ema12_series[i] is not None and ema26_series[i] is not None:
            macd_values.append(ema12_series[i] - ema26_series[i])

    if len(macd_values) < 9:
        return None, None, None

    signal = ema(macd_values, 9)
    current_macd = macd_values[-1]

    if signal is None:
        return None, None, None

    histogram = current_macd - signal
    return current_macd, signal, histogram


# ============================================================
# جلب بيانات السوق من Binance
# ============================================================

def get_market_data(symbol="BTCUSDT", interval="1h", limit=250):
    url = "https://api.binance.com/api/v3/klines"

    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    }

    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()

    raw = response.json()

    if not isinstance(raw, list) or len(raw) < 200:
        raise ValueError("بيانات السوق غير كافية.")

    candles = []

    for item in raw:
        candles.append(
            {
                "open_time": item[0],
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
        )

    return candles


# ============================================================
# التحليل الفني
# ============================================================

def technical_analysis(candles):
    closes = [x["close"] for x in candles]
    volumes = [x["volume"] for x in candles]

    price = closes[-1]

    ema20 = ema(closes, 20)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)
    current_rsi = rsi(closes, 14)
    current_atr = atr(candles, 14)
    current_macd, macd_signal, macd_hist = macd(closes)

    if None in (
        ema20,
        ema50,
        ema200,
        current_rsi,
        current_atr,
        current_macd,
        macd_signal,
        macd_hist,
    ):
        raise ValueError("تعذر حساب المؤشرات.")

    recent = candles[-50:]
    support = min(x["low"] for x in recent)
    resistance = max(x["high"] for x in recent)

    average_volume = sma(volumes, 20)
    volume_ok = average_volume is not None and volumes[-1] > average_volume

    score = 0
    reasons = []

    # الاتجاه
    if price > ema20 > ema50 > ema200:
        score += 3
        reasons.append("الاتجاه صاعد قوي: السعر فوق EMA20/50/200.")
    elif price > ema50:
        score += 2
        reasons.append("الاتجاه العام يميل للصعود.")
    elif price < ema20 < ema50 < ema200:
        score -= 3
        reasons.append("الاتجاه هابط قوي: السعر تحت EMA20/50/200.")
    elif price < ema50:
        score -= 2
        reasons.append("الاتجاه العام يميل للهبوط.")
    else:
        reasons.append("الاتجاه غير واضح.")

    # RSI
    if current_rsi < 30:
        score += 2
        reasons.append(f"RSI={current_rsi:.1f}: تشبع بيع.")
    elif current_rsi > 70:
        score -= 2
        reasons.append(f"RSI={current_rsi:.1f}: تشبع شراء.")
    else:
        reasons.append(f"RSI={current_rsi:.1f}: في منطقة غير متطرفة.")

    # MACD
    if current_macd > macd_signal and macd_hist > 0:
        score += 2
        reasons.append("MACD إيجابي والزخم صاعد.")
    elif current_macd < macd_signal and macd_hist < 0:
        score -= 2
        reasons.append("MACD سلبي والزخم هابط.")
    else:
        reasons.append("MACD غير حاسم.")

    if volume_ok:
        reasons.append("حجم التداول أعلى من متوسط 20 شمعة.")
    else:
        reasons.append("حجم التداول ليس أعلى من متوسطه.")

    if score >= 5:
        signal = "BUY"
    elif score <= -5:
        signal = "SELL"
    else:
        signal = "HOLD"

    confidence = min(95, 50 + abs(score) * 7)

    return {
        "price": price,
        "ema20": ema20,
        "ema50": ema50,
        "ema200": ema200,
        "rsi": current_rsi,
        "atr": current_atr,
        "macd": current_macd,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
        "support": support,
        "resistance": resistance,
        "score": score,
        "signal": signal,
        "confidence": confidence,
        "reasons": reasons,
    }


# ============================================================
# الأخبار - اختيارية عبر NewsAPI
# ============================================================

def get_news():
    if not NEWS_API_KEY:
        return {
            "status": "OFF",
            "headline": "خدمة الأخبار غير مفعلة؛ أضف NEWS_API_KEY.",
        }

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": "Bitcoin OR cryptocurrency OR crypto",
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 5,
        "apiKey": NEWS_API_KEY,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()

        data = response.json()
        articles = data.get("articles", [])

        if not articles:
            return {
                "status": "OK",
                "headline": "لا توجد أخبار حديثة.",
            }

        titles = []
        for article in articles[:3]:
            title = article.get("title")
            if title:
                titles.append(title)

        return {
            "status": "OK",
            "headline": "\n".join(f"• {x}" for x in titles),
        }

    except Exception as exc:
        logger.warning("News error: %s", exc)
        return {
            "status": "ERROR",
            "headline": "تعذر جلب الأخبار حاليًا.",
        }


# ============================================================
# إدارة المخاطر
# ============================================================

def calculate_trade_levels(analysis):
    entry = analysis["price"]
    current_atr = analysis["atr"]
    signal = analysis["signal"]

    if signal not in ("BUY", "SELL"):
        return None

    # SL = 1.5 ATR / TP = 3 ATR => R:R = 1:2
    stop_distance = current_atr * 1.5
    take_distance = current_atr * 3.0

    if signal == "BUY":
        stop_loss = entry - stop_distance
        take_profit = entry + take_distance
    else:
        stop_loss = entry + stop_distance
        take_profit = entry - take_distance

    risk_amount = portfolio["usd"] * RISK_PER_TRADE
    position_size = risk_amount / stop_distance if stop_distance > 0 else 0

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "risk_amount": risk_amount,
        "position_size": position_size,
        "risk_reward": 2.0,
    }


def risk_allows_trade():
    start = portfolio["daily_start_balance"]
    current = portfolio["usd"]

    if start <= 0:
        return False, "رصيد البداية غير صالح."

    daily_loss = max(0.0, (start - current) / start)

    if daily_loss >= MAX_DAILY_LOSS:
        return False, "تم إيقاف التداول اليومي بسبب تجاوز حد الخسارة."

    if portfolio["consecutive_losses"] >= 3:
        return False, "تم إيقاف التداول مؤقتًا بعد 3 خسائر متتالية."

    return True, "OK"


# ============================================================
# تنفيذ Paper Trade فقط
# ============================================================

def execute_simulated_trade(analysis):
    allowed, reason = risk_allows_trade()

    if not allowed:
        return False, reason

    if analysis["signal"] == "HOLD":
        return False, "لا توجد إشارة قوية. القرار الصحيح هو HOLD."

    trade = calculate_trade_levels(analysis)

    if not trade:
        return False, "تعذر حساب مستويات الصفقة."

    # لا يتم تغيير المحفظة هنا لأن الصفقة تحتاج متابعة مستقبلية
    # وهذا الإصدار يستخدم Paper Trading بدون تنفيذ حقيقي.
    return True, trade


# ============================================================
# تنسيق التحليل
# ============================================================

def format_analysis(analysis, news):
    trade = calculate_trade_levels(analysis)

    text = (
        "🤖 تحليل تداول متعدد العوامل\n\n"
        f"🪙 BTCUSDT\n"
        f"💵 السعر: {analysis['price']:.2f} $\n\n"
        f"📈 الإشارة: {analysis['signal']}\n"
        f"🧠 الثقة: {analysis['confidence']:.0f}%\n"
        f"📊 Score: {analysis['score']}\n\n"
        f"📐 EMA20: {analysis['ema20']:.2f}\n"
        f"📐 EMA50: {analysis['ema50']:.2f}\n"
        f"📐 EMA200: {analysis['ema200']:.2f}\n"
        f"📊 RSI: {analysis['rsi']:.2f}\n"
        f"📉 MACD: {analysis['macd']:.4f}\n"
        f"📏 ATR: {analysis['atr']:.2f}\n\n"
        f"🟢 الدعم: {analysis['support']:.2f}\n"
        f"🔴 المقاومة: {analysis['resistance']:.2f}\n\n"
    )

    if trade:
        text += (
            "🛡 إدارة المخاطر\n"
            f"Entry: {trade['entry']:.2f}\n"
            f"Stop Loss: {trade['stop_loss']:.2f}\n"
            f"Take Profit: {trade['take_profit']:.2f}\n"
            f"Risk/Reward: 1:{trade['risk_reward']:.1f}\n"
            f"Risk: {trade['risk_amount']:.2f} $\n"
            f"Position Size: {trade['position_size']:.6f}\n\n"
        )
    else:
        text += "🛡 إدارة المخاطر: لا توجد صفقة؛ HOLD.\n\n"

    text += "🔎 أسباب القرار:\n"
    text += "\n".join(f"• {x}" for x in analysis["reasons"])

    text += (
        "\n\n📰 الأخبار:\n"
        f"{news['headline']}\n\n"
        "⚠️ النظام للتحليل وPaper Trading فقط، "
        "ولا يضمن الربح."
    )

    return text


# ============================================================
# Telegram
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📊 التحليل والتوقع"],
        ["💰 المحفظة", "🚀 تنفيذ صفقة محاكاة"],
        ["📰 الأخبار", "ℹ️ المساعدة"],
    ]

    await update.message.reply_text(
        "أهلاً بك في بوت التداول 🤖\n\n"
        "البوت الآن يعمل بتحليل فني + إدارة مخاطر + "
        "انضباط + متابعة أخبار اختيارية.\n\n"
        "⚠️ التداول الحقيقي غير مفعل.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
        ),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "الأوامر:\n\n"
        "/start - تشغيل القائمة\n"
        "/analyze - تحليل BTCUSDT\n"
        "/news - آخر الأخبار\n"
        "/portfolio - المحفظة التجريبية\n\n"
        "أو استخدم الأزرار."
    )


async def send_analysis(update: Update):
    try:
        candles = get_market_data("BTCUSDT", "1h", 250)
        analysis = technical_analysis(candles)
        news = get_news()

        await update.message.reply_text(
            format_analysis(analysis, news)
        )

    except requests.RequestException:
        await update.message.reply_text(
            "❌ تعذر الاتصال ببيانات السوق الآن. حاول لاحقًا."
        )
    except Exception as exc:
        logger.exception("Analysis error")
        await update.message.reply_text(
            f"❌ خطأ في التحليل: {exc}"
        )


async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري تحليل السوق...")
    await send_analysis(update)


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    news = get_news()
    await update.message.reply_text(
        f"📰 متابعة الأخبار:\n\n{news['headline']}"
    )


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        candles = get_market_data("BTCUSDT", "1h", 2)
        price = candles[-1]["close"]
    except Exception:
        price = 0.0

    total = portfolio["usd"] + portfolio["btc"] * price

    await update.message.reply_text(
        "💰 Paper Trading\n\n"
        f"💵 USD: {portfolio['usd']:.2f} $\n"
        f"🪙 BTC: {portfolio['btc']:.6f}\n"
        f"📊 BTC Price: {price:.2f} $\n"
        f"💎 Total: {total:.2f} $\n"
        f"📉 Consecutive Losses: {portfolio['consecutive_losses']}"
    )


async def simulated_trade_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ جاري فحص شروط الصفقة وإدارة المخاطر...")

    try:
        candles = get_market_data("BTCUSDT", "1h", 250)
        analysis = technical_analysis(candles)
        allowed, result = execute_simulated_trade(analysis)

        if not allowed:
            await update.message.reply_text(
                f"🛑 لا توجد صفقة.\n\n{result}"
            )
            return

        trade = result

        await update.message.reply_text(
            "🧪 Paper Trade فقط\n\n"
            f"📌 الاتجاه: {analysis['signal']}\n"
            f"💵 Entry: {trade['entry']:.2f}\n"
            f"🛑 Stop Loss: {trade['stop_loss']:.2f}\n"
            f"🎯 Take Profit: {trade['take_profit']:.2f}\n"
            f"💰 Risk: {trade['risk_amount']:.2f} $\n"
            f"📦 Position Size: {trade['position_size']:.6f}\n"
            f"⚖️ Risk/Reward: 1:{trade['risk_reward']:.1f}\n\n"
            "لم يتم إرسال أي أمر إلى منصة تداول حقيقية."
        )

    except Exception as exc:
        logger.exception("Paper trade error")
        await update.message.reply_text(
            f"❌ تعذر تنفيذ المحاكاة: {exc}"
        )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == "📊 التحليل والتوقع":
        await update.message.reply_text("⏳ جاري التحليل...")
        await send_analysis(update)

    elif text == "💰 المحفظة":
        await portfolio_command(update, context)

    elif text == "🚀 تنفيذ صفقة محاكاة":
        await simulated_trade_command(update, context)

    elif text == "📰 الأخبار":
        await news_command(update, context)

    elif text == "ℹ️ المساعدة":
        await help_command(update, context)

    else:
        await update.message.reply_text(
            "استخدم /start لإظهار القائمة."
        )


# ============================================================
# التشغيل
# ============================================================

def main():
    if not TOKEN:
        raise RuntimeError(
            "لم يتم العثور على TELEGRAM_BOT_TOKEN. "
            "أضفه في Environment Variables."
        )

    # تشغيل خادم الويب في Thread منفصل
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )
    application.add_handler(
        CommandHandler("help", help_command)
    )
    application.add_handler(
        CommandHandler("analyze", analyze_command)
    )
    application.add_handler(
        CommandHandler("news", news_command)
    )
    application.add_handler(
        CommandHandler("portfolio", portfolio_command)
    )
    application.add_handler(
        CommandHandler("trade", simulated_trade_command)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Trading Telegram bot started.")
    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()



