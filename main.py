import os
import re
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import sqlite3
import json
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from telethon import TelegramClient, functions, types
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
    UserNotParticipantError,
    RPCError,
    ChannelInvalidError,
    ChannelPrivateError,
    UsernameNotOccupiedError
)

# بارگذاری environment variables
load_dotenv()

# ==================== تنظیمات ====================

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN not found in environment variables!")

ALLOWED_USERS = [int(id.strip()) for id in os.getenv("ALLOWED_USERS", "").split(",") if id.strip()]
REPORT_CHANNEL = os.getenv("REPORT_CHANNEL", "@ValkyrieReport")
REPORT_CHANNEL_ID = int(os.getenv("REPORT_CHANNEL_ID", "-1004392030066"))

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== دیتابیس ====================

DB_FILE = "bot_database.db"
SESSIONS_DIR = "sessions"

os.makedirs(SESSIONS_DIR, exist_ok=True)

class Database:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self.init_db()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # جدول کاربران
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                is_admin INTEGER DEFAULT 0,
                joined_date TEXT,
                is_banned INTEGER DEFAULT 0
            )
        ''')
        
        # جدول اکانت‌ها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                user_id INTEGER,
                session_file TEXT,
                api_id TEXT,
                api_hash TEXT,
                created_at TEXT,
                is_active INTEGER DEFAULT 1,
                last_used TEXT,
                is_valid INTEGER DEFAULT 1
            )
        ''')
        
        # جدول گزارشات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT,
                group_link TEXT,
                report_text TEXT,
                accounts_count INTEGER,
                repeat_count INTEGER,
                success_count INTEGER,
                fail_count INTEGER,
                total_count INTEGER,
                join_results TEXT,
                results TEXT,
                user_id INTEGER,
                created_at TEXT
            )
        ''')
        
        # جدول تنظیمات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # جدول لاگ
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                created_at TEXT
            )
        ''')
        
        # اضافه کردن ادمین‌های اولیه
        for user_id in ALLOWED_USERS:
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, is_admin, joined_date)
                VALUES (?, 1, ?)
            ''', (user_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    
    # ==================== توابع کاربران ====================
    
    def add_user(self, user_id, username=None, first_name=None, last_name=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_date)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, datetime.now().isoformat()))
        conn.commit()
        conn.close()
    
    def is_admin(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT is_admin FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result and result[0] == 1
    
    def get_admins(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE is_admin = 1')
        results = cursor.fetchall()
        conn.close()
        return [row[0] for row in results]
    
    def add_admin(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_admin = 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    
    def remove_admin(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_admin = 0 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    
    # ==================== توابع اکانت‌ها ====================
    
    def add_account(self, phone, username, first_name, last_name, user_id, session_file, api_id, api_hash):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO accounts 
            (phone, username, first_name, last_name, user_id, session_file, api_id, api_hash, created_at, is_active, is_valid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (phone, username, first_name, last_name, user_id, session_file, api_id, api_hash, datetime.now().isoformat(), 1, 1))
        conn.commit()
        conn.close()
        logger.info(f"Account added: {phone}")
    
    def get_accounts(self, only_valid=True):
        conn = self.get_connection()
        cursor = conn.cursor()
        if only_valid:
            cursor.execute('SELECT * FROM accounts WHERE is_active = 1 AND is_valid = 1 ORDER BY id ASC')
        else:
            cursor.execute('SELECT * FROM accounts WHERE is_active = 1 ORDER BY id ASC')
        results = cursor.fetchall()
        conn.close()
        return [dict(row) for row in results]
    
    def get_account(self, phone):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM accounts WHERE phone = ? AND is_active = 1', (phone,))
        result = cursor.fetchone()
        conn.close()
        return dict(result) if result else None
    
    def delete_account(self, phone):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE accounts SET is_active = 0 WHERE phone = ?', (phone,))
        conn.commit()
        conn.close()
        logger.info(f"Account deleted: {phone}")
    
    def mark_account_invalid(self, phone, reason):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE accounts SET is_valid = 0 WHERE phone = ?', (phone,))
        conn.commit()
        conn.close()
        logger.warning(f"Account marked invalid: {phone} - {reason}")
    
    def update_account_last_used(self, phone):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE accounts SET last_used = ? WHERE phone = ?', (datetime.now().isoformat(), phone))
        conn.commit()
        conn.close()
    
    # ==================== توابع گزارشات ====================
    
    def add_report(self, group_name, group_link, report_text, accounts_count, repeat_count, 
                   success_count, fail_count, total_count, join_results, results, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reports 
            (group_name, group_link, report_text, accounts_count, repeat_count, 
             success_count, fail_count, total_count, join_results, results, user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (group_name, group_link, report_text, accounts_count, repeat_count,
              success_count, fail_count, total_count, 
              json.dumps(join_results), json.dumps(results), 
              user_id, datetime.now().isoformat()))
        conn.commit()
        report_id = cursor.lastrowid
        conn.close()
        logger.info(f"Report saved: ID {report_id}")
        return report_id
    
    def get_reports(self, limit=10):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM reports 
            ORDER BY id DESC 
            LIMIT ?
        ''', (limit,))
        results = cursor.fetchall()
        conn.close()
        reports = []
        for row in results:
            report = dict(row)
            report['join_results'] = json.loads(report['join_results']) if report['join_results'] else []
            report['results'] = json.loads(report['results']) if report['results'] else []
            reports.append(report)
        return reports
    
    # ==================== توابع لاگ ====================
    
    def add_log(self, user_id, action, details=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO logs (user_id, action, details, created_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, action, details, datetime.now().isoformat()))
        conn.commit()
        conn.close()

