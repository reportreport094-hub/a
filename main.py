import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import json
import os
import logging
from datetime import datetime
import time
import re
from telethon import TelegramClient, errors
import asyncio
import threading

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# توکن ربات
TOKEN = "8986723154:AAH1qTObY9bo0A-csQFnSDYVcRhYr_DtsJ0"  # حتماً تغییر دهید!

# لیست ایدی های مجاز
ALLOWED_USERS = [7803165903, 7795617350]

# فایل ذخیره‌سازی
DATA_FILE = "bot_data.json"
SESSIONS_DIR = "sessions"

# ایجاد پوشه‌ها
os.makedirs(SESSIONS_DIR, exist_ok=True)

# ایجاد ربات
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# ساختار داده
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return default_data()
    return default_data()

def default_data():
    return {
        "accounts": [],
        "admins": [],
        "reports": [],
        "orders": []
    }

def save_data(data):
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving data: {e}")
        return False

data = load_data()

# کلاس مدیریت سشن
class SessionManager:
    def __init__(self):
        self.active_sessions = {}
        self.client = None
    
    async def create_session(self, phone, api_id, api_hash, password=None):
        try:
            # ایجاد کلاینت جدید
            session_file = os.path.join(SESSIONS_DIR, f"{phone}.session")
            client = TelegramClient(session_file, int(api_id), api_hash)
            
            await client.connect()
            
            # ارسال کد تایید
            if not await client.is_user_authorized():
                await client.send_code_request(phone)
                return {
                    "status": "code_sent",
                    "phone": phone,
                    "client": client,
                    "session_file": session_file
                }
            else:
                return {
                    "status": "already_authorized",
                    "phone": phone
                }
                
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def verify_code(self, client, code, password=None):
        try:
            await client.sign_in(code=code)
            
            if password:
                await client.sign_in(password=password)
            
            # ذخیره اطلاعات سشن
            me = await client.get_me()
            
            account_info = {
                "phone": me.phone,
                "username": me.username,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "user_id": me.id,
                "session_file": client.session.filename,
                "created_at": datetime.now().isoformat(),
                "is_active": True
            }
            
            # ذخیره در دیتا
            data["accounts"].append(account_info)
            save_data(data)
            
            return {
                "status": "success",
                "account": account_info
            }
            
        except errors.SessionPasswordNeededError:
            return {
                "status": "password_needed"
            }
        except Exception as e:
            logger.error(f"Error verifying code: {e}")
            return {
                "status": "error",
                "error": str(e)
            }

session_manager = SessionManager()

# دکمه‌های شیشه‌ای (Inline Keyboard)
def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📊 گزارشات", callback_data="reports"),
        InlineKeyboardButton("➕ افزودن اکانت", callback_data="add_account"),
        InlineKeyboardButton("📋 لیست اکانت‌ها", callback_data="list_accounts"),
        InlineKeyboardButton("👤 مدیریت ادمین", callback_data="manage_admins"),
        InlineKeyboardButton("🛒 سفارش جدید", callback_data="new_order"),
        InlineKeyboardButton("📦 سفارشات من", callback_data="my_orders"),
        InlineKeyboardButton("❓ راهنما", callback_data="help")
    ]
    markup.add(*buttons)
    return markup

# دکمه بازگشت
def back_button():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu"))
    return markup

# دکمه بازگشت با متن دلخواه
def back_button_with_text(callback_data="back_to_menu"):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data=callback_data))
    return markup

# تابع بررسی دسترسی
def is_allowed(user_id):
    return user_id in ALLOWED_USERS or user_id in data["admins"]

# تابع ارسال/ویرایش پیام
def send_or_edit_message(chat_id, text, reply_markup=None, message_id=None):
    try:
        if message_id:
            # ویرایش پیام قبلی
            bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return True
        else:
            # ارسال پیام جدید
            bot.send_message(
                chat_id,
                text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
            return True
    except Exception as e:
        logger.error(f"Error in send_or_edit_message: {e}")
        # اگر ویرایش نشد، پیام جدید بفرست
        try:
            return bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode='HTML')
        except:
            return False

