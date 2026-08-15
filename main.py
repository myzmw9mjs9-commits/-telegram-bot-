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
# الإعدادات
# ============================================================

TOKEN = "8811018278:AAF36qLjzSNDz8qxcrk8SPkKerzycIpipv4"

STARTING_BALANCE = 1000.0
RISK_PER_TRADE = 0.01  # 1%
MAX_DAILY_LOSS = 0.03  # 3%
NEWS_API_KEY = ""

# ============================================================
# خادم ويب صغير لـ Render
# ============================================================

app_web = Flask(__name__)

@app_web.route("/")
def home():
    return "Trading bot is alive!"

def run_web():
    port = int(os.environ.get("PORT", "8080"))
    app_web.run(host="0.0.0.0", port=port, use_reloader=False)

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
    gains, losses = [], []
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
        tr = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(tr)
    return sum(true_ranges[-period:]) / period

def macd(values):
    if len(values) < 35:
        return None, None, None
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
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    response = requests.get(url, params=params, timeout=15)
    response.raise_for_status()
    raw = response.json()
    if not isinstance(raw, list) or len(raw) < 200:
        raise ValueError("بيانات السوق غير كافية.")
    candles = []
    for item in raw:
        candles.append({
            "open_time": item[0],
            "open": float(item[1]),
            "high": float(item[2]),
            "low": float(item[3]),
            "close": float(item[4]),
            "volume": float(item[5]),
        })
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

    recent = candles[-50:]
    support = min(x["low"] for x in recent)
    resistance = max(x["high"] for x in recent)
    average_volume = sma(volumes, 20)
    volume_ok = average_volume is not None and volumes[-1] > average_volume

    score = 0
    reasons = []

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

    if current_rsi < 30:
        score += 2
        reasons.append(f"RSI={current_rsi:.1f}: تشبع بيع.")
    elif current_rsi > 70:
        score -= 2
        reasons.append(f"RSI={current_rsi:.1f}: تشبع شراء.")
    else:
        reasons.append(f"RSI={current_rsi:.1f}: في منطقة غير متطرفة.")

    if current_macd > macd_signal and macd_hist > 0:
        score += 2
        reasons.append("MACD إيجابي والزخم صاعد.")
    elif current_macd < macd_signal and macd_hist < 0:
        score -= 2
        reasons.append("MACD سلبي والزخم هابط.")

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

def format_analysis(analysis):
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
        "🔎 أسباب القرار:\n"
    )
    text += "\n".join(f"• {x}" for x in analysis["reasons"])
    return text

# ============================================================
# Telegram Handlers
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["📊 التحليل والتوقع"],
        ["💰 المحفظة", "🚀 تنفيذ صفقة محاكاة"]
    ]
    await update.message.reply_text(
        "أهلاً بك في بوت التداول بالذكاء الاصطناعي! 🤖\nاختر خياراً من القائمة أدناه:",
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == "📊 التحليل والتوقع":
        await update.message.reply_text("⏳ جاري تحليل السوق مع Binance...")
        try:
            candles = get_market_data("BTCUSDT", "1h", 250)
            analysis = technical_analysis(candles)
            await update.message.reply_text(format_analysis(analysis))
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في جلب البيانات: {e}")

    elif text == "💰 المحفظة":
        try:
            candles = get_market_data("BTCUSDT", "1h", 2)
            price = candles[-1]["close"]
        except Exception:
            price = 0.0
        total = portfolio["usd"] + (portfolio["btc"] * price)
        msg = (
            f"💵 رصيد الدولار: {portfolio['usd']:.2f} $\n"
            f"🪙 رصيد البيتكوين: {portfolio['btc']:.6f} BTC\n"
            f"💎 إجمالي قيمة المحفظة: {total:.2f} $"
        )
        await update.message.reply_text(msg)

    elif text == "🚀 تنفيذ صفقة محاكاة":
        await update.message.reply_text("⏳ جاري فحص فرصة التداول...")
        try:
            candles = get_market_data("BTCUSDT", "1h", 250)
            analysis = technical_analysis(candles)
            await update.message.reply_text(f"🎯 قرار المحاكاة الحالي: {analysis['signal']} (مستوى الثقة {analysis['confidence']}%)")
        except Exception as e:
            await update.message.reply_text("❌ تعذر تنفيذ الصفقة التجريبية.")

if __name__ == "__main__":
    Thread(target=run_web, daemon=True).start()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
