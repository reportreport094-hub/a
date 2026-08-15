import os
import re
import logging
import asyncio
from datetime import datetime, timedelta
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

OWNER_IDS = [7803165903, 7795617350]
REPORT_CHANNEL = os.getenv("REPORT_CHANNEL", "@ValkyrieReport")
REPORT_CHANNEL_ID = int(os.getenv("REPORT_CHANNEL_ID", "-1004392030066"))

ADMIN_REPORT_COOLDOWN = 3600

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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_report_log (
                user_id INTEGER PRIMARY KEY,
                last_report_time TEXT
            )
        ''')
        
        for user_id in OWNER_IDS:
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
    
    def is_owner(self, user_id):
        return user_id in OWNER_IDS
    
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
                   success_count, fail_count, total_count, results, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO reports 
            (group_name, group_link, report_text, accounts_count, repeat_count, 
             success_count, fail_count, total_count, results, user_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (group_name, group_link, report_text, accounts_count, repeat_count,
              success_count, fail_count, total_count, 
              json.dumps(results), 
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
    
    def get_admin_last_report(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT last_report_time FROM admin_report_log WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def set_admin_last_report(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO admin_report_log (user_id, last_report_time)
            VALUES (?, ?)
        ''', (user_id, datetime.now().isoformat()))
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

def is_owner(user_id):
    return user_id in OWNER_IDS

def is_admin(user_id):
    return db.is_admin(user_id) or is_owner(user_id)

def is_allowed(user_id):
    return is_admin(user_id) or is_owner(user_id)

def check_user_access(update):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        logger.warning(f"Unauthorized access attempt from user {user_id}")
        return False
    return True

def check_admin_report_limit(user_id):
    if is_owner(user_id):
        return True, None
    
    last_time = db.get_admin_last_report(user_id)
    if last_time:
        last_dt = datetime.fromisoformat(last_time)
        if datetime.now() - last_dt < timedelta(seconds=ADMIN_REPORT_COOLDOWN):
            remaining = int((timedelta(seconds=ADMIN_REPORT_COOLDOWN) - (datetime.now() - last_dt)).total_seconds())
            minutes = remaining // 60
            seconds = remaining % 60
            return False, f"{minutes} دقیقه و {seconds} ثانیه"
    
    return True, None

# ==================== منوها ====================

