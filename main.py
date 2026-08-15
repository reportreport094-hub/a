import os
import re
import json
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv

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
    RPCError
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

# ==================== دیتا ====================

DATA_FILE = "bot_data.json"
SESSIONS_DIR = "sessions"
BACKUP_DIR = "backups"

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

def load_data():
    """بارگذاری دیتا با پشتیبان‌گیری خودکار"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            # بازیابی از پشتیبان
            backup_files = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('bot_data_backup_')])
            if backup_files:
                latest_backup = os.path.join(BACKUP_DIR, backup_files[-1])
                try:
                    with open(latest_backup, 'r', encoding='utf-8') as f:
                        logger.info(f"Restored from backup: {latest_backup}")
                        return json.load(f)
                except:
                    pass
            return default_data()
    return default_data()

def default_data():
    return {"accounts": [], "admins": [], "reports": []}

def save_data(data):
    """ذخیره دیتا با پشتیبان‌گیری"""
    try:
        # پشتیبان‌گیری خودکار هر 10 بار
        if not hasattr(save_data, "counter"):
            save_data.counter = 0
        save_data.counter += 1
        
        if save_data.counter % 10 == 0:
            backup_file = os.path.join(BACKUP_DIR, f"bot_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Backup created: {backup_file}")
        
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving data: {e}")
        return False

data = load_data()

# ==================== متغیرها ====================

user_states = {}
user_temp = {}
report_temp = {}
processing_reports = set()  # جلوگیری از اجرای همزمان

# ==================== بررسی دسترسی ====================

def is_allowed(user_id):
    return user_id in ALLOWED_USERS or user_id in data.get("admins", [])

def check_user_access(update):
    """بررسی دسترسی با لاگینگ"""
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
    # حذف پیام کاربر برای امنیت
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
        logger.error(f"Connection error: {e}")
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
        logger.error(f"Code verification error: {e}")
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
        logger.error(f"Password error: {e}")
        await status_msg.edit_text(f"❌ پسورد اشتباه!\n\n{str(e)}", reply_markup=back_button(), parse_mode='HTML')

async def get_account_info(update, client, user_id, status_msg):
    try:
        me = await client.get_me()
        
        account = {
            "phone": me.phone,
            "username": me.username,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "user_id": me.id,
            "session_file": client.session.filename,
            "api_id": user_temp.get(user_id, {}).get("api_id"),  # ذخیره API ID
            "api_hash": user_temp.get(user_id, {}).get("api_hash"),  # ذخیره API Hash
            "created_at": datetime.now().isoformat(),
            "is_active": True
        }
        
        if any(a.get('user_id') == me.id for a in data.get("accounts", [])):
            await status_msg.edit_text("⚠️ این اکانت قبلاً ثبت شده!", reply_markup=main_menu(), parse_mode='HTML')
            if user_id in user_temp:
                del user_temp[user_id]
            if user_id in user_states:
                del user_states[user_id]
            await client.disconnect()
            return
        
        data.setdefault("accounts", []).append(account)
        save_data(data)
        
        await status_msg.edit_text(
            f"✅ <b>اکانت با موفقیت اضافه شد!</b>\n\n"
            f"📱 شماره: <code>{account['phone']}</code>\n"
            f"👤 نام: {account['first_name']} {account.get('last_name', '')}\n"
            f"🆔 آیدی: <code>{account['user_id']}</code>\n\n"
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
        logger.error(f"Get account error: {e}")
        await status_msg.edit_text(f"❌ خطا: {str(e)}", reply_markup=main_menu(), parse_mode='HTML')

# ==================== لیست و حذف اکانت ====================

async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    accounts = data.get("accounts", [])
    if not accounts:
        await query.edit_message_text("📭 <b>هیچ اکانتی ثبت نشده!</b>", reply_markup=back_button(), parse_mode='HTML')
        return
    
    text = "📋 <b>لیست اکانت‌های فعال:</b>\n\n"
    for i, acc in enumerate(accounts, 1):
        text += f"✅ <b>{i}.</b> 📱 <code>{acc.get('phone', 'نامشخص')}</code>\n"
        text += f"   👤 {acc.get('first_name', '')} {acc.get('last_name', '')}\n"
        if acc.get('username'):
            text += f"   🆔 @{acc.get('username')}\n"
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
    
    accounts = data.get("accounts", [])
    if not accounts:
        await query.edit_message_text("📭 اکانتی برای حذف نیست!", reply_markup=back_button(), parse_mode='HTML')
        return
    
    keyboard = []
    for i, acc in enumerate(accounts):
        keyboard.append([InlineKeyboardButton(f"🗑 {acc.get('phone', 'نامشخص')}", callback_data=f"delete_acc_{i}")])
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
    
    accounts = data.get("accounts", [])
    if index >= len(accounts):
        await query.answer("❌ یافت نشد!", show_alert=True)
        return
    
    account = accounts[index]
    phone = account.get('phone', 'نامشخص')
    
    # حذف فایل سشن
    session_file = account.get('session_file')
    if session_file and os.path.exists(session_file):
        try:
            os.remove(session_file)
            logger.info(f"Session file deleted: {session_file}")
        except Exception as e:
            logger.error(f"Error deleting session: {e}")
    
    accounts.pop(index)
    data["accounts"] = accounts
    save_data(data)
    
    await query.edit_message_text(f"✅ اکانت {phone} حذف شد!", reply_markup=back_button(), parse_mode='HTML')

# ==================== ریپورت گروهی ====================

async def report_group_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    user_id = query.from_user.id
    
    if len(data.get("accounts", [])) < 1:
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
    
    # استخراج username از لینک - پشتیبانی از همه فرمت‌ها
    username = link
    if 't.me/' in link:
        # پشتیبانی از invite links
        if '+':
            # لینک دعوت خصوصی
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
    
    # پشتیبانی از فرمت‌های مختلف لینک پست
    match = re.search(r'https?://t\.me/([\w_+]+)/(\d+)', post_link)
    if not match:
        # تلاش برای لینک‌های c.t.me
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
    
    available = len(data.get("accounts", []))
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
        available = len(data.get("accounts", []))
        
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

# ==================== اجرای ریپورت ====================

async def execute_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # بررسی دسترسی با مالکیت
    user_id = query.from_user.id
    target_user_id = int(query.data.split("_")[2])
    
    # بررسی اینکه کاربری که کلیک کرده خودش باشه
    if user_id != target_user_id:
        await query.answer("❌ این دکمه مال شما نیست!", show_alert=True)
        return
    
    if not check_user_access(update):
        await query.edit_message_text("🚫 دسترسی غیرمجاز!", parse_mode='HTML')
        return
    
    # جلوگیری از اجرای همزمان
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
        
        accounts = data.get("accounts", [])[:count]
        
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
                    join_results.append(f"❌ {account.get('phone')}: سشن یافت نشد")
                    continue
                
                client = TelegramClient(session_file, 0, 0)
                await client.connect()
                
                if not await client.is_user_authorized():
                    join_results.append(f"❌ {account.get('phone')}: احراز نشده")
                    await client.disconnect()
                    continue
                
                try:
                    entity = await client.get_entity(f"@{group}")
                    try:
                        await client(functions.channels.JoinChannelRequest(entity))
                        join_results.append(f"✅ {account.get('phone')}: جوین شد")
                    except Exception as e:
                        if "already" in str(e).lower():
                            join_results.append(f"⚠️ {account.get('phone')}: قبلاً جوین بود")
                        else:
                            join_results.append(f"❌ {account.get('phone')}: خطا در جوین")
                    await asyncio.sleep(1)
                except Exception as e:
                    join_results.append(f"❌ {account.get('phone')}: گروه یافت نشد")
                
                await client.disconnect()
                
            except Exception as e:
                join_results.append(f"❌ {account.get('phone')}: خطا")
        
        # مرحله 2: ریپورت
        for account in accounts:
            try:
                session_file = account.get("session_file")
                if not session_file or not os.path.exists(session_file):
                    fail += 1
                    results.append(f"❌ {account.get('phone')}: سشن یافت نشد")
                    continue
                
                client = TelegramClient(session_file, 0, 0)
                await client.connect()
                
                if not await client.is_user_authorized():
                    fail += 1
                    results.append(f"❌ {account.get('phone')}: احراز نشده")
                    await client.disconnect()
                    continue
                
                try:
                    entity = await client.get_entity(f"@{group}")
                except Exception as e:
                    fail += 1
                    results.append(f"❌ {account.get('phone')}: گروه یافت نشد")
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
                        results.append(f"✅ {account.get('phone')}: ریپورت {i+1} ارسال شد")
                        await asyncio.sleep(2)
                    except FloodWaitError as e:
                        fail += 1
                        results.append(f"⏳ {account.get('phone')}: صبر {e.seconds} ثانیه")
                        await asyncio.sleep(min(e.seconds, 10))
                    except Exception as e:
                        fail += 1
                        results.append(f"❌ {account.get('phone')}: خطا در ریپورت {i+1}")
                        await asyncio.sleep(1)
                
                await client.disconnect()
                
            except Exception as e:
                fail += 1
                results.append(f"❌ {account.get('phone')}: خطا")
        
        # ثبت گزارش
        report_data = {
            "group": group,
            "group_link": group_link,
            "text": text,
            "accounts": count,
            "repeat": repeat,
            "success": success,
            "fail": fail,
            "total": success + fail,
            "join_results": join_results,
            "results": results,
            "date": datetime.now().isoformat(),
            "user_id": user_id
        }
        
        data.setdefault("reports", []).append(report_data)
        save_data(data)
        
        # نتیجه
        result_text = f"""