# ==================== دستورات اصلی ====================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    if not is_allowed(user_id):
        bot.send_message(
            message.chat.id,
            "🚫 <b>دسترسی غیرمجاز!</b>\n\n"
            "شما اجازه استفاده از این ربات را ندارید.\n"
            "برای دریافت دسترسی با ادمین تماس بگیرید.",
            parse_mode='HTML'
        )
        return
    
    welcome_text = """
🌟 <b>به ربات حرفه‌ای مدیریت تلگرام خوش آمدید!</b> 🌟

<b>🤖 رباتی قدرتمند برای مدیریت اکانت‌های تلگرام</b>

✨ <b>قابلیت‌های ویژه:</b>
• ➕ افزودن اکانت‌های تلگرام با سشن
• 📊 مدیریت و گزارش‌گیری از اکانت‌ها
• 🛒 ثبت سفارش‌های پیشرفته
• 👥 مدیریت ادمین‌های ربات
• 📋 لیست کامل اکانت‌های فعال
• 🔒 امنیت بالا با دسترسی‌های محدود
• 💾 ذخیره‌سازی خودکار اطلاعات

<b>📌 راهنمای سریع:</b>
برای شروع، یکی از دکمه‌های زیر را انتخاب کنید.
برای افزودن اکانت جدید، روی دکمه <b>"➕ افزودن اکانت"</b> کلیک کنید.

<b>⚠️ نکات امنیتی:</b>
• توکن و اطلاعات خود را محافظت کنید
• فقط به افراد مطمئن دسترسی بدهید
• سشن‌ها به صورت امن ذخیره می‌شوند

<b>📞 پشتیبانی:</b>
در صورت بروز مشکل، با ادمین تماس بگیرید.

💪 <i>با استفاده از این ربات، مدیریت اکانت‌های تلگرام خود را حرفه‌ای‌تر کنید!</i>
"""
    
    # ارسال پیام خوشامدگویی با دکمه‌های منو
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_menu()
    )

