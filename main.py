import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import logging
from datetime import datetime
import re
import asyncio
import threading
from telethon import TelegramClient, errors, functions, types
import time

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# توکن ربات
TOKEN = "8986723154:AAH1qTObY9bo0A-csQFnSDYVcRhYr_DtsJ0"  # تغییر دهید

# لیست ایدی های مجاز
ALLOWED_USERS = [7803165903, 7795617350]

# فایل ذخیره‌سازی
DATA_FILE = "bot_data.json"
SESSIONS_DIR = "sessions"

# ایجاد پوشه‌ها
os.makedirs(SESSIONS_DIR, exist_ok=True)

# ایجاد ربات
bot = telebot.TeleBot(TOKEN, parse_mode='HTML')

# ==================== ساختار داده ====================

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
        "orders": [],
        "report_jobs": []
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

# ==================== متغیرهای موقت ====================

user_temp_data = {}  # برای ذخیره اطلاعات موقت کاربران
report_temp = {}  # برای ذخیره اطلاعات ریپورت

# ==================== منوها ====================

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton("📊 گزارشات", callback_data="reports"),
        InlineKeyboardButton("➕ افزودن اکانت", callback_data="add_account"),
        InlineKeyboardButton("📋 لیست اکانت‌ها", callback_data="list_accounts"),
        InlineKeyboardButton("👤 مدیریت ادمین", callback_data="manage_admins"),
        InlineKeyboardButton("🛡 ریپورت گروهی", callback_data="report_group"),
        InlineKeyboardButton("📦 سفارشات", callback_data="my_orders"),
        InlineKeyboardButton("❓ راهنما", callback_data="help")
    ]
    markup.add(*buttons)
    return markup

def back_button():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu"))
    return markup

def back_button_with_text(callback_data="back_to_menu"):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data=callback_data))
    return markup

# ==================== بررسی دسترسی ====================

def is_allowed(user_id):
    return user_id in ALLOWED_USERS or user_id in data["admins"]

# ==================== شروع ====================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    if not is_allowed(user_id):
        bot.send_message(
            message.chat.id,
            "🚫 <b>دسترسی غیرمجاز!</b>\n\n"
            "شما اجازه استفاده از این ربات را ندارید.",
            parse_mode='HTML'
        )
        return
    
    welcome_text = """
🌟 <b>به ربات حرفه‌ای مدیریت تلگرام خوش آمدید!</b> 🌟

<b>🤖 رباتی قدرتمند برای مدیریت و ریپورت گروه‌های تلگرام</b>

✨ <b>قابلیت‌های ویژه:</b>
• ➕ افزودن اکانت‌های تلگرام با سشن
• 🛡 ریپورت گروهی با چندین اکانت
• 📊 مدیریت و گزارش‌گیری
• 👥 مدیریت ادمین‌ها
• 📋 لیست کامل اکانت‌ها
• 💾 ذخیره‌سازی خودکار اطلاعات

<b>📌 راهنمای سریع:</b>
برای افزودن اکانت جدید:
1️⃣ روی دکمه <b>"➕ افزودن اکانت"</b> کلیک کنید
2️⃣ شماره تلفن را وارد کنید
3️⃣ API ID را وارد کنید
4️⃣ API Hash را وارد کنید
5️⃣ در صورت نیاز پسورد را وارد کنید
6️⃣ کد تایید را وارد کنید

برای ریپورت گروهی:
1️⃣ روی دکمه <b>"🛡 ریپورت گروهی"</b> کلیک کنید
2️⃣ لینک گروه را بفرستید
3️⃣ لینک پست را بفرستید
4️⃣ متن ریپورت را وارد کنید
5️⃣ تعداد اکانت‌ها را مشخص کنید
6️⃣ تعداد دفعات ریپورت را تعیین کنید

⚠️ <b>نکات امنیتی:</b>
• توکن خود را محافظت کنید
• فقط به افراد مطمئن دسترسی بدهید
• سشن‌ها به صورت امن ذخیره می‌شوند
"""
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_menu()
    )

# ==================== افزودن اکانت ====================

