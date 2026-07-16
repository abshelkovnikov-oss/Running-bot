from telegram.ext import MessageHandler, CallbackQueryHandler, filters

# Универсальный обработчик
async def debug_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("\n🔥 ===== ПРИШЛО ОБНОВЛЕНИЕ =====")
    print(update)
    print("================================\n")

    # Если это кнопка — обязательно отвечаем
    if update.callback_query:
        await update.callback_query.answer()
        print("✅ Это callback_query:", update.callback_query.data)

    # Если это сообщение
    if update.message:
        print("✅ Это сообщение:", update.message.text)


# Добавляем САМЫМ ПЕРВЫМ
app.add_handler(MessageHandler(filters.ALL, debug_all), group=0)
app.add_handler(CallbackQueryHandler(debug_all), group=0)