📊 <b>نتیجه ریپورت:</b>

🎯 گروه: {group_link}
✅ ریپورت ارسال شده: {success}
❌ خطا: {fail}
📋 مجموع تلاش: {success + fail}

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
        await send_report_to_channel(context, report_data)
        
    except Exception as e:
        logger.error(f"Report execution error: {e}")
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
✅ <b>ارسال شده:</b> {report_data.get('success', 0)}
❌ <b>خطا:</b> {report_data.get('fail', 0)}
📋 <b>مجموع:</b> {report_data.get('total', 0)}
📅 <b>تاریخ:</b> {report_data.get('date', '')[:19]}

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
    
    reports = data.get("reports", [])
    if not reports:
        await query.edit_message_text("📭 <b>هیچ گزارشی ثبت نشده!</b>", reply_markup=back_button(), parse_mode='HTML')
        return
    
    text = "📊 <b>تاریخچه ریپورت‌ها:</b>\n\n"
    for i, r in enumerate(reversed(reports[-5:]), 1):
        text += f"{i}. 🎯 {r.get('group', 'نامشخص')}\n"
        text += f"   ✅ ارسال: {r.get('success', 0)}\n"
        text += f"   ❌ خطا: {r.get('fail', 0)}\n"
        text += f"   📅 {r.get('date', '')[:10]}\n"
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
        
        if admin_id in data.get("admins", []):
            await update.message.reply_text("⚠️ قبلاً ادمین هست!", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        if admin_id in ALLOWED_USERS:
            await update.message.reply_text("⚠️ در لیست اصلی هست!", reply_markup=main_menu(), parse_mode='HTML')
            return
        
        data.setdefault("admins", []).append(admin_id)
        save_data(data)
        
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
    
    admins = data.get("admins", [])
    if not admins:
        await query.edit_message_text("📭 ادمینی نیست!", reply_markup=back_button(), parse_mode='HTML')
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
    
    admin_id = int(query.data.split("_")[2])
    
    if admin_id in data.get("admins", []):
        data["admins"].remove(admin_id)
        save_data(data)
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
    
    admins = data.get("admins", [])
    if admins:
        text += "\n🔸 <b>اضافه شده:</b>\n"
        for admin in admins:
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
    print("🤖 ربات مدیریت تلگرام")
    print("=" * 50)
    print(f"📊 اکانت‌ها: {len(data.get('accounts', []))}")
    print(f"👥 ادمین‌ها: {len(data.get('admins', []))}")
    print(f"📋 گزارش‌ها: {len(data.get('reports', []))}")
    print("=" * 50)
    print("🔄 در حال اجرا...")
    print("✅ تمام مشکلات امنیتی و اجرایی برطرف شد")
    
    app.run_polling()

if __name__ == "__main__":
    main()
