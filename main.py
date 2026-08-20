# مثال لتشريط الشراء الفائق:
def should_buy(rsi_value, current_price, ema_200):
    # شرط القوة: RSI رخيص + الاتجاه العام صاعد
    if rsi_value < 35 and current_price > ema_200:
        return True # إشارة دخول قوية جداً
    return False

# داخل دالة التداول:
if should_buy(current_rsi, current_price, current_ema):
    # تنفيذ الصفقة
    execute_trade()
else:
    # عدم مخاطرة البوت والانتظار
    print("السوق غير آمن حالياً، تم إلغاء الصفقة لحماية المحفظة.")
