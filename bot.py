import os
import logging
import sqlite3
import random
import string
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ================== НАСТРОЙКИ ==================
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))

# Режимы разговора
CHOOSING_ACTION, ENTERING_INVITE, ENTERING_RUN_DATA, CHOOSING_STATS = range(4)

# ================== ЛОГИРОВАНИЕ ==================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================== БАЗА ДАННЫХ SQLITE ==================
DB_NAME = "running_bot.db"

def get_db_connection():
    """Создает соединение с БД и возвращает его"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Инициализация таблиц базы данных"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            invited_by INTEGER,
            is_active INTEGER DEFAULT 1,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invited_by) REFERENCES users (user_id)
        )
    ''')
    
    # Таблица забегов
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
    
    # Таблица кодов приглашений
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS invites (
            code TEXT PRIMARY KEY,
            admin_id INTEGER NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_id) REFERENCES users (user_id)
        )
    ''')
    
    # Индексы для быстрого поиска
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_runs_user_id ON runs(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_runs_run_date ON runs(run_date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_invites_code ON invites(code)')
    
    conn.commit()
    conn.close()
    
    logger.info("База данных инициализирована")

# ================== РАБОТА С БАЗОЙ ДАННЫХ ==================
class DatabaseManager:
    @staticmethod
    def add_user(user_id: int, name: str, invited_by: int = None) -> bool:
        """Добавляет нового пользователя"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO users (user_id, name, invited_by, is_active) VALUES (?, ?, ?, 1)",
                (user_id, name, invited_by)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления пользователя: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def get_user(user_id: int) -> Optional[Dict]:
        """Получает данные пользователя"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения пользователя: {e}")
            return None
        finally:
            conn.close()

    @staticmethod
    def update_user_status(user_id: int, is_active: bool) -> bool:
        """Обновляет статус пользователя"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "UPDATE users SET is_active = ? WHERE user_id = ?",
                (1 if is_active else 0, user_id)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка обновления статуса: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def add_run(user_id: int, city: str, race_name: str, run_date: str, km: float) -> bool:
        """Добавляет забег"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO runs (user_id, city, race_name, run_date, km) VALUES (?, ?, ?, ?, ?)",
                (user_id, city, race_name, run_date, km)
            )
            conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Ошибка добавления забега: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def get_user_runs(user_id: int) -> List[Dict]:
        """Получает все забеги пользователя"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM runs WHERE user_id = ? ORDER BY run_date DESC",
                (user_id,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения забегов: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def get_total_km(user_id: int) -> float:
        """Получает общий километраж пользователя"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT SUM(km) as total FROM runs WHERE user_id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return row['total'] if row and row['total'] else 0.0
        except sqlite3.Error as e:
            logger.error(f"Ошибка подсчета километража: {e}")
            return 0.0
        finally:
            conn.close()

    @staticmethod
    def get_all_active_users() -> List[Dict]:
        """Получает всех активных пользователей"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT * FROM users WHERE is_active = 1 ORDER BY name"
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения пользователей: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def get_all_users_with_stats() -> List[Dict]:
        """Получает всех пользователей с их статистикой"""
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
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def create_invite_code(admin_id: int, code: str = None) -> str:
        """Создает новый код приглашения"""
        if not code:
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
            # Код уже существует, генерируем новый
            if not code:
                return DatabaseManager.create_invite_code(admin_id)
            return None
        except sqlite3.Error as e:
            logger.error(f"Ошибка создания кода: {e}")
            return None
        finally:
            conn.close()

    @staticmethod
    def use_invite_code(code: str) -> Optional[int]:
        """Использует код приглашения, возвращает admin_id"""
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Проверяем и помечаем код как использованный
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
        except sqlite3.Error as e:
            logger.error(f"Ошибка использования кода: {e}")
            return None
        finally:
            conn.close()

    @staticmethod
    def get_invite_codes(admin_id: int = None) -> List[Dict]:
        """Получает список кодов приглашений"""
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
        except sqlite3.Error as e:
            logger.error(f"Ошибка получения кодов: {e}")
            return []
        finally:
            conn.close()

    @staticmethod
    def get_total_all_km() -> float:
        """Получает общий километраж всех пользователей"""
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
        except sqlite3.Error as e:
            logger.error(f"Ошибка подсчета общего километража: {e}")
            return 0.0
        finally:
            conn.close()

# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

def get_user_name(user_id: int) -> str:
    user = DatabaseManager.get_user(user_id)
    return user['name'] if user else "Неизвестный"

def get_stats_text(user_id: int) -> str:
    """Возвращает статистику по конкретному пользователю"""
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
    """Рейтинг всех участников по общему километражу"""
    users_stats = DatabaseManager.get_all_users_with_stats()
    
    if not users_stats:
        return "👥 Нет зарегистрированных участников."
    
    active_users = [u for u in users_stats if u['is_active'] == 1]
    if not active_users:
        return "👥 Нет активных участников."
    
    text = "🏆 Рейтинг участников (по общему км):\n\n"
    
    for i, user in enumerate(active_users[:10], 1):
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
        runs = user['runs_count']
        km = user['total_km']
        text += f"{medal} {user['name']} — {km:.1f} км ({runs} забегов)\n"
    
    if len(active_users) > 10:
        text += f"\n... и еще {len(active_users) - 10} участников"
    
    return text

# ================== КОМАНДЫ БОТА ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    
    # Проверяем, зарегистрирован ли пользователь
    existing_user = DatabaseManager.get_user(user_id)
    if existing_user and existing_user['is_active'] == 1:
        await update.message.reply_text(
            f"👋 Добро пожаловать, {existing_user['name']}!\n"
            "Используйте /menu для доступа к функциям."
        )
        return ConversationHandler.END
    
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
        return ConversationHandler.END
    
    # Обычный пользователь — запрашиваем код приглашения
    await update.message.reply_text(
        "🔐 Это закрытое корпоративное сообщество.\n"
        "Введите код приглашения, полученный от администратора:\n\n"
        "Или напишите /cancel для отмены."
    )
    return ENTERING_INVITE

async def enter_invite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    code = update.message.text.strip().upper()
    
    # Проверяем код
    admin_id = DatabaseManager.use_invite_code(code)
    if admin_id:
        name = update.effective_user.full_name
        if DatabaseManager.add_user(user_id, name, admin_id):
            await update.message.reply_text(
                f"✅ Добро пожаловать, {name}!\n"
                "Теперь вы можете фиксировать свои забеги.\n"
                "Используйте /menu для доступа."
            )
            return ConversationHandler.END
        else:
            await update.message.reply_text("❌ Ошибка регистрации. Попробуйте позже.")
            return ConversationHandler.END
    else:
        await update.message.reply_text(
            "❌ Неверный или уже использованный код приглашения.\n"
            "Пожалуйста, проверьте код и попробуйте снова.\n"
            "Или напишите /cancel для выхода."
        )
        return ENTERING_INVITE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ Операция отменена.")
    return ConversationHandler.END

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user = DatabaseManager.get_user(user_id)
    
    if not user or user['is_active'] != 1:
        await update.message.reply_text(
            "❌ Вы не зарегистрированы или ваш аккаунт деактивирован.\n"
            "Используйте /start для регистрации."
        )
        return
    
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
    
    await update.message.reply_text(
        f"🏃 Главное меню, {user['name']}!",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data == "add_run":
        await query.edit_message_text(
            "📝 Введите данные забега в формате:\n"
            "Город, Название забега, Дата (ГГГГ-ММ-ДД), Километраж\n\n"
            "Пример: Москва, Марафон, 2026-07-14, 42.2\n\n"
            "Или напишите /cancel для отмены."
        )
        return ENTERING_RUN_DATA
    
    elif data == "my_stats":
        text = get_stats_text(user_id)
        await query.edit_message_text(text)
        return ConversationHandler.END
    
    elif data == "rating":
        text = get_rating_text()
        await query.edit_message_text(text)
        return ConversationHandler.END
    
    elif data == "total_km":
        total = DatabaseManager.get_total_all_km()
        await query.edit_message_text(f"📏 Общий километраж сообщества: {total:.1f} км")
        return ConversationHandler.END
    
    elif data == "gen_invite" and is_admin(user_id):
        code = DatabaseManager.create_invite_code(user_id)
        if code:
            await query.edit_message_text(
                f"🔑 Новый код приглашения:\n`{code}`\n\n"
                "Отправьте этот код новому участнику.\n"
                "Код действителен для одного использования."
            )
        else:
            await query.edit_message_text("❌ Ошибка генерации кода.")
        return ConversationHandler.END
    
    elif data == "my_invites" and is_admin(user_id):
        codes = DatabaseManager.get_invite_codes(user_id)
        if not codes:
            await query.edit_message_text("У вас нет созданных кодов приглашений.")
            return ConversationHandler.END
        
        text = "📋 Ваши коды приглашений:\n\n"
        for code in codes[:10]:
            status = "✅ Использован" if code['used'] else "🟢 Активен"
            text += f"`{code['code']}` — {status}\n"
            text += f"   Создан: {code['created_at'][:10]}\n"
        
        if len(codes) > 10:
            text += f"\n... и еще {len(codes) - 10} кодов"
        
        await query.edit_message_text(text)
        return ConversationHandler.END
    
    elif data == "list_users" and is_admin(user_id):
        users_list = DatabaseManager.get_all_active_users()
        if not users_list:
            await query.edit_message_text("👥 Нет активных участников.")
            return ConversationHandler.END
        
        text = "👥 Список активных участников:\n\n"
        for user in users_list:
            total_km = DatabaseManager.get_total_km(user['user_id'])
            runs_count = len(DatabaseManager.get_user_runs(user['user_id']))
            text += f"• {user['name']}\n"
            text += f"  🏃 {runs_count} забегов, 📏 {total_km:.1f} км\n"
        
        await query.edit_message_text(text[:4000])  # Telegram ограничение
        return ConversationHandler.END
    
    return ConversationHandler.END

async def add_run_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    user = DatabaseManager.get_user(user_id)
    
    if not user or user['is_active'] != 1:
        await update.message.reply_text("❌ Вы не зарегистрированы.")
        return ConversationHandler.END
    
    try:
        parts = [p.strip() for p in update.message.text.split(",")]
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
        else:
            await update.message.reply_text("❌ Ошибка сохранения забега. Попробуйте позже.")
        
    except ValueError as e:
        await update.message.reply_text(
            f"❌ Ошибка: {e}\n\n"
            "📝 Правильный формат:\n"
            "Город, Название, ГГГГ-ММ-ДД, Километраж\n\n"
            "Пример: Москва, Марафон, 2026-07-14, 42.2\n\n"
            "Попробуйте снова или /cancel"
        )
        return ENTERING_RUN_DATA
    
    return ConversationHandler.END

# ================== АДМИН-КОМАНДЫ ==================
async def admin_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Админ может добавить пользователя вручную: /add_user ID Имя"""
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
    """Админ может деактивировать пользователя: /remove_user ID"""
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
    """Админ может активировать пользователя: /activate_user ID"""
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
    """Показывает общую статистику сообщества: /stats"""
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
    
    # Conversation для регистрации с кодом
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ENTERING_INVITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_invite)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)
    
    # Conversation для добавления забега
    run_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^add_run$")],
        states={
            ENTERING_RUN_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_run_data)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(run_conv)
    
    # Остальные callback обработчики
    app.add_handler(CallbackQueryHandler(
        button_handler, 
        pattern="^(my_stats|rating|total_km|gen_invite|my_invites|list_users)$"
    ))
    
    # Команды
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("add_user", admin_add_user))
    app.add_handler(CommandHandler("remove_user", admin_remove_user))
    app.add_handler(CommandHandler("activate_user", admin_activate_user))
    app.add_handler(CommandHandler("stats", admin_stats))
    
    # Обработчик для остальных сообщений
    async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "❓ Неизвестная команда.\n"
            "Используйте /menu для доступа к функциям."
        )
    
    app.add_handler(MessageHandler(filters.COMMAND, unknown))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text(
        "Используйте /menu для доступа к функциям бота."
    )))
    
    logger.info("Бот запущен с базой данных SQLite...")
    app.run_polling()

if __name__ == "__main__":
    main()
