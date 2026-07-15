import os
import pandas as pd
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

CITIES_EXCEL = "cities.xlsx"

# --- ИНИЦИАЛИЗАЦИЯ ТАБЛИЦЫ ГОРОДОВ ---
def init_cities_db():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS city_distances (
                id SERIAL PRIMARY KEY,
                city_name TEXT,
                distance_from_start FLOAT
            );
        """)
        
        # ИСПРАВЛЕНИЕ: берем [0], так как fetchone() возвращает кортеж типа (0,)
        cur.execute("SELECT COUNT(*) FROM city_distances")
        count_result = cur.fetchone()[0] 
        
        print(f"В таблице сейчас строк: {count_result}") # Для отладки

        if count_result == 0:
            if os.path.exists(CITIES_EXCEL):
                df = pd.read_excel(CITIES_EXCEL)
                for _, row in df.iterrows():
                    cur.execute(
                        "INSERT INTO city_distances (city_name, distance_from_start) VALUES (%s, %s)",
                        (row['Город'], row['Расстояние'])
                    )
                conn.commit()
                logging.info("Таблица городов успешно загружена.")
                print("Данные успешно загружены из Excel!")
            else:
                logging.warning(f"Файл {CITIES_EXCEL} не найден!")
        
        cur.close()
        conn.close()
    except Exception as e:
        logging.error(f"Ошибка при инициализации таблицы городов: {e}")


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

async def get_end_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = None
    cur = None
    try:
        # Парсим дату, которую ввел пользователь
        date_text = update.message.text
        end_dt = datetime.strptime(date_text, '%d.%m.%Y').date()
        start_dt = context.user_data.get('start_period')

        if not start_dt:
            await update.message.reply_text("Ошибка: не задана дата начала периода.")
            return ConversationHandler.END

        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
    
        # 1. Получаем общую сумму пробега за выбранный период
        cur.execute(
            "SELECT COALESCE(SUM(distance), 0) FROM races WHERE race_date >= %s AND race_date <= %s",
            (start_dt, end_dt)
        )
        total_dist = cur.fetchone()[0]
        
        # Если total_dist - Decimal, конвертируем в float
        if hasattr(total_dist, '__float__'):
            total_dist = float(total_dist)

        # 2. Ищем ближайший город (первый город, чья дистанция больше нашего пробега)
        cur.execute(
            "SELECT city_name, distance_from_start FROM city_distances WHERE distance_from_start > %s ORDER BY distance_from_start ASC LIMIT 1",
            (total_dist,)
        )
        next_city_data = cur.fetchone()

        # 3. Получаем дистанцию до Москвы
        cur.execute(
            "SELECT distance_from_start FROM city_distances WHERE city_name ILIKE 'москва' LIMIT 1"
        )
        moscow_data = cur.fetchone()
        moscow_dist = float(moscow_data[0]) if moscow_data else 0.0

        # Формируем сообщение
        response = f"Итоги периода с {start_dt.strftime('%d.%m.%Y')} по {end_dt.strftime('%d.%m.%Y')}:\n"
        response += f"🏁 Всего пройдено: {total_dist:.2f} км\n\n"

        if next_city_data:
            next_city_name, next_city_dist = next_city_data
            # Конвертируем Decimal в float если нужно
            if hasattr(next_city_dist, '__float__'):
                next_city_dist = float(next_city_dist)
            left_to_city = next_city_dist - total_dist
            response += f"📍 Следующий город: {next_city_name}\n"
            response += f"🛣️ До него осталось: {left_to_city:.2f} км\n"
        else:
            response += "🎉 Поздравляем! Вы достигли конечной точки!\n"

        if moscow_dist > 0:
            if total_dist < moscow_dist:
                left_to_moscow = moscow_dist - total_dist
                response += f"🏛️ До Москвы осталось: {left_to_moscow:.2f} км"
            else:
                response += "🇷🇺 Вы уже в Москве (или проехали её)!"
        
        await update.message.reply_text(response)
        return ConversationHandler.END
        
    except ValueError as e:
        logging.error(f"Ошибка парсинга даты: {e}")
        await update.message.reply_text("Пожалуйста, введите дату в формате ДД.ММ.ГГГГ")
        return ConversationHandler.END
        
    except psycopg2.Error as e:
        logging.error(f"Ошибка базы данных: {e}")
        await update.message.reply_text("Произошла ошибка при работе с базой данных.")
        return ConversationHandler.END
        
    except Exception as e:
        logging.error(f"Ошибка в функции расчет: {e}", exc_info=True)
        await update.message.reply_text("Произошла ошибка при расчете итогов.")
        return ConversationHandler.END
        
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# --- СТАНДАРТНЫЙ ЗАПУСК ---
if __name__ == '__main__':
    # init_db() — функция должна быть определена выше (как в прошлых ответах)
    # init_cities_db()
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
