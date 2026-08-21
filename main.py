def check_order_block(klines):
    # klines: أحدث الشموع من Binance (فريم 15m)
    closes = [float(k[4]) for k in klines]
    opens = [float(k[1]) for k in klines]
    lows = [float(k[3]) for k in klines]
    highs = [float(k[2]) for k in klines]
    
    # الشمعة الشارحة للانفجار (الشمعة قبل الأخيرة -2)
    # والبحث عن الشمعة الحمراء الأخيرة قبل الانفجار (-3)
    is_explosion = (closes[-2] - opens[-2]) / opens[-2] > 0.015  # صعود بأكثر من 1.5%
    is_prev_red = closes[-3] < opens[-3]                          # الشمعة التي قبلها حمراء (OB)
    
    if is_explosion and is_prev_red:
        ob_top = highs[-3]    # أعلى سعر في منطقة الطلب
        ob_bottom = lows[-3]  # أقل سعر في منطقة الطلب (وقف الخسارة يكون تحته)
        return True, ob_top, ob_bottom
        
    return False, 0, 0
