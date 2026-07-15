import os
import pandas as pd
import logging
import psycopg2
import calendar
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, 
    CommandHandler, 
    MessageHandler, 
    filters, 
    ConversationHandler, 
    CallbackQueryHandler,
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

DATE, NAME, CITY, RACE_NAME, DISTANCE = range(5)
START_DATE, END_DATE = range(2)

class CalendarButtons:
    """Класс для создания кнопок календаря"""
    
    @staticmethod
    def create_calendar(year: int, month: int, callback_prefix: str = "cal"):
        """Создает инлайн-клавиатуру с календарем"""
        # Заголовок с месяцем и годом
        month_names = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                      'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
        
        # Создаем календарь
        cal = calendar.monthcalendar(year, month)
        
        # Кнопки навигации
        keyboard = [
            [
                InlineKeyboardButton(
                    f"◀️ {month_names[month-1]} {year} ▶️",
                    callback_data=f"{callback_prefix}_none"
                )
            ],
            [
                InlineKeyboardButton("Пн", callback_data=f"{callback_prefix}_none"),
                InlineKeyboardButton("Вт", callback_data=f"{callback_prefix}_none"),
                InlineKeyboardButton("Ср", callback_data=f"{callback_prefix}_none"),
                InlineKeyboardButton("Чт", callback_data=f"{callback_prefix}_none"),
                InlineKeyboardButton("Пт", callback_data=f"{callback_prefix}_none"),
                InlineKeyboardButton("Сб", callback_data=f"{callback_prefix}_none"),
                InlineKeyboardButton("Вс", callback_data=f"{callback_prefix}_none"),
            ]
        ]
        
        # Добавляем дни месяца
        for week in cal:
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(" ", callback_data=f"{callback_prefix}_none"))
                else:
                    row.append(
                        InlineKeyboardButton(
                            str(day), 
                            callback_data=f"{callback_prefix}_{year}_{month}_{day}"
                        )
                    )
            keyboard.append(row)
        
        # Кнопки навигации по месяцам
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1
        
        keyboard.append([
            InlineKeyboardButton("◀️", callback_data=f"{callback_prefix}_{prev_year}_{prev_month}_nav"),
            InlineKeyboardButton("Сегодня", callback_data=f"{callback_prefix}_today"),
            InlineKeyboardButton("▶️", callback_data=f"{callback_prefix}_{next_year}_{next_month}_nav"),
        ])
        
        # Кнопка отмены
        keyboard.append([
            InlineKeyboardButton("❌ Отмена", callback_data=f"{callback_prefix}_cancel")
        ])
        
        return InlineKeyboardMarkup(keyboard)

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
            SELECT participant_name, ROUND(SUM(distance)) as total_km 
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
            name = row[0] if row[0] else "Неизвестный"
            dist = int(row[1]) if row[1] is not None else 0
            
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "
            else:
                medal = f"{i}. "
            
            line = f"{medal}*{name}* — {dist} км\n"
            
            if len(text) + len(line) > 4000:
                await update.message.reply_text(text, parse_mode="Markdown")
                text = "📊 **Продолжение рейтинга:**\n\n" + line
            else:
                text += line
        
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logging.error(e)
        await update.message.reply_text("Ошибка при расчете статистики.")


