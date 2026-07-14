import os
import logging
import sqlite3
import random
import string
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            is_authorized INTEGER DEFAULT 0,
            registration_date TEXT
        )
    ''')
    
    # Таблица кодов приглашений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invite_codes (
            code TEXT PRIMARY KEY,
            created_by INTEGER,
            used_by INTEGER DEFAULT NULL,
            created_date TEXT,
            used_date TEXT
        )
    ''')
    
    # Таблица забегов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            city TEXT,
            race_name TEXT,
            runner_name TEXT,
            date TEXT,
            distance REAL,
            added_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Проверка авторизации
def is_authorized(user_id):
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    cursor.execute('SELECT is_authorized FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result and result == 1

# Проверка админа
def is_admin(user_id):
    return user_id == ADMIN_ID

# Генерация кода приглашения
def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    print(f"🆔 ADMIN_ID из переменной: {ADMIN_ID}")
    print(f"🆔 User ID: {user_id}")
    print(f"👤 User name: {user.first_name}")
    
    # Проверяем админа
    if is_admin(user_id):
        print("✅ Это админ!")
    else:
        print("❌ Не админ")

    
    
    if is_authorized(user_id):
        keyboard = [
            [KeyboardButton("📝 Добавить забег")],
            [KeyboardButton("📊 Моя статистика"), KeyboardButton("🏆 Рейтинг")],
            [KeyboardButton("📈 Общая статистика")]
        ]
        if is_admin(user_id):
            keyboard.append([KeyboardButton("👑 Админ-панель")])
        
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f"Привет, {user.first_name}! 🏃‍♂️\n"
            f"Добро пожаловать в корпоративный беговой клуб!\n\n"
            f"Выбери действие:",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Привет! 👋\n"
            "Это закрытый корпоративный беговой клуб.\n\n"
            "Для доступа введи код приглашения:\n"
            "Формат: /code ТВОЙ_КОД"
        )

# Регистрация по коду
async def register_with_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if len(context.args) != 1:
        await update.message.reply_text("Используй: /code ТВОЙ_КОД")
        return
    
    code = context.args.upper()
    
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    
    # Проверяем код
    cursor.execute('SELECT * FROM invite_codes WHERE code = ? AND used_by IS NULL', (code,))
    invite = cursor.fetchone()
    
    if not invite:
        await update.message.reply_text("❌ Неверный или уже использованный код!")
        conn.close()
        return
    
    # Регистрируем пользователя
    cursor.execute('''
        INSERT OR REPLACE INTO users 
        (user_id, username, first_name, last_name, is_authorized, registration_date)
        VALUES (?, ?, ?, ?, 1, ?)
    ''', (user_id, user.username, user.first_name, user.last_name, datetime.now().isoformat()))
    
    # Отмечаем код как использованный
    cursor.execute('''
        UPDATE invite_codes 
        SET used_by = ?, used_date = ? 
        WHERE code = ?
    ''', (user_id, datetime.now().isoformat(), code))
    
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        "✅ Регистрация успешна!\n"
        "Добро пожаловать в беговой клуб! 🏃‍♂️\n\n"
        "Нажми /start для начала работы."
    )

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа! Используйте /code для регистрации.")
        return
    
    # Добавление забега
    if text == "📝 Добавить забег":
        await update.message.reply_text(
            "📝 Добавление забега\n\n"
            "Отправь данные в формате:\n"
            "Город | Название забега | Фамилия | Дата | Километраж\n\n"
            "Пример:\n"
            "Москва | Московский марафон | Иванов | 15.10.2024 | 42.2"
        )
        context.user_data['waiting_for_run'] = True
        return
    
    # Моя статистика
    elif text == "📊 Моя статистика":
        await my_stats(update, context)
        return
    
    # Рейтинг
    elif text == "🏆 Рейтинг":
        await rating(update, context)
        return
    
    # Общая статистика
    elif text == "📈 Общая статистика":
        await general_stats(update, context)
        return
    
    # Админ-панель
    elif text == "👑 Админ-панель" and is_admin(user_id):
        await admin_panel(update, context)
        return
    
    # Создать код приглашения
    elif text == "🎫 Создать код приглашения" and is_admin(user_id):
        await create_invite_code(update, context)
        return
    
    # Список кодов
    elif text == "📋 Список кодов" and is_admin(user_id):
        await list_invite_codes(update, context)
        return
    
    # Список участников
    elif text == "👥 Список участников" and is_admin(user_id):
        await list_users(update, context)
        return
    
    # Назад из админ-панели
    elif text == "◀️ Назад":
        await start(update, context)
        return
    
    # Обработка добавления забега
    elif context.user_data.get('waiting_for_run'):
        await process_run_data(update, context)
        return
    
    # Обработка удаления пользователя
    elif context.user_data.get('waiting_for_user_id'):
        await process_remove_user(update, context)
        return
    
    else:
        await update.message.reply_text("Используйте кнопки меню для навигации.")

