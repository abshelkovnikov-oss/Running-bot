import os
import logging
import pandas as pd
import psycopg2
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "123456789").split(",")]
EXCEL_FILE = "data.xlsx"

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ ---
def init_db():
    if not DATABASE_URL:
        return
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id SERIAL PRIMARY KEY,
                city TEXT,
                race_name TEXT,
                race_date DATE,
                distance FLOAT,
                participant_name TEXT
            );
        """)
        cur.execute("SELECT COUNT(*) FROM races")
        if cur.fetchone()[0] == 0 and os.path.exists(EXCEL_FILE):
            df = pd.read_excel(EXCEL_FILE)
            for _, row in df.iterrows():
                cur.execute(
                    "INSERT INTO races (city, race_name, race_date, distance, participant_name) VALUES (%s, %s, %s, %s, %s)",
                    (row['Город'], row['Название'], row['Дата'], row['Дистанция'], row['ФИО'])
                )
            conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка БД: {e}")

# --- ОБРАБОТКА СПИСКА С ФИЛЬТРОМ ---

async def list_races(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = "SELECT city, race_name, race_date, distance, participant_name FROM races"
    params = []
    header = "🏃 **Предстоящие забеги:**\n\n"

    # Логика фильтрации
    if context.args:
        arg = context.args[0].lower()
        if arg == "все":
            header = "🏃 **Весь список забегов:**\n\n"
            query += " ORDER BY race_date ASC"
        elif arg.isdigit() and len(arg) == 4:
            header = f"🏃 **Забеги за {arg} год:**\n\n"
            query += " WHERE EXTRACT(YEAR FROM race_date) = %s ORDER BY race_date ASC"
            params.append(int(arg))
        else:
            await update.message.reply_text("Неверный формат. Используйте: `/list`, `/list все` или `/list 2025`")
            return
    else:
        # По умолчанию — только будущие
        query += " WHERE race_date >= CURRENT_DATE ORDER BY race_date ASC"

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            await update.message.reply_text("По вашему запросу забегов не найдено.")
            return

        messages = []
        current_msg = header

        for r in rows:
            date_str = r[2].strftime('%d.%m.%Y')
            race_info = f"👤 *{r[4]}*\n📍 {r[0]} | {r[1]}\n🗓 {date_str} | 🏁 {r[3]} км\n\n"
            
            if len(current_msg) + len(race_info) > 4000:
                messages.append(current_msg)
                current_msg = race_info
            else:
                current_msg += race_info
        
        messages.append(current_msg)

        for msg in messages:
            await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await update.message.reply_text("Ошибка при получении данных.")

async def add_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        # Формат: /add Город Название ГГГГ-ММ-ДД Дистанция ФИО
        args = context.args
        city, name, r_date, dist = args[0], args[1], args[2], float(args[3])
        fio = " ".join(args[4:]) # Берем всё остальное как ФИО

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO races (city, race_name, race_date, distance, participant_name) VALUES (%s, %s, %s, %s, %s)",
            (city, name, r_date, dist, fio)
        )
        conn.commit()
        cur.close()
        conn.close()
        await update.message.reply_text(f"✅ Забег добавлен!")
    except:
        await update.message.reply_text("Ошибка! Формат: `/add Москва Марафон 2025-05-20 42.2 Иван Иванов`", parse_mode="Markdown")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Используйте:\n/list — только будущие\n/list все — все записи\n/list 2024 — за год"
    )

if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_races))
    app.add_handler(CommandHandler("add", add_race))
    app.run_polling()
