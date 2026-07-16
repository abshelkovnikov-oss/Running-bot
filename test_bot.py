import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ---------------- ЛОГИ ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.DEBUG,  # важно для отладки
)

# ---------------- КОМАНДЫ ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Нажми меня", callback_data="test_button")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Бот запущен ✅\nНажми кнопку ниже:",
        reply_markup=reply_markup,
    )


async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Команда /test получена")


# ---------------- CALLBACK ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        text=f"✅ Нажата кнопка: {query.data}"
    )


# ---------------- DEBUG ВСЕГО ----------------

async def debug_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("\n🔥 ===== ПРИШЛО ОБНОВЛЕНИЕ =====")
    print(update)
    print("================================\n")


# ---------------- ЗАПУСК ----------------

def main():
    TOKEN = "ВСТАВЬ_СВОЙ_ТОКЕН_СЮДА"

    app = ApplicationBuilder().token(TOKEN).build()

    # ВАЖНО: debug ставим первым
    app.add_handler(MessageHandler(filters.ALL, debug_all), group=0)
    app.add_handler(CallbackQueryHandler(debug_all), group=0)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("✅ Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
