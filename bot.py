import os
import logging
import sqlite3
import random
import string
from datetime import datetime
from typing import Dict, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ================== НАСТРОЙКИ ==================
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "123456789").split(",")]

# ================== ЛОГИРОВАНИЕ ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== БАЗА ДАННЫХ SQLITE ==================
DB_NAME = "running_bot.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            invited_by INTEGER,
            is_active INTEGER DEFAULT 1,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            city TEXT NOT NULL,
            race_name TEXT NOT NULL,
            run_date DATE NOT NULL,
            km REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invites (
            code TEXT PRIMARY KEY,
            admin_id INTEGER NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_runs_run_date ON runs(run_date)')
    
    conn.commit()
    conn.close()
    logger.info("База данных инициализирована")

# ================== РАБОТА С БАЗОЙ ДАННЫХ ==================
class DatabaseManager:
    @staticmethod
    def add_user(user_id: int, name: str, invited_by: int = None) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO users (user_id, name, invited_by, is_active) VALUES (?, ?, ?, 1)",
                (user_id, name, invited_by)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def get_user(user_id: int) -> Optional[Dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Ошибка получения пользователя: {e}")
            return None
        finally:
            conn.close()

    @staticmethod
    def update_user_status(user_id: int, is_active: bool) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET is_active = ? WHERE user_id = ?",
                (1 if is_active else 0, user_id)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def add_run(user_id: int, city: str, race_name: str, run_date: str, km: float) -> bool:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO runs (user_id, city, race_name, run_date, km) VALUES (?, ?, ?, ?, ?)",
                (user_id, city, race_name, run_date, km)
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления забега: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def get_user_runs(user_id: int) -> List[Dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM runs WHERE user_id = ? ORDER BY run_date DESC",
                (user_id,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения забегов: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def get_total_km(user_id: int) -> float:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT COALESCE(SUM(km), 0) as total FROM runs WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return row['total'] if row else 0.0
        except Exception as e:
            logger.error(f"Ошибка подсчета километража: {e}")
            return 0.0
        finally:
            conn.close()

    @staticmethod
    def get_all_active_users() -> List[Dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM users WHERE is_active = 1 ORDER BY name"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения пользователей: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def get_all_users_with_stats() -> List[Dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT 
                    u.user_id,
                    u.name,
                    u.is_active,
                    COUNT(r.id) as runs_count,
                    COALESCE(SUM(r.km), 0) as total_km
                FROM users u
                LEFT JOIN runs r ON u.user_id = r.user_id
                WHERE u.is_active = 1
                GROUP BY u.user_id
                ORDER BY total_km DESC
            ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def create_invite_code(admin_id: int) -> Optional[str]:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO invites (code, admin_id) VALUES (?, ?)",
                (code, admin_id)
            )
            conn.commit()
            return code
        except sqlite3.IntegrityError:
            # Если код уже существует, генерируем новый
            return DatabaseManager.create_invite_code(admin_id)
        except Exception as e:
            logger.error(f"Ошибка создания кода: {e}")
            return None
        finally:
            conn.close()

    @staticmethod
    def use_invite_code(code: str) -> Optional[int]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT admin_id FROM invites WHERE code = ? AND used = 0",
                (code,)
            )
            row = cursor.fetchone()
            if row:
                admin_id = row['admin_id']
                cursor.execute(
                    "UPDATE invites SET used = 1 WHERE code = ?",
                    (code,)
                )
                conn.commit()
                return admin_id
            return None
        except Exception as e:
            logger.error(f"Ошибка использования кода: {e}")
            return None
        finally:
            conn.close()

    @staticmethod
    def get_invite_codes(admin_id: int = None) -> List[Dict]:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if admin_id:
                cursor.execute(
                    "SELECT * FROM invites WHERE admin_id = ? ORDER BY created_at DESC",
                    (admin_id,)
                )
            else:
                cursor.execute("SELECT * FROM invites ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Ошибка получения кодов: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def get_total_all_km() -> float:
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT COALESCE(SUM(r.km), 0) as total
                FROM runs r
                JOIN users u ON r.user_id = u.user_id
                WHERE u.is_active = 1
            ''')
            row = cursor.fetchone()
            return row['total'] if row else 0.0
        except Exception as e:
            logger.error(f"Ошибка подсчета общего километража: {e}")
            return 0.0
        finally:
            conn.close()

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_user_name(user_id: int) -> str:
    user = DatabaseManager.get_user(user_id)
    return user['name'] if user else "Неизвестный"

def get_stats_text(user_id: int) -> str:
    user = DatabaseManager.get_user(user_id)
    if not user:
        return "❌ Пользователь не найден."
    
    name = user['name']
    user_runs = DatabaseManager.get_user_runs(user_id)
    
    if not user_runs:
        return f"🏃 {name} — пока нет забегов."
    
    total = DatabaseManager.get_total_km(user_id)
    avg = total / len(user_runs) if user_runs else 0
    
    text = f"📊 Статистика {name}:\n"
    text += f"🏅 Всего забегов: {len(user_runs)}\n"
    text += f"📏 Общий километраж: {total:.1f} км\n"
    text += f"📈 Средний: {avg:.1f} км\n\n"
    text += "📋 Последние забеги:\n"
    
    for i, run in enumerate(user_runs[:5], 1):
        text += f"{i}. {run['city']} — {run['race_name']} ({run['run_date']}) {run['km']} км\n"
    
    if len(user_runs) > 5:
        text += f"\n... и еще {len(user_runs) - 5} забегов"
    
    return text

def get_rating_text() -> str:
    users_stats = DatabaseManager.get_all_users_with_stats()
    
    if not users_stats:
        return "👥 Нет зарегистрированных участников."
    
    text = "🏆 Рейтинг участников (по общему км):\n\n"
    
    for i, user in enumerate(users_stats[:10], 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        runs = user['runs_count']
        km = user['total_km']
        text += f"{medal} {user['name']} — {km:.1f} км ({runs} забегов)\n"
    
    if len(users_stats) > 10:
        text += f"\n... и еще {len(users_stats) - 10} участников"
    
    return text

def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Главное меню"""
    keyboard = [
        [InlineKeyboardButton("📝 Добавить забег", callback_data="add_run")],
        [InlineKeyboardButton("📊 Моя статистика", callback_data="my_stats")],
        [InlineKeyboardButton("🏆 Рейтинг всех", callback_data="rating")],
        [InlineKeyboardButton("📏 Общий километраж", callback_data="total_km")],
    ]
    
    if is_admin(user_id):
        keyboard.extend([
            [InlineKeyboardButton("🔑 Сгенерировать код", callback_data="gen_invite")],
            [InlineKeyboardButton("👥 Список участников", callback_data="list_users")],
            [InlineKeyboardButton("📋 Мои коды", callback_data="my_invites")],
        ])
    
    return InlineKeyboardMarkup(keyboard)

def get_back_button() -> InlineKeyboardMarkup:
    """Кнопка возврата в меню"""
    keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data="back_to_menu")]]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_button() -> InlineKeyboardMarkup:
    """Кнопка отмены"""
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_action")]]
    return InlineKeyboardMarkup(keyboard)

# ================== ОБРАБОТЧИКИ КОМАНД ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    # Проверяем, зарегистрирован ли пользователь
    existing_user = DatabaseManager.get_user(user_id)
    if existing_user and existing_user['is_active'] == 1:
        await update.message.reply_text(
            f"👋 Добро пожаловать, {existing_user['name']}!\n"
            "Используйте /menu для доступа к функциям."
        )
        return
    
    # Если админ — сразу регистрируем
    if is_admin(user_id):
        name = update.effective_user.full_name
        if DatabaseManager.add_user(user_id, name, user_id):
            await update.message.reply_text(
                f"✅ Админ {name} зарегистрирован!\n"
                "Используйте /menu для доступа."
            )
        else:
            await update.message.reply_text("❌ Ошибка регистрации. Попробуйте позже.")
        return
    
    # Обычный пользователь — запрашиваем код
    await update.message.reply_text(
        "🔐 Это закрытое корпоративное сообщество.\n"
        "Введите код приглашения, полученный от администратора:"
    )
    # Сохраняем состояние что ждем код
    context.user_data['waiting_for_code'] = True

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик всех текстовых сообщений"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    # Проверяем, ждем ли мы код приглашения
    if context.user_data.get('waiting_for_code'):
        # Пытаемся использовать код
        admin_id = DatabaseManager.use_invite_code(text.upper())
        if admin_id:
            name = update.effective_user.full_name
            if DatabaseManager.add_user(user_id, name, admin_id):
                await update.message.reply_text(
                    f"✅ Добро пожаловать, {name}!\n"
                    "Теперь вы можете фиксировать свои забеги.\n"
                    "Используйте /menu для доступа."
                )
                context.user_data['waiting_for_code'] = False
                return
            else:
                await update.message.reply_text("❌ Ошибка регистрации. Попробуйте позже.")
                return
        else:
            await update.message.reply_text(
                "❌ Неверный код приглашения.\n"
                "Пожалуйста, проверьте код и попробуйте снова.\n"
                "Или напишите /cancel для отмены."
            )
            return
    
    # Проверяем, ждем ли мы данные забега
    if context.user_data.get('waiting_for_run'):
        await process_run_data(update, context)
        return
    
    # Если ничего не ждем, отправляем в меню
    await update.message.reply_text(
        "Используйте /menu для доступа к функциям бота."
    )

async def process_run_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработка введенных данных забега"""
    user_id = update.effective_user.id
    text = update.message.text.strip()
    
    try:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 4:
            raise ValueError("Неверный формат")
        
        city, race_name, date_str, km_str = parts
        
        # Проверка даты
        datetime.strptime(date_str, "%Y-%m-%d")
        
        # Проверка километража
        km = float(km_str)
        if km <= 0:
            raise ValueError("Километраж должен быть больше 0")
        if km > 1000:
            raise ValueError("Слишком большой километраж (макс. 1000 км)")
        
        # Добавляем забег
        if DatabaseManager.add_run(user_id, city, race_name, date_str, km):
            total_km = DatabaseManager.get_total_km(user_id)
            await update.message.reply_text(
                f"✅ Забег добавлен!\n"
                f"📍 Город: {city}\n"
                f"🏅 Название: {race_name}\n"
                f"📅 Дата: {date_str}\n"
                f"📏 Километраж: {km} км\n\n"
                f"📊 Ваш общий километраж: {total_km:.1f} км\n\n"
                f"Используйте /menu для продолжения."
            )
            context.user_data['waiting_for_run'] = False
        else:
            await update.message.reply_text("❌ Ошибка сохранения забега. Попробуйте позже.")
        
    except ValueError as e:
        await update.message.reply_text(
            f"❌ Ошибка: {e}\n\n"
            "📝 Правильный формат:\n"
            "Город, Название, ГГГГ-ММ-ДД, Километраж\n\n"
            "Пример: Москва, Марафон, 2026-07-14, 42.2\n\n"
            "Используйте /cancel для отмены"
        )

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает главное меню"""
    user_id = update.effective_user.id
    user = DatabaseManager.get_user(user_id)
    
    if not user or user['is_active'] != 1:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы или ваш аккаунт деактивирован.\n"
            "Используйте /start для регистрации."
        )
        return
    
    keyboard = get_main_menu_keyboard(user_id)
    await update.message.reply_text(
        f"🏃 Главное меню, {user['name']}!",
        reply_markup=keyboard,
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отмена текущего действия"""
    context.user_data['waiting_for_code'] = False
    context.user_data['waiting_for_run'] = False
    await update.message.reply_text("❌ Операция отменена. Используйте /menu для доступа.")

# ================== ОБРАБОТЧИК КНОПОК ==================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # Проверяем регистрацию
    user = DatabaseManager.get_user(user_id)
    if not user or user['is_active'] != 1:
        await query.edit_message_text("❌ Вы не зарегистрированы. Используйте /start")
        return
    
    # ===== ОБРАБОТКА КНОПОК =====
    
    # Кнопка "Назад в меню"
    if data == "back_to_menu":
        keyboard = get_main_menu_keyboard(user_id)
        await query.edit_message_text(
            f"🏃 Главное меню, {user['name']}!",
            reply_markup=keyboard
        )
        return
    
    # Кнопка "Отмена"
    if data == "cancel_action":
        context.user_data['waiting_for_run'] = False
        keyboard = get_main_menu_keyboard(user_id)
        await query.edit_message_text(
            "❌ Действие отменено",
            reply_markup=keyboard
        )
        return
    
    # Кнопка "Моя статистика"
    if data == "my_stats":
        text = get_stats_text(user_id)
        await query.edit_message_text(text, reply_markup=get_back_button())
        return
    
    # Кнопка "Рейтинг всех"
    if data == "rating":
        text = get_rating_text()
        await query.edit_message_text(text, reply_markup=get_back_button())
        return
    
    # Кнопка "Общий километраж"
    if data == "total_km":
        total = DatabaseManager.get_total_all_km()
        await query.edit_message_text(
            f"📏 Общий километраж сообщества: {total:.1f} км",
            reply_markup=get_back_button()
        )
        return
    
    # Кнопка "Сгенерировать код" - ДЛЯ АДМИНОВ
    if data == "gen_invite":
        if not is_admin(user_id):
            await query.edit_message_text("⛔ Только для администраторов.")
            return
        
        code = DatabaseManager.create_invite_code(user_id)
        if code:
            await query.edit_message_text(
                f"🔑 Новый код приглашения:\n\n`{code}`\n\n"
                "Отправьте этот код новому участнику.\n"
                "Код действителен для одного использования.",
                reply_markup=get_back_button()
            )
        else:
            await query.edit_message_text(
                "❌ Ошибка генерации кода.",
                reply_markup=get_back_button()
            )
        return
    
    # Кнопка "Мои коды" - ДЛЯ АДМИНОВ
    if data == "my_invites":
        if not is_admin(user_id):
            await query.edit_message_text("⛔ Только для администраторов.")
            return
        
        codes = DatabaseManager.get_invite_codes(user_id)
        if not codes:
            await query.edit_message_text(
                "У вас нет созданных кодов приглашений.",
                reply_markup=get_back_button()
            )
            return
        
        text = "📋 Ваши коды приглашений:\n\n"
        for code in codes[:10]:
            status = "✅ Использован" if code['used'] else "🟢 Активен"
            text += f"`{code['code']}` — {status}\n"
            text += f"   Создан: {code['created_at'][:10]}\n"
        
        if len(codes) > 10:
            text += f"\n... и еще {len(codes) - 10} кодов"
        
        await query.edit_message_text(text, reply_markup=get_back_button())
        return
    
    # Кнопка "Список участников" - ДЛЯ АДМИНОВ
    if data == "list_users":
        if not is_admin(user_id):
            await query.edit_message_text("⛔ Только для администраторов.")
            return
        
        users_list = DatabaseManager.get_all_active_users()
        if not users_list:
            await query.edit_message_text(
                "👥 Нет активных участников.",
                reply_markup=get_back_button()
            )
            return
        
        text = "👥 Список активных участников:\n\n"
        for user_item in users_list:
            total_km = DatabaseManager.get_total_km(user_item['user_id'])
            runs_count = len(DatabaseManager.get_user_runs(user_item['user_id']))
            text += f"• {user_item['name']}\n"
            text += f"  🏃 {runs_count} забегов, 📏 {total_km:.1f} км\n"
        
        await query.edit_message_text(text[:4000], reply_markup=get_back_button())
        return
    
    # Кнопка "Добавить забег"
    if data == "add_run":
        context.user_data['waiting_for_run'] = True
        await query.edit_message_text(
            "📝 Введите данные забега в формате:\n"
            "Город, Название забега, Дата (ГГГГ-ММ-ДД), Километраж\n\n"
            "Пример: Москва, Марафон, 2026-07-14, 42.2\n\n"
            "Нажмите 'Отмена' для отмены.",
            reply_markup=get_cancel_button()
        )
        return
    
    # Если ничего не подошло
    await query.edit_message_text("❌ Неизвестная команда.")

# ================== АДМИН-КОМАНДЫ ==================
async def admin_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Только для администраторов.")
        return
    
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text(
                "📝 Использование: /add_user <user_id> <имя>\n"
                "Пример: /add_user 123456789 Иван Петров"
            )
            return
        
        target_id = int(args[0])
        name = " ".join(args[1:])
        
        if DatabaseManager.add_user(target_id, name, user_id):
            await update.message.reply_text(f"✅ Пользователь {name} (ID: {target_id}) успешно добавлен.")
        else:
            await update.message.reply_text("❌ Ошибка добавления пользователя.")
            
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя. Должно быть число.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def admin_remove_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Только для администраторов.")
        return
    
    try:
        if not context.args:
            await update.message.reply_text("📝 Использование: /remove_user <user_id>")
            return
        
        target_id = int(context.args[0])
        
        if target_id == user_id:
            await update.message.reply_text("❌ Вы не можете деактивировать себя.")
            return
        
        user = DatabaseManager.get_user(target_id)
        if user:
            if DatabaseManager.update_user_status(target_id, False):
                await update.message.reply_text(f"❌ Пользователь {user['name']} деактивирован.")
            else:
                await update.message.reply_text("❌ Ошибка деактивации пользователя.")
        else:
            await update.message.reply_text("❌ Пользователь не найден.")
            
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя. Должно быть число.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def admin_activate_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Только для администраторов.")
        return
    
    try:
        if not context.args:
            await update.message.reply_text("📝 Использование: /activate_user <user_id>")
            return
        
        target_id = int(context.args[0])
        user = DatabaseManager.get_user(target_id)
        
        if user:
            if DatabaseManager.update_user_status(target_id, True):
                await update.message.reply_text(f"✅ Пользователь {user['name']} активирован.")
            else:
                await update.message.reply_text("❌ Ошибка активации пользователя.")
        else:
            await update.message.reply_text("❌ Пользователь не найден.")
            
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя. Должно быть число.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Только для администраторов.")
        return
    
    try:
        users = DatabaseManager.get_all_active_users()
        total_users = len(users)
        
        all_runs = 0
        total_km = 0
        for user in users:
            runs = DatabaseManager.get_user_runs(user['user_id'])
            all_runs += len(runs)
            total_km += DatabaseManager.get_total_km(user['user_id'])
        
        invites = DatabaseManager.get_invite_codes()
        used_invites = sum(1 for i in invites if i['used'])
        total_invites = len(invites)
        
        text = "📊 **Статистика сообщества**\n\n"
        text += f"👥 Всего участников: {total_users}\n"
        text += f"🏃 Всего забегов: {all_runs}\n"
        text += f"📏 Общий километраж: {total_km:.1f} км\n"
        text += f"📈 Средний км на участника: {total_km/total_users if total_users > 0 else 0:.1f} км\n"
        text += f"\n🔑 Всего кодов: {total_invites}\n"
        text += f"✅ Использовано: {used_invites}\n"
        text += f"🟢 Активно: {total_invites - used_invites}\n"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

# ================== MAIN ==================
def main() -> None:
    # Инициализация базы данных
    init_database()
    
    # Создание приложения
    app = Application.builder().token(TOKEN).build()
    
    # ===== ОБРАБОТЧИКИ =====
    
    # 1. Сначала команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("add_user", admin_add_user))
    app.add_handler(CommandHandler("remove_user", admin_remove_user))
    app.add_handler(CommandHandler("activate_user", admin_activate_user))
    app.add_handler(CommandHandler("stats", admin_stats))
    
    # 2. Потом обработчик кнопок
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # 3. В конце обработчик текстовых сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("✅ Бот запущен с базой данных SQLite...")
    app.run_polling()

if __name__ == "__main__":
    main()
