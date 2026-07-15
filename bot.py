import os
import logging
import pandas as pd
import psycopg2
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# --- ЧТЕНИЕ НАСТРОЕК ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# На railway переменная обычно называется DATABASE_URL или DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DATABASE_URL")
# Твоя логика получения списка админов
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "123456789").split(",")]

EXCEL_FILE = "data.xlsx"

# --- ИНИЦИАЛИЗАЦИЯ БАЗЫ (СОЗДАНИЕ ТАБЛИЦЫ И ИМПОРТ) ---
def init_db():
    if not DATABASE_URL:
        logging.error("Переменная DATABASE_URL не установлена!")
        return

    try:
        # Подключаемся к PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()

        # Создаем таблицу, если она еще не создана
        cur.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id SERIAL PRIMARY KEY,
                city TEXT,
                race_name TEXT,
                race_date DATE,
                distance FLOAT
            );
        """)

        # Проверяем, есть ли уже данные
        cur.execute("SELECT COUNT(*) FROM races")
        if cur.fetchone()[0] == 0:
            if os.path.exists(EXCEL_FILE):
                logging.info("База пуста. Загружаю данные из Excel...")
                df = pd.read_excel(EXCEL_FILE)
                for _, row in df.iterrows():
                    cur.execute(
                        "INSERT INTO races (city, race_name, race_date, distance) VALUES (%s, %s, %s, %s)",
                        (row['Город'], row['Название'], row['Дата'], row['Дистанция'])
                    )
                conn.commit()
                logging.info(f"Загружено {len(df)} записей.")
            else:
                logging.warning("Файл Excel не найден. База осталась пустой.")
        
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка БД при старте: {e}")

# --- КОМАНДЫ БОТА ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для учета забегов.\n\n"
        "Команды:\n"
        "/list — список всех забегов\n"
        "/add — добавить забег (только для админов)"
    )

async def list_races(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT city, race_name, race_date, distance FROM races ORDER BY race_date ASC")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if not rows:
            await update.message.reply_text("Забегов пока нет.")
            return

        msg = "🏃 **Список забегов:**\n\n"
        for r in rows:
            date_str = r[2].strftime('%d.%m.%Y')
            msg += f"📍 {r[0]} — *{r[1]}*\n🗓 {date_str} | {r[3]} км\n\n"
        
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"Ошибка при чтении: {e}")

async def add_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверка на админа
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав администратора.")
        return

    try:
        # Формат: /add Москва Марафон 2024-05-20 10.5
        args = context.args
        city, name, r_date, dist = args[0], args[1], args[2], float(args[3])

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO races (city, race_name, race_date, distance) VALUES (%s, %s, %s, %s)",
            (city, name, r_date, dist)
        )
        conn.commit()
        cur.close()
        conn.close()

        await update.message.reply_text(f"✅ Забег '{name}' добавлен!")
    except Exception:
        await update.message.reply_text("Ошибка! Используйте: /add Город Название ГГГГ-ММ-ДД Дистанция")

# --- ЗАПУСК ---
if __name__ == '__main__':
    # 1. Сначала готовим базу данных
    init_db()

    # 2. Запускаем бота
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_races))
    app.add_handler(CommandHandler("add", add_race))

    logging.info("Бот запущен и готов к работе!")
    app.run_polling()