# ==================== مدیریت دکمه‌ها ====================

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    
    if not is_allowed(user_id):
        bot.answer_callback_query(call.id, "🚫 شما دسترسی ندارید!", show_alert=True)
        return
    
    # پیام فعلی را برای ویرایش نگه می‌داریم
    msg_id = call.message.message_id
    chat_id = call.message.chat.id
    
    # بازگشت به منو
    if call.data == "back_to_menu":
        bot.edit_message_text(
            "🌟 <b>به منوی اصلی خوش آمدید!</b>\n\nلطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        return
    
    # گزارشات
    if call.data == "reports":
        if not data["reports"]:
            bot.edit_message_text(
                "📭 <b>هیچ گزارشی ثبت نشده است!</b>\n\n"
                "برای ثبت گزارش، ابتدا یک اکانت اضافه کنید و سپس گزارش ثبت کنید.",
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=back_button(),
                parse_mode='HTML'
            )
        else:
            text = "📊 <b>لیست گزارشات:</b>\n\n"
            for i, report in enumerate(reversed(data["reports"][-10:]), 1):
                text += f"<b>{i}.</b> 📱 اکانت: <code>{report.get('phone', 'نامشخص')}</code>\n"
                text += f"📝 گزارش: {report.get('text', 'بدون متن')}\n"
                text += f"🕐 تاریخ: {report.get('date', 'نامشخص')}\n"
                text += "─" * 30 + "\n"
            
            if len(data["reports"]) > 10:
                text += f"\n<i>🔹 نمایش ۱۰ گزارش آخر از {len(data['reports'])} گزارش</i>"
            
            bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=back_button(),
                parse_mode='HTML'
            )
        bot.answer_callback_query(call.id)
        return
    
    # لیست اکانت‌ها
    if call.data == "list_accounts":
        if not data["accounts"]:
            bot.edit_message_text(
                "📭 <b>هیچ اکانتی ثبت نشده است!</b>\n\n"
                "برای افزودن اکانت جدید، روی دکمه <b>'➕ افزودن اکانت'</b> کلیک کنید.",
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=back_button(),
                parse_mode='HTML'
            )
        else:
            text = "📋 <b>لیست اکانت‌های فعال:</b>\n\n"
            for i, acc in enumerate(data["accounts"], 1):
                status = "✅" if acc.get('is_active', True) else "❌"
                text += f"{status} <b>{i}.</b> 📱 {acc.get('phone', 'نامشخص')}\n"
                text += f"   👤 {acc.get('first_name', '')} {acc.get('last_name', '')}\n"
                if acc.get('username'):
                    text += f"   @{acc.get('username')}\n"
                text += f"   🆔 {acc.get('user_id', 'نامشخص')}\n"
                text += f"   📅 {acc.get('created_at', 'نامشخص')[:10]}\n"
                text += "─" * 30 + "\n"
            
            bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=msg_id,
                reply_markup=back_button(),
                parse_mode='HTML'
            )
        bot.answer_callback_query(call.id)
        return
    
    # افزودن اکانت
    if call.data == "add_account":
        bot.edit_message_text(
            "🔐 <b>افزودن اکانت جدید تلگرام</b>\n\n"
            "لطفاً اطلاعات زیر را به ترتیب وارد کنید:\n\n"
            "1️⃣ <b>شماره تلفن</b> (به همراه کد کشور)\n"
            "   مثال: <code>+989123456789</code>\n\n"
            "2️⃣ <b>API ID</b> (از my.telegram.org)\n"
            "3️⃣ <b>API Hash</b> (از my.telegram.org)\n"
            "4️⃣ (اختیاری) <b>پسورد</b> (در صورت وجود)\n\n"
            "⚠️ <i>دقت کنید اطلاعات را دقیق وارد کنید.</i>\n"
            "برای شروع، <b>شماره تلفن</b> را وارد کنید:",
            chat_id=chat_id,
            message_id=msg_id,
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        # شروع فرآیند افزودن اکانت
        bot.register_next_step_handler(call.message, process_add_account_step1)
        return

# ==================== فرآیند افزودن اکانت ====================

# متغیرهای موقت برای ذخیره اطلاعات کاربر
user_temp_data = {}

def process_add_account_step1(message):
    user_id = message.from_user.id
    phone = message.text.strip()
    
    # بررسی فرمت شماره
    if not re.match(r'^\+?\d{10,15}$', phone):
        bot.send_message(
            message.chat.id,
            "❌ <b>فرمت شماره تلفن نامعتبر!</b>\n\n"
            "لطفاً شماره را با فرمت صحیح وارد کنید:\n"
            "مثال: <code>+989123456789</code>\n\n"
            "برای لغو، روی دکمه بازگشت کلیک کنید.",
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_add_account_step1)
        return
    
    user_temp_data[user_id] = {"phone": phone}
    
    bot.send_message(
        message.chat.id,
        f"✅ شماره <code>{phone}</code> ثبت شد.\n\n"
        "🔑 لطفاً <b>API ID</b> خود را وارد کنید:\n"
        "(از سایت my.telegram.org دریافت کنید)",
        reply_markup=back_button_with_text("cancel_add_account"),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_add_account_step2)

def process_add_account_step2(message):
    user_id = message.from_user.id
    api_id = message.text.strip()
    
    if not api_id.isdigit():
        bot.send_message(
            message.chat.id,
            "❌ <b>API ID باید عددی باشد!</b>\n\n"
            "لطفاً یک عدد معتبر وارد کنید.\n"
            "مثال: <code>1234567</code>",
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_add_account_step2)
        return
    
    user_temp_data[user_id]["api_id"] = api_id
    
    bot.send_message(
        message.chat.id,
        f"✅ API ID ثبت شد.\n\n"
        "🔐 لطفاً <b>API Hash</b> خود را وارد کنید:",
        reply_markup=back_button_with_text("cancel_add_account"),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_add_account_step3)

def process_add_account_step3(message):
    user_id = message.from_user.id
    api_hash = message.text.strip()
    
    if len(api_hash) < 10:
        bot.send_message(
            message.chat.id,
            "❌ <b>API Hash نامعتبر!</b>\n\n"
            "لطفاً یک API Hash معتبر وارد کنید.",
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_add_account_step3)
        return
    
    user_temp_data[user_id]["api_hash"] = api_hash
    
    # سوال درباره پسورد
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ دارد", callback_data=f"has_password_{user_id}"),
        InlineKeyboardButton("❌ ندارد", callback_data=f"no_password_{user_id}")
    )
    markup.add(InlineKeyboardButton("🔙 لغو", callback_data="cancel_add_account"))
    
    bot.send_message(
        message.chat.id,
        "🔒 <b>آیا این اکانت پسورد دارد؟</b>\n\n"
        "اگر اکانت شما پسورد (Two-Factor Authentication) دارد، انتخاب کنید.",
        reply_markup=markup,
        parse_mode='HTML'
    )