@bot.callback_query_handler(func=lambda call: call.data == "add_account")
def add_account_start(call):
    user_id = call.from_user.id
    
    # ریست اطلاعات قبلی
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    user_temp_data[user_id] = {}
    
    bot.edit_message_text(
        "🔐 <b>افزودن اکانت جدید تلگرام</b>\n\n"
        "لطفاً اطلاعات زیر را به ترتیب وارد کنید:\n\n"
        "1️⃣ <b>شماره تلفن</b> (به همراه کد کشور)\n"
        "   مثال: <code>+989123456789</code>\n\n"
        "2️⃣ <b>API ID</b> (از my.telegram.org)\n"
        "3️⃣ <b>API Hash</b> (از my.telegram.org)\n"
        "4️⃣ (اختیاری) <b>پسورد</b> (در صورت وجود)\n"
        "5️⃣ <b>کد تایید</b> (ارسال می‌شود)\n\n"
        "⚠️ <i>دقت کنید اطلاعات را دقیق وارد کنید.</i>\n"
        "برای شروع، <b>شماره تلفن</b> را وارد کنید:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button_with_text("cancel_add_account"),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)
    bot.register_next_step_handler(call.message, process_phone)

def process_phone(message):
    user_id = message.from_user.id
    phone = message.text.strip()
    
    # بررسی فرمت شماره
    if not re.match(r'^\+?\d{10,15}$', phone):
        bot.send_message(
            message.chat.id,
            "❌ <b>فرمت شماره تلفن نامعتبر!</b>\n\n"
            "لطفاً شماره را با فرمت صحیح وارد کنید:\n"
            "مثال: <code>+989123456789</code>",
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_phone)
        return
    
    user_temp_data[user_id]["phone"] = phone
    
    bot.send_message(
        message.chat.id,
        f"✅ شماره <code>{phone}</code> ثبت شد.\n\n"
        "🔑 لطفاً <b>API ID</b> خود را وارد کنید:\n"
        "(از سایت my.telegram.org دریافت کنید)",
        reply_markup=back_button_with_text("cancel_add_account"),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_api_id)

def process_api_id(message):
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
        bot.register_next_step_handler(message, process_api_id)
        return
    
    user_temp_data[user_id]["api_id"] = api_id
    
    bot.send_message(
        message.chat.id,
        f"✅ API ID ثبت شد.\n\n"
        "🔐 لطفاً <b>API Hash</b> خود را وارد کنید:\n"
        "(از my.telegram.org دریافت کنید)",
        reply_markup=back_button_with_text("cancel_add_account"),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_api_hash)

def process_api_hash(message):
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
        bot.register_next_step_handler(message, process_api_hash)
        return
    
    user_temp_data[user_id]["api_hash"] = api_hash
    
    # سوال درباره پسورد
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ دارد", callback_data=f"has_password_{user_id}"),
        InlineKeyboardButton("❌ ندارد", callback_data=f"no_password_{user_id}")
    )
    markup.add(InlineKeyboardButton("🔙 لغو", callback_data="cancel_add_account"))
    
    bot.send_message(
        message.chat.id,
        "🔒 <b>آیا این اکانت پسورد (Two-Factor Authentication) دارد؟</b>\n\n"
        "اگر اکانت شما پسورد دارد، روی <b>✅ دارد</b> کلیک کنید.",
        reply_markup=markup,
        parse_mode='HTML'
    )