# --- НАЧАЛО ДИАЛОГА /total ---
async def total_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинаем диалог выбора периода"""
    # Получаем текущую дату
    now = datetime.now()
    year = now.year
    month = now.month
    
    # Создаем календарь для выбора даты начала
    keyboard = CalendarButtons.create_calendar(year, month, "start")
    
    await update.message.reply_text(
        "📅 **Выберите дату НАЧАЛА периода:**\n\n"
        "Нажмите на день в календаре.\n"
        "Используйте стрелки для переключения месяцев.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )
    return START_DATE

async def calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на календарь"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    parts = data.split('_')
    prefix = parts[0]  # 'start' или 'end'
    
    # Обработка отмены
    if data.endswith('_cancel'):
        await query.edit_message_text("❌ Выбор даты отменен.")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Обработка "Сегодня"
    if data.endswith('_today'):
        today = datetime.now().date()
        day = today.day
        month = today.month
        year = today.year
        
        # Имитируем выбор даты
        callback_data = f"{prefix}_{year}_{month}_{day}"
        return await process_date_selection(update, context, callback_data)
    
    # Обработка навигации по месяцам
    if data.endswith('_nav'):
        year = int(parts[1])
        month = int(parts[2])
        
        # Обновляем календарь
        keyboard = CalendarButtons.create_calendar(year, month, prefix)
        await query.edit_message_text(
            f"📅 **Выберите дату {'НАЧАЛА' if prefix == 'start' else 'ОКОНЧАНИЯ'} периода:**",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return
    
    # Обработка выбора дня
    if len(parts) == 4 and parts[1].isdigit() and parts[2].isdigit() and parts[3].isdigit():
        return await process_date_selection(update, context, data)
    
    # Если ничего не подошло
    await query.edit_message_text("❌ Неизвестная команда. Попробуйте еще раз.")
    return ConversationHandler.END

async def process_date_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, callback_data: str):
    """Обработка выбранной даты"""
    query = update.callback_query
    parts = callback_data.split('_')
    prefix = parts[0]
    year = int(parts[1])
    month = int(parts[2])
    day = int(parts[3])
    
    selected_date = datetime(year, month, day).date()
    date_str = selected_date.strftime('%d.%m.%Y')
    
    if prefix == 'start':
        # Сохраняем дату начала
        context.user_data['start_period'] = selected_date
        
        # Показываем подтверждение и переходим к выбору даты окончания
        await query.edit_message_text(
            f"✅ **Дата начала выбрана:** {date_str}\n\n"
            f"Теперь выберите дату **ОКОНЧАНИЯ** периода:",
            parse_mode="Markdown"
        )
        
        # Показываем календарь для выбора даты окончания
        now = datetime.now()
        keyboard = CalendarButtons.create_calendar(now.year, now.month, "end")
        
        await query.message.reply_text(
            "📅 **Выберите дату ОКОНЧАНИЯ периода:**",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        return END_DATE
        
    elif prefix == 'end':
        # Сохраняем дату окончания
        context.user_data['end_period'] = selected_date
        
        # Проверяем, что дата окончания не раньше даты начала
        start_date = context.user_data.get('start_period')
        if start_date and selected_date < start_date:
            await query.edit_message_text(
                f"❌ **Ошибка!**\n\n"
                f"Дата окончания ({date_str}) не может быть раньше даты начала ({start_date.strftime('%d.%m.%Y')}).\n\n"
                f"Пожалуйста, выберите дату окончания снова:",
                parse_mode="Markdown"
            )
            
            # Показываем календарь снова
            now = datetime.now()
            keyboard = CalendarButtons.create_calendar(now.year, now.month, "end")
            await query.message.reply_text(
                "📅 **Выберите дату ОКОНЧАНИЯ периода:**",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            return END_DATE
        
        # Все хорошо - считаем итоги
        await query.edit_message_text(
            f"✅ **Дата окончания выбрана:** {date_str}\n\n"
            f"⏳ Выполняется расчет...",
            parse_mode="Markdown"
        )
        
        # Вызываем функцию расчета
        return await calculate_total(update, context)

async def calculate_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Расчет итогов за период"""
    conn = None
    cur = None
    try:
        start_dt = context.user_data.get('start_period')
        end_dt = context.user_data.get('end_period')
        
        if not start_dt or not end_dt:
            await update.effective_message.reply_text("❌ Ошибка: не выбраны даты периода.")
            return ConversationHandler.END
        
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
    
        # 1. Получаем общую сумму пробега ЗА ВСЁ ВРЕМЯ
        cur.execute("SELECT COALESCE(SUM(distance), 0) FROM races")
        total_all_time = cur.fetchone()[0]
        if hasattr(total_all_time, '__float__'):
            total_all_time = float(total_all_time)

        # 2. Получаем сумму пробега ЗА ВЫБРАННЫЙ ПЕРИОД
        cur.execute(
            "SELECT COALESCE(SUM(distance), 0) FROM races WHERE race_date >= %s AND race_date <= %s",
            (start_dt, end_dt)
        )
        total_period = cur.fetchone()[0]
        if hasattr(total_period, '__float__'):
            total_period = float(total_period)

        # 3. Ищем ближайший город
        cur.execute(
            "SELECT city_name, distance_from_start FROM city_distances WHERE distance_from_start > %s ORDER BY distance_from_start ASC LIMIT 1",
            (total_all_time,)
        )
        next_city_data = cur.fetchone()

        # 4. Получаем дистанцию до Москвы
        cur.execute(
            "SELECT distance_from_start FROM city_distances WHERE city_name ILIKE 'москва' LIMIT 1"
        )
        moscow_data = cur.fetchone()
        moscow_dist = float(moscow_data[0]) if moscow_data else 0.0

        # Формируем сообщение
        response = f"📊 **Итоги периода**\n"
        response += f"с {start_dt.strftime('%d.%m.%Y')} по {end_dt.strftime('%d.%m.%Y')}:\n\n"
        response += f"🏁 Пройдено за период: {total_period:.2f} км\n"
        response += f"📊 Всего пройдено за всё время: {total_all_time:.2f} км\n\n"

        if next_city_data:
            next_city_name, next_city_dist = next_city_data
            if hasattr(next_city_dist, '__float__'):
                next_city_dist = float(next_city_dist)
            left_to_city = next_city_dist - total_all_time
            response += f"📍 Следующий город: {next_city_name}\n"
            response += f"🛣️ До него осталось: {left_to_city:.2f} км\n"
        else:
            response += "🎉 Поздравляем! Вы достигли конечной точки!\n"

        if moscow_dist > 0:
            if total_all_time < moscow_dist:
                left_to_moscow = moscow_dist - total_all_time
                response += f"🏛️ До Москвы осталось: {left_to_moscow:.2f} км"
            else:
                response += "🇷🇺 Вы уже в Москве (или проехали её)!"
        
        # Отправляем результат
        if update.callback_query:
            await update.callback_query.message.reply_text(response, parse_mode="Markdown")
        else:
            await update.effective_message.reply_text(response, parse_mode="Markdown")
        
        # Очищаем данные
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logging.error(f"Ошибка в функции расчета: {e}", exc_info=True)
        error_msg = "❌ Произошла ошибка при расчете итогов."
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.effective_message.reply_text(error_msg)
        return ConversationHandler.END
        
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# --- ПОЛУЧАЕМ ДАТУ НАЧАЛА ---
async def get_start_date_old(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
async def get_end_date_old(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
        # 1. Получаем общую сумму пробега ЗА ВСЁ ВРЕМЯ (для определения города)
        cur.execute(
            "SELECT COALESCE(ROUND(SUM(distance)), 0) FROM races"
        )
        total_all_time = cur.fetchone()[0]
        if hasattr(total_all_time, '__float__'):
            total_all_time = float(total_all_time)

        # 2. Получаем сумму пробега ЗА ВЫБРАННЫЙ ПЕРИОД (для отчета)
        cur.execute(
            "SELECT COALESCE(SUM(distance), 0) FROM races WHERE race_date >= %s AND race_date <= %s",
            (start_dt, end_dt)
        )
        total_period = cur.fetchone()[0]
        if hasattr(total_period, '__float__'):
            total_period = float(total_period)

        # 3. Ищем ближайший город (исходя из общего пробега за всё время)
        cur.execute(
            "SELECT city_name, distance_from_start FROM city_distances WHERE distance_from_start > %s ORDER BY distance_from_start ASC LIMIT 1",
            (total_all_time,)
        )
        next_city_data = cur.fetchone()

        # 4. Получаем дистанцию до Москвы
        cur.execute(
            "SELECT distance_from_start FROM city_distances WHERE city_name ILIKE 'москва' LIMIT 1"
        )
        moscow_data = cur.fetchone()
        moscow_dist = float(moscow_data[0]) if moscow_data else 0.0

        # Формируем сообщение
        response = f"Итоги периода с {start_dt.strftime('%d.%m.%Y')} по {end_dt.strftime('%d.%m.%Y')}:\n"
        response += f"🏁 Пройдено за период: {total_period:.2f} км\n"
        response += f"📊 Всего пройдено за всё время: {total_all_time:.2f} км\n\n"

        if next_city_data:
            next_city_name, next_city_dist = next_city_data
            if hasattr(next_city_dist, '__float__'):
                next_city_dist = float(next_city_dist)
            left_to_city = next_city_dist - total_all_time
            response += f"📍 Следующий город: {next_city_name}\n"
            response += f"🛣️ До него осталось: {left_to_city:.2f} км\n"
        else:
            response += "🎉 Поздравляем! Вы достигли конечной точки!\n"

        if moscow_dist > 0:
            if total_all_time < moscow_dist:
                left_to_moscow = moscow_dist - total_all_time
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

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS

async def delete_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет забег по ID (только для админов)"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещен! Только администраторы могут удалять забеги.")
        return
    
    if not context.args or len(context.args) == 0:
        await update.message.reply_text(
            "❌ Укажите ID забега для удаления.\n"
            "Пример: /delete_race 784"
        )
        return
    
    try:
        race_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом!")
        return
    
    conn = None
    cur = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute("SELECT id, participant_name, race_name, race_date FROM races WHERE id = %s", (race_id,))
        race = cur.fetchone()
        
        if not race:
            await update.message.reply_text(f"❌ Забег с ID {race_id} не найден.")
            return
        
        race_info = (
            f"📅 Дата: {race[3].strftime('%d.%m.%Y')}\n"
            f"👤 Участник: {race[1]}\n"
            f"🏃 Забег: {race[2]}"
        )
        
        cur.execute("DELETE FROM races WHERE id = %s", (race_id,))
        conn.commit()
        
        await update.message.reply_text(
            f"✅ Забег с ID {race_id} успешно удален!\n\n"
            f"Удаленная запись:\n{race_info}"
        )
        
    except psycopg2.Error as e:
        logging.error(f"Ошибка базы данных при удалении: {e}")
        await update.message.reply_text(f"❌ Ошибка при удалении: {e}")
    except Exception as e:
        logging.error(f"Ошибка при удалении: {e}")
        await update.message.reply_text(f"❌ Произошла ошибка: {e}")
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

async def start_add_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начинаем процесс добавления забега с проверкой прав"""
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь администратором
    if not is_admin(user_id):
        await update.message.reply_text(
            "⛔ Доступ запрещен!\n"
            "Только администраторы могут добавлять новые забеги."
        )
        return ConversationHandler.END
    
    await update.message.reply_text(
        "🏃 Начинаем добавление нового забега!\n"
        "Введите дату забега в формате ДД.ММ.ГГГГ (например, 15.07.2026):"
    )
    return DATE

async def add_race_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем дату забега"""
    try:
        date_text = update.message.text
        race_date = datetime.strptime(date_text, '%d.%m.%Y').date()
        context.user_data['race_date'] = race_date
        
        await update.message.reply_text(
            "✅ Дата сохранена!\n"
            "Теперь введите ФИО участника:"
        )
        return NAME
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты!\n"
            "Пожалуйста, введите дату в формате ДД.ММ.ГГГГ (например, 15.07.2026):"
        )
        return DATE