# مدیریت پسورد
@bot.callback_query_handler(func=lambda call: call.data.startswith(("has_password_", "no_password_")))
def handle_password(call):
    user_id = call.from_user.id
    data_parts = call.data.split("_")
    action = data_parts[0]
    temp_user_id = int(data_parts[2]) if len(data_parts) > 2 else None
    
    # بررسی اینکه کاربر خودش این درخواست رو زده
    if temp_user_id != user_id:
        bot.answer_callback_query(call.id, "❌ این درخواست برای شما نیست!", show_alert=True)
        return
    
    if action == "has_password":
        bot.edit_message_text(
            "🔑 <b>لطفاً پسورد اکانت را وارد کنید:</b>\n\n"
            "⚠️ دقت کنید پسورد را دقیق وارد کنید.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        bot.register_next_step_handler(call.message, process_add_account_step4_password)
    
    elif action == "no_password":
        user_temp_data[user_id]["password"] = None
        bot.edit_message_text(
            "✅ بدون پسورد.\n\n"
            "🔄 در حال اتصال به تلگرام...",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        # ادامه فرآیند بدون پسورد
        create_telegram_session(user_id, call.message)

def process_add_account_step4_password(message):
    user_id = message.from_user.id
    password = message.text.strip()
    
    if len(password) < 4:
        bot.send_message(
            message.chat.id,
            "❌ <b>پسورد باید حداقل ۴ کاراکتر باشد!</b>\n\n"
            "لطفاً پسورد صحیح را وارد کنید.",
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_add_account_step4_password)
        return
    
    user_temp_data[user_id]["password"] = password
    
    bot.send_message(
        message.chat.id,
        "✅ پسورد ثبت شد.\n\n"
        "🔄 در حال اتصال به تلگرام...",
        reply_markup=back_button_with_text("cancel_add_account"),
        parse_mode='HTML'
    )
    
    create_telegram_session(user_id, message)

# ایجاد سشن تلگرام
def create_telegram_session(user_id, message):
    temp_data = user_temp_data.get(user_id, {})
    phone = temp_data.get("phone")
    api_id = temp_data.get("api_id")
    api_hash = temp_data.get("api_hash")
    password = temp_data.get("password")
    
    if not all([phone, api_id, api_hash]):
        bot.send_message(
            message.chat.id,
            "❌ <b>خطا!</b>\nاطلاعات کامل نیست. لطفاً دوباره تلاش کنید.",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        return
    
    # ارسال پیام وضعیت
    status_msg = bot.send_message(
        message.chat.id,
        "⏳ <b>در حال ایجاد سشن...</b>\n\n"
        f"📱 شماره: <code>{phone}</code>\n"
        "🔄 لطفاً صبر کنید...",
        parse_mode='HTML'
    )
    
    # اجرای async در thread جداگانه
    def run_async():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(create_session_async(user_id, message, status_msg))
        loop.close()
    
    thread = threading.Thread(target=run_async)
    thread.start()

async def create_session_async(user_id, message, status_msg):
    temp_data = user_temp_data.get(user_id, {})
    phone = temp_data.get("phone")
    api_id = temp_data.get("api_id")
    api_hash = temp_data.get("api_hash")
    password = temp_data.get("password")
    
    try:
        # ارسال درخواست کد
        result = await session_manager.create_session(phone, api_id, api_hash, password)
        
        if result["status"] == "code_sent":
            # کد تایید ارسال شد
            client = result["client"]
            
            bot.edit_message_text(
                "📨 <b>کد تایید ارسال شد!</b>\n\n"
                f"📱 شماره: <code>{phone}</code>\n\n"
                "🔑 لطفاً کد تایید ۵ رقمی را که به تلگرام شما ارسال شده وارد کنید:\n"
                "(اگر کد را دریافت نکردید، درخواست مجدد دهید)",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=back_button_with_text("cancel_add_account"),
                parse_mode='HTML'
            )
            
            # ذخیره کلاینت برای مرحله بعد
            user_temp_data[user_id]["client"] = client
            
            # منتظر دریافت کد
            bot.register_next_step_handler(message, verify_code_step, client, user_id)
            
        elif result["status"] == "already_authorized":
            bot.edit_message_text(
                "✅ <b>این اکانت قبلاً احراز هویت شده!</b>\n\n"
                f"📱 شماره: <code>{phone}</code>\n"
                "🔄 در حال دریافت اطلاعات...",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode='HTML'
            )
            # ادامه برای دریافت اطلاعات
            await get_account_info(message, client, user_id)
            
        else:
            bot.edit_message_text(
                f"❌ <b>خطا در اتصال!</b>\n\n"
                f"🔴 {result.get('error', 'خطای ناشناخته')}\n\n"
                "لطفاً اطلاعات را بررسی کرده و دوباره تلاش کنید.",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Error in create_session_async: {e}")
        bot.edit_message_text(
            f"❌ <b>خطا!</b>\n\n"
            f"🔴 {str(e)}\n\n"
            "لطفاً دوباره تلاش کنید.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

# تایید کد
def verify_code_step(message, client, user_id):
    code = message.text.strip()
    
    if not code.isdigit() or len(code) != 5:
        bot.send_message(
            message.chat.id,
            "❌ <b>کد نامعتبر!</b>\n\n"
            "کد تایید باید ۵ رقم باشد.\n"
            "لطفاً کد صحیح را وارد کنید:",
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, verify_code_step, client, user_id)
        return
    
    # ارسال پیام وضعیت
    status_msg = bot.send_message(
        message.chat.id,
        "⏳ <b>در حال تایید کد...</b>",
        parse_mode='HTML'
    )
    
    # اجرای async
    def run_async():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(verify_code_async(message, client, user_id, code, status_msg))
        loop.close()
    
    thread = threading.Thread(target=run_async)
    thread.start()

async def verify_code_async(message, client, user_id, code, status_msg):
    temp_data = user_temp_data.get(user_id, {})
    password = temp_data.get("password")
    
    try:
        result = await session_manager.verify_code(client, code, password)
        
        if result["status"] == "success":
            account = result["account"]
            
            bot.edit_message_text(
                "✅ <b>اکانت با موفقیت اضافه شد!</b>\n\n"
                f"📱 شماره: <code>{account['phone']}</code>\n"
                f"👤 نام: {account['first_name']} {account.get('last_name', '')}\n"
                f"🆔 آیدی: <code>{account['user_id']}</code>\n"
                f"📅 تاریخ: {account['created_at'][:10]}\n\n"
                "🎉 اکانت شما آماده استفاده است!",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            
            # پاک کردن داده موقت
            if user_id in user_temp_data:
                del user_temp_data[user_id]
                
        elif result["status"] == "password_needed":
            bot.edit_message_text(
                "🔑 <b>این اکانت نیاز به پسورد دارد!</b>\n\n"
                "لطفاً پسورد اکانت را وارد کنید:",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=back_button_with_text("cancel_add_account"),
                parse_mode='HTML'
            )
            bot.register_next_step_handler(message, process_password_after_code, client, user_id)
            
        else:
            bot.edit_message_text(
                f"❌ <b>خطا در تایید کد!</b>\n\n"
                f"🔴 {result.get('error', 'خطای ناشناخته')}\n\n"
                "لطفاً دوباره تلاش کنید.",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Error in verify_code_async: {e}")
        bot.edit_message_text(
            f"❌ <b>خطا!</b>\n\n"
            f"🔴 {str(e)}",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

async def get_account_info(message, client, user_id):
    try:
        me = await client.get_me()
        
        account_info = {
            "phone": me.phone,
            "username": me.username,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "user_id": me.id,
            "session_file": client.session.filename,
            "created_at": datetime.now().isoformat(),
            "is_active": True
        }
        
        # بررسی تکراری نبودن
        if any(acc.get('user_id') == me.id for acc in data["accounts"]):
            bot.send_message(
                message.chat.id,
                "⚠️ <b>این اکانت قبلاً ثبت شده است!</b>",
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            return
        
        data["accounts"].append(account_info)
        save_data(data)
        
        bot.send_message(
            message.chat.id,
            "✅ <b>اکانت با موفقیت اضافه شد!</b>\n\n"
            f"📱 شماره: <code>{account_info['phone']}</code>\n"
            f"👤 نام: {account_info['first_name']}\n"
            f"🆔 آیدی: <code>{account_info['user_id']}</code>",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
        bot.send_message(
            message.chat.id,
            f"❌ <b>خطا!</b>\n\n{str(e)}",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

# ==================== سفارشات ====================

@bot.callback_query_handler(func=lambda call: call.data == "new_order")
def new_order(call):
    bot.edit_message_text(
        "🛒 <b>ثبت سفارش جدید</b>\n\n"
        "لطفاً جزئیات سفارش خود را وارد کنید:\n\n"
        "📝 <b>عنوان سفارش:</b>\n"
        "📋 <b>توضیحات:</b>\n"
        "💰 <b>مبلغ:</b>\n"
        "📅 <b>تاریخ تحویل:</b>\n\n"
        "مثال:\n"
        "<code>سفارش طراحی لوگو\n"
        "طراحی لوگو برای شرکت فناوری\n"
        "2,500,000 تومان\n"
        "1402/12/15</code>\n\n"
        "⚠️ <i>هر خط یک بخش از سفارش است.</i>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button_with_text("cancel_order"),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)
    bot.register_next_step_handler(call.message, process_new_order)

def process_new_order(message):
    order_text = message.text.strip().split('\n')
    
    if len(order_text) < 4:
        bot.send_message(
            message.chat.id,
            "❌ <b>فرمت سفارش نامعتبر!</b>\n\n"
            "لطفاً اطلاعات را کامل وارد کنید:\n"
            "عنوان\nتوضیحات\nمبلغ\nتاریخ تحویل",
            reply_markup=back_button_with_text("cancel_order"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_new_order)
        return
    
    order = {
        "title": order_text[0],
        "description": order_text[1] if len(order_text) > 1 else "",
        "price": order_text[2] if len(order_text) > 2 else "نامشخص",
        "delivery_date": order_text[3] if len(order_text) > 3 else "نامشخص",
        "user_id": message.from_user.id,
        "user_name": message.from_user.first_name,
        "created_at": datetime.now().isoformat(),
        "status": "در انتظار تایید"
    }
    
    data["orders"].append(order)
    save_data(data)
    
    # ارسال به ادمین‌ها
    admin_text = f"""
📦 <b>سفارش جدید!</b>

👤 کاربر: {order['user_name']}
🆔 آیدی: <code>{order['user_id']}</code>

📝 <b>عنوان:</b> {order['title']}
📋 <b>توضیحات:</b> {order['description']}
💰 <b>مبلغ:</b> {order['price']}
📅 <b>تاریخ تحویل:</b> {order['delivery_date']}
🕐 <b>تاریخ ثبت:</b> {order['created_at'][:10]}

✅ برای تایید، روی دکمه زیر کلیک کنید.
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ تایید سفارش", callback_data=f"confirm_order_{len(data['orders'])-1}"),
        InlineKeyboardButton("❌ رد سفارش", callback_data=f"reject_order_{len(data['orders'])-1}")
    )
    
    # ارسال به همه ادمین‌ها
    for admin_id in data["admins"] + ALLOWED_USERS:
        try:
            bot.send_message(admin_id, admin_text, reply_markup=markup, parse_mode='HTML')
        except:
            pass
    
    bot.send_message(
        message.chat.id,
        "✅ <b>سفارش شما با موفقیت ثبت شد!</b>\n\n"
        f"📝 عنوان: {order['title']}\n"
        f"💰 مبلغ: {order['price']}\n"
        "🔄 وضعیت: در انتظار تایید\n\n"
        "به زودی با شما تماس گرفته می‌شود.",
        reply_markup=main_menu(),
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith(("confirm_order_", "reject_order_")))
def handle_order_decision(call):
    action, order_index = call.data.split("_")[0], int(call.data.split("_")[2])
    
    if order_index >= len(data["orders"]):
        bot.answer_callback_query(call.id, "❌ سفارش یافت نشد!", show_alert=True)
        return
    
    order = data["orders"][order_index]
    
    if action == "confirm":
        order["status"] = "تایید شده"
        status_text = "✅ تایید شد"
    else:
        order["status"] = "رد شده"
        status_text = "❌ رد شد"
    
    save_data(data)
    
    bot.edit_message_text(
        f"📦 <b>وضعیت سفارش تغییر کرد</b>\n\n"
        f"📝 عنوان: {order['title']}\n"
        f"🔄 وضعیت جدید: {status_text}",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    # اطلاع به کاربر
    try:
        bot.send_message(
            order['user_id'],
            f"🔄 <b>وضعیت سفارش شما تغییر کرد!</b>\n\n"
            f"📝 عنوان: {order['title']}\n"
            f"🔄 وضعیت جدید: {status_text}",
            parse_mode='HTML'
        )
    except:
        pass
    
    bot.answer_callback_query(call.id, f"✅ سفارش {status_text}")

@bot.callback_query_handler(func=lambda call: call.data == "my_orders")
def my_orders(call):
    user_id = call.from_user.id
    user_orders = [o for o in data["orders"] if o.get('user_id') == user_id]
    
    if not user_orders:
        bot.edit_message_text(
            "📭 <b>شما هیچ سفارشی ثبت نکرده‌اید!</b>\n\n"
            "برای ثبت سفارش جدید، روی دکمه <b>'🛒 سفارش جدید'</b> کلیک کنید.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
    else:
        text = "📦 <b>سفارشات من:</b>\n\n"
        for i, order in enumerate(reversed(user_orders), 1):
            status_emoji = "✅" if order['status'] == "تایید شده" else "⏳" if order['status'] == "در انتظار تایید" else "❌"
            text += f"{status_emoji} <b>{i}.</b> {order['title']}\n"
            text += f"   💰 {order['price']}\n"
            text += f"   🔄 {order['status']}\n"
            text += "─" * 30 + "\n"
        
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
    
    bot.answer_callback_query(call.id)

# ==================== مدیریت ادمین ====================

@bot.callback_query_handler(func=lambda call: call.data == "manage_admins")
def manage_admins(call):
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("➕ افزودن ادمین", callback_data="add_admin_ui"),
        InlineKeyboardButton("🗑 حذف ادمین", callback_data="remove_admin_ui"),
        InlineKeyboardButton("📋 لیست ادمین‌ها", callback_data="list_admins")
    ]
    markup.add(*buttons)
    markup.add(InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu"))
    
    bot.edit_message_text(
        "👥 <b>مدیریت ادمین‌ها</b>\n\n"
        "از دکمه‌های زیر برای مدیریت ادمین‌ها استفاده کنید:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "add_admin_ui")
def add_admin_ui(call):
    bot.edit_message_text(
        "👤 <b>افزودن ادمین جدید</b>\n\n"
        "لطفاً <b>آیدی عددی</b> کاربر مورد نظر را وارد کنید:\n\n"
        "⚠️ <i>فقط کاربرانی که آیدی آنها را وارد کنید، به ربات دسترسی خواهند داشت.</i>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)
    bot.register_next_step_handler(call.message, process_add_admin)

def process_add_admin(message):
    try:
        admin_id = int(message.text.strip())
        
        if admin_id in data["admins"]:
            bot.send_message(
                message.chat.id,
                "⚠️ <b>این کاربر قبلاً ادمین است!</b>",
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            return
        
        if admin_id in ALLOWED_USERS:
            bot.send_message(
                message.chat.id,
                "⚠️ <b>این کاربر در لیست اصلی است و نیازی به افزودن ندارد!</b>",
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            return
        
        data["admins"].append(admin_id)
        save_data(data)
        
        bot.send_message(
            message.chat.id,
            f"✅ <b>ادمین با موفقیت اضافه شد!</b>\n\n"
            f"🆔 آیدی: <code>{admin_id}</code>",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        
        # اطلاع به کاربر جدید
        try:
            bot.send_message(
                admin_id,
                "🎉 <b>شما به عنوان ادمین به ربات اضافه شدید!</b>\n\n"
                "حالا می‌توانید از تمام امکانات ربات استفاده کنید.",
                parse_mode='HTML'
            )
        except:
            pass
            
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ <b>فرمت نامعتبر!</b>\n\n"
            "لطفاً یک آیدی عددی معتبر وارد کنید.",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

@bot.callback_query_handler(func=lambda call: call.data == "remove_admin_ui")
def remove_admin_ui(call):
    if not data["admins"]:
        bot.edit_message_text(
            "📭 <b>هیچ ادمینی ثبت نشده است!</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for admin in data["admins"]:
        markup.add(InlineKeyboardButton(
            f"🗑 حذف {admin}",
            callback_data=f"remove_admin_{admin}"
        ))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="manage_admins"))
    
    bot.edit_message_text(
        "👥 <b>لیست ادمین‌ها:</b>\n\n"
        "برای حذف یک ادمین، روی دکمه مربوطه کلیک کنید:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_admin_"))
def remove_admin(call):
    admin_id = int(call.data.split("_")[2])
    
    if admin_id in data["admins"]:
        data["admins"].remove(admin_id)
        save_data(data)
        
        bot.edit_message_text(
            f"✅ <b>ادمین حذف شد!</b>\n\n"
            f"🆔 آیدی: <code>{admin_id}</code>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id, "✅ ادمین حذف شد")
    else:
        bot.answer_callback_query(call.id, "❌ ادمین یافت نشد!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "list_admins")
def list_admins(call):
    text = "👥 <b>لیست ادمین‌ها:</b>\n\n"
    text += "🔹 <b>ادمین‌های اصلی:</b>\n"
    for uid in ALLOWED_USERS:
        text += f"   • <code>{uid}</code> (اصلی)\n"
    
    if data["admins"]:
        text += "\n🔸 <b>ادمین‌های اضافه شده:</b>\n"
        for admin in data["admins"]:
            text += f"   • <code>{admin}</code>\n"
    else:
        text += "\n📭 <i>هیچ ادمین اضافه‌ای ثبت نشده است.</i>"
    
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button_with_text("manage_admins"),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

# ==================== راهنما ====================

@bot.callback_query_handler(func=lambda call: call.data == "help")
def help_menu(call):
    help_text = """
❓ <b>راهنمای ربات</b>

<b>🔹 افزودن اکانت:</b>
• شماره تلفن را وارد کنید
• API ID و API Hash را از my.telegram.org دریافت کنید
• کد تایید را وارد کنید
• در صورت نیاز، پسورد را وارد کنید

<b>🔹 مدیریت اکانت‌ها:</b>
• مشاهده لیست اکانت‌ها
• ثبت گزارش برای هر اکانت
• حذف اکانت‌های غیرفعال

<b>🔹 سفارشات:</b>
• ثبت سفارش جدید
• مشاهده سفارشات خود
• پیگیری وضعیت سفارش

<b>🔹 مدیریت ادمین:</b>
• افزودن ادمین جدید
• حذف ادمین
• مشاهده لیست ادمین‌ها

<b>⚠️ نکات امنیتی:</b>
• هرگز توکن خود را به اشتراک نگذارید
• از اکانت‌های قابل اعتماد استفاده کنید
• سشن‌ها به صورت امن ذخیره می‌شوند

<b>📞 پشتیبانی:</b>
در صورت مشکل با ادمین تماس بگیرید.
"""
    
    bot.edit_message_text(
        help_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

# ==================== لغو عملیات ====================

@bot.callback_query_handler(func=lambda call: call.data == "cancel_add_account")
def cancel_add_account(call):
    user_id = call.from_user.id
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    bot.edit_message_text(
        "❌ <b>عملیات لغو شد!</b>\n\n"
        "به منوی اصلی بازگشتید.",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_order")
def cancel_order(call):
    bot.edit_message_text(
        "❌ <b>ثبت سفارش لغو شد!</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

# ==================== اجرای ربات ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 ربات حرفه‌ای مدیریت تلگرام")
    print("=" * 50)
    print(f"📊 تعداد اکانت‌ها: {len(data['accounts'])}")
    print(f"👥 تعداد ادمین‌ها: {len(data['admins'])}")
    print(f"📦 تعداد سفارشات: {len(data['orders'])}")
    print("=" * 50)
    print("🔄 ربات در حال اجراست...")
    
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        print(f"❌ خطا: {e}")
