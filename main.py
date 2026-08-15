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

load_dotenv()

# ==================== تنظیمات ====================

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("❌ BOT_TOKEN not found in environment variables!")

ALLOWED_USERS = [int(id.strip()) for id in os.getenv("ALLOWED_USERS", "").split(",") if id.strip()]
REPORT_CHANNEL = os.getenv("REPORT_CHANNEL", "@ValkyrieReport")
REPORT_CHANNEL_ID = int(os.getenv("REPORT_CHANNEL_ID", "-1004392030066"))

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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                created_at TEXT
            )
        ''')
        
        for user_id in ALLOWED_USERS:
            cursor.execute('''
                INSERT OR IGNORE INTO users (user_id, is_admin, joined_date)
                VALUES (?, 1, ?)
            ''', (user_id, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    
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
    
    def add_log(self, user_id, action, details=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO logs (user_id, action, details, created_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, action, details, datetime.now().isoformat()))
        conn.commit()
        conn.close()

db = Database()

# ==================== متغیرها ====================

user_states = {}
user_temp = {}
report_temp = {}
processing_reports = set()
user_msg_ids = {}

# ==================== تابع سانسور شماره ====================

def mask_phone(phone):
    if not phone:
        return "نامشخص"
    phone_str = str(phone)
    if len(phone_str) <= 6:
        return phone_str
    return phone_str[:3] + "******" + phone_str[-3:]

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
        [InlineKeyboardButton("🛡 ریپورت کانال", callback_data="report_group")],
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
🔥 <b>به ربات ریپورتر والکری خوش آمدید!</b>

⚡ <b>ربات حرفه‌ای گزارش‌گیری از کانال‌های تلگرام</b>

📌 <b>قابلیت‌های ربات:</b>
🛡 <b>ریپورت کانال:</b> ارسال گزارش علیه کانال‌های متخلف با استفاده از چندین اکانت
➕ <b>افزودن اکانت:</b> اضافه کردن اکانت‌های تلگرام با سشن
📋 <b>لیست اکانت‌ها:</b> مشاهده و مدیریت اکانت‌های ثبت شده
📊 <b>گزارشات:</b> مشاهده تاریخچه کامل گزارشات ارسال شده
👤 <b>مدیریت ادمین:</b> افزودن یا حذف ادمین‌های جدید

<b>📌 راهنمای استفاده:</b>
برای ریپورت یک کانال، روی دکمه <b>"🛡 ریپورت کانال"</b> کلیک کنید.
برای اضافه کردن اکانت جدید، روی دکمه <b>"➕ افزودن اکانت"</b> کلیک کنید.

⚠️ <b>نکات مهم:</b>
• برای انجام ریپورت حداقل به ۱ اکانت نیاز دارید
• API ID و API Hash را از سایت my.telegram.org دریافت کنید
• کد تایید را به صورت ۵.۱.۷.۳.۲ وارد کنید
• شماره تلفن‌ها برای حفظ حریم خصوصی سانسور می‌شوند

📣 <b>کانال گزارشات:</b>
https://t.me/ValkyrieReport
"""
    msg = await update.message.reply_text(text, reply_markup=main_menu(), parse_mode='HTML')
    user_msg_ids[user_id] = msg.message_id
    db.add_log(user_id, "start", "User started bot")

# ==================== افزودن اکانت ====================

async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_temp[user_id] = {}
    user_states[user_id] = "waiting_phone"
    
    text = """
➕ <b>افزودن اکانت جدید</b>

برای اضافه کردن یک اکانت تلگرام، اطلاعات زیر را به ترتیب وارد کنید:

<b>1️⃣ شماره تلفن</b> (همراه با کد کشور)
مثال: <code>+989123456789</code>

<b>2️⃣ API ID</b> (از سایت my.telegram.org)
<b>3️⃣ API Hash</b> (از سایت my.telegram.org)
<b>4️⃣ کد تایید</b> (به تلگرام شما ارسال می‌شود)
<b>5️⃣ پسورد</b> (در صورت فعال بودن Two-Factor)

📱 <b>لطفاً شماره تلفن</b> خود را وارد کنید:
"""
    await query.edit_message_text(text, reply_markup=back_button(), parse_mode='HTML')

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_phone":
        return
    
    phone = update.message.text.strip()
    
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        await update.message.reply_text(
            "❌ شماره تلفن نامعتبر است!\n\n"
            "لطفاً شماره را با کد کشور وارد کنید.\n"
            "مثال: <code>+989123456789</code>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    user_temp[user_id]['phone'] = phone
    user_states[user_id] = "waiting_api_id"
    
    await update.message.reply_text(
        f"✅ شماره <code>{mask_phone(phone)}</code> با موفقیت ثبت شد.\n\n"
        "🔑 <b>مرحله بعد: وارد کردن API ID</b>\n\n"
        "لطفاً <b>API ID</b> خود را وارد کنید.\n"
        "این کد را از سایت <b>my.telegram.org</b> دریافت کنید.\n"
        "⚠️ توجه: API ID باید عددی بین 1 تا 2147483647 باشد.",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_api_id":
        return
    
    api_id = update.message.text.strip()
    
    try:
        api_id_int = int(api_id)
        if api_id_int <= 0 or api_id_int > 2147483647:
            await update.message.reply_text(
                "❌ API ID نامعتبر است!\n\n"
                "API ID باید عددی بین 1 تا 2147483647 باشد.\n"
                "لطفاً دوباره وارد کنید:",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            return
    except ValueError:
        await update.message.reply_text(
            "❌ API ID باید عدد باشد!\n\n"
            "لطفاً یک عدد معتبر وارد کنید.",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    user_temp[user_id]['api_id'] = api_id
    user_states[user_id] = "waiting_api_hash"
    
    await update.message.reply_text(
        f"✅ API ID با موفقیت ثبت شد.\n\n"
        "🔐 <b>مرحله بعد: وارد کردن API Hash</b>\n\n"
        "لطفاً <b>API Hash</b> خود را وارد کنید.\n"
        "این کد را از سایت <b>my.telegram.org</b> دریافت کنید.",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_api_hash":
        return
    
    api_hash = update.message.text.strip()
    
    if len(api_hash) < 20:
        await update.message.reply_text(
            "❌ API Hash نامعتبر است!\n\n"
            "لطفاً API Hash صحیح را از سایت my.telegram.org دریافت کنید.",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    user_temp[user_id]['api_hash'] = api_hash
    user_states[user_id] = "waiting_code"
    
    await update.message.reply_text(
        "⏳ <b>در حال ارسال کد تایید به تلگرام...</b>\n\n"
        "لطفاً چند لحظه صبر کنید...",
        parse_mode='HTML'
    )
    
    await start_connection(user_id, update)

async def start_connection(user_id, update):
    temp = user_temp.get(user_id, {})
    phone = temp.get("phone")
    api_id = temp.get("api_id")
    api_hash = temp.get("api_hash")
    
    if not all([phone, api_id, api_hash]):
        await update.message.reply_text("❌ اطلاعات کامل نیست!", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{phone}.session")
        client = TelegramClient(session_file, int(api_id), api_hash)
        
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            user_temp[user_id]['client'] = client
            
            await update.message.reply_text(
                f"📨 <b>کد تایید با موفقیت ارسال شد!</b>\n\n"
                f"📱 شماره: <code>{mask_phone(phone)}</code>\n\n"
                "🔑 لطفاً کد تایید ۵ رقمی را وارد کنید.\n\n"
                "⚠️ <b>نکته:</b> کد را به صورت <b>۵.۱.۷.۳.۲</b> وارد کنید.",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            user_states[user_id] = "waiting_code"
        else:
            await get_account_info(update, client, user_id)
            
    except PhoneNumberInvalidError:
        await update.message.reply_text("❌ شماره وارد شده معتبر نیست!", reply_markup=main_menu(), parse_mode='HTML')
    except FloodWaitError as e:
        await update.message.reply_text(f"⏳ لطفاً {e.seconds} ثانیه صبر کنید.", reply_markup=main_menu(), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Connection error: {e}\n{traceback.format_exc()}")
        await update.message.reply_text(f"❌ خطا در اتصال!\n\n{str(e)}", reply_markup=main_menu(), parse_mode='HTML')

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_code":
        return
    
    code_input = update.message.text.strip()
    code = code_input.replace('.', '').replace('،', '').replace(' ', '').strip()
    
    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text(
            "❌ کد تایید نامعتبر است!\n\n"
            "کد تایید باید ۵ رقم باشد.\n"
            "لطفاً کد را به صورت <b>۵.۱.۷.۳.۲</b> وارد کنید.",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    await update.message.reply_text("⏳ در حال تایید کد...", parse_mode='HTML')
    
    client = user_temp.get(user_id, {}).get('client')
    if not client:
        await update.message.reply_text("❌ خطا در اتصال!", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    try:
        await client.sign_in(code=code)
        await get_account_info(update, client, user_id)
        
    except SessionPasswordNeededError:
        user_states[user_id] = "waiting_password"
        await update.message.reply_text(
            "🔑 <b>این اکانت دارای رمز عبور (Two-Factor) است!</b>\n\n"
            "لطفاً رمز عبور اکانت خود را وارد کنید:",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        
    except PhoneCodeExpiredError:
        await update.message.reply_text(
            "❌ کد تایید منقضی شده است!\n\n"
            "در حال ارسال کد جدید...",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        try:
            phone = user_temp.get(user_id, {}).get("phone")
            await client.send_code_request(phone)
            await update.message.reply_text(
                "📨 کد جدید با موفقیت ارسال شد!\n\n"
                "لطفاً کد جدید را وارد کنید:",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
        except Exception as e:
            await update.message.reply_text(f"❌ خطا: {str(e)}", reply_markup=main_menu(), parse_mode='HTML')
        
    except PhoneCodeInvalidError:
        await update.message.reply_text(
            "❌ کد اشتباه است!\n\n"
            "لطفاً کد را دقیق وارد کنید.",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        user_states[user_id] = "waiting_code"
        
    except Exception as e:
        logger.error(f"Code verification error: {e}\n{traceback.format_exc()}")
        await update.message.reply_text(f"❌ خطا در تایید کد!\n\n{str(e)}", reply_markup=main_menu(), parse_mode='HTML')

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_password":
        return
    
    password = update.message.text.strip()
    
    if len(password) < 4:
        await update.message.reply_text(
            "❌ رمز عبور باید حداقل ۴ کاراکتر باشد!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    await update.message.reply_text("⏳ در حال تایید رمز عبور...", parse_mode='HTML')
    
    client = user_temp.get(user_id, {}).get('client')
    if not client:
        await update.message.reply_text("❌ خطا در اتصال!", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    try:
        await client.sign_in(password=password)
        await get_account_info(update, client, user_id)
    except Exception as e:
        logger.error(f"Password error: {e}\n{traceback.format_exc()}")
        await update.message.reply_text(
            f"❌ رمز عبور اشتباه است!\n\n{str(e)}",
            reply_markup=back_button(),
            parse_mode='HTML'
        )

async def get_account_info(update, client, user_id):
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
            await update.message.reply_text(
                "⚠️ این اکانت قبلاً ثبت شده است!",
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            if user_id in user_temp:
                del user_temp[user_id]
            if user_id in user_states:
                del user_states[user_id]
            await client.disconnect()
            return
        
        db.add_account(phone, username, first_name, last_name, telegram_id, session_file, api_id, api_hash)
        db.add_log(user_id, "add_account", f"Added account {phone}")
        
        await update.message.reply_text(
            f"✅ <b>اکانت با موفقیت اضافه شد!</b>\n\n"
            f"📱 <b>شماره:</b> <code>{mask_phone(phone)}</code>\n"
            f"👤 <b>نام:</b> {first_name} {last_name or ''}\n"
            f"🆔 <b>آیدی:</b> <code>{telegram_id}</code>\n"
            f"📅 <b>تاریخ:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            "🎉 اکانت شما با موفقیت ثبت شد!",
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
        await update.message.reply_text(f"❌ خطا: {str(e)}", reply_markup=main_menu(), parse_mode='HTML')

# ==================== لیست اکانت‌ها ====================

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    accounts = db.get_accounts()
    if not accounts:
        await query.edit_message_text(
            "📭 <b>هیچ اکانتی ثبت نشده است!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    text = "📋 <b>لیست اکانت‌ها:</b>\n\n"
    for i, acc in enumerate(accounts, 1):
        status = "✅" if acc.get('is_valid', 1) else "❌"
        text += f"{status} <b>{i}.</b> 📱 <code>{mask_phone(acc['phone'])}</code>\n"
        text += f"   👤 {acc['first_name'] or ''} {acc['last_name'] or ''}\n"
        if acc['username']:
            text += f"   🆔 @{acc['username']}\n"
        text += "─" * 30 + "\n"
    
    keyboard = [
        [InlineKeyboardButton("🗑 حذف اکانت", callback_data="delete_account_menu")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def delete_account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    accounts = db.get_accounts()
    if not accounts:
        await query.edit_message_text(
            "📭 هیچ اکانتی برای حذف وجود ندارد!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    keyboard = []
    for i, acc in enumerate(accounts):
        keyboard.append([InlineKeyboardButton(f"🗑 {mask_phone(acc['phone'])}", callback_data=f"delete_acc_{i}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="list_accounts")])
    
    await query.edit_message_text(
        "🗑 انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
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
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
    
    db.delete_account(phone)
    db.add_log(user_id, "delete_account", f"Deleted account {phone}")
    
    await query.edit_message_text(
        f"✅ اکانت <code>{mask_phone(phone)}</code> حذف شد!",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

# ==================== ریپورت کانال ====================

async def report_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    accounts = db.get_accounts()
    if len(accounts) < 1:
        await query.edit_message_text(
            "⚠️ <b>هیچ اکانتی ثبت نشده است!</b>\n\n"
            "ابتدا یک اکانت اضافه کنید.",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    report_temp[user_id] = {
        "posts": [],
        "report_texts": [],
        "count": None,
        "repeat": None,
        "group": None,
        "group_link": None,
        "current_step": "group"
    }
    user_states[user_id] = "waiting_report_group"
    
    await query.edit_message_text(
        "🛡 <b>ریپورت کانال</b>\n\n"
        "مراحل:\n"
        "1️⃣ لینک کانال\n"
        "2️⃣ لینک پست‌ها (چندتایی)\n"
        "3️⃣ متن گزارش (چندتایی)\n"
        "4️⃣ تعداد اکانت\n"
        "5️⃣ تعداد دفعات\n\n"
        "📎 لینک کانال را ارسال کنید:\n"
        "مثال: <code>@username</code> یا <code>https://t.me/username</code>",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_report_group_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_group":
        return
    
    link = update.message.text.strip()
    
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
        await update.message.reply_text(
            "❌ لینک نامعتبر!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    report_temp[user_id]["group"] = username
    report_temp[user_id]["group_link"] = link
    report_temp[user_id]["current_step"] = "post"
    user_states[user_id] = "waiting_report_post"
    
    await update.message.reply_text(
        f"✅ لینک کانال ثبت شد.\n\n"
        "📝 لینک پست را ارسال کنید:\n"
        "مثال: <code>https://t.me/username/123</code>\n\n"
        "💡 می‌توانید چندین لینک ارسال کنید.\n"
        "پس از اتمام، روی دکمه زیر کلیک کنید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ پست دیگری ندارم", callback_data="no_more_posts")]
        ]),
        parse_mode='HTML'
    )

async def handle_report_post_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_post":
        return
    
    post_link = update.message.text.strip()
    
    match = re.search(r'https?://t\.me/([\w_+]+)/(\d+)', post_link)
    if not match:
        match = re.search(r'https?://t\.me/c/(\d+)/(\d+)', post_link)
    
    if not match:
        await update.message.reply_text(
            "❌ لینک پست نامعتبر!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ پست دیگری ندارم", callback_data="no_more_posts")]
            ]),
            parse_mode='HTML'
        )
        return
    
    if "posts" not in report_temp[user_id]:
        report_temp[user_id]["posts"] = []
    
    msg_id = int(match.group(2))
    if msg_id not in report_temp[user_id]["posts"]:
        report_temp[user_id]["posts"].append(msg_id)
    
    await update.message.reply_text(
        f"✅ لینک پست ثبت شد! (تعداد: {len(report_temp[user_id]['posts'])})\n\n"
        "لینک بعدی را بفرستید یا روی دکمه زیر کلیک کنید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ پست دیگری ندارم", callback_data="no_more_posts")]
        ]),
        parse_mode='HTML'
    )

async def no_more_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_states or user_states[user_id] != "waiting_report_post":
        await query.answer("⚠️ در این مرحله نیستید!", show_alert=True)
        return
    
    if "posts" not in report_temp[user_id] or not report_temp[user_id]["posts"]:
        await query.edit_message_text(
            "❌ هیچ لینک پستی ارسال نکرده‌اید!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    report_temp[user_id]["current_step"] = "text"
    user_states[user_id] = "waiting_report_text"
    
    await query.edit_message_text(
        f"✅ <b>{len(report_temp[user_id]['posts'])}</b> لینک پست ثبت شد.\n\n"
        "📄 متن گزارش را وارد کنید:\n"
        "مثال: <i>این کانال کلاهبرداری است</i>\n\n"
        "💡 می‌توانید چندین متن ارسال کنید.\n"
        "پس از اتمام، روی دکمه زیر کلیک کنید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ متن دیگری ندارم", callback_data="no_more_texts")]
        ]),
        parse_mode='HTML'
    )

async def handle_report_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_text":
        return
    
    report_text = update.message.text.strip()
    
    if len(report_text) < 10:
        await update.message.reply_text(
            "❌ متن حداقل ۱۰ کاراکتر!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ متن دیگری ندارم", callback_data="no_more_texts")]
            ]),
            parse_mode='HTML'
        )
        return
    
    if "report_texts" not in report_temp[user_id]:
        report_temp[user_id]["report_texts"] = []
    
    if report_text not in report_temp[user_id]["report_texts"]:
        report_temp[user_id]["report_texts"].append(report_text)
    
    await update.message.reply_text(
        f"✅ متن گزارش ثبت شد! (تعداد: {len(report_temp[user_id]['report_texts'])})\n\n"
        "متن بعدی را بفرستید یا روی دکمه زیر کلیک کنید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ متن دیگری ندارم", callback_data="no_more_texts")]
        ]),
        parse_mode='HTML'
    )

async def no_more_texts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id not in user_states or user_states[user_id] != "waiting_report_text":
        await query.answer("⚠️ در این مرحله نیستید!", show_alert=True)
        return
    
    if "report_texts" not in report_temp[user_id] or not report_temp[user_id]["report_texts"]:
        await query.edit_message_text(
            "❌ هیچ متن گزارشی ارسال نکرده‌اید!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    report_temp[user_id]["current_step"] = "count"
    user_states[user_id] = "waiting_report_count"
    
    accounts = db.get_accounts()
    available = len(accounts)
    
    await query.edit_message_text(
        f"✅ <b>{len(report_temp[user_id]['report_texts'])}</b> متن گزارش ثبت شد.\n\n"
        f"📊 تعداد اکانت‌های موجود: <b>{available}</b>\n\n"
        f"🔢 تعداد اکانت‌ها را وارد کنید (حداکثر {available}):",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_report_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_count":
        return
    
    try:
        count = int(update.message.text.strip())
        accounts = db.get_accounts()
        available = len(accounts)
        
        if count < 1 or count > available:
            await update.message.reply_text(
                f"❌ بین ۱ تا {available} وارد کنید!",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            return
        
        report_temp[user_id]["count"] = count
        report_temp[user_id]["current_step"] = "repeat"
        user_states[user_id] = "waiting_report_repeat"
        
        await update.message.reply_text(
            f"✅ تعداد: <b>{count}</b>\n\n"
            "🔄 تعداد دفعات (۱ تا ۳):",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ عدد وارد کنید!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )

async def handle_report_repeat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_report_repeat":
        return
    
    try:
        repeat = int(update.message.text.strip())
        
        if repeat < 1 or repeat > 3:
            await update.message.reply_text(
                "❌ بین ۱ تا ۳ وارد کنید!",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            return
        
        report_temp[user_id]["repeat"] = repeat
        
        temp = report_temp.get(user_id, {})
        
        summary = f"""
📋 <b>خلاصه:</b>

🎯 کانال: {temp.get('group_link', 'نامشخص')}
📝 پست‌ها: {len(temp.get('posts', []))}
📄 متن‌ها: {len(temp.get('report_texts', []))}
🔢 اکانت‌ها: {temp.get('count', 0)}
🔄 دفعات: {temp.get('repeat', 0)}

⚠️ تایید میکنی؟
"""
        
        keyboard = [
            [InlineKeyboardButton("✅ اجرا", callback_data=f"execute_report_{user_id}")],
            [InlineKeyboardButton("❌ لغو", callback_data="cancel_report")]
        ]
        
        await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
        if user_id in user_states:
            del user_states[user_id]
        
    except ValueError:
        await update.message.reply_text(
            "❌ عدد وارد کنید!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )

# ==================== اجرای ریپورت ====================

async def execute_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    target_user_id = int(query.data.split("_")[2])
    user_msg_ids[user_id] = query.message.message_id
    
    if user_id != target_user_id:
        await query.answer("❌ این دکمه مال تو نیست!", show_alert=True)
        return
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
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
            "⏳ <b>در حال اجرا...</b>\n\nلطفاً صبر کنید...",
            parse_mode='HTML'
        )
        
        group = temp.get("group")
        group_link = temp.get("group_link")
        report_texts = temp.get("report_texts", ["گزارش کلاهبرداری"])
        count = temp.get("count", 1)
        repeat = temp.get("repeat", 1)
        posts = temp.get("posts", [])
        
        accounts = db.get_accounts()[:count]
        
        if len(accounts) < count:
            await query.edit_message_text("❌ تعداد اکانت کافی نیست!", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        total_success = 0
        total_fail = 0
        all_results = []
        all_join_results = []
        
        for post_index, msg_id in enumerate(posts, 1):
            for text_index, report_text in enumerate(report_texts, 1):
                success = 0
                fail = 0
                results = []
                join_results = []
                
                if post_index == 1 and text_index == 1:
                    for account in accounts:
                        try:
                            session_file = account.get("session_file")
                            if not session_file or not os.path.exists(session_file):
                                join_results.append(f"❌ {mask_phone(account['phone'])}: سشن یافت نشد")
                                continue
                            
                            api_id = account.get("api_id")
                            api_hash = account.get("api_hash")
                            
                            if not api_id or not api_hash:
                                join_results.append(f"❌ {mask_phone(account['phone'])}: اطلاعات API موجود نیست")
                                continue
                            
                            client = TelegramClient(session_file, int(api_id), api_hash)
                            await client.connect()
                            
                            if not await client.is_user_authorized():
                                join_results.append(f"❌ {mask_phone(account['phone'])}: احراز نشده")
                                await client.disconnect()
                                continue
                            
                            try:
                                entity = await client.get_entity(f"@{group}")
                                try:
                                    await client(functions.channels.JoinChannelRequest(entity))
                                    join_results.append(f"✅ {mask_phone(account['phone'])}: جوین شد")
                                except FloodWaitError as e:
                                    join_results.append(f"⏳ {mask_phone(account['phone'])}: صبر {e.seconds}s")
                                    await asyncio.sleep(min(e.seconds, 5))
                                except Exception as e:
                                    if "already" in str(e).lower():
                                        join_results.append(f"⚠️ {mask_phone(account['phone'])}: قبلاً جوین بود")
                                    else:
                                        join_results.append(f"❌ {mask_phone(account['phone'])}: خطا در جوین")
                                await asyncio.sleep(1)
                            except Exception:
                                join_results.append(f"❌ {mask_phone(account['phone'])}: کانال نامعتبر")
                            
                            await client.disconnect()
                            
                        except Exception as e:
                            join_results.append(f"❌ {mask_phone(account['phone'])}: خطا")
                
                for account in accounts:
                    try:
                        session_file = account.get("session_file")
                        if not session_file or not os.path.exists(session_file):
                            fail += 1
                            results.append(f"❌ {mask_phone(account['phone'])}: سشن یافت نشد")
                            continue
                        
                        api_id = account.get("api_id")
                        api_hash = account.get("api_hash")
                        
                        if not api_id or not api_hash:
                            fail += 1
                            results.append(f"❌ {mask_phone(account['phone'])}: اطلاعات API موجود نیست")
                            continue
                        
                        client = TelegramClient(session_file, int(api_id), api_hash)
                        await client.connect()
                        
                        if not await client.is_user_authorized():
                            fail += 1
                            results.append(f"❌ {mask_phone(account['phone'])}: احراز نشده")
                            await client.disconnect()
                            continue
                        
                        try:
                            entity = await client.get_entity(f"@{group}")
                        except Exception:
                            fail += 1
                            results.append(f"❌ {mask_phone(account['phone'])}: کانال نامعتبر")
                            await client.disconnect()
                            continue
                        
                        for i in range(repeat):
                            try:
                                await client(functions.messages.ReportRequest(
                                    peer=entity,
                                    id=[msg_id],
                                    reason=types.InputReportReasonSpam(),
                                    message=report_text
                                ))
                                success += 1
                                results.append(f"✅ {mask_phone(account['phone'])}: پست {post_index} - متن {text_index} - ریپورت {i+1}")
                                await asyncio.sleep(2)
                            except FloodWaitError as e:
                                fail += 1
                                results.append(f"⏳ {mask_phone(account['phone'])}: صبر {e.seconds}s")
                                await asyncio.sleep(min(e.seconds, 10))
                            except Exception as e:
                                fail += 1
                                results.append(f"❌ {mask_phone(account['phone'])}: خطا")
                                await asyncio.sleep(1)
                        
                        await client.disconnect()
                        
                    except Exception as e:
                        fail += 1
                        results.append(f"❌ {mask_phone(account['phone'])}: خطا")
                
                total_success += success
                total_fail += fail
                all_results.extend(results)
                all_join_results.extend(join_results)
        
        report_id = db.add_report(
            group, group_link, str(report_texts), count, repeat,
            total_success, total_fail, total_success + total_fail,
            all_join_results, all_results, user_id
        )
        
        db.add_log(user_id, "execute_report", f"Report {report_id} - Success: {total_success}, Fail: {total_fail}")
        
        result_text = f"""
📊 <b>نتیجه:</b>

🎯 {group_link}
📝 پست‌ها: {len(posts)}
📄 متن‌ها: {len(report_texts)}
✅ موفق: {total_success}
❌ خطا: {total_fail}
📋 مجموع: {total_success + total_fail}

📋 وضعیت جوین:
"""
        
        for jr in all_join_results[:3]:
            result_text += f"\n{jr}"
        
        if len(all_join_results) > 3:
            result_text += f"\n... {len(all_join_results)-3} نتیجه دیگر"
        
        result_text += f"\n\n📋 نتیجه ریپورت:"
        
        for r in all_results[:3]:
            result_text += f"\n{r}"
        
        if len(all_results) > 3:
            result_text += f"\n... {len(all_results)-3} نتیجه دیگر"
        
        await query.edit_message_text(
            result_text,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        
        await send_report_to_channel(context, {
            "group_link": group_link,
            "accounts": count,
            "repeat": repeat,
            "success": total_success,
            "fail": total_fail,
            "total": total_success + total_fail,
            "results": all_results,
            "date": datetime.now().isoformat(),
            "posts_count": len(posts),
            "texts_count": len(report_texts)
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
📊 <b>گزارش جدید</b>

🎯 {report_data.get('group_link', 'نامشخص')}
📝 پست‌ها: {report_data.get('posts_count', 0)}
📄 متن‌ها: {report_data.get('texts_count', 0)}
🔢 اکانت‌ها: {report_data.get('accounts', 0)}
🔄 دفعات: {report_data.get('repeat', 0)}
✅ موفق: {report_data.get('success', 0)}
❌ خطا: {report_data.get('fail', 0)}
📋 مجموع: {report_data.get('total', 0)}
📅 {report_data.get('date', '')[:19]}

📋 جزئیات:
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
        
    except Exception as e:
        logger.error(f"Error sending report to channel: {e}")

# ==================== گزارشات ====================

async def show_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    reports = db.get_reports(10)
    if not reports:
        await query.edit_message_text(
            "📭 گزارشی ثبت نشده!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    text = "📊 <b>تاریخچه:</b>\n\n"
    for i, r in enumerate(reports[:5], 1):
        text += f"{i}. 🎯 {r.get('group_name', 'نامشخص')}\n"
        text += f"   ✅ موفق: {r.get('success_count', 0)}\n"
        text += f"   ❌ خطا: {r.get('fail_count', 0)}\n"
        text += f"   📅 {r.get('created_at', '')[:10]}\n"
        text += "─" * 30 + "\n"
    
    await query.edit_message_text(
        text,
        reply_markup=back_button(),
        parse_mode='HTML'
    )

# ==================== مدیریت ادمین ====================

async def manage_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    keyboard = [
        [InlineKeyboardButton("➕ افزودن", callback_data="add_admin")],
        [InlineKeyboardButton("🗑 حذف", callback_data="remove_admin")],
        [InlineKeyboardButton("📋 لیست", callback_data="list_admins")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(
        "👥 مدیریت ادمین:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    user_states[user_id] = "waiting_admin_id"
    
    await query.edit_message_text(
        "➕ آیدی عددی رو وارد کن:",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_admin_id":
        return
    
    try:
        admin_id = int(update.message.text.strip())
        
        if db.is_admin(admin_id):
            await update.message.reply_text("⚠️ قبلاً هست!", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        if admin_id in ALLOWED_USERS:
            await update.message.reply_text("⚠️ در لیست اصلی هست!", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        db.add_admin(admin_id)
        db.add_log(user_id, "add_admin", f"Added admin {admin_id}")
        
        await update.message.reply_text(
            f"✅ ادمین {admin_id} اضافه شد!",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        del user_states[user_id]
            
    except ValueError:
        await update.message.reply_text(
            "❌ عدد وارد کن!",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    admins = db.get_admins()
    admins = [a for a in admins if a not in ALLOWED_USERS]
    
    if not admins:
        await query.edit_message_text(
            "📭 ادمین اضافه‌ای نیست!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    keyboard = []
    for admin in admins:
        keyboard.append([InlineKeyboardButton(f"🗑 {admin}", callback_data=f"remove_adm_{admin}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="manage_admins")])
    
    await query.edit_message_text(
        "🗑 انتخاب کن:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def remove_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    admin_id = int(query.data.split("_")[2])
    
    if db.is_admin(admin_id) and admin_id not in ALLOWED_USERS:
        db.remove_admin(admin_id)
        db.add_log(user_id, "remove_admin", f"Removed admin {admin_id}")
        await query.edit_message_text(
            f"✅ {admin_id} حذف شد!",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
    else:
        await query.answer("❌ یافت نشد!", show_alert=True)

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    text = "👥 <b>ادمین‌ها:</b>\n\n"
    text += "🔹 اصلی:\n"
    for uid in ALLOWED_USERS:
        text += f"   • <code>{uid}</code>\n"
    
    admins = db.get_admins()
    extra_admins = [a for a in admins if a not in ALLOWED_USERS]
    
    if extra_admins:
        text += "\n🔸 اضافه شده:\n"
        for admin in extra_admins:
            text += f"   • <code>{admin}</code>\n"
    else:
        text += "\n📭 اضافه‌ای نیست."
    
    await query.edit_message_text(
        text,
        reply_markup=back_button(),
        parse_mode='HTML'
    )

# ==================== راهنما ====================

async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 دسترسی غیرمجاز!", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    text = """
❓ <b>راهنما</b>

<b>🛡 ریپورت کانال:</b>
لینک کانال → لینک پست‌ها → متن‌ها → تعداد اکانت → تعداد دفعات

<b>➕ افزودن اکانت:</b>
شماره → API ID → API Hash → کد تایید

<b>📋 مدیریت:</b>
لیست اکانت‌ها - حذف اکانت - مدیریت ادمین

⚠️ <b>نکات:</b>
• API ID و Hash از my.telegram.org
• کد تایید: ۵.۱.۷.۳.۲
"""
    
    await query.edit_message_text(
        text,
        reply_markup=back_button(),
        parse_mode='HTML'
    )

# ==================== دکمه‌های عمومی ====================

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    if user_id in user_states:
        del user_states[user_id]
    if user_id in user_temp:
        del user_temp[user_id]
    if user_id in report_temp:
        del report_temp[user_id]
    
    await query.edit_message_text(
        "🌟 <b>منوی اصلی</b>",
        reply_markup=main_menu(),
        parse_mode='HTML'
    )

async def cancel_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    if user_id in report_temp:
        del report_temp[user_id]
    if user_id in user_states:
        del user_states[user_id]
    
    await query.edit_message_text(
        "❌ لغو شد!",
        reply_markup=main_menu(),
        parse_mode='HTML'
    )

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
    
    try:
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(app.bot.delete_webhook())
        loop.close()
        logger.info("Webhook deleted successfully")
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")
    
    app.add_handler(CommandHandler("start", start))
    
    app.add_handler(CallbackQueryHandler(add_account_start, pattern="add_account"))
    app.add_handler(CallbackQueryHandler(list_accounts, pattern="list_accounts"))
    app.add_handler(CallbackQueryHandler(delete_account_menu, pattern="delete_account_menu"))
    app.add_handler(CallbackQueryHandler(delete_account, pattern="^delete_acc_"))
    app.add_handler(CallbackQueryHandler(report_group_start, pattern="report_group"))
    app.add_handler(CallbackQueryHandler(execute_report, pattern="^execute_report_"))
    app.add_handler(CallbackQueryHandler(no_more_posts, pattern="no_more_posts"))
    app.add_handler(CallbackQueryHandler(no_more_texts, pattern="no_more_texts"))
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
    print("🔥 ربات ریپورتر والکری")
    print("=" * 50)
    accounts = db.get_accounts()
    admins = db.get_admins()
    reports = db.get_reports(10)
    print(f"📊 اکانت‌ها: {len(accounts)}")
    print(f"👥 ادمین‌ها: {len(admins)}")
    print(f"📋 گزارش‌ها: {len(reports)}")
    print("=" * 50)
    print("🔄 در حال اجرا...")
    print("✅ شماره‌ها سانسور میشن")
    print("✅ پشتیبانی از چندین پست و متن")
    print("✅ Webhook غیرفعال شد")
    print("=" * 50)
    
    app.run_polling()

if __name__ == "__main__":
    main()