# Обработка добавления забега
async def process_run_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    try:
        parts = [part.strip() for part in text.split('|')]
        if len(parts) != 5:
            raise ValueError("Неверное количество параметров")
        
        city, race_name, runner_name, date_str, distance_str = parts
        distance = float(distance_str.replace(',', '.'))
        
        # Проверяем дату
        try:
            datetime.strptime(date_str, '%d.%m.%Y')
        except:
            raise ValueError("Неверный формат даты")
        
        # Сохраняем в БД
        conn = sqlite3.connect('running_club.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO runs (user_id, city, race_name, runner_name, date, distance, added_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, city, race_name, runner_name, date_str, distance, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Забег добавлен!\n\n"
            f"🏙️ Город: {city}\n"
            f"🏃‍♂️ Забег: {race_name}\n"
            f"👤 Участник: {runner_name}\n"
            f"📅 Дата: {date_str}\n"
            f"📏 Дистанция: {distance} км"
        )
        
        context.user_data['waiting_for_run'] = False
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка в формате данных!\n\n"
            f"Используй формат:\n"
            f"Город | Название | Фамилия | ДД.ММ.ГГГГ | Километры\n\n"
            f"Пример:\n"
            f"Москва | Московский марафон | Иванов | 15.10.2024 | 42.2"
        )

# Моя статистика
async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT city, race_name, runner_name, date, distance 
        FROM runs 
        WHERE user_id = ? 
        ORDER BY date DESC
    ''', (user_id,))
    runs = cursor.fetchall()
    
    cursor.execute('SELECT SUM(distance) FROM runs WHERE user_id = ?', (user_id,))
    total_distance = cursor.fetchone() or 0
    
    conn.close()
    
    if not runs:
        await update.message.reply_text("📊 У вас пока нет записей о забегах.")
        return
    
    message = f"📊 Ваша статистика:\n\n"
    message += f"🏃‍♂️ Всего забегов: {len(runs)}\n"
    message += f"📏 Общий километраж: {total_distance:.1f} км\n\n"
    message += "📝 Последние забеги:\n"
    
    for run in runs[:10]:  # Показываем последние 10
        city, race_name, runner_name, date, distance = run
        message += f"• {date} - {city}, {race_name} ({distance} км)\n"
    
    await update.message.reply_text(message)

# Общий рейтинг
async def rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.first_name, u.last_name, 
               COUNT(r.id) as runs_count, 
               COALESCE(SUM(r.distance), 0) as total_distance
        FROM users u
        LEFT JOIN runs r ON u.user_id = r.user_id
        WHERE u.is_authorized = 1
        GROUP BY u.user_id
        ORDER BY total_distance DESC
    ''')
    results = cursor.fetchall()
    conn.close()
    
    message = "🏆 Рейтинг участников:\n\n"
    
    for i, (first_name, last_name, runs_count, total_distance) in enumerate(results, 1):
        name = f"{first_name} {last_name or ''}".strip()
        
        if i == 1:
            emoji = "🥇"
        elif i == 2:
            emoji = "🥈"
        elif i == 3:
            emoji = "🥉"
        else:
            emoji = f"{i}."
        
        message += f"{emoji} {name}\n"
        message += f"   📏 {total_distance:.1f} км | 🏃‍♂️ {runs_count} забегов\n\n"
    
    await update.message.reply_text(message)

# Общая статистика
async def general_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_authorized = 1')
    total_users = cursor.fetchone()
    
    cursor.execute('SELECT COUNT(*) FROM runs')
    total_runs = cursor.fetchone()
    
    cursor.execute('SELECT COALESCE(SUM(distance), 0) FROM runs')
    total_distance = cursor.fetchone()
    
    cursor.execute('SELECT COALESCE(AVG(distance), 0) FROM runs')
    avg_distance = cursor.fetchone()
    
    conn.close()
    
    message = f"📈 Общая статистика клуба:\n\n"
    message += f"👥 Участников: {total_users}\n"
    message += f"🏃‍♂️ Всего забегов: {total_runs}\n"
    message += f"📏 Общий километраж: {total_distance:.1f} км\n"
    message += f"📊 Средняя дистанция: {avg_distance:.1f} км\n"
    
    await update.message.reply_text(message)