def main_menu():
    keyboard = [
        [InlineKeyboardButton("🛡 سیستم هوشمند گزارش تخلفات (Report)", callback_data="report_group")],
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

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("🛡 سیستم هوشمند گزارش تخلفات (Report)", callback_data="report_group")],
        [
            InlineKeyboardButton("📋 لیست اکانت‌ها", callback_data="list_accounts"),
            InlineKeyboardButton("📊 گزارشات", callback_data="reports")
        ],
        [
            InlineKeyboardButton("📣 کانال گزارشات", url="https://t.me/ValkyrieReport"),
            InlineKeyboardButton("❓ راهنما", callback_data="help")
        ],
        [InlineKeyboardButton("👨‍💻 درباره تیم", callback_data="developer")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")]])

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
    
    text = """
⁭⁯⁯⁭⁯               ⁭⁯⁯⁭⁯               ⁭⁯⁯⁭⁯               ⁭⁯⁯⁭⁯               ⁭⁯⁯⁭⁯‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌
🌟 <b>به منوی اصلی بازگشتید.</b>

<b>لطفاً انتخاب کنید :</b>
"""
    
    await query.edit_message_text(
        text,
        reply_markup=main_menu() if is_owner(user_id) else admin_menu(),
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
    
    text = "❌ <b>عملیات لغو شد!</b>"
    
    await query.edit_message_text(
        text,
        reply_markup=main_menu() if is_owner(user_id) else admin_menu(),
        parse_mode='HTML'
    )

# ==================== شروع ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    
    db.add_user(user_id, user.username, user.first_name, user.last_name)
    
    if not check_user_access(update):
        await update.message.reply_text("🚫 <b>دسترسی غیرمجاز!</b>", parse_mode='HTML')
        return
    
    text = """
🔥 <b>به ربات ریپورتر والکری خوش آمدید</b>

⚡ <b>ابزار حرفه‌ای گزارش‌گیری هوشمند در تلگرام</b>

📌 <b>ویژگی‌های اصلی:</b>
🛡 ریپورت کانال با استفاده از چندین اکانت
➕ افزودن سریع سشن (Session)
📋 مدیریت و مشاهده وضعیت اکانت‌ها
📊 گزارش‌گیری دقیق و لحظه‌ای

⚠️ <b>پیش‌نیازها:</b>
• اتصال حداقل ۱ اکانت
• داشتن API ID و API Hash (از my.telegram.org)
• سیستم امنیتی: تمامی شماره‌ها بصورت خودکار سانسور می‌شوند
"""
    
    if is_owner(user_id):
        reply_markup = main_menu()
    else:
        reply_markup = admin_menu()
    
    msg = await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
    user_msg_ids[user_id] = msg.message_id
    db.add_log(user_id, "start", "User started bot")

# ==================== درباره تیم ====================

async def developer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    text = """
🚀 <b>معرفی ربات ریپورتر والکری (Valkyrie Reporter)</b>

والکری، قدرتمندترین ابزار مدیریت گزارش (Report) برای مقابله با کانال‌های متخلف در تلگرام. این ربات با بهره‌گیری از سیستم پیشرفته مالتی-اکانت، فرآیند گزارش‌گیری را به صورت هوشمند و گروهی انجام می‌دهد.

🛠 <b>ویژگی‌های کلیدی:</b>
• <b>ریپورت دسته‌جمعی:</b> استفاده از چندین سشن (Session) به‌صورت همزمان
• <b>مدیریت پیشرفته:</b> پنل اختصاصی برای افزودن و مدیریت اکانت‌ها
• <b>گزارش‌گیری دقیق:</b> مشاهده تاریخچه و وضعیت تمامی گزارش‌های ارسالی
• <b>پایداری بالا:</b> طراحی شده برای عملکرد بهینه و سریع

💻 <b>توسعه یافته توسط:</b> تیم ریپر ووید (Ripper Void)

📞 <b>ارتباط با برنامه‌نویس:</b>
جهت پشتیبانی و سوالات فنی:
👉 @XMrAmer

✅ <b>نسخه:</b> 2.0
📅 <b>آخرین بروزرسانی:</b> 2024-05-23
"""
    
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
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    text = """
❓ <b>راهنمای کامل ربات ریپورتر والکری</b>

<b>🛡 ریپورت کانال:</b>
برای گزارش کانال‌های متخلف
مراحل: لینک کانال → لینک پست‌ها → متن‌ها → تعداد اکانت → تعداد دفعات

<b>➕ افزودن اکانت:</b>
اضافه کردن اکانت تلگرام با سشن
مراحل: شماره → API ID → API Hash → کد تایید

<b>📋 لیست اکانت‌ها:</b>
مشاهده همه اکانت‌های ثبت شده و حذف اکانت‌های اضافی

<b>📊 گزارشات:</b>
مشاهده تاریخچه گزارشات ارسال شده

<b>👤 مدیریت ادمین:</b>
افزودن یا حذف ادمین‌های جدید

<b>📣 کانال گزارشات:</b>
مشاهده همه گزارشات در کانال

⚠️ <b>نکات مهم:</b>
• برای ریپورت حداقل ۱ اکانت نیاز دارید
• API ID و Hash رو از my.telegram.org بگیرید
• کد تایید رو به صورت ۵.۱.۷.۳.۲ وارد کنید
• توصیه: هر اکانت ۱ بار ریپورت بزند
• اطلاعات شما به صورت امن در دیتابیس ذخیره می‌شود
• شماره تلفن‌ها برای حفظ حریم خصوصی سانسور می‌شوند
"""
    
    await query.edit_message_text(
        text,
        reply_markup=back_button(),
        parse_mode='HTML'
    )

# ==================== افزودن اکانت ====================

async def add_account_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    if not is_owner(query.from_user.id):
        await query.answer("❌ <b>فقط مالک میتواند اکانت اضافه کند!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_temp[user_id] = {}
    user_states[user_id] = "waiting_phone"
    
    text = """
➕ <b>افزودن اکانت به ربات ریپورتر</b>

<b>1.</b> شماره تلفن (با کد کشور):
<b>2.</b> آیپی عددی API ID:
<b>3.</b> آیپی هش API Hash:
<b>4.</b> کد تأیید:
<b>5.</b> رمز عبور (در صورت نیاز):

📱<b>لطفا شماره تلفن اکانت را وارد نمایید :</b>
"""
    await query.edit_message_text(text, reply_markup=back_button(), parse_mode='HTML')

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_phone":
        return
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ <b>فقط مالک میتواند اکانت اضافه کند!</b>", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    phone = update.message.text.strip()
    
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        await update.message.reply_text(
            "❌ <b>شماره نامعتبر!</b> مثال: <code>+989123456789</code>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    user_temp[user_id]['phone'] = phone
    user_states[user_id] = "waiting_api_id"
    
    await update.message.reply_text(
        f"✅ <b>شماره</b> <code>{mask_phone(phone)}</code> <b>ثبت شد.</b>\n\n"
        "🔑 <b>API ID</b> را وارد کنید:\n(از my.telegram.org)",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_api_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_api_id":
        return
    
    if not is_owner(user_id):
        return
    
    api_id = update.message.text.strip()
    
    try:
        api_id_int = int(api_id)
        if api_id_int <= 0 or api_id_int > 2147483647:
            await update.message.reply_text(
                "❌ <b>API ID باید بین 1 تا 2147483647 باشد!</b>",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            return
    except ValueError:
        await update.message.reply_text(
            "❌ <b>API ID باید عدد باشد!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    user_temp[user_id]['api_id'] = api_id
    user_states[user_id] = "waiting_api_hash"
    
    await update.message.reply_text(
        f"✅ <b>API ID ثبت شد.</b>\n\n"
        "🔐 <b>API Hash</b> را وارد کنید:\n(از my.telegram.org)",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_api_hash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_api_hash":
        return
    
    if not is_owner(user_id):
        return
    
    api_hash = update.message.text.strip()
    
    if len(api_hash) < 20:
        await update.message.reply_text(
            "❌ <b>API Hash نامعتبر!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    user_temp[user_id]['api_hash'] = api_hash
    user_states[user_id] = "waiting_code"
    
    await update.message.reply_text(
        "⏳ <b>در حال ارسال کد تایید...</b>",
        parse_mode='HTML'
    )
    
    await start_connection(user_id, update)

async def start_connection(user_id, update):
    temp = user_temp.get(user_id, {})
    phone = temp.get("phone")
    api_id = temp.get("api_id")
    api_hash = temp.get("api_hash")
    
    if not all([phone, api_id, api_hash]):
        await update.message.reply_text("❌ <b>اطلاعات کامل نیست!</b>", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{phone}.session")
        client = TelegramClient(session_file, int(api_id), api_hash)
        
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            user_temp[user_id]['client'] = client
            
            await update.message.reply_text(
                f"📨 <b>کد تایید ارسال شد!</b>\n\n"
                f"📱 <code>{mask_phone(phone)}</code>\n\n"
                "🔑 <b>کد ۵ رقمی</b> را وارد کنید:\n"
                "⚠️ به صورت <b>۵.۱.۷.۳.۲</b>",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            user_states[user_id] = "waiting_code"
        else:
            await get_account_info(update, client, user_id)
            
    except PhoneNumberInvalidError:
        await update.message.reply_text("❌ <b>شماره معتبر نیست!</b>", reply_markup=main_menu(), parse_mode='HTML')
    except FloodWaitError as e:
        await update.message.reply_text(f"⏳ <b>{e.seconds} ثانیه صبر کنید.</b>", reply_markup=main_menu(), parse_mode='HTML')
    except Exception as e:
        logger.error(f"Connection error: {e}")
        await update.message.reply_text(f"❌ <b>خطا:</b> {str(e)}", reply_markup=main_menu(), parse_mode='HTML')

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_code":
        return
    
    if not is_owner(user_id):
        return
    
    code_input = update.message.text.strip()
    code = code_input.replace('.', '').replace('،', '').replace(' ', '').strip()
    
    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text(
            "❌ <b>کد ۵ رقم باشد!</b> مثال: <code>5.1.7.3.2</code>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    await update.message.reply_text("⏳ <b>در حال تایید کد...</b>", parse_mode='HTML')
    
    client = user_temp.get(user_id, {}).get('client')
    if not client:
        await update.message.reply_text("❌ <b>خطا در اتصال!</b>", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    try:
        await client.sign_in(code=code)
        await get_account_info(update, client, user_id)
        
    except SessionPasswordNeededError:
        user_states[user_id] = "waiting_password"
        await update.message.reply_text(
            "🔑 <b>این اکانت پسورد دارد!</b>\n\nلطفاً <b>پسورد</b> را وارد کنید:",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        
    except PhoneCodeExpiredError:
        await update.message.reply_text(
            "❌ <b>کد منقضی شد!</b> در حال ارسال مجدد...",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        try:
            phone = user_temp.get(user_id, {}).get("phone")
            await client.send_code_request(phone)
            await update.message.reply_text("📨 <b>کد جدید ارسال شد!</b>", reply_markup=back_button(), parse_mode='HTML')
        except Exception as e:
            await update.message.reply_text(f"❌ <b>خطا:</b> {str(e)}", reply_markup=main_menu(), parse_mode='HTML')
        
    except PhoneCodeInvalidError:
        await update.message.reply_text(
            "❌ <b>کد اشتباه!</b> دوباره وارد کنید:",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        user_states[user_id] = "waiting_code"
        
    except Exception as e:
        logger.error(f"Code error: {e}")
        await update.message.reply_text(f"❌ <b>خطا:</b> {str(e)}", reply_markup=main_menu(), parse_mode='HTML')

async def handle_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_password":
        return
    
    if not is_owner(user_id):
        return
    
    password = update.message.text.strip()
    
    if len(password) < 4:
        await update.message.reply_text(
            "❌ <b>پسورد حداقل ۴ کاراکتر!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    await update.message.reply_text("⏳ <b>در حال تایید پسورد...</b>", parse_mode='HTML')
    
    client = user_temp.get(user_id, {}).get('client')
    if not client:
        await update.message.reply_text("❌ <b>خطا در اتصال!</b>", reply_markup=main_menu(), parse_mode='HTML')
        return
    
    try:
        await client.sign_in(password=password)
        await get_account_info(update, client, user_id)
    except Exception as e:
        logger.error(f"Password error: {e}")
        await update.message.reply_text(
            f"❌ <b>پسورد اشتباه!</b>\n\n{str(e)}",
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
                "⚠️ <b>این اکانت قبلاً ثبت شده!</b>",
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
            f"✅ <b>اکانت اضافه شد!</b>\n\n"
            f"📱 <code>{mask_phone(phone)}</code>\n"
            f"👤 {first_name} {last_name or ''}\n"
            f"🆔 <code>{telegram_id}</code>\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            reply_markup=main_menu() if is_owner(user_id) else admin_menu(),
            parse_mode='HTML'
        )
        
        if user_id in user_temp:
            del user_temp[user_id]
        if user_id in user_states:
            del user_states[user_id]
        
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"Get account error: {e}")
        await update.message.reply_text(f"❌ <b>خطا:</b> {str(e)}", reply_markup=main_menu(), parse_mode='HTML')

# ==================== لیست اکانت‌ها ====================

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    accounts = db.get_accounts()
    if not accounts:
        text = """
📭 <b>در حال حاضر هیچ اکانتی ثبت نشده است.</b>

لطفاً برای شروع، ابتدا به بخش <b>"➕ افزودن اکانت"</b> مراجعه کرده و حساب کاربری خود را اضافه کنید.
"""
        await query.edit_message_text(
            text,
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
    
    keyboard = []
    if is_owner(user_id):
        keyboard.append([InlineKeyboardButton("🗑 حذف اکانت", callback_data="delete_account_menu")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def delete_account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ <b>فقط مالک میتواند اکانت حذف کند!</b>", show_alert=True)
        return
    
    user_msg_ids[user_id] = query.message.message_id
    
    accounts = db.get_accounts()
    if not accounts:
        await query.edit_message_text(
            "📭 <b>اکانتی برای حذف نیست!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    keyboard = []
    for i, acc in enumerate(accounts):
        keyboard.append([InlineKeyboardButton(f"🗑 {mask_phone(acc['phone'])}", callback_data=f"delete_acc_{i}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="list_accounts")])
    
    await query.edit_message_text(
        "🗑 <b>انتخاب کنید:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def delete_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ <b>فقط مالک میتواند اکانت حذف کند!</b>", show_alert=True)
        return
    
    user_msg_ids[user_id] = query.message.message_id
    index = int(query.data.split("_")[2])
    
    accounts = db.get_accounts()
    if index >= len(accounts):
        await query.answer("❌ <b>یافت نشد!</b>", show_alert=True)
        return
    
    account = accounts[index]
    phone = account['phone']
    
    session_file = account.get('session_file')
    if session_file and os.path.exists(session_file):
        try:
            os.remove(session_file)
        except:
            pass
    
    db.delete_account(phone)
    db.add_log(user_id, "delete_account", f"Deleted account {phone}")
    
    await query.edit_message_text(
        f"✅ <code>{mask_phone(phone)}</code> <b>حذف شد!</b>",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

# ==================== ریپورت کانال ====================

async def report_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    if not is_owner(user_id):
        can_report, remaining = check_admin_report_limit(user_id)
        if not can_report:
            await query.edit_message_text(
                f"⏳ <b>صبر کنید!</b>\n\n"
                f"شما باید <b>{remaining}</b> صبر کنید تا دوباره بتوانید گزارش بدهید.\n\n"
                f"⚠️ این محدودیت برای جلوگیری از اسپم است.",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            return
    
    accounts = db.get_accounts()
    if len(accounts) < 1:
        text = """
📭 <b>در حال حاضر هیچ اکانتی ثبت نشده است.</b>

لطفاً برای شروع، ابتدا به بخش <b>"➕ افزودن اکانت"</b> مراجعه کرده و حساب کاربری خود را اضافه کنید.
"""
        await query.edit_message_text(
            text,
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
        """
🛡 <b>سیستم هوشمند گزارش تخلفات (Report) ربات والکری</b>

جهت بررسی و پیگیری کانال‌های متخلف، لطفاً اطلاعات زیر را با دقت تکمیل و ارسال نمایید:

<b>مراحل ثبت گزارش:</b>
1️⃣ <b>لینک کانال:</b> (آیدی یا لینک مستقیم)
2️⃣ <b>لینک پست‌های متخلف:</b> (ارسال حداقل ۳ نمونه جهت تسریع در بررسی)
3️⃣ <b>دلیل گزارش:</b> (شرح کوتاه و مستدل از نوع تخلف)
4️⃣ <b>تعداد اکانت درخواستی:</b> (ظرفیت مورد نظر شما)
5️⃣ <b>دفعات تکرار:</b> (تعداد دفعات اجرای عملیات)

📎 <b>درگاه ثبت گزارش:</b>
لطفاً لینک کانال مورد نظر را به فرمت زیر ارسال کنید:
<code>@Username</code> یا <code>https://t.me/Username</code>
""",
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
            "❌ <b>لینک نامعتبر!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    report_temp[user_id]["group"] = username
    report_temp[user_id]["group_link"] = link
    report_temp[user_id]["current_step"] = "post"
    user_states[user_id] = "waiting_report_post"
    
    await update.message.reply_text(
        f"✅ <b>لینک کانال ثبت شد.</b>\n\n"
        "📝 <b>لینک پست</b> را بفرستید:\n"
        "مثال: <code>https://t.me/username/123</code>\n\n"
        "💡 می‌توانید <b>چندین لینک</b> بفرستید.\n"
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
            "❌ <b>لینک پست نامعتبر!</b>",
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
        f"✅ <b>لینک پست ثبت شد!</b> (تعداد: {len(report_temp[user_id]['posts'])})\n\n"
        "📎 لینک بعدی را بفرستید یا روی دکمه زیر کلیک کنید.",
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
        await query.answer("⚠️ <b>در این مرحله نیستید!</b>", show_alert=True)
        return
    
    if "posts" not in report_temp[user_id] or not report_temp[user_id]["posts"]:
        await query.edit_message_text(
            "❌ <b>هیچ لینک پستی ارسال نکرده‌اید!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    report_temp[user_id]["current_step"] = "text"
    user_states[user_id] = "waiting_report_text"
    
    await query.edit_message_text(
        f"✅ <b>{len(report_temp[user_id]['posts'])}</b> لینک پست ثبت شد.\n\n"
        "📄 <b>متن گزارش</b> را وارد کنید:\n"
        "مثال: <i>این کانال کلاهبرداری است</i>\n\n"
        "💡 می‌توانید <b>چندین متن</b> بفرستید.\n"
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
            "❌ <b>متن حداقل ۱۰ کاراکتر!</b>",
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
        f"✅ <b>متن ثبت شد!</b> (تعداد: {len(report_temp[user_id]['report_texts'])})\n\n"
        "📎 متن بعدی را بفرستید یا روی دکمه زیر کلیک کنید.",
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
        await query.answer("⚠️ <b>در این مرحله نیستید!</b>", show_alert=True)
        return
    
    if "report_texts" not in report_temp[user_id] or not report_temp[user_id]["report_texts"]:
        await query.edit_message_text(
            "❌ <b>هیچ متن گزارشی ارسال نکرده‌اید!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    report_temp[user_id]["current_step"] = "count"
    user_states[user_id] = "waiting_report_count"
    
    accounts = db.get_accounts()
    available = len(accounts)
    
    await query.edit_message_text(
        f"✅ <b>{len(report_temp[user_id]['report_texts'])}</b> متن ثبت شد.\n\n"
        f"📊 <b>تعداد اکانت‌ها:</b> {available}\n\n"
        f"🔢 <b>تعداد اکانت‌ها</b> را وارد کنید (حداکثر {available}):",
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
                f"❌ <b>بین ۱ تا {available} وارد کنید!</b>",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            return
        
        report_temp[user_id]["count"] = count
        report_temp[user_id]["current_step"] = "repeat"
        user_states[user_id] = "waiting_report_repeat"
        
        await update.message.reply_text(
            f"✅ <b>تعداد:</b> {count}\n\n"
            "🔄 <b>تعداد دفعات</b> (۱ تا ۳):",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        
    except ValueError:
        await update.message.reply_text(
            "❌ <b>عدد وارد کنید!</b>",
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
                "❌ <b>بین ۱ تا ۳ وارد کنید!</b>",
                reply_markup=back_button(),
                parse_mode='HTML'
            )
            return
        
        report_temp[user_id]["repeat"] = repeat
        
        temp = report_temp.get(user_id, {})
        
        summary = f"""
📋 <b>خلاصه:</b>

🎯 <b>کانال:</b> {temp.get('group_link', 'نامشخص')}
📝 <b>پست‌ها:</b> {len(temp.get('posts', []))}
📄 <b>متن‌ها:</b> {len(temp.get('report_texts', []))}
🔢 <b>اکانت‌ها:</b> {temp.get('count', 0)}
🔄 <b>دفعات:</b> {temp.get('repeat', 0)}

⚠️ <b>تایید میکنی؟</b>
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
            "❌ <b>عدد وارد کنید!</b>",
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
        await query.answer("❌ <b>این دکمه مال تو نیست!</b>", show_alert=True)
        return
    
    if not check_user_access(update):
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    if user_id in processing_reports:
        await query.answer("⏳ <b>در حال اجراست!</b>", show_alert=True)
        return
    
    temp = report_temp.get(user_id, {})
    if not temp:
        await query.edit_message_text("❌ <b>اطلاعات یافت نشد!</b>", reply_markup=main_menu() if is_owner(user_id) else admin_menu(), parse_mode='HTML')
        return
    
    if not is_owner(user_id):
        db.set_admin_last_report(user_id)
    
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
            await query.edit_message_text("❌ <b>تعداد اکانت کافی نیست!</b>", reply_markup=main_menu() if is_owner(user_id) else admin_menu(), parse_mode='HTML')
            return
        
        total_success = 0
        total_fail = 0
        all_results = []
        
        for post_index, msg_id in enumerate(posts, 1):
            for text_index, report_text in enumerate(report_texts, 1):
                success = 0
                fail = 0
                results = []
                
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
                            except Exception:
                                fail += 1
                                results.append(f"❌ {mask_phone(account['phone'])}: خطا")
                                await asyncio.sleep(1)
                        
                        await client.disconnect()
                        
                    except Exception:
                        fail += 1
                        results.append(f"❌ {mask_phone(account['phone'])}: خطا")
                
                total_success += success
                total_fail += fail
                all_results.extend(results)
        
        report_id = db.add_report(
            group, group_link, str(report_texts), count, repeat,
            total_success, total_fail, total_success + total_fail,
            all_results, user_id
        )
        
        db.add_log(user_id, "execute_report", f"Report {report_id}")
        
        result_text = f"""
📊 <b>نتیجه:</b>

🎯 {group_link}
📝 <b>پست‌ها:</b> {len(posts)}
📄 <b>متن‌ها:</b> {len(report_texts)}
✅ <b>موفق:</b> {total_success}
❌ <b>خطا:</b> {total_fail}
📋 <b>مجموع:</b> {total_success + total_fail}

📋 <b>نتیجه ریپورت:</b>
"""
        
        for r in all_results[:5]:
            result_text += f"\n{r}"
        
        if len(all_results) > 5:
            result_text += f"\n... {len(all_results)-5} نتیجه دیگر"
        
        await query.edit_message_text(
            result_text,
            reply_markup=main_menu() if is_owner(user_id) else admin_menu(),
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
        logger.error(f"Report execution error: {e}")
        await query.edit_message_text(f"❌ <b>خطا:</b> {str(e)}", reply_markup=main_menu() if is_owner(user_id) else admin_menu(), parse_mode='HTML')
    finally:
        processing_reports.discard(user_id)
        if user_id in report_temp:
            del report_temp[user_id]

async def send_report_to_channel(context, report_data):
    try:
        text = f"""
📊 <b>گزارش جدید</b>

🎯 {report_data.get('group_link', 'نامشخص')}
📝 <b>پست‌ها:</b> {report_data.get('posts_count', 0)}
📄 <b>متن‌ها:</b> {report_data.get('texts_count', 0)}
🔢 <b>اکانت‌ها:</b> {report_data.get('accounts', 0)}
🔄 <b>دفعات:</b> {report_data.get('repeat', 0)}
✅ <b>موفق:</b> {report_data.get('success', 0)}
❌ <b>خطا:</b> {report_data.get('fail', 0)}
📋 <b>مجموع:</b> {report_data.get('total', 0)}
📅 {report_data.get('date', '')[:19]}
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
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    reports = db.get_reports(10)
    if not reports:
        await query.edit_message_text(
            "📭 <b>هیچ گزارشی ثبت نشده!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    text = "📊 <b>تاریخچه:</b>\n\n"
    for i, r in enumerate(reports[:5], 1):
        text += f"{i}. 🎯 {r.get('group_name', 'نامشخص')}\n"
        text += f"   ✅ <b>موفق:</b> {r.get('success_count', 0)}\n"
        text += f"   ❌ <b>خطا:</b> {r.get('fail_count', 0)}\n"
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
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ <b>فقط مالک میتواند ادمین مدیریت کند!</b>", show_alert=True)
        return
    
    user_msg_ids[user_id] = query.message.message_id
    
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
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ <b>فقط مالک میتواند ادمین اضافه کند!</b>", show_alert=True)
        return
    
    user_msg_ids[user_id] = query.message.message_id
    user_states[user_id] = "waiting_admin_id"
    
    await query.edit_message_text(
        "➕ <b>افزودن ادمین</b>\n\n🆔 <b>آیدی عددی</b> را وارد کنید:",
        reply_markup=back_button(),
        parse_mode='HTML'
    )

async def handle_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not check_user_access(update) or user_id not in user_states or user_states[user_id] != "waiting_admin_id":
        return
    
    if not is_owner(user_id):
        return
    
    try:
        admin_id = int(update.message.text.strip())
        
        if db.is_admin(admin_id):
            await update.message.reply_text("⚠️ <b>قبلاً ادمین هست!</b>", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        if admin_id in OWNER_IDS:
            await update.message.reply_text("⚠️ <b>این کاربر مالک است!</b>", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        db.add_admin(admin_id)
        db.add_log(user_id, "add_admin", f"Added admin {admin_id}")
        
        await update.message.reply_text(
            f"✅ <b>ادمین</b> <code>{admin_id}</code> <b>اضافه شد!</b>",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        del user_states[user_id]
            
    except ValueError:
        await update.message.reply_text(
            "❌ <b>عدد وارد کنید!</b>",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ <b>فقط مالک میتواند ادمین حذف کند!</b>", show_alert=True)
        return
    
    user_msg_ids[user_id] = query.message.message_id
    
    admins = db.get_admins()
    admins = [a for a in admins if a not in OWNER_IDS]
    
    if not admins:
        await query.edit_message_text(
            "📭 <b>ادمین اضافه‌ای نیست!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    keyboard = []
    for admin in admins:
        keyboard.append([InlineKeyboardButton(f"🗑 {admin}", callback_data=f"remove_adm_{admin}")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="manage_admins")])
    
    await query.edit_message_text(
        "🗑 <b>انتخاب کنید:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def remove_admin_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.answer("❌ <b>فقط مالک میتواند ادمین حذف کند!</b>", show_alert=True)
        return
    
    user_msg_ids[user_id] = query.message.message_id
    admin_id = int(query.data.split("_")[2])
    
    if db.is_admin(admin_id) and admin_id not in OWNER_IDS:
        db.remove_admin(admin_id)
        db.add_log(user_id, "remove_admin", f"Removed admin {admin_id}")
        await query.edit_message_text(
            f"✅ <b>ادمین</b> <code>{admin_id}</code> <b>حذف شد!</b>",
            reply_markup=back_button(),
            parse_mode='HTML'
        )
    else:
        await query.answer("❌ <b>یافت نشد!</b>", show_alert=True)

async def list_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.answer("🚫 <b>دسترسی غیرمجاز!</b>", show_alert=True)
        return
    
    user_id = query.from_user.id
    user_msg_ids[user_id] = query.message.message_id
    
    text = "👥 <b>لیست ادمین‌ها:</b>\n\n"
    text += "🔹 <b>مالک‌ها:</b>\n"
    for uid in OWNER_IDS:
        text += f"   • <code>{uid}</code> (دسترسی کامل)\n"
    
    admins = db.get_admins()
    extra_admins = [a for a in admins if a not in OWNER_IDS]
    
    if extra_admins:
        text += "\n🔸 <b>ادمین‌ها:</b>\n"
        for admin in extra_admins:
            text += f"   • <code>{admin}</code> (دسترسی محدود)\n"
    else:
        text += "\n📭 <i>هیچ ادمینی اضافه نشده.</i>"
    
    await query.edit_message_text(
        text,
        reply_markup=back_button(),
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

# ==================== اجرا ====================

async def async_main():
    app = Application.builder().token(TOKEN).build()
    
    try:
        await app.bot.delete_webhook()
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
    app.add_handler(CallbackQueryHandler(developer, pattern="developer"))
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
    print("✅ همه پیام‌ها ویرایشی")
    print("✅ فقط مالک‌ها دسترسی کامل دارند")
    print("✅ ادمین‌ها دسترسی محدود دارند")
    print("✅ محدودیت گزارش برای ادمین‌ها (۱ ساعت)")
    print("✅ دکمه درباره تیم اضافه شد")
    print("✅ متن‌های جدید اعمال شدند")
    print("=" * 50)
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

def main():
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(async_main())
        loop.close()
    except RuntimeError:
        asyncio.run(async_main())

if __name__ == "__main__":
    main()
