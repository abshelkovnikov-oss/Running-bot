import os
import logging
import pandas as pd
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Настройки логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("TELEGRAM_TOKEN")  # Токен бота из настроек railway
DATABASE_URL = os.getenv("DATABASE_URL")  # URL базы данных из github
ADMIN_IDS = [12345678, 87654321]  # ЗАМЕНИ на свои ID (через запятую)
EXCEL_FILE = "data.xlsx"

# --- ФУНКЦИЯ ИНИЦИАЛИЗАЦИИ БАЗЫ ---
def init_and_load():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # 1. Создаем таблицу, если её нет
        cur.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id SERIAL PRIMARY KEY,
                city TEXT,
                race_name TEXT,
                race_date DATE,
                distance FLOAT
            );
        """)

        # 2. Проверяем, пустая ли таблица
        cur.execute("SELECT COUNT(*) FROM races")
        count = cur.fetchone()[0]

        if count == 0:
            logging.info("База пуста. Начинаю загрузку из Excel...")
            if os.path.exists(EXCEL_FILE):
                df = pd.read_excel(EXCEL_FILE)
                for _, row in df.iterrows():
                    cur.execute(
                        "INSERT INTO races (city, race_name, race_date, distance) VALUES (%s, %s, %s, %s)",
                        (row['Город'], row['Название'], row['Дата'], row['Дистанция'])
                    )
                conn.commit()
                logging.info(f"Загружено строк: {len(df)}")
            else:
                logging.warning(f"Файл {EXCEL_FILE} не найден. Пропускаю импорт.")
        else:
            logging.info("База уже содержит данные. Пропускаю импорт.")

        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка при инициализации БД: {e}")

# --- КОМАНДЫ БОТА ---

# Старт
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для управления забегами. Используй /list для просмотра.")

# Просмотр забегов
async def list_races(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT city, race_name, race_date, distance FROM races ORDER BY race_date ASC")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        await update.message.reply_text("В базе пока нет забегов.")
        return

    msg = "🏃 **Список забегов:**\n\n"
    for r in rows:
        msg += f"📍 {r[0]} | {r[1]} | 📅 {r[2]} | 🏁 {r[3]} км\n"
    
    await update.message.reply_text(msg, parse_mode="Markdown")

# Добавление нового забега админом
async def add_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав администратора.")
        return

    try:
        # Пример: /add Москва "Марафон" 2024-09-22 42.2
        data = context.args
        city = data[0]
        name = data[1]
        date = data[2]
        dist = float(data[3])

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO races (city, race_name, race_date, distance) VALUES (%s, %s, %s, %s)",
            (city, name, date, dist)
        )
        conn.commit()
        cur.close()
        conn.close()

        await update.message.reply_text(f"✅ Забег '{name}' успешно добавлен!")
    except Exception as e:
        await update.message.reply_text("Ошибка! Формат: /add Город Название ГГГГ-ММ-ДД Дистанция")

# --- ЗАПУСК ---
if __name__ == '__main__':
    # Сначала проверяем базу и загружаем данные
    init_and_load()

    # Запускаем бота
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_races))
    app.add_handler(CommandHandler("add", add_race))

    logging.info("Бот запущен...")
    app.run_polling()
