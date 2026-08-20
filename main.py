# إما أن تحذف السطر 9 الذي ينادي should_buy(current_rsi, ...)
# أو تقوم بتعريف المتغيرات قبل استدعاء الدالة بهذا الشكل:

current_rsi = 30.0
current_price = 65000.0
current_ema = 60000.0

def should_buy(rsi_value, current_price, ema_200):
    if rsi_value < 35 and current_price > ema_200:
        return True
    return False

# الآن لن يظهر الخطأ عند التشغيل
if should_buy(current_rsi, current_price, current_ema):
    print("إشارة شراء قوية")
