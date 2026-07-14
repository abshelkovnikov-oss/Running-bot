import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Добавь эти строки отладки:
print("🚀 Запуск бота...")
print(f"BOT_TOKEN установлен: {bool(os.getenv('BOT_TOKEN'))}")
print(f"ADMIN_ID установлен: {bool(os.getenv('ADMIN_ID'))}")

bot_token = os.getenv("BOT_TOKEN")
if not bot_token:
    print("❌ BOT_TOKEN не найден!")
    exit()

print("✅ Создаю приложение...")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен бота (добавь в переменные окружения Railway)
BOT_TOKEN = "YOUR_BOT_TOKEN"

# ID админа (твой Telegram ID)
ADMIN_ID = 1190800579  # Замени на свой ID

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

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
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

# Добавление забега
async def add_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа!")
        return
    
    await update.message.reply_text(
        "📝 Добавление забега\n\n"
        "Отправь данные в формате:\n"
        "Город | Название забега | Фамилия | Дата | Километраж\n\n"
        "Пример:\n"
        "Москва | Московский марафон | Иванов | 15.10.2024 | 42.2"
    )
    
    context.user_data['waiting_for_run'] = True

# Обработка добавления забега
async def process_run_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('waiting_for_run'):
        return
    
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
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа!")
        return
    
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
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа!")
        return
    
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT u.first_name, u.last_name, 
               COUNT(r.id) as runs_count, 
               SUM(r.distance) as total_distance
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
        total_distance = total_distance or 0
        runs_count = runs_count or 0
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
    user_id = update.effective_user.id
    
    if not is_authorized(user_id):
        await update.message.reply_text("❌ У вас нет доступа!")
        return
    
    conn = sqlite3.connect('running_club.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM users WHERE is_authorized = 1')
    total_users = cursor.fetchone()
    
    cursor.execute('SELECT COUNT(*) FROM runs')
    total_runs = cursor.fetchone()
    
    cursor.execute('SELECT SUM(distance) FROM runs')
    total_distance = cursor.fetchone() or 0
    
    cursor.execute('SELECT AVG(distance) FROM runs')
    avg_distance = cursor.fetchone() or 0
    
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
        [KeyboardButton("🗑️ Удалить забег"), KeyboardButton("🚫 Заблокировать участника")],
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
        await update.message