# ==================== مدیریت پسورد ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith(("has_password_", "no_password_")))
def handle_password_choice(call):
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
        bot.register_next_step_handler(call.message, process_password)
    
    elif action == "no_password":
        user_temp_data[user_id]["password"] = None
        bot.edit_message_text(
            "✅ بدون پسورد.\n\n"
            "🔄 در حال ارسال درخواست به تلگرام...",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        # شروع فرآیند اتصال
        start_telegram_connection(user_id, call.message)

def process_password(message):
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
        bot.register_next_step_handler(message, process_password)
        return
    
    user_temp_data[user_id]["password"] = password
    
    bot.send_message(
        message.chat.id,
        "✅ پسورد ثبت شد.\n\n"
        "🔄 در حال ارسال درخواست به تلگرام...",
        reply_markup=back_button_with_text("cancel_add_account"),
        parse_mode='HTML'
    )
    
    start_telegram_connection(user_id, message)

# ==================== اتصال به تلگرام ====================

def start_telegram_connection(user_id, message):
    temp_data = user_temp_data.get(user_id, {})
    phone = temp_data.get("phone")
    api_id = temp_data.get("api_id")
    api_hash = temp_data.get("api_hash")
    
    if not all([phone, api_id, api_hash]):
        bot.send_message(
            message.chat.id,
            "❌ <b>اطلاعات کامل نیست!</b>\n\n"
            "لطفاً دوباره از ابتدا تلاش کنید.",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        return
    
    # ارسال پیام وضعیت
    status_msg = bot.send_message(
        message.chat.id,
        "⏳ <b>در حال اتصال به تلگرام...</b>\n\n"
        f"📱 شماره: <code>{phone}</code>\n"
        "🔄 لطفاً صبر کنید...",
        parse_mode='HTML'
    )
    
    # اجرا در ترد جداگانه
    def run_async():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(connect_to_telegram(user_id, message, status_msg))
        loop.close()
    
    thread = threading.Thread(target=run_async)
    thread.start()

async def connect_to_telegram(user_id, message, status_msg):
    temp_data = user_temp_data.get(user_id, {})
    phone = temp_data.get("phone")
    api_id = temp_data.get("api_id")
    api_hash = temp_data.get("api_hash")
    password = temp_data.get("password")
    
    try:
        # ایجاد کلاینت
        session_file = os.path.join(SESSIONS_DIR, f"{phone}.session")
        client = TelegramClient(session_file, int(api_id), api_hash)
        
        await client.connect()
        
        # بررسی احراز هویت
        if not await client.is_user_authorized():
            # ارسال کد تایید
            await client.send_code_request(phone)
            
            bot.edit_message_text(
                "📨 <b>کد تایید ارسال شد!</b>\n\n"
                f"📱 شماره: <code>{phone}</code>\n\n"
                "🔑 لطفاً کد تایید ۵ رقمی را که به تلگرام شما ارسال شده وارد کنید:\n"
                "(اگر کد را دریافت نکردید، دوباره تلاش کنید)",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=back_button_with_text("cancel_add_account"),
                parse_mode='HTML'
            )
            
            # ذخیره کلاینت برای مرحله بعد
            user_temp_data[user_id]["client"] = client
            
            # منتظر دریافت کد
            bot.register_next_step_handler(message, verify_code_step, client, user_id)
            
        else:
            # قبلاً احراز هویت شده
            bot.edit_message_text(
                "✅ <b>این اکانت قبلاً احراز هویت شده!</b>\n\n"
                "🔄 در حال دریافت اطلاعات...",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode='HTML'
            )
            
            # دریافت اطلاعات اکانت
            await get_account_info(message, client, user_id, status_msg)
            
    except Exception as e:
        logger.error(f"Error connecting to Telegram: {e}")
        bot.edit_message_text(
            f"❌ <b>خطا در اتصال!</b>\n\n"
            f"🔴 {str(e)}\n\n"
            "لطفاً اطلاعات را بررسی کنید و دوباره تلاش کنید.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

# ==================== تایید کد ====================

def verify_code_step(message, client, user_id):
    code = message.text.strip()
    
    # بررسی کد
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
    
    # اجرا در ترد جداگانه
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
        # تایید کد
        await client.sign_in(code=code)
        
        # اگر پسورد نیاز باشد
        if password:
            try:
                await client.sign_in(password=password)
            except errors.SessionPasswordNeededError:
                bot.edit_message_text(
                    "🔑 <b>این اکانت نیاز به پسورد دارد!</b>\n\n"
                    "لطفاً پسورد اکانت را وارد کنید:",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    reply_markup=back_button_with_text("cancel_add_account"),
                    parse_mode='HTML'
                )
                bot.register_next_step_handler(message, process_password_after_code, client, user_id)
                return
        
        # دریافت اطلاعات اکانت
        await get_account_info(message, client, user_id, status_msg)
        
    except errors.SessionPasswordNeededError:
        bot.edit_message_text(
            "🔑 <b>این اکانت نیاز به پسورد دارد!</b>\n\n"
            "لطفاً پسورد اکانت را وارد کنید:",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_password_after_code, client, user_id)
        
    except Exception as e:
        logger.error(f"Error verifying code: {e}")
        bot.edit_message_text(
            f"❌ <b>خطا در تایید کد!</b>\n\n"
            f"🔴 {str(e)}\n\n"
            "لطفاً دوباره تلاش کنید.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

def process_password_after_code(message, client, user_id):
    password = message.text.strip()
    
    if len(password) < 4:
        bot.send_message(
            message.chat.id,
            "❌ <b>پسورد باید حداقل ۴ کاراکتر باشد!</b>",
            reply_markup=back_button_with_text("cancel_add_account"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_password_after_code, client, user_id)
        return
    
    # ارسال پیام وضعیت
    status_msg = bot.send_message(
        message.chat.id,
        "⏳ <b>در حال تایید پسورد...</b>",
        parse_mode='HTML'
    )
    
    def run_async():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(verify_password_async(message, client, user_id, password, status_msg))
        loop.close()
    
    thread = threading.Thread(target=run_async)
    thread.start()

async def verify_password_async(message, client, user_id, password, status_msg):
    try:
        await client.sign_in(password=password)
        await get_account_info(message, client, user_id, status_msg)
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        bot.edit_message_text(
            f"❌ <b>پسورد اشتباه است!</b>\n\n"
            f"🔴 {str(e)}",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

# ==================== دریافت اطلاعات اکانت ====================

async def get_account_info(message, client, user_id, status_msg):
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
            bot.edit_message_text(
                "⚠️ <b>این اکانت قبلاً ثبت شده است!</b>",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            if user_id in user_temp_data:
                del user_temp_data[user_id]
            return
        
        # ذخیره اکانت
        data["accounts"].append(account_info)
        save_data(data)
        
        # نمایش پیام موفقیت
        success_text = f"""
✅ <b>اکانت با موفقیت اضافه شد!</b>

📱 <b>شماره:</b> <code>{account_info['phone']}</code>
👤 <b>نام:</b> {account_info['first_name']} {account_info.get('last_name', '')}
🆔 <b>آیدی:</b> <code>{account_info['user_id']}</code>
📅 <b>تاریخ:</b> {account_info['created_at'][:10]}

🎉 اکانت شما آماده استفاده است!
"""
        
        bot.edit_message_text(
            success_text,
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        
        # پاک کردن دیتای موقت
        if user_id in user_temp_data:
            del user_temp_data[user_id]
        
        # بستن کلاینت
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"Error getting account info: {e}")
        bot.edit_message_text(
            f"❌ <b>خطا!</b>\n\n"
            f"🔴 {str(e)}",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

# ==================== لیست اکانت‌ها ====================

@bot.callback_query_handler(func=lambda call: call.data == "list_accounts")
def list_accounts(call):
    if not data["accounts"]:
        bot.edit_message_text(
            "📭 <b>هیچ اکانتی ثبت نشده است!</b>\n\n"
            "برای افزودن اکانت جدید، روی دکمه <b>'➕ افزودن اکانت'</b> کلیک کنید.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        return
    
    text = "📋 <b>لیست اکانت‌های فعال:</b>\n\n"
    for i, acc in enumerate(data["accounts"], 1):
        status = "✅" if acc.get('is_active', True) else "❌"
        text += f"{status} <b>{i}.</b> 📱 <code>{acc.get('phone', 'نامشخص')}</code>\n"
        text += f"   👤 {acc.get('first_name', '')} {acc.get('last_name', '')}\n"
        if acc.get('username'):
            text += f"   @{acc.get('username')}\n"
        text += f"   🆔 <code>{acc.get('user_id', 'نامشخص')}</code>\n"
        text += f"   📅 {acc.get('created_at', 'نامشخص')[:10]}\n"
        text += "─" * 30 + "\n"
    
    # اضافه کردن دکمه حذف اکانت
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🗑 حذف اکانت", callback_data="delete_account_menu"))
    markup.add(InlineKeyboardButton("🔙 بازگشت به منو", callback_data="back_to_menu"))
    
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

# ==================== حذف اکانت ====================

@bot.callback_query_handler(func=lambda call: call.data == "delete_account_menu")
def delete_account_menu(call):
    if not data["accounts"]:
        bot.edit_message_text(
            "📭 <b>هیچ اکانتی برای حذف وجود ندارد!</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for i, acc in enumerate(data["accounts"]):
        phone = acc.get('phone', 'نامشخص')
        markup.add(InlineKeyboardButton(
            f"🗑 حذف {phone}",
            callback_data=f"delete_account_{i}"
        ))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="list_accounts"))
    
    bot.edit_message_text(
        "🗑 <b>انتخاب اکانت برای حذف:</b>\n\n"
        "روی اکانت مورد نظر کلیک کنید:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_account_"))
def delete_account(call):
    index = int(call.data.split("_")[2])
    
    if index >= len(data["accounts"]):
        bot.answer_callback_query(call.id, "❌ اکانت یافت نشد!", show_alert=True)
        return
    
    account = data["accounts"][index]
    phone = account.get('phone', 'نامشخص')
    
    # حذف فایل سشن
    session_file = account.get('session_file')
    if session_file and os.path.exists(session_file):
        try:
            os.remove(session_file)
        except:
            pass
    
    # حذف از لیست
    data["accounts"].pop(index)
    save_data(data)
    
    bot.edit_message_text(
        f"✅ <b>اکانت {phone} با موفقیت حذف شد!</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id, "✅ اکانت حذف شد")

# ==================== گزارشات ====================

@bot.callback_query_handler(func=lambda call: call.data == "reports")
def show_reports(call):
    if not data["reports"]:
        bot.edit_message_text(
            "📭 <b>هیچ گزارشی ثبت نشده است!</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        return
    
    text = "📊 <b>لیست گزارشات ریپورت:</b>\n\n"
    for i, report in enumerate(reversed(data["reports"][-10:]), 1):
        text += f"<b>{i}.</b> 🎯 گروه: {report.get('group', 'نامشخص')}\n"
        text += f"   ✅ موفق: {report.get('success_count', 0)}\n"
        text += f"   ❌ ناموفق: {report.get('fail_count', 0)}\n"
        text += f"   📅 {report.get('date', 'نامشخص')[:10]}\n"
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
                "⚠️ <b>این کاربر در لیست اصلی است!</b>",
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

# ==================== سفارشات ====================

@bot.callback_query_handler(func=lambda call: call.data == "my_orders")
def my_orders(call):
    user_id = call.from_user.id
    user_orders = [o for o in data["orders"] if o.get('user_id') == user_id]
    
    if not user_orders:
        bot.edit_message_text(
            "📭 <b>شما هیچ سفارشی ثبت نکرده‌اید!</b>",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
    else:
        text = "📦 <b>سفارشات من:</b>\n\n"
        for i, order in enumerate(reversed(user_orders), 1):
            status_emoji = "✅" if order.get('status') == "تایید شده" else "⏳" if order.get('status') == "در انتظار تایید" else "❌"
            text += f"{status_emoji} <b>{i}.</b> {order.get('title', 'بدون عنوان')}\n"
            text += f"   💰 {order.get('price', 'نامشخص')}\n"
            text += f"   🔄 {order.get('status', 'نامشخص')}\n"
            text += "─" * 30 + "\n"
        
        bot.edit_message_text(
            text,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
    
    bot.answer_callback_query(call.id)

# ==================== راهنما ====================

@bot.callback_query_handler(func=lambda call: call.data == "help")
def help_menu(call):
    help_text = """
❓ <b>راهنمای ربات</b>

<b>🔹 افزودن اکانت:</b>
1. شماره تلفن را وارد کنید
2. API ID را از my.telegram.org بگیرید
3. API Hash را وارد کنید
4. در صورت نیاز پسورد را وارد کنید
5. کد تایید را وارد کنید

<b>🔹 ریپورت گروهی:</b>
1. لینک گروه/کانال را بفرستید
2. لینک پست را بفرستید
3. متن ریپورت را وارد کنید
4. تعداد اکانت‌ها را مشخص کنید
5. تعداد دفعات ریپورت را تعیین کنید

<b>🔹 مدیریت اکانت‌ها:</b>
• مشاهده لیست اکانت‌ها
• حذف اکانت‌های غیرفعال

<b>🔹 مدیریت ادمین:</b>
• افزودن ادمین جدید
• حذف ادمین
• مشاهده لیست ادمین‌ها

<b>⚠️ نکات امنیتی:</b>
• هرگز توکن خود را به اشتراک نگذارید
• از اکانت‌های قابل اعتماد استفاده کنید
• سشن‌ها به صورت امن ذخیره می‌شوند
"""
    
    bot.edit_message_text(
        help_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

# ==================== ریپورت گروهی ====================

@bot.callback_query_handler(func=lambda call: call.data == "report_group")
def report_group_start(call):
    user_id = call.from_user.id
    
    if len(data["accounts"]) < 1:
        bot.edit_message_text(
            "⚠️ <b>هیچ اکانتی ثبت نشده است!</b>\n\n"
            "لطفاً ابتدا اکانت‌های خود را اضافه کنید.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        return
    
    if user_id in report_temp:
        del report_temp[user_id]
    report_temp[user_id] = {}
    
    bot.edit_message_text(
        "🛡 <b>ریپورت گروهی/کانال</b>\n\n"
        "لطفاً <b>لینک گروه یا کانال</b> مورد نظر را ارسال کنید:\n\n"
        "مثال:\n"
        "<code>https://t.me/username</code>\n"
        "یا\n"
        "<code>@username</code>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button_with_text("cancel_report"),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)
    bot.register_next_step_handler(call.message, process_report_group_link)

def process_report_group_link(message):
    user_id = message.from_user.id
    link = message.text.strip()
    
    # استخراج username
    username = link
    if 't.me/' in link:
        username = link.split('t.me/')[-1]
    if username.startswith('@'):
        username = username[1:]
    username = username.split('/')[0]
    
    if not username:
        bot.send_message(
            message.chat.id,
            "❌ <b>لینک نامعتبر!</b>\n\n"
            "لطفاً یک لینک معتبر ارسال کنید.",
            reply_markup=back_button_with_text("cancel_report"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_report_group_link)
        return
    
    report_temp[user_id]["group_username"] = username
    report_temp[user_id]["group_link"] = link
    
    bot.send_message(
        message.chat.id,
        f"✅ لینک گروه ثبت شد.\n\n"
        "📝 حالا <b>لینک پست</b> مورد نظر برای ریپورت را ارسال کنید:\n\n"
        "مثال: <code>https://t.me/username/123</code>",
        reply_markup=back_button_with_text("cancel_report"),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_report_post_link)

def process_report_post_link(message):
    user_id = message.from_user.id
    post_link = message.text.strip()
    
    if not re.match(r'https?://t\.me/[\w_]+/\d+', post_link):
        bot.send_message(
            message.chat.id,
            "❌ <b>لینک پست نامعتبر!</b>\n\n"
            "لطفاً یک لینک معتبر ارسال کنید.",
            reply_markup=back_button_with_text("cancel_report"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_report_post_link)
        return
    
    report_temp[user_id]["post_link"] = post_link
    
    # استخراج message_id
    try:
        message_id = int(post_link.split('/')[-1])
        report_temp[user_id]["message_id"] = message_id
    except:
        pass
    
    bot.send_message(
        message.chat.id,
        f"✅ لینک پست ثبت شد.\n\n"
        "📝 <b>متن ریپورت</b> را وارد کنید:\n\n"
        "این متنی است که برای ریپورت ارسال می‌شود.\n"
        "مثال: <i>این گروه کلاهبرداری است</i>",
        reply_markup=back_button_with_text("cancel_report"),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_report_text)

def process_report_text(message):
    user_id = message.from_user.id
    report_text = message.text.strip()
    
    if len(report_text) < 10:
        bot.send_message(
            message.chat.id,
            "❌ <b>متن ریپورت خیلی کوتاه است!</b>\n\n"
            "لطفاً متن کامل‌تری وارد کنید (حداقل ۱۰ کاراکتر).",
            reply_markup=back_button_with_text("cancel_report"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_report_text)
        return
    
    report_temp[user_id]["report_text"] = report_text
    
    available = len(data["accounts"])
    
    bot.send_message(
        message.chat.id,
        f"✅ متن ریپورت ثبت شد.\n\n"
        f"📊 <b>تعداد اکانت‌های موجود:</b> {available}\n\n"
        "🔢 <b>تعداد اکانت‌هایی که می‌خواهید ریپورت بزنند را وارد کنید:</b>\n"
        f"(حداکثر: {available})",
        reply_markup=back_button_with_text("cancel_report"),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_report_account_count)

def process_report_account_count(message):
    user_id = message.from_user.id
    try:
        count = int(message.text.strip())
        available = len(data["accounts"])
        
        if count < 1 or count > available:
            bot.send_message(
                message.chat.id,
                f"❌ <b>تعداد نامعتبر!</b>\n\n"
                f"لطفاً عددی بین ۱ تا {available} وارد کنید.",
                reply_markup=back_button_with_text("cancel_report"),
                parse_mode='HTML'
            )
            bot.register_next_step_handler(message, process_report_account_count)
            return
        
        report_temp[user_id]["account_count"] = count
        
        bot.send_message(
            message.chat.id,
            f"✅ تعداد اکانت‌ها: {count}\n\n"
            "🔄 <b>هر اکانت چند بار ریپورت بزند؟</b>\n"
            "(۱ تا ۵ بار پیشنهاد می‌شود)",
            reply_markup=back_button_with_text("cancel_report"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_report_repeat_count)
        
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ <b>لطفاً یک عدد معتبر وارد کنید!</b>",
            reply_markup=back_button_with_text("cancel_report"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_report_account_count)

def process_report_repeat_count(message):
    user_id = message.from_user.id
    try:
        repeat = int(message.text.strip())
        
        if repeat < 1 or repeat > 10:
            bot.send_message(
                message.chat.id,
                "❌ <b>تعداد نامعتبر!</b>\n\n"
                "تعداد دفعات باید بین ۱ تا ۱۰ باشد.",
                reply_markup=back_button_with_text("cancel_report"),
                parse_mode='HTML'
            )
            bot.register_next_step_handler(message, process_report_repeat_count)
            return
        
        report_temp[user_id]["repeat_count"] = repeat
        
        # نمایش خلاصه
        show_report_summary(user_id, message)
        
    except ValueError:
        bot.send_message(
            message.chat.id,
            "❌ <b>لطفاً یک عدد معتبر وارد کنید!</b>",
            reply_markup=back_button_with_text("cancel_report"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_report_repeat_count)

def show_report_summary(user_id, message):
    temp = report_temp.get(user_id, {})
    
    summary = f"""
📋 <b>خلاصه ریپورت:</b>

🎯 <b>گروه/کانال:</b> {temp.get('group_link', 'نامشخص')}
📝 <b>لینک پست:</b> {temp.get('post_link', 'نامشخص')}
📄 <b>متن ریپورت:</b> {temp.get('report_text', 'نامشخص')}
🔢 <b>تعداد اکانت‌ها:</b> {temp.get('account_count', 0)}
🔄 <b>تعداد دفعات:</b> {temp.get('repeat_count', 0)}

⚠️ <i>آیا از انجام این ریپورت مطمئن هستید؟</i>
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ تایید و اجرا", callback_data=f"execute_report_{user_id}"),
        InlineKeyboardButton("❌ لغو", callback_data="cancel_report")
    )
    
    bot.send_message(
        message.chat.id,
        summary,
        reply_markup=markup,
        parse_mode='HTML'
    )

# ==================== اجرای ریپورت ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith("execute_report_"))
def execute_report(call):
    user_id = int(call.data.split("_")[2])
    temp = report_temp.get(user_id, {})
    
    if not temp:
        bot.answer_callback_query(call.id, "❌ اطلاعات ریپورت یافت نشد!")
        return
    
    status_msg = bot.edit_message_text(
        "⏳ <b>در حال اجرای ریپورت...</b>\n\n"
        "لطفاً صبر کنید...",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    def run_report():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(execute_report_async(user_id, call.message, status_msg))
        loop.close()
    
    thread = threading.Thread(target=run_report)
    thread.start()
    
    bot.answer_callback_query(call.id, "✅ ریپورت در حال اجرا...")

async def execute_report_async(user_id, message, status_msg):
    temp = report_temp.get(user_id, {})
    
    group_username = temp.get("group_username")
    post_link = temp.get("post_link")
    report_text = temp.get("report_text", "گزارش کلاهبرداری")
    account_count = temp.get("account_count", 1)
    repeat_count = temp.get("repeat_count", 1)
    message_id = temp.get("message_id")
    
    # انتخاب اکانت‌ها
    accounts = data["accounts"][:account_count]
    
    if len(accounts) < account_count:
        bot.edit_message_text(
            "❌ <b>تعداد اکانت‌ها کافی نیست!</b>",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        return
    
    results = []
    success_count = 0
    fail_count = 0
    total_attempts = account_count * repeat_count
    
    bot.edit_message_text(
        f"⏳ <b>در حال ریپورت...</b>\n\n"
        f"📊 اکانت‌ها: {len(accounts)}\n"
        f"🔄 دفعات: {repeat_count}\n"
        f"📋 مجموع: {total_attempts}\n"
        f"✅ موفق: 0\n"
        f"❌ ناموفق: 0",
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        parse_mode='HTML'
    )
    
    for idx, account in enumerate(accounts):
        try:
            session_file = account.get("session_file")
            if not session_file or not os.path.exists(session_file):
                results.append(f"❌ اکانت {account.get('phone')}: فایل سشن یافت نشد")
                fail_count += 1
                continue
            
            client = TelegramClient(session_file, 0, 0)
            await client.connect()
            
            if not await client.is_user_authorized():
                results.append(f"❌ اکانت {account.get('phone')}: احراز هویت نشده")
                fail_count += 1
                await client.disconnect()
                continue
            
            try:
                entity = await client.get_entity(f"@{group_username}")
            except Exception as e:
                results.append(f"❌ اکانت {account.get('phone')}: گروه یافت نشد")
                fail_count += 1
                await client.disconnect()
                continue
            
            if not message_id:
                try:
                    if '/' in post_link:
                        parts = post_link.split('/')
                        if parts[-1].isdigit():
                            message_id = int(parts[-1])
                except:
                    pass
                
                if not message_id:
                    results.append(f"❌ اکانت {account.get('phone')}: لینک پست نامعتبر")
                    fail_count += 1
                    await client.disconnect()
                    continue
            
            # انجام ریپورت با تکرار
            for i in range(repeat_count):
                try:
                    report_reason = types.InputReportReasonSpam()
                    
                    await client(functions.messages.ReportRequest(
                        peer=entity,
                        id=[message_id],
                        reason=report_reason,
                        message=report_text
                    ))
                    
                    success_count += 1
                    results.append(f"✅ اکانت {account.get('phone')}: ریپورت {i+1} موفق")
                    
                    await asyncio.sleep(1.5)
                    
                except Exception as e:
                    results.append(f"❌ اکانت {account.get('phone')}: خطا در ریپورت {i+1}")
                    fail_count += 1
                
                # بروزرسانی وضعیت
                try:
                    progress = int((idx * repeat_count + i + 1) / total_attempts * 100)
                    bot.edit_message_text(
                        f"⏳ <b>در حال ریپورت...</b> {progress}%\n\n"
                        f"📊 اکانت‌ها: {len(accounts)}\n"
                        f"🔄 دفعات: {repeat_count}\n"
                        f"📋 مجموع: {total_attempts}\n"
                        f"✅ موفق: {success_count}\n"
                        f"❌ ناموفق: {fail_count}\n"
                        f"📌 {idx+1}/{len(accounts)}",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            await client.disconnect()
            
        except Exception as e:
            results.append(f"❌ اکانت {account.get('phone')}: خطا")
            fail_count += 1
    
    # ثبت گزارش
    report_record = {
        "group": group_username,
        "post_link": post_link,
        "report_text": report_text,
        "accounts_used": account_count,
        "repeat_count": repeat_count,
        "success_count": success_count,
        "fail_count": fail_count,
        "total_attempts": total_attempts,
        "results": results,
        "user_id": user_id,
        "date": datetime.now().isoformat()
    }
    
    data["reports"].append(report_record)
    save_data(data)
    
    # نمایش نتیجه
    result_text = f"""
📊 <b>نتیجه ریپورت:</b>

🎯 گروه: {group_username}
✅ موفق: {success_count}
❌ ناموفق: {fail_count}
📋 مجموع: {total_attempts}

📋 <b>جزئیات:</b>
"""
    
    for res in results[:10]:
        result_text += f"\n{res}"
    
    if len(results) > 10:
        result_text += f"\n\n<i>... و {len(results) - 10} نتیجه دیگر</i>"
    
    bot.edit_message_text(
        result_text,
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    
    if user_id in report_temp:
        del report_temp[user_id]

# ==================== دکمه‌های عمومی ====================

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    bot.edit_message_text(
        "🌟 <b>منوی اصلی</b>\n\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_add_account")
def cancel_add_account(call):
    user_id = call.from_user.id
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    
    bot.edit_message_text(
        "❌ <b>عملیات افزودن اکانت لغو شد!</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_report")
def cancel_report(call):
    user_id = call.from_user.id
    if user_id in report_temp:
        del report_temp[user_id]
    
    bot.edit_message_text(
        "❌ <b>عملیات ریپورت لغو شد!</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

# ==================== اجرای ربات ====================

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 ربات حرفه‌ای مدیریت و ریپورت تلگرام")
    print("=" * 60)
    print(f"📊 تعداد اکانت‌ها: {len(data['accounts'])}")
    print(f"👥 تعداد ادمین‌ها: {len(data['admins'])}")
    print(f"📦 تعداد سفارشات: {len(data['orders'])}")
    print(f"📋 تعداد گزارش‌ها: {len(data['reports'])}")
    print("=" * 60)
    print("🔄 ربات در حال اجراست...")
    print("=" * 60)
    
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        print(f"❌ خطا: {e}")
