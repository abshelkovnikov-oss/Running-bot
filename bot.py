import os
import logging
import psycopg2
from datetime import datetime  # Добавьте эту строку
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ConversationHandler, 
    ContextTypes
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "0").split(",")]

# --- КОМАНДА /list С ФИЛЬТРОМ ПО МЕСЯЦУ ---
async def list_races(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = "SELECT city, race_name, race_date, distance, participant_name FROM races"
    params = []
    header = "🏃 **Список забегов:**\n\n"

    if context.args:
        arg = context.args[0].lower()
        
        # Проверка формата ММ.ГГГГ (например, 05.2026)
        if "." in arg and len(arg) == 7:
            try:
                month, year = arg.split(".")
                query += " WHERE EXTRACT(MONTH FROM race_date) = %s AND EXTRACT(YEAR FROM race_date) = %s"
                params.extend([int(month), int(year)])
                header = f"📅 **Забеги за {month}.{year}:**\n\n"
            except ValueError:
                await update.message.reply_text("Ошибка формата. Используйте ММ.ГГГГ (например: 05.2026)")
                return
        elif arg == "все":
            header = "🏃 **Все забеги за всё время:**\n\n"
        elif arg.isdigit() and len(arg) == 4:
            query += " WHERE EXTRACT(YEAR FROM race_date) = %s"
            params.append(int(arg))
            header = f"📅 **Забеги за {arg} год:**\n\n"
    else:
        # По умолчанию — только будущие
        query += " WHERE race_date >= CURRENT_DATE"
        header = "🏃 **Предстоящие забеги:**\n\n"

    query += " ORDER BY race_date ASC"

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            await update.message.reply_text("Записей не найдено.")
            return

        messages = []
        current_msg = header
        for r in rows:
            date_str = r[2].strftime('%d.%m.%Y')
            info = f"👤 *{r[4]}*\n📍 {r[0]} | {r[1]}\n🗓 {date_str} | 🏁 {r[3]} км\n\n"
            
            if len(current_msg) + len(info) > 4000:
                messages.append(current_msg)
                current_msg = info
            else:
                current_msg += info
        
        messages.append(current_msg)
        for msg in messages:
            await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logging.error(e)
        await update.message.reply_text("Ошибка при чтении базы.")

# --- НОВАЯ КОМАНДА /stats (РЕЙТИНГ УЧАСТНИКОВ) ---
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Группируем по ФИО, суммируем дистанцию и сортируем
        cur.execute("""
            SELECT participant_name, SUM(distance) as total_km 
            FROM races 
            GROUP BY participant_name 
            ORDER BY total_km DESC
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            await update.message.reply_text("Данных для статистики пока нет.")
            return

        text = "🏆 **Рейтинг участников по километрам:**\n\n"
        for i, row in enumerate(rows, 1):
            name = row[0]
            dist = row[1]
            text += f"{i}. *{name}* — {dist:.2f} км\n"

        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("Ошибка при расчете статистики.")
START_DATE, END_DATE = range(2)

# --- НАЧАЛО ДИАЛОГА /total ---
async def total_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите дату начала периода в формате ДД.ММ.ГГГГ (например, 01.01.2024):")
    return START_DATE

# --- ПОЛУЧАЕМ ДАТУ НАЧАЛА ---
async def get_start_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date_text = update.message.text
        # Проверяем корректность даты
        start_dt = datetime.strptime(date_text, '%d.%m.%Y').date()
        context.user_data['start_period'] = start_dt
        await update.message.reply_text(f"Принято: {start_dt}. Теперь введите дату окончания (ДД.ММ.ГГГГ):")
        return END_DATE
    except ValueError:
        await update.message.reply_text("Неверный формат! Введите дату как ДД.ММ.ГГГГ")
        return START_DATE

# --- ПОЛУЧАЕМ ДАТУ ОКОНЧАНИЯ И СЧИТАЕМ ---
async def get_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date_text = update.message.text
        end_dt = datetime.strptime(date_text, '%d.%m.%Y').date()
        start_dt = context.user_data['start_period']

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # 1. Считаем сумму за период
        cur.execute(
            "SELECT SUM(distance) FROM races WHERE race_date >= %s AND race_date <= %s",
            (start_dt, end_dt)
        )
        period_sum = cur.fetchone()[0] or 0

        # 2. Считаем общую сумму всего
        cur.execute("SELECT SUM(distance) FROM races")
        total_sum = cur.fetchone()[0] or 0

        cur.close()
        conn.close()

        await update.message.reply_text(
            f"📊 **Итоги:**\n\n"
            f"🔹 За период с {start_dt.strftime('%d.%m.%Y')} по {end_dt.strftime('%d.%m.%Y')}\n"
            f"🏃 Пробежали: **{period_sum:.2f} км**\n\n"
            f"🌍 Всего за всё время: **{total_sum:.2f} км**",
            parse_mode="Markdown"
        )
        
        context.user_data.clear() # Очищаем данные
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text("Неверный формат! Введите дату как ДД.ММ.ГГГГ")
        return END_DATE

# Функция отмены
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Расчет отменен.")
    return ConversationHandler.END


# --- СТАНДАРТНЫЙ ЗАПУСК ---
if __name__ == '__main__':
    # init_db() — функция должна быть определена выше (как в прошлых ответах)
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    total_conv = ConversationHandler(
        entry_points=[CommandHandler('total', total_start)],
        states={
            START_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_start_date)],
            END_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_end_date)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    app.add_handler(total_conv)
    app.add_handler(CommandHandler("list", list_races))
    app.add_handler(CommandHandler("stats", stats))
    # Добавь сюда остальные хендлеры (start, add_race)

    app.run_polling()