# ایجاد نمونه دیتابیس
db = Database()

# ==================== متغیرها ====================

user_states = {}
user_temp = {}
report_temp = {}
processing_reports = set()

# ==================== بررسی دسترسی ====================

def is_allowed(user_id):
    if user_id in ALLOWED_USERS:
        return True
    return db.is_admin(user_id)

def check_user_access(update):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        logger.warning(f"Unauthorized access attempt from user {user_id}")
        return False
    return True

# ==================== منوها ====================

def main_menu():
    keyboard = [
        [InlineKeyboardButton("🛡 ریپورت گروهی", callback_data="report_group")],
        [
            InlineKeyboardButton("➕ افزودن اکانت", callback_data="add_account"),
            InlineKeyboardButton("📋 لیست اکانت‌ها", callback_data="list_accounts")
        ],
        [
            InlineKeyboardButton("📊 گزارشات", callback_data="reports"),
            InlineKeyboardButton("👤 مدیریت ادمین", callback_data="manage_admins")
        ],
        [
            InlineKeyboardButton("📣 کانال گزارشات", url="https://t.me/ValkyrieReport"),
            InlineKeyboardButton("❓ راهنما", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")]])

# ==================== شروع ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    
    db.add_user(user_id, user.username, user.first_name, user.last_name)
    
    if not check_user_access(update):
        await update.message.reply_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    text = """
🌟 <b>به ربات مدیریت تلگرام خوش آمدید!</b>

📌 <b>قابلیت‌ها:</b>
🛡 ریپورت گروهی با چندین اکانت
➕ افزودن اکانت با سشن
📋 مدیریت اکانت‌ها
📊 مشاهده گزارشات
📣 ارسال گزارش به کانال

برای شروع یکی از گزینه‌ها رو انتخاب کن.
"""
    await update.message.reply_text(text, reply_markup=main_menu(), parse_mode='HTML')
    db.add_log(user_id, "start", "User started bot")

# ==================== افزودن اکانت ====================

async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    user_id = query.from_user.id
    user_temp[user_id] = {}
    user_states[user_id] = "waiting_phone"
    
    text = """
➕ <b>افزودن اکانت جدید</b>

برای اضافه کردن اکانت، اطلاعات زیر رو وارد کن:

1️⃣ شماره تلفن (با کد کشور)
   مثال: <code>+989123456789</code>

📱 <b>شماره تلفن</b> رو وارد کن:
"""
    await query.edit_message_text(text, reply_markup=back_button(), parse_mode='HTML')

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_phone":
        return
    
    phone = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        await update.message.reply_text(
            "❌ شماره نامعتبر! لطفاً با کد کشور وارد کن.\nمثال: <code>+989123456789</code>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    user_temp[user_id]['phone'] = phone
    user_states[user_id] = "waiting_api_id"
    
    await update.message.reply_text(
        f"✅ شماره <code>{phone}</code> ثبت شد.\n\n"
        "🔑 <b>API ID</b> رو وارد کن:\n"
        "(از سایت my.telegram.org دریافت کن)",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_api_id":
        return
    
    api_id = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    
    try:
        api_id_int = int(api_id)
        if api_id_int <= 0 or api_id_int > 2147483647:
            await update.message.reply_text(
                "❌ API ID باید بین 1 تا 2147483647 باشه.",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            return
    except ValueError:
        await update.message.reply_text(
            "❌ API ID باید عدد باشه! لطفاً دوباره وارد کن.",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    user_temp[user_id]['api_id'] = api_id
    user_states[user_id] = "waiting_api_hash"
    
    await update.message.reply_text(
        f"✅ API ID ثبت شد.\n\n"
        "🔐 <b>API Hash</b> رو وارد کن:\n"
        "(از my.telegram.org دریافت کن)",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_api_hash":
        return
    
    api_hash = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    
    if len(api_hash) < 20:
        await update.message.reply_text(
            "❌ API Hash نامعتبر! لطفاً دوباره وارد کن.",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    user_temp[user_id]['api_hash'] = api_hash
    user_states[user_id] = "waiting_code"
    
    status_msg = await update.message.reply_text(
        "⏳ در حال ارسال کد تایید به تلگرام...\nلطفاً صبر کن...",
        parse_mode='HTML'
    )
    
    await start_connection(user_id, update, status_msg)

async def start_connection(user_id, update, status_msg):
    temp = user_temp.get(user_id, {})
    phone = temp.get("phone")
    api_id = temp.get("api_id")
    api_hash = temp.get("api_hash")
    
    if not all([phone, api_id, api_hash]):
        await status_msg.edit_text("❌ اطلاعات کامل نیست!", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{phone}.session")
        client = TelegramClient(session_file, int(api_id), api_hash)
        
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            user_temp[user_id]['client'] = client
            
            await status_msg.edit_text(
                f"📨 <b>کد تایید ارسال شد!</b>\n\n"
                f"📱 شماره: <code>{phone}</code>\n\n"
                "🔑 کد تایید رو به صورت <b>۱.۲.۳.۴.۵</b> وارد کن:",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            user_states[user_id] = "waiting_code"
        else:
            await get_account_info(update, client, user_id, status_msg)
            
    except PhoneNumberInvalidError:
        await status_msg.edit_text("❌ شماره وارد شده معتبر نیست!", reply_markup=main_menu(), parse_mode='HTML')
    except FloodWaitError as e:
        await status_msg.edit_text(f"⏳ لطفاً {e.seconds} ثانیه صبر کن.", reply_markup=main_menu(), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Connection error: {e}\n{traceback.format_exc()}")
        await status_msg.edit_text(f"❌ خطا در اتصال!\n\n{str(e)}", reply_markup=main_menu(), parse_mode='HTML')

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_code":
        return
    
    code_input = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    
    code = code_input.replace('.', '').replace('،', '').replace(' ', '').strip()
    
    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text(
            "❌ کد باید ۵ رقم باشه! مثال: <code>12345</code>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    status_msg = await update.message.reply_text("⏳ در حال تایید کد...", parse_mode='HTML')
    
    client = user_temp.get(user_id, {}).get('client')
    if not client:
        await status_msg.edit_text("❌ خطا در اتصال!", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    try:
        await client.sign_in(code=code)
        await get_account_info(update, client, user_id, status_msg)
        
    except SessionPasswordNeededError:
        user_states[user_id] = "waiting_password"
        await status_msg.edit_text(
            "🔑 <b>این اکانت پسورد (Two-Factor) داره!</b>\n\n"
            "⚠️ توجه: پسورد شما امن است و ذخیره نمی‌شود",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        
    except PhoneCodeExpiredError:
        await status_msg.edit_text("❌ کد منقضی شده! در حال ارسال مجدد...", reply_markup=back_button(), parse_mode='HTML')
        try:
            phone = user_temp.get(user_id, {}).get("phone")
            await client.send_code_request(phone)
            await update.message.reply_text("📨 کد جدید ارسال شد!", reply_markup=back_button(), parse_mode='HTML')
        except Exception as e:
            await status_msg.edit_text(f"❌ خطا: {str(e)}", reply_markup=main_menu(), parse_mode='HTML')
        
    except PhoneCodeInvalidError:
        await status_msg.edit_text("❌ کد اشتباه! دوباره وارد کن:", reply_markup=back_button(), parse_mode='HTML')
        user_states[user_id] = "waiting_code"
        
    except Exception as e:
        logger.error(f"Code verification error: {e}\n{traceback.format_exc()}")
        await status_msg.edit_text(f"❌ خطا در تایید کد!\n\n{str(e)}", reply_markup=main_menu(), parse_mode='HTML')

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_password":
        return
    
    password = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    
    if len(password) < 4:
        await update.message.reply_text("❌ پسورد حداقل ۴ کاراکتر!", reply_markup=back_button(), parse_mode='HTML')
        return
    
    status_msg = await update.message.reply_text("⏳ در حال تایید پسورد...", parse_mode='HTML')
    
    client = user_temp.get(user_id, {}).get('client')
    if not client:
        await status_msg.edit_text("❌ خطا در اتصال!", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    try:
        await client.sign_in(password=password)
        await get_account_info(update, client, user_id, status_msg)
    except Exception as e:
        logger.error(f"Password error: {e}\n{traceback.format_exc()}")
        await status_msg.edit_text(f"❌ پسورد اشتباه!\n\n{str(e)}", reply_markup=back_button(), parse_mode='HTML')

async def get_account_info(update, client, user_id, status_msg):
    try:
        me = await client.get_me()
        
        phone = me.phone
        username = me.username
        first_name = me.first_name
        last_name = me.last_name
        telegram_id = me.id
        session_file = client.session.filename
        api_id = user_temp.get(user_id, {}).get("api_id")
        api_hash = user_temp.get(user_id, {}).get("api_hash")
        
        existing = db.get_account(phone)
        if existing:
            await status_msg.edit_text("⚠️ این اکانت قبلاً ثبت شده!", reply_markup=main_menu(), parse_mode='HTML')
            if user_id in user_temp:
                del user_temp[user_id]
            if user_id in user_states:
                del user_states[user_id]
            await client.disconnect()
            return
        
        db.add_account(phone, username, first_name, last_name, telegram_id, session_file, api_id, api_hash)
        db.add_log(user_id, "add_account", f"Added account {phone}")
        
        await status_msg.edit_text(
            f"✅ <b>اکانت با موفقیت اضافه شد!</b>\n\n"
            f"📱 شماره: <code>{phone}</code>\n"
            f"👤 نام: {first_name} {last_name or ''}\n"
            f"🆔 آیدی: <code>{telegram_id}</code>\n\n"
            "🎉 اکانت آماده استفاده است!",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        
        if user_id in user_temp:
            del user_temp[user_id]
        if user_id in user_states:
            del user_states[user_id]
        
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"Get account error: {e}\n{traceback.format_exc()}")
        await status_msg.edit_text(f"❌ خطا: {str(e)}", reply_markup=main_menu(), parse_mode='HTML')

# ==================== لیست و حذف اکانت ====================

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    accounts = db.get_accounts()
    if not accounts:
        await query.edit_message_text("📭 <b>هیچ اکانتی ثبت نشده!</b>", reply_markup=back_button(), parse_mode='HTML')
        return
    
    text = "📋 <b>لیست اکانت‌های فعال:</b>\n\n"
    for i, acc in enumerate(accounts, 1):
        status = "✅" if acc.get('is_valid', 1) else "❌"
        text += f"{status} <b>{i}.</b> 📱 <code>{acc['phone']}</code>\n"
        text += f"   👤 {acc['first_name'] or ''} {acc['last_name'] or ''}\n"
        if acc['username']:
            text += f"   🆔 @{acc['username']}\n"
        text += "─" * 25 + "\n"
    
    keyboard = [
        [InlineKeyboardButton("🗑 حذف اکانت", callback_data="delete_account_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def delete_account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    accounts = db.get_accounts()
    if not accounts:
        await query.edit_message_text("📭 اکانتی برای حذف نیست!", reply_markup=back_button(), parse_mode='HTML')
        return
    
    keyboard = []
    for i, acc in enumerate(accounts):
        keyboard.append([InlineKeyboardButton(f"🗑 {acc['phone']}", callback_data=f"delete_acc_{i}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="list_accounts")])
    
    await query.edit_message_text("🗑 <b>انتخاب اکانت برای حذف:</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    user_id = query.from_user.id
    index = int(query.data.split("_")[2])
    
    accounts = db.get_accounts()
    if index >= len(accounts):
        await query.answer("❌ یافت نشد!", show_alert=True)
        return
    
    account = accounts[index]
    phone = account['phone']
    
    session_file = account.get('session_file')
    if session_file and os.path.exists(session_file):
        try:
            os.remove(session_file)
            logger.info(f"Session file deleted: {session_file}")
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
    
    db.delete_account(phone)
    db.add_log(user_id, "delete_account", f"Deleted account {phone}")
    
    await query.edit_message_text(f"✅ اکانت {phone} حذف شد!", reply_markup=back_button(), parse_mode='HTML')

# ==================== ریپورت گروهی ====================

async def report_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    user_id = query.from_user.id
    
    accounts = db.get_accounts()
    if len(accounts) < 1:
        await query.edit_message_text("⚠️ <b>هیچ اکانتی ثبت نشده!</b>", reply_markup=back_button(), parse_mode='HTML')
        return
    
    report_temp[user_id] = {}
    user_states[user_id] = "waiting_report_group"
    
    await query.edit_message_text(
        "🛡 <b>ریپورت گروهی/کانال</b>\n\n"
        "برای ریپورت یک گروه یا کانال، مراحل زیر رو طی کن:\n\n"
        "1️⃣ لینک گروه یا کانال رو بفرست\n"
        "2️⃣ لینک پست مورد نظر رو بفرست\n"
        "3️⃣ متن ریپورت رو وارد کن\n"
        "4️⃣ تعداد اکانت‌ها رو مشخص کن\n"
        "5️⃣ تعداد دفعات ریپورت رو تعیین کن\n\n"
        "📎 <b>لینک گروه</b> رو بفرست:\n"
        "مثال: <code>@username</code> یا <code>https://t.me/username</code>",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_report_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_group":
        return
    
    link = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    
    username = link
    if 't.me/' in link:
        if '+' in link:
            invite_hash = link.split('t.me/')[-1].split('/')[0] if '/' in link.split('t.me/')[-1] else link.split('t.me/')[-1]
            username = f"+{invite_hash}"
        else:
            username = link.split('t.me/')[-1].split('/')[0]
    
    if username.startswith('@'):
        username = username[1:]
    
    if not username:
        await update.message.reply_text("❌ لینک نامعتبر!", reply_markup=back_button(), parse_mode='HTML')
        return
    
    report_temp[user_id]["group"] = username
    report_temp[user_id]["group_link"] = link
    user_states[user_id] = "waiting_report_post"
    
    await update.message.reply_text(
        f"✅ لینک گروه ثبت شد.\n\n"
        "📝 <b>لینک پست</b> رو بفرست:\n"
        "مثال: <code>https://t.me/username/123</code>",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_report_post_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_post":
        return
    
    post_link = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    
    match = re.search(r'https?://t\.me/([\w_+]+)/(\d+)', post_link)
    if not match:
        match = re.search(r'https?://t\.me/c/(\d+)/(\d+)', post_link)
    
    if not match:
        await update.message.reply_text(
            "❌ لینک پست نامعتبر!\nلطفاً یک لینک معتبر بفرست:",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    report_temp[user_id]["post_link"] = post_link
    report_temp[user_id]["msg_id"] = int(match.group(2))
    user_states[user_id] = "waiting_report_text"
    
    await update.message.reply_text(
        f"✅ لینک پست ثبت شد.\n\n"
        "📄 <b>متن ریپورت</b> رو وارد کن:\n"
        "مثال: <i>این گروه کلاهبرداری است</i>",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_report_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_text":
        return
    
    report_text = update.message.text.strip()
    try:
        await update.message.delete()
    except:
        pass
    
    if len(report_text) < 10:
        await update.message.reply_text("❌ متن حداقل ۱۰ کاراکتر!", reply_markup=back_button(), parse_mode='HTML')
        return
    
    report_temp[user_id]["text"] = report_text
    user_states[user_id] = "waiting_report_count"
    
    accounts = db.get_accounts()
    available = len(accounts)
    await update.message.reply_text(
        f"✅ متن ثبت شد.\n\n"
        f"📊 <b>تعداد اکانت‌ها</b> (حداکثر {available}):",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_report_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_count":
        return
    
    try:
        await update.message.delete()
    except:
        pass
    
    try:
        count = int(update.message.text.strip())
        accounts = db.get_accounts()
        available = len(accounts)
        
        if count < 1 or count > available:
            await update.message.reply_text(f"❌ بین ۱ تا {available} وارد کن!", reply_markup=back_button(), parse_mode='HTML')
            return
        
        report_temp[user_id]["count"] = count
        user_states[user_id] = "waiting_report_repeat"
        
        await update.message.reply_text(
            f"✅ تعداد: {count}\n\n"
            "🔄 <b>تعداد دفعات</b> (۱ تا ۳):\n"
            "(توصیه: ۱ بار برای جلوگیری از محدودیت)",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        
    except ValueError:
        await update.message.reply_text("❌ عدد وارد کن!", reply_markup=back_button(), parse_mode='HTML')

async def handle_report_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_repeat":
        return
    
    try:
        await update.message.delete()
    except:
        pass
    
    try:
        repeat = int(update.message.text.strip())
        
        if repeat < 1 or repeat > 3:
            await update.message.reply_text("❌ بین ۱ تا ۳ وارد کن!", reply_markup=back_button(), parse_mode='HTML')
            return
        
        report_temp[user_id]["repeat"] = repeat
        
        temp = report_temp.get(user_id, {})
        
        summary = f"""
📋 <b>خلاصه ریپورت:</b>

🎯 <b>گروه:</b> {temp.get('group_link', 'نامشخص')}
📝 <b>لینک پست:</b> {temp.get('post_link', 'نامشخص')}
📄 <b>متن ریپورت:</b> {temp.get('text', 'نامشخص')}
🔢 <b>تعداد اکانت‌ها:</b> {temp.get('count', 0)}
🔄 <b>تعداد دفعات:</b> {temp.get('repeat', 0)}

⚠️ <b>آیا از انجام این ریپورت مطمئنی؟</b>
"""
        
        keyboard = [
            [InlineKeyboardButton("✅ تایید و اجرا", callback_data=f"execute_report_{user_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data="cancel_report")]
        ]
        
        await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
        if user_id in user_states:
            del user_states[user_id]
        
    except ValueError:
        await update.message.reply_text("❌ عدد وارد کن!", reply_markup=back_button(), parse_mode='HTML')

# ==================== اجرای ریپورت (نسخه نهایی) ====================

async def execute_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    target_user_id = int(query.data.split("_")[2])
    
    if user_id != target_user_id:
        await query.answer("❌ این دکمه مال شما نیست!", show_alert=True)
        return
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    if user_id in processing_reports:
        await query.answer("⏳ در حال اجراست!", show_alert=True)
        return
    
    temp = report_temp.get(user_id, {})
    if not temp:
        await query.edit_message_text("❌ اطلاعات یافت نشد!", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    processing_reports.add(user_id)
    
    try:
        await query.edit_message_text(
            "⏳ <b>در حال اجرای ریپورت...</b>\n\nلطفاً صبر کن...",
            parse_mode='HTML'
        )
        
        group = temp.get("group")
        group_link = temp.get("group_link")
        text = temp.get("text", "گزارش کلاهبرداری و اسکم")
        count = temp.get("count", 1)
        repeat = temp.get("repeat", 1)
        msg_id = temp.get("msg_id")
        
        accounts = db.get_accounts()[:count]
        
        if len(accounts) < count:
            await query.edit_message_text("❌ تعداد اکانت کافی نیست!", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        success = 0
        fail = 0
        results = []
        join_results = []
        
        # مرحله 1: جوین شدن
        for account in accounts:
            try:
                session_file = account.get("session_file")
                if not session_file or not os.path.exists(session_file):
                    join_results.append(f"❌ {account['phone']}: سشن یافت نشد")
                    continue
                
                # ✅ استفاده از API ID و Hash ذخیره شده - بدون fallback
                api_id = account.get("api_id")
                api_hash = account.get("api_hash")
                
                if not api_id or not api_hash:
                    error_msg = f"API credentials missing for {account['phone']}"
                    logger.error(error_msg)
                    db.mark_account_invalid(account['phone'], "Missing API credentials")
                    join_results.append(f"❌ {account['phone']}: اطلاعات API موجود نیست")
                    continue
                
                client = TelegramClient(session_file, int(api_id), api_hash)
                await client.connect()
                
                if not await client.is_user_authorized():
                    db.mark_account_invalid(account['phone'], "Not authorized")
                    join_results.append(f"❌ {account['phone']}: احراز نشده")
                    await client.disconnect()
                    continue
                
                try:
                    entity = await client.get_entity(f"@{group}")
                    try:
                        await client(functions.channels.JoinChannelRequest(entity))
                        join_results.append(f"✅ {account['phone']}: جوین شد")
                    except FloodWaitError as e:
                        join_results.append(f"⏳ {account['phone']}: صبر {e.seconds}s")
                        await asyncio.sleep(min(e.seconds, 5))
                    except Exception as e:
                        if "already" in str(e).lower():
                            join_results.append(f"⚠️ {account['phone']}: قبلاً جوین بود")
                        else:
                            join_results.append(f"❌ {account['phone']}: خطا در جوین - {str(e)[:50]}")
                    await asyncio.sleep(1)
                except (ChannelInvalidError, ChannelPrivateError, UsernameNotOccupiedError) as e:
                    join_results.append(f"❌ {account['phone']}: گروه نامعتبر یا خصوصی - {str(e)[:30]}")
                except Exception as e:
                    join_results.append(f"❌ {account['phone']}: خطا - {str(e)[:50]}")
                
                await client.disconnect()
                db.update_account_last_used(account['phone'])
                
            except Exception as e:
                join_results.append(f"❌ {account['phone']}: خطا - {str(e)[:50]}")
        
        # مرحله 2: ریپورت - فقط برای اکانت‌هایی که جوین شده‌اند یا حداقل معتبر هستند
        for account in accounts:
            try:
                session_file = account.get("session_file")
                if not session_file or not os.path.exists(session_file):
                    fail += 1
                    results.append(f"❌ {account['phone']}: سشن یافت نشد")
                    continue
                
                api_id = account.get("api_id")
                api_hash = account.get("api_hash")
                
                if not api_id or not api_hash:
                    fail += 1
                    results.append(f"❌ {account['phone']}: اطلاعات API موجود نیست")
                    continue
                
                client = TelegramClient(session_file, int(api_id), api_hash)
                await client.connect()
                
                if not await client.is_user_authorized():
                    fail += 1
                    results.append(f"❌ {account['phone']}: احراز نشده")
                    await client.disconnect()
                    continue
                
                try:
                    entity = await client.get_entity(f"@{group}")
                except (ChannelInvalidError, ChannelPrivateError, UsernameNotOccupiedError) as e:
                    fail += 1
                    results.append(f"❌ {account['phone']}: گروه نامعتبر - {str(e)[:30]}")
                    await client.disconnect()
                    continue
                except Exception as e:
                    fail += 1
                    results.append(f"❌ {account['phone']}: خطا - {str(e)[:50]}")
                    await client.disconnect()
                    continue
                
                for i in range(repeat):
                    try:
                        await client(functions.messages.ReportRequest(
                            peer=entity,
                            id=[msg_id],
                            reason=types.InputReportReasonSpam(),
                            message=text
                        ))
                        success += 1
                        # توجه: موفقیت فقط به معنی ارسال درخواست است، نه تایید نهایی توسط تلگرام
                        results.append(f"✅ {account['phone']}: درخواست ریپورت {i+1} ارسال شد")
                        await asyncio.sleep(2)
                    except FloodWaitError as e:
                        fail += 1
                        results.append(f"⏳ {account['phone']}: صبر {e.seconds} ثانیه")
                        await asyncio.sleep(min(e.seconds, 10))
                    except Exception as e:
                        fail += 1
                        results.append(f"❌ {account['phone']}: خطا در ریپورت {i+1} - {str(e)[:50]}")
                        await asyncio.sleep(1)
                
                await client.disconnect()
                db.update_account_last_used(account['phone'])
                
            except Exception as e:
                fail += 1
                results.append(f"❌ {account['phone']}: خطا - {str(e)[:50]}")
        
        # ثبت گزارش در دیتابیس
        report_id = db.add_report(
            group, group_link, text, count, repeat,
            success, fail, success + fail,
            join_results, results, user_id
        )
        
        db.add_log(user_id, "execute_report", f"Report {report_id} executed - Success: {success}, Fail: {fail}")
        
        # نتیجه
        result_text = f"""
📊 <b>نتیجه ریپورت:</b>

🎯 گروه: {group_link}
✅ درخواست ریپورت ارسال شده: {success}
❌ خطا: {fail}
📋 مجموع تلاش: {success + fail}

⚠️ <b>توجه:</b> "موفق" به معنی ارسال موفق درخواست به تلگرام است، نه تایید نهایی گزارش توسط تلگرام.

📋 <b>وضعیت جوین:</b>
"""
        
        for jr in join_results[:3]:
            result_text += f"\n{jr}"
        
        if len(join_results) > 3:
            result_text += f"\n... {len(join_results)-3} نتیجه دیگر"
        
        result_text += f"\n\n📋 <b>نتیجه ریپورت:</b>"
        
        for r in results[:3]:
            result_text += f"\n{r}"
        
        if len(results) > 3:
            result_text += f"\n... {len(results)-3} نتیجه دیگر"
        
        await query.edit_message_text(result_text, reply_markup=main_menu(), parse_mode='HTML')
        
        # ارسال به کانال
        await send_report_to_channel(context, {
            "group_link": group_link,
            "text": text,
            "accounts": count,
            "repeat": repeat,
            "success": success,
            "fail": fail,
            "total": success + fail,
            "results": results,
            "date": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Report execution error: {e}\n{traceback.format_exc()}")
        await query.edit_message_text(f"❌ خطا: {str(e)}", reply_markup=main_menu(), parse_mode='HTML')
    finally:
        processing_reports.discard(user_id)
        if user_id in report_temp:
            del report_temp[user_id]

# ==================== ارسال به کانال ====================

async def send_report_to_channel(context, report_data):
    try:
        text = f"""
📊 <b>گزارش جدید ریپورت</b>

🎯 <b>گروه/کانال:</b> {report_data.get('group_link', 'نامشخص')}
📝 <b>متن ریپورت:</b> {report_data.get('text', 'نامشخص')}
🔢 <b>تعداد اکانت‌ها:</b> {report_data.get('accounts', 0)}
🔄 <b>تعداد دفعات:</b> {report_data.get('repeat', 0)}
✅ <b>درخواست ارسال شده:</b> {report_data.get('success', 0)}
❌ <b>خطا:</b> {report_data.get('fail', 0)}
📋 <b>مجموع:</b> {report_data.get('total', 0)}
📅 <b>تاریخ:</b> {report_data.get('date', '')[:19]}

⚠️ <b>نکته:</b> "موفق" به معنی ارسال موفق درخواست است، نه تایید نهایی تلگرام.

📋 <b>جزئیات:</b>
"""
        
        for r in report_data.get('results', [])[:5]:
            text += f"\n{r}"
        
        if len(report_data.get('results', [])) > 5:
            text += f"\n... {len(report_data.get('results', []))-5} نتیجه دیگر"
        
        await context.bot.send_message(
            chat_id=REPORT_CHANNEL_ID,
            text=text,
            parse_mode='HTML'
        )
        
        logger.info(f"Report sent to channel")
        
    except Exception as e:
        logger.error(f"Error sending report to channel: {e}")

# ==================== بقیه توابع ====================

async def show_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    reports = db.get_reports(10)
    if not reports:
        await query.edit_message_text("📭 <b>هیچ گزارشی ثبت نشده!</b>", reply_markup=back_button(), parse_mode='HTML')
        return
    
    text = "📊 <b>تاریخچه ریپورت‌ها:</b>\n\n"
    for i, r in enumerate(reports[:5], 1):
        text += f"{i}. 🎯 {r.get('group_name', 'نامشخص')}\n"
        text += f"   ✅ ارسال: {r.get('success_count', 0)}\n"
        text += f"   ❌ خطا: {r.get('fail_count', 0)}\n"
        text += f"   📅 {r.get('created_at', '')[:10]}\n"
        text += "─" * 25 + "\n"
    
    await query.edit_message_text(text, reply_markup=back_button(), parse_mode='HTML')

async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    keyboard = [
        [InlineKeyboardButton("➕ افزودن ادمین", callback_data="add_admin")],
        [InlineKeyboardButton("🗑 حذف ادمین", callback_data="remove_admin")],
        [InlineKeyboardButton("📋 لیست ادمین‌ها", callback_data="list_admins")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(
        "👥 <b>مدیریت ادمین‌ها</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    user_states[query.from_user.id] = "waiting_admin_id"
    await query.edit_message_text(
        "➕ <b>افزودن ادمین</b>\n\n🆔 آیدی عددی رو وارد کن:",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_admin_id":
        return
    
    try:
        await update.message.delete()
    except:
        pass
    
    try:
        admin_id = int(update.message.text.strip())
        
        if db.is_admin(admin_id):
            await update.message.reply_text("⚠️ قبلاً ادمین هست!", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        if admin_id in ALLOWED_USERS:
            await update.message.reply_text("⚠️ در لیست اصلی هست!", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        db.add_admin(admin_id)
        db.add_log(user_id, "add_admin", f"Added admin {admin_id}")
        
        await update.message.reply_text(f"✅ ادمین <code>{admin_id}</code> اضافه شد!", reply_markup=main_menu(), parse_mode='HTML')
        del user_states[user_id]
            
    except ValueError:
        await update.message.reply_text("❌ عدد وارد کن!", reply_markup=main_menu(), parse_mode='HTML')

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    admins = db.get_admins()
    admins = [a for a in admins if a not in ALLOWED_USERS]
    
    if not admins:
        await query.edit_message_text("📭 ادمین اضافه‌ای نیست!", reply_markup=back_button(), parse_mode='HTML')
        return
    
    keyboard = []
    for admin in admins:
        keyboard.append([InlineKeyboardButton(f"🗑 {admin}", callback_data=f"remove_adm_{admin}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="manage_admins")])
    
    await query.edit_message_text("🗑 انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def remove_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    user_id = query.from_user.id
    admin_id = int(query.data.split("_")[2])
    
    if db.is_admin(admin_id) and admin_id not in ALLOWED_USERS:
        db.remove_admin(admin_id)
        db.add_log(user_id, "remove_admin", f"Removed admin {admin_id}")
        await query.edit_message_text(f"✅ ادمین {admin_id} حذف شد!", reply_markup=back_button(), parse_mode='HTML')
    else:
        await query.answer("❌ یافت نشد!", show_alert=True)

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    text = "👥 <b>لیست ادمین‌ها:</b>\n\n"
    text += "🔹 <b>ادمین‌های اصلی:</b>\n"
    for uid in ALLOWED_USERS:
        text += f"   • <code>{uid}</code>\n"
    
    admins = db.get_admins()
    extra_admins = [a for a in admins if a not in ALLOWED_USERS]
    
    if extra_admins:
        text += "\n🔸 <b>اضافه شده:</b>\n"
        for admin in extra_admins:
            text += f"   • <code>{admin}</code>\n"
    else:
        text += "\n📭 <i>هیچ ادمین اضافه‌ای ثبت نشده.</i>"
    
    await query.edit_message_text(text, reply_markup=back_button(), parse_mode='HTML')

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    text = """
❓ <b>راهنمای کامل ربات</b>

<b>🛡 ریپورت گروهی:</b>
مراحل: لینک گروه → لینک پست → متن → تعداد اکانت → تعداد دفعات

<b>➕ افزودن اکانت:</b>
مراحل: شماره → API ID → API Hash → کد تایید

<b>📋 مدیریت:</b>
لیست اکانت‌ها، حذف، مدیریت ادمین

<b>📣 کانال گزارشات:</b>
مشاهده همه گزارش‌ها

⚠️ <b>نکات مهم:</b>
• برای ریپورت حداقل ۱ اکانت نیاز دارید
• API ID و Hash رو از my.telegram.org بگیر
• کد تایید رو به صورت ۱.۲.۳.۴.۵ وارد کن
• توصیه: هر اکانت ۱ بار ریپورت بزنه
"""
    
    await query.edit_message_text(text, reply_markup=back_button(), parse_mode='HTML')

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_temp:
        del user_temp[user_id]
    
    await query.edit_message_text(
        "🌟 <b>منوی اصلی</b>",
        reply_markup=main_menu(),
        parse_mode='HTML'
    )

async def cancel_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id in report_temp:
        del report_temp[user_id]
    if user_id in user_states:
        del user_states[user_id]
    
    await query.edit_message_text("❌ لغو شد!", reply_markup=main_menu(), parse_mode='HTML')

# ==================== هندلر پیام ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not check_user_access(update):
        return
    
    if user_id in user_states:
        state = user_states[user_id]
        
        if state == "waiting_phone":
            await handle_phone(update, context)
        elif state == "waiting_api_id":
            await handle_api_id(update, context)
        elif state == "waiting_api_hash":
            await handle_api_hash(update, context)
        elif state == "waiting_code":
            await handle_code(update, context)
        elif state == "waiting_password":
            await handle_password(update, context)
        elif state == "waiting_admin_id":
            await handle_add_admin(update, context)
        elif state == "waiting_report_group":
            await handle_report_group_link(update, context)
        elif state == "waiting_report_post":
            await handle_report_post_link(update, context)
        elif state == "waiting_report_text":
            await handle_report_text(update, context)
        elif state == "waiting_report_count":
            await handle_report_count(update, context)
        elif state == "waiting_report_repeat":
            await handle_report_repeat(update, context)

# ==================== Main ====================

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    
    app.add_handler(CallbackQueryHandler(add_account_start, pattern="add_account"))
    app.add_handler(CallbackQueryHandler(list_accounts, pattern="list_accounts"))
    app.add_handler(CallbackQueryHandler(delete_account_menu, pattern="delete_account_menu"))
    app.add_handler(CallbackQueryHandler(delete_account, pattern="^delete_acc_"))
    app.add_handler(CallbackQueryHandler(report_group_start, pattern="report_group"))
    app.add_handler(CallbackQueryHandler(execute_report, pattern="^execute_report_"))
    app.add_handler(CallbackQueryHandler(show_reports, pattern="reports"))
    app.add_handler(CallbackQueryHandler(manage_admins, pattern="manage_admins"))
    app.add_handler(CallbackQueryHandler(add_admin, pattern="add_admin"))
    app.add_handler(CallbackQueryHandler(remove_admin, pattern="remove_admin"))
    app.add_handler(CallbackQueryHandler(remove_admin_confirm, pattern="^remove_adm_"))
    app.add_handler(CallbackQueryHandler(list_admins, pattern="list_admins"))
    app.add_handler(CallbackQueryHandler(help_menu, pattern="help"))
    app.add_handler(CallbackQueryHandler(back_to_menu, pattern="back_to_menu"))
    app.add_handler(CallbackQueryHandler(cancel_report, pattern="cancel_report"))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("=" * 50)
    print("🤖 ربات مدیریت تلگرام - نسخه نهایی")
    print("=" * 50)
    accounts = db.get_accounts()
    admins = db.get_admins()
    reports = db.get_reports(10)
    print(f"📊 اکانت‌ها: {len(accounts)}")
    print(f"👥 ادمین‌ها: {len(admins)}")
    print(f"📋 گزارش‌ها: {len(reports)}")
    print("=" * 50)
    print("🔄 در حال اجرا...")
    print("✅ دیتابیس SQLite فعال است")
    print("✅ Fallback 0,0 حذف شد")
    print("✅ مدیریت خطای دقیق اضافه شد")
    print("✅ توضیح درباره موفقیت گزارش اضافه شد")
    print("=" * 50)
    
    app.run_polling()

if __name__ == "__main__":
    main()
