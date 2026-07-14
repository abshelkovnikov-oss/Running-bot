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
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None

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
    return result and result[0] == 1

# Проверка админа
def is_admin(user_id):
    return ADMIN_ID and user_id == ADMIN_ID

# Генерация кода приглашения
def generate_invite_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # ОТЛАДКА
    print(f"🆔 ADMIN_ID: {ADMIN_ID}")
    print(f"🆔 User ID: {user_id}")
    print(f"👤 User name: {user.first_name}")
    
    # Автоматически регистрируем админа ТОЛЬКО если он не зарегистрирован
    if is_admin(user_id) and not is_authorized(user_id):
        conn = sqlite3.connect('running_club.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users 
            (user_id, username, first_name, last_name, is_authorized, registration_date)
            VALUES (?, ?, ?, ?, 1, ?)
        ''', (user_id, user.username, user.first_name, user.last_name, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        print("✅ Админ зарегистрирован автоматически!")
    
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
    
    code = context.args[0].upper()
    
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
    
    # Удалить участника
    elif text == "🗑️ Удалить участника" and is_admin(user_id):
        await remove_user_start(update, context)
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

# Остальные функции остаются без изменений...
# (my_stats, rating, general_stats, admin_panel, create_invite_code, etc.)

# Основная функция
def main():
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не установлен!")
        return
    
    if not ADMIN_ID:
        print("❌ Ошибка: ADMIN_ID не установлен!")
        return
    
    # Инициализация БД
    init_db()
    
    print(f"🆔 ADMIN_ID: {ADMIN_ID}")
    print(f"🤖 BOT_TOKEN: установлен")
    
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
