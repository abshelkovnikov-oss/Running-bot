import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.DEBUG  # Включаем DEBUG для детального логирования
)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# Состояние для ConversationHandler
TEST_STATE = 1

# ==================== ФУНКЦИИ ====================

async def test_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /test - показывает кнопку"""
    logging.info("🔵 test_start вызван")
    
    keyboard = [
        [InlineKeyboardButton("✅ Тестовая кнопка", callback_data="test_button")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🧪 **Нажмите на кнопку для теста:**",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    logging.info("🟢 Кнопка отправлена, возвращаем TEST_STATE")
    return TEST_STATE

async def test_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия на кнопку"""
    query = update.callback_query
    logging.info(f"🟢 Получен callback: {query.data}")
    
    # ОБЯЗАТЕЛЬНО: отвечаем на callback
    await query.answer()
    
    # Редактируем сообщение
    await query.edit_message_text("✅ **Кнопка работает!**\n\nCallback-обработчик успешно принял запрос.", parse_mode="Markdown")
    
    logging.info("✅ Callback обработан")
    return ConversationHandler.END

async def test_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена теста"""
    await update.message.reply_text("❌ Тест отменен.")
    context.user_data.clear()
    return ConversationHandler.END

# ==================== СОЗДАНИЕ ОБРАБОТЧИКОВ ====================

# Создаем ConversationHandler для теста
test_conv = ConversationHandler(
    entry_points=[CommandHandler("test", test_start)],
    states={
        TEST_STATE: [
            CallbackQueryHandler(test_callback_handler),
        ],
    },
    fallbacks=[CommandHandler("cancel", test_cancel)],
)
# ==================== ЗАПУСК ====================

if __name__ == '__main__':
    print("🚀 Запуск тестового бота...")
    print(f"📝 Токен: {BOT_TOKEN[:10]}..." if BOT_TOKEN else "❌ Токен не найден!")
    
    if not BOT_TOKEN:
        print("❌ ОШИБКА: BOT_TOKEN не задан!")
        exit(1)
    
    # Создаем приложение
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Добавляем обработчик
    app.add_handler(test_conv)
    
    # Добавляем команду /start
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Привет! Используй /test для проверки callback-кнопок."
        )
    app.add_handler(CommandHandler("start", start))
    
    print("✅ Бот запущен! Напишите /test в чате.")
    print("📊 Логи будут показывать, что происходит...")
    
    # Запускаем бота
    app.run_polling()