async def add_race_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем ФИО участника"""
    participant_name = update.message.text.strip()
    if len(participant_name) < 2:
        await update.message.reply_text(
            "❌ Имя слишком короткое!\n"
            "Пожалуйста, введите полное ФИО:"
        )
        return NAME
    
    context.user_data['full_name'] = participant_name  # Сохраняем как full_name, но в БД будет participant_name
    
    await update.message.reply_text(
        f"✅ ФИО сохранено: {participant_name}\n"
        "Теперь введите город, где проходил забег:"
    )
    return CITY

async def add_race_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем город проведения забега"""
    city = update.message.text.strip()
    if len(city) < 2:
        await update.message.reply_text(
            "❌ Название города слишком короткое!\n"
            "Пожалуйста, введите корректное название города:"
        )
        return CITY
    
    context.user_data['city'] = city
    
    await update.message.reply_text(
        f"✅ Город сохранен: {city}\n"
        "Теперь введите название забега (например, 'Московский марафон 2026'):"
    )
    return RACE_NAME

async def add_race_name_event(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем название забега"""
    race_name = update.message.text.strip()
    if len(race_name) < 2:
        await update.message.reply_text(
            "❌ Название слишком короткое!\n"
            "Пожалуйста, введите корректное название забега:"
        )
        return RACE_NAME
    
    context.user_data['race_name'] = race_name
    
    await update.message.reply_text(
        f"✅ Название забега сохранено: {race_name}\n"
        "Теперь введите дистанцию забега в километрах (например, 42.2):"
    )
    return DISTANCE

async def add_race_distance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получаем дистанцию и сохраняем все данные в базу"""
    conn = None
    cur = None
    try:
        # Парсим дистанцию
        distance_text = update.message.text.replace(',', '.')
        distance = float(distance_text)
        
        if distance <= 0:
            await update.message.reply_text(
                "❌ Дистанция должна быть больше 0!\n"
                "Пожалуйста, введите корректную дистанцию:"
            )
            return DISTANCE
        
        # Получаем все данные из context
        race_date = context.user_data.get('race_date')
        participant_name = context.user_data.get('full_name')  # В context хранится как full_name
        city = context.user_data.get('city')
        race_name = context.user_data.get('race_name')
        
        # Проверяем, что все данные есть
        if not all([race_date, participant_name, city, race_name]):
            logging.error(f"Отсутствуют данные: race_date={race_date}, participant_name={participant_name}, city={city}, race_name={race_name}")
            await update.message.reply_text(
                "❌ Ошибка: не все данные заполнены.\n"
                "Пожалуйста, начните добавление забега заново командой /add_race"
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        # Сохраняем в базу данных
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Используем participant_name вместо full_name
        cur.execute(
            """INSERT INTO races (race_date, participant_name, city, race_name, distance) 
               VALUES (%s, %s, %s, %s, %s)""",
            (race_date, participant_name, city, race_name, distance)
        )
        conn.commit()
        
        # Формируем сообщение об успешном добавлении
        response = (
            "✅ Забег успешно добавлен!\n\n"
            f"📅 Дата: {race_date.strftime('%d.%m.%Y')}\n"
            f"👤 Участник: {participant_name}\n"
            f"📍 Город: {city}\n"
            f"🏃 Забег: {race_name}\n"
            f"📏 Дистанция: {distance:.2f} км"
        )
        
        await update.message.reply_text(response)
        
        # Очищаем данные пользователя
        context.user_data.clear()
        
        return ConversationHandler.END
        
    except ValueError as e:
        logging.error(f"Ошибка парсинга дистанции: {e}")
        await update.message.reply_text(
            "❌ Неверный формат дистанции!\n"
            "Пожалуйста, введите число (например, 42.2 или 21,1):"
        )
        return DISTANCE
        
    except psycopg2.Error as e:
        logging.error(f"Ошибка базы данных при добавлении забега: {e}")
        await update.message.reply_text(
            f"❌ Произошла ошибка при сохранении в базу данных.\n"
            f"Ошибка: {str(e)[:100]}\n"
            "Пожалуйста, попробуйте позже."
        )
        return ConversationHandler.END
        
    except Exception as e:
        logging.error(f"Ошибка при добавлении забега: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Произошла непредвиденная ошибка:\n{str(e)[:100]}\n"
            "Пожалуйста, попробуйте позже."
        )
        return ConversationHandler.END
        
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

async def cancel_add_race(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена добавления забега"""
    await update.message.reply_text(
        "❌ Добавление забега отменено.\n"
        "Все введенные данные были удалены."
    )
    context.user_data.clear()
    return ConversationHandler.END

async def set_bot_commands(application):
    """Устанавливает команды в меню бота"""
    commands = [
        BotCommand("start", "🚀 Запустить бота"),
        BotCommand("add_race", "➕ Добавить новый забег"),
        BotCommand("list", "📋 Список забегов"),
        BotCommand("stats", "🏆 Моя статистика"),
        BotCommand("total", "📊 Итоги за период"),
    ]    
    await application.bot.set_my_commands(commands)
    logging.info("✅ Команды меню успешно установлены!")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_name = update.effective_user.first_name    
    welcome_text = (
        f"👋 Привет, {user_name}!\n\n"
        "Я бот для учета пробегов! 🏃\n\n"
        "📌 Доступные команды:\n"
        "/add_race - ➕ Добавить новый забег\n"
        "/list - 📋 Список всех забегов\n"
        "/stats - 🏆 Рейтинг участников\n"
        "/total - 📊 Итоги за выбранный период\n\n"
        "Выберите команду в меню или отправьте её в чат!"
    )
    await update.message.reply_text(welcome_text)

async def update_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обновляет меню команд (только для админов)"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещен!")
        return
    
    await set_bot_commands(context.bot)
    await update.message.reply_text("✅ Меню команд обновлено!")

add_race_conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler('add_race', start_add_race),  # или MessageHandler для кнопки
    ],
    states={
        DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_race_date)],
        NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_race_name)],
        CITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_race_city)],
        RACE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_race_name_event)],
        DISTANCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_race_distance)],
    },
    fallbacks=[
        CommandHandler('cancel', cancel_add_race),
    ],
    allow_reentry=True,
)

total_conv = ConversationHandler(
    entry_points=[CommandHandler('total', total_start)],
    states={
        START_DATE: [
            CallbackQueryHandler(calendar_callback, pattern="^start_"),
            # Разрешаем также текстовый ввод для совместимости
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_start_date_old),
        ],
        END_DATE: [
            CallbackQueryHandler(calendar_callback, pattern="^end_"),
            # Разрешаем также текстовый ввод для совместимости
            MessageHandler(filters.TEXT & ~filters.COMMAND, get_end_date_old),
        ],
    },
    fallbacks=[
        CommandHandler('cancel', cancel),
    ],
    allow_reentry=True,
)

# --- СТАНДАРТНЫЙ ЗАПУСК ---
if __name__ == '__main__':
    # init_db() — функция должна быть определена выше (как в прошлых ответах)
    # init_cities_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_races))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("delete_race", delete_race))
    app.add_handler(CommandHandler("update_menu", update_menu))  
    app.add_handler(add_race_conv_handler)
    app.add_handler(total_conv) 
    app.add_handler(CallbackQueryHandler(calendar_callback, pattern="^(start|end)_"))
    
    # Устанавливаем команды в меню при запуске
    async def post_init(application):
        await set_bot_commands(application)
    
    app.post_init = post_init
    
    logging.info("🚀 Бот запущен!")
    app.run_polling()
