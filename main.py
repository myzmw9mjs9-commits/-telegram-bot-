import nest_asyncio
import ccxt
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

nest_asyncio.apply()

TELEGRAM_TOKEN = "8811018278:AAGoRYuDg8L_FqSne62PKPpksx-LMbXyn0I"

usdt_balance = 1000.0
btc_balance = 0.0
buy_price = 0.0
exchange = ccxt.kraken()

def analyze_market():
    try:
        ohlcv = exchange.fetch_ohlcv('BTC/USD', timeframe='1m', limit=150)
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        
        df['returns'] = df['close'].pct_change()
        df['ma_5'] = df['close'].rolling(5).mean()
        df['ma_20'] = df['close'].rolling(20).mean()

        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))

        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26

        df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
        df.dropna(inplace=True)

        features = ['returns', 'ma_5', 'ma_20', 'rsi', 'macd']
        X = df[features]
        y = df['target']

        model = RandomForestClassifier(n_estimators=100, random_state=42)
        model.fit(X[:-1], y[:-1])

        pred = model.predict(X.tail(1))[0]
        last_price = df['close'].iloc[-1]
        last_rsi = df['rsi'].iloc[-1]
        last_macd = df['macd'].iloc[-1]

        return pred, last_price, last_rsi, last_macd
    except Exception as e:
        print(f"خطأ في التحليل: {e}")
        return 0, 60000.0, 50.0, 0.0

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['📊 التحليل والتوقع', '💰 المحفظة'], ['🚀 تنفيذ صفقة محاكاة']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("🤖 أهلاً بك في النسخة المطورة من بوت التداول الذكي!\nاختر خياراً من الأزرار:", reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global usdt_balance, btc_balance, buy_price
    text = update.message.text

    if text == '📊 التحليل والتوقع':
        pred, price, rsi, macd = analyze_market()
        signal = "📈 صاعد (فرصة شراء)" if pred == 1 else "📉 هابط أو محايد (انتظار/بيع)"
        
        msg = (
            f"💵 **سعر البيتكوين:** {price:.2f} $\n"
            f"📊 **مؤشر RSI:** {rsi:.1f}\n"
            f"📉 **مؤشر MACD:** {macd:.2f}\n"
            f"🤖 **توقع الذكاء الاصطناعي:** {signal}"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == '💰 المحفظة':
        total_val = usdt_balance + (btc_balance * analyze_market()[1])
        msg = (
            f"💵 **رصيد الدولار:** {usdt_balance:.2f} $\n"
            f"🪙 **رصيد البيتكوين:** {btc_balance:.6f} BTC\n"
            f"💎 **إجمالي قيمة المحفظة:** {total_val:.2f} $"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif text == '🚀 تنفيذ صفقة محاكاة':
        await update.message.reply_text("⏳ جاري تحليل المؤشرات المتقدمة وسعر السوق...")
        pred, price, rsi, macd = analyze_market()

        if btc_balance > 0:
            change_pct = ((price - buy_price) / buy_price) * 100
            if change_pct >= 3.0:
                gained = btc_balance * price
                usdt_balance += gained
                btc_balance = 0.0
                await update.message.reply_text(f"🎯 **[جني أرباح Take-Profit]**: ارتفع السعر بـ {change_pct:.2f}%! تم البيع عند {price:.2f} $ وحصولك على {gained:.2f} $")
                return
            elif change_pct <= -1.5:
                gained = btc_balance * price
                usdt_balance += gained
                btc_balance = 0.0
                await update.message.reply_text(f"🛑 **[وقف خسارة Stop-Loss]**: انخفض السعر بـ {change_pct:.2f}%! تم البيع حماية لمحفظتك عند {price:.2f} $")
                return

        if pred == 1 and rsi < 70 and usdt_balance >= 100:
            btc_bought = 100 / price
            usdt_balance -= 100
            btc_balance += btc_bought
            buy_price = price
            await update.message.reply_text(f"🟢 **[صفقة شراء]**: تم شراء {btc_bought:.6f} BTC بسعر {price:.2f} $\nمؤشر RSI: {rsi:.1f}")

        elif (pred == 0 or rsi > 70) and btc_balance > 0:
            gained = btc_balance * price
            usdt_balance += gained
            btc_balance = 0.0
            await update.message.reply_text(f"🔴 **[صفقة بيع]**: تم بيع البيتكوين بسعر {price:.2f} $، الرصيد المسترد: {gained:.2f} $")
        else:
            await update.message.reply_text(f"ℹ️ **تنبيه:** النظام يفضل الانتظار لعدم توفر فرصة قوية. السعر: {price:.2f} $ (RSI: {rsi:.1f})")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("⚡ البوت يعمل الآن!")
    app.run_polling(poll_interval=1.0, drop_pending_updates=True)