# Админ-панель
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав администратора!")
        return
    
    keyboard = [
        [KeyboardButton("🎫 Создать код приглашения")],
        [KeyboardButton("📋 Список кодов"), KeyboardButton("👥 Список участников")],
        [KeyboardButton("🗑️ Удалить участника")],
        [KeyboardButton("◀️ Назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "👑 Админ-панель\n\nВыберите действие:",
        reply_markup=reply_markup
    )

# Создание кода приглашения
async def create_invite_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав администратора!")
        return
    
    code = generate_invite_code()
    
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO invite_codes (code, created_by, created_date)
        VALUES (?, ?, ?)
    ''', (code, user_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ Код приглашения создан!\n\n"
        f"🎫 Код: `{code}`\n\n"
        f"Отправьте этот код новому участнику.\n"
        f"Для регистрации нужно написать боту: /code {code}",
        parse_mode='Markdown'
    )

# Список кодов приглашений
async def list_invite_codes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав администратора!")
        return
    
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT ic.code, ic.created_date, ic.used_date, 
               u.first_name, u.last_name
        FROM invite_codes ic
        LEFT JOIN users u ON ic.used_by = u.user_id
        ORDER BY ic.created_date DESC
    ''')
    codes = cursor.fetchall()
    conn.close()
    
    if not codes:
        await update.message.reply_text("📋 Кодов приглашений пока нет.")
        return
    
    message = "📋 Коды приглашений:\n\n"
    
    for code, created_date, used_date, first_name, last_name in codes:
        created = datetime.fromisoformat(created_date).strftime('%d.%m.%Y %H:%M')
        
        if used_date:
            used = datetime.fromisoformat(used_date).strftime('%d.%m.%Y %H:%M')
            user_name = f"{first_name} {last_name or ''}".strip()
            status = f"✅ Использован {used} ({user_name})"
        else:
            status = "⏳ Не использован"
        
        message += f"🎫 `{code}`\n"
        message += f"   📅 Создан: {created}\n"
        message += f"   {status}\n\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

# Список участников
async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав администратора!")
        return
    
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.user_id, u.first_name, u.last_name, u.username, 
               u.registration_date, COUNT(r.id) as runs_count,
               COALESCE(SUM(r.distance), 0) as total_distance
        FROM users u
        LEFT JOIN runs r ON u.user_id = r.user_id
        WHERE u.is_authorized = 1
        GROUP BY u.user_id
        ORDER BY u.registration_date DESC
    ''')
    users = cursor.fetchall()
    conn.close()
    
    if not users:
        await update.message.reply_text("👥 Участников пока нет.")
        return
    
    message = "👥 Список участников:\n\n"
    
    for user_data in users:
        user_id_db, first_name, last_name, username, reg_date, runs_count, total_distance = user_data
        name = f"{first_name} {last_name or ''}".strip()
        username_str = f"@{username}" if username else "без username"
        reg_date_str = datetime.fromisoformat(reg_date).strftime('%d.%m.%Y')
        
        message += f"👤 {name} ({username_str})\n"
        message += f"   🆔 ID: {user_id_db}\n"
        message += f"   📅 Регистрация: {reg_date_str}\n"
        message += f"   🏃‍♂️ Забегов: {runs_count} | 📏 {total_distance:.1f} км\n\n"
    
    await update.message.reply_text(message)

# Удаление участника
async def remove_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ У вас нет прав администратора!")
        return
    
    await update.message.reply_text(
        "🗑️ Удаление участника\n\n"
        "Отправьте ID пользователя для удаления.\n"
        "ID можно найти в списке участников."
    )
    context.user_data['waiting_for_user_id'] = True

# Обработка удаления пользователя
async def process_remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    try:
        target_user_id = int(text)
        
        if target_user_id == ADMIN_ID:
            await update.message.reply_text("❌ Нельзя удалить администратора!")
            context.user_data['waiting_for_user_id'] = False
            return
        
        conn = sqlite3.connect('running_club.db')
        cursor = conn.cursor()
        
        # Проверяем существование пользователя
        cursor.execute('SELECT first_name, last_name FROM users WHERE user_id = ?', (target_user_id,))
        user_data = cursor.fetchone()
        
        if not user_data:
            await update.message.reply_text("❌ Пользователь не найден!")
            conn.close()
            context.user_data['waiting_for_user_id'] = False
            return
        
        # Удаляем забеги пользователя
        cursor.execute('DELETE FROM runs WHERE user_id = ?', (target_user_id,))
        
        # Удаляем пользователя
        cursor.execute('DELETE FROM users WHERE user_id = ?', (target_user_id,))
        
        conn.commit()
        conn.close()
        
        name = f"{user_data[0]} {user_data[1] or ''}".strip()
        await update.message.reply_text(
            f"✅ Пользователь {name} (ID: {target_user_id}) удален!\n"
            f"Все его забеги также удалены."
        )
        
        context.user_data['waiting_for_user_id'] = False
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID! Введите числовой ID.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при удалении: {str(e)}")
        context.user_data['waiting_for_user_id'] = False

# Обновляем обработчик сообщений для удаления участника
async def handle_message_updated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа! Используйте /code для регистрации.")
        return
    
    # Удалить участника
    if text == "🗑️ Удалить участника" and is_admin(user_id):
        await remove_user_start(update, context)
        return
    
    # Остальной код handle_message остается таким же...
    # (весь предыдущий код функции handle_message)

# Основная функция
def main():
    # Инициализация БД
    init_db()
    
    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("code", register_with_code))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Запуск бота
    print("🚀 Бот запущен!")
    application.run_polling()

if __name__ == '__main__':
    main()
