# معالج لكل الرسائل النصية (غير الأوامر)
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    # هنا تحدد ردود مختلفة حسب النص المرسل
    if message.text == "المحفظة":
        bot.reply_to(message, "💰 محفظتك الحالية: 1000 دولار (رصيد تجريبي)")
    elif message.text == "التحليل والتوقع":
        bot.reply_to(message, "📊 الاتجاه الحالي: صاعد. توقع السعر خلال ساعة: +2.5%")
    elif message.text == "تنفيذ صفقة محاكاة":
        bot.reply_to(message, "✅ تم تنفيذ صفقة شراء وهمية بقيمة 100 دولار")
    else:
        # أي كلمة أخرى
        bot.reply_to(message, f"أرسلت: {message.text}\nاستخدم الأزرار الموجودة أو اكتب /start")