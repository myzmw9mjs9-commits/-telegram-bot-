# ============================================================
# جلب بيانات السوق (Binance + CoinGecko احتياطي)
# ============================================================
def get_btc_price():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    # المحاولة الأولى: Binance
    try:
        url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
        res = requests.get(url, headers=headers, timeout=5).json()
        if "price" in res:
            return float(res["price"])
    except Exception as e:
        logger.error(f"Binance error: {e}")

    # المحاولة الثانية (احتياطية): CoinGecko
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
        res = requests.get(url, headers=headers, timeout=5).json()
        return float(res["bitcoin"]["usd"])
    except Exception as e:
        logger.error(f"CoinGecko error: {e}")
        return None
