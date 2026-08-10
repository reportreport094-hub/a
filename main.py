import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import logging
from datetime import datetime
import re
import asyncio
import threading
from telethon import TelegramClient, functions, types
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError
)
import time

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TOKEN = "8986723154:AAH1qTObY9bo0A-csQFnSDYVcRhYr_DtsJ0"
ALLOWED_USERS = [7803165903, 7795617350]

DATA_FILE = "bot_data.json"
SESSIONS_DIR = "sessions"

os.makedirs(SESSIONS_DIR, exist_ok=True)

bot = telebot.TeleBot(TOKEN, parse_mode='HTML')
try:
    bot.remove_webhook()
except:
    pass

# ==================== دیتا ====================

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

# ==================== متغیرهای موقت ====================

user_temp = {}
report_temp = {}
user_message_ids = {}  # ذخیره message_id برای ویرایش

# ==================== منوها ====================

def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    
    markup.add(InlineKeyboardButton("🛡 ریپورت گروهی", callback_data="report_group"))
    
    markup.add(
        InlineKeyboardButton("➕ افزودن اکانت", callback_data="add_account"),
        InlineKeyboardButton("📋 لیست اکانت‌ها", callback_data="list_accounts")
    )
    
    markup.add(
        InlineKeyboardButton("📊 گزارشات", callback_data="reports"),
        InlineKeyboardButton("👤 مدیریت ادمین", callback_data="manage_admins")
    )
    
    markup.add(InlineKeyboardButton("❓ راهنما", callback_data="help"))
    
    return markup

def back_button():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu"))
    return markup

def back_to_main():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 منوی اصلی", callback_data="back_to_menu"))
    return markup

# ==================== بررسی دسترسی ====================

def is_allowed(user_id):
    return user_id in ALLOWED_USERS or user_id in data["admins"]

# ==================== تابع ویرایش پیام ====================

def edit_message(chat_id, message_id, text, reply_markup=None):
    try:
        bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return True
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        return False

def send_or_edit(chat_id, message_id, text, reply_markup=None):
    if message_id:
        return edit_message(chat_id, message_id, text, reply_markup)
    else:
        msg = bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode='HTML')
        return msg.message_id

# ==================== شروع ====================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    if not is_allowed(user_id):
        bot.send_message(
            message.chat.id,
            "🚫 دسترسی غیرمجاز!",
            parse_mode='HTML'
        )
        return
    
    welcome_text = """
🌟 <b>ربات مدیریت تلگرام</b>

📌 <b>قابلیت‌ها:</b>
🛡 ریپورت گروهی با چندین اکانت
➕ افزودن اکانت با سشن
📋 مدیریت اکانت‌ها
📊 مشاهده گزارشات

برای شروع یکی از گزینه‌ها رو انتخاب کن.
"""
    
    msg = bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    user_message_ids[user_id] = msg.message_id

# ==================== افزودن اکانت (کاملاً ویرایشی) ====================

@bot.callback_query_handler(func=lambda call: call.data == "add_account")
def add_account_start(call):
    user_id = call.from_user.id
    
    if user_id in user_temp:
        del user_temp[user_id]
    user_temp[user_id] = {}
    
    # ذخیره message_id برای ویرایش
    user_message_ids[user_id] = call.message.message_id
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        "➕ <b>افزودن اکانت جدید</b>\n\n"
        "برای اضافه کردن اکانت، اطلاعات زیر رو وارد کن:\n\n"
        "1️⃣ شماره تلفن (با کد کشور)\n"
        "   مثال: <code>+989123456789</code>\n\n"
        "2️⃣ API ID (از my.telegram.org)\n"
        "3️⃣ API Hash (از my.telegram.org)\n"
        "4️⃣ کد تایید (به تلگرامت ارسال میشه)\n\n"
        "📱 <b>شماره تلفن</b> رو وارد کن:",
        back_to_main()
    )
    
    bot.register_next_step_handler(call.message, process_phone)
    bot.answer_callback_query(call.id)

def process_phone(message):
    user_id = message.from_user.id
    phone = message.text.strip()
    msg_id = user_message_ids.get(user_id)
    
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        edit_message(
            message.chat.id,
            msg_id,
            "❌ شماره نامعتبر! لطفاً با کد کشور وارد کن.\n"
            "مثال: <code>+989123456789</code>",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_phone)
        return
    
    user_temp[user_id]['phone'] = phone
    
    edit_message(
        message.chat.id,
        msg_id,
        f"✅ شماره <code>{phone}</code> ثبت شد.\n\n"
        "🔑 <b>API ID</b> رو وارد کن:\n"
        "(از سایت my.telegram.org دریافت کن)\n"
        "⚠️ API ID باید عددی بین 1 تا 2147483647 باشه.",
        back_to_main()
    )
    bot.register_next_step_handler(message, process_api_id)

def process_api_id(message):
    user_id = message.from_user.id
    api_id = message.text.strip()
    msg_id = user_message_ids.get(user_id)
    
    try:
        api_id_int = int(api_id)
        if api_id_int > 2147483647:
            edit_message(
                message.chat.id,
                msg_id,
                "❌ عدد خیلی بزرگه! API ID باید بین 1 تا 2147483647 باشه.",
                back_to_main()
            )
            bot.register_next_step_handler(message, process_api_id)
            return
    except:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ API ID باید عدد باشه! لطفاً دوباره وارد کن.",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_api_id)
        return
    
    user_temp[user_id]['api_id'] = api_id
    
    edit_message(
        message.chat.id,
        msg_id,
        f"✅ API ID ثبت شد.\n\n"
        "🔐 <b>API Hash</b> رو وارد کن:\n"
        "(از my.telegram.org دریافت کن)",
        back_to_main()
    )
    bot.register_next_step_handler(message, process_api_hash)

def process_api_hash(message):
    user_id = message.from_user.id
    api_hash = message.text.strip()
    msg_id = user_message_ids.get(user_id)
    
    if len(api_hash) < 20:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ API Hash نامعتبر! لطفاً دوباره وارد کن.",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_api_hash)
        return
    
    user_temp[user_id]['api_hash'] = api_hash
    
    edit_message(
        message.chat.id,
        msg_id,
        "⏳ در حال ارسال کد تایید به تلگرام...\n"
        "لطفاً صبر کن...",
        None
    )
    
    start_connection(user_id, message, msg_id)

def start_connection(user_id, message, msg_id):
    temp = user_temp.get(user_id, {})
    phone = temp.get("phone")
    api_id = temp.get("api_id")
    api_hash = temp.get("api_hash")
    
    if not all([phone, api_id, api_hash]):
        edit_message(
            message.chat.id,
            msg_id,
            "❌ اطلاعات کامل نیست! دوباره تلاش کن.",
            main_menu()
        )
        return
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(connect_to_telegram(user_id, message, msg_id))
            loop.close()
        except Exception as e:
            logger.error(f"Error in async thread: {e}")
            edit_message(
                message.chat.id,
                msg_id,
                f"❌ خطا در اتصال!\n\n{str(e)}",
                main_menu()
            )
    
    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

async def connect_to_telegram(user_id, message, msg_id):
    temp = user_temp.get(user_id, {})
    phone = temp.get("phone")
    api_id = temp.get("api_id")
    api_hash = temp.get("api_hash")
    
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{phone}.session")
        client = TelegramClient(session_file, int(api_id), api_hash)
        
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            
            user_temp[user_id]['client'] = client
            
            edit_message(
                message.chat.id,
                msg_id,
                f"📨 <b>کد تایید ارسال شد!</b>\n\n"
                f"📱 شماره: <code>{phone}</code>\n\n"
                "🔑 کد تایید رو به صورت <b>۱.۲.۳.۴.۵</b> وارد کن:\n"
                "(مثلاً اگر کد ۱۲۳۴۵ است، عدد ۱۲۳۴۵ رو وارد کن)\n\n"
                "⚠️ توجه: کد باید ۵ رقم باشه",
                back_to_main()
            )
            
            bot.register_next_step_handler(message, verify_code, client, user_id)
        else:
            await get_account_info(message, client, user_id, msg_id)
            
    except PhoneNumberInvalidError:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ شماره وارد شده معتبر نیست!",
            main_menu()
        )
    except FloodWaitError as e:
        edit_message(
            message.chat.id,
            msg_id,
            f"⏳ لطفاً {e.seconds} ثانیه صبر کن و دوباره تلاش کن.",
            main_menu()
        )
    except Exception as e:
        logger.error(f"Error connecting: {e}")
        edit_message(
            message.chat.id,
            msg_id,
            f"❌ خطا در اتصال!\n\n{str(e)}",
            main_menu()
        )

def verify_code(message, client, user_id):
    code_input = message.text.strip()
    code = code_input.replace('.', '').replace('،', '').replace(' ', '').strip()
    msg_id = user_message_ids.get(user_id)
    
    if not code.isdigit() or len(code) != 5:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ کد باید ۵ رقم باشه! لطفاً کد رو به صورت ۱.۲.۳.۴.۵ وارد کن:\n"
            "مثال: <code>12345</code> یا <code>1.2.3.4.5</code>",
            back_to_main()
        )
        bot.register_next_step_handler(message, verify_code, client, user_id)
        return
    
    edit_message(
        message.chat.id,
        msg_id,
        "⏳ در حال تایید کد...",
        None
    )
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(verify_code_async(message, client, user_id, code, msg_id))
            loop.close()
        except Exception as e:
            logger.error(f"Error in verify async: {e}")
            edit_message(
                message.chat.id,
                msg_id,
                f"❌ خطا!\n\n{str(e)}",
                main_menu()
            )
    
    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

async def verify_code_async(message, client, user_id, code, msg_id):
    try:
        await client.sign_in(code=code)
        await get_account_info(message, client, user_id, msg_id)
        
    except SessionPasswordNeededError:
        edit_message(
            message.chat.id,
            msg_id,
            "🔑 <b>این اکانت پسورد (Two-Factor) داره!</b>\n\n"
            "لطفاً پسورد اکانت رو وارد کن:",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_password, client, user_id)
        
    except PhoneCodeExpiredError:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ کد تایید منقضی شده!\n\n"
            "در حال ارسال کد جدید...",
            back_to_main()
        )
        
        try:
            phone = user_temp.get(user_id, {}).get("phone")
            await client.send_code_request(phone)
            
            edit_message(
                message.chat.id,
                msg_id,
                "📨 کد جدید ارسال شد! لطفاً وارد کن:",
                back_to_main()
            )
            bot.register_next_step_handler(message, verify_code, client, user_id)
            
        except Exception as e:
            edit_message(
                message.chat.id,
                msg_id,
                f"❌ خطا در ارسال کد جدید: {str(e)}",
                main_menu()
            )
        
    except PhoneCodeInvalidError:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ کد اشتباه!\n\n"
            "لطفاً کد رو دقیق وارد کن.\n"
            "کد رو به صورت <b>۱.۲.۳.۴.۵</b> وارد کن.",
            back_to_main()
        )
        bot.register_next_step_handler(message, verify_code, client, user_id)
        
    except Exception as e:
        logger.error(f"Error verifying: {e}")
        edit_message(
            message.chat.id,
            msg_id,
            f"❌ خطا در تایید کد!\n\n{str(e)}",
            main_menu()
        )

def process_password(message, client, user_id):
    password = message.text.strip()
    msg_id = user_message_ids.get(user_id)
    
    if len(password) < 4:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ پسورد حداقل ۴ کاراکتر! دوباره وارد کن:",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_password, client, user_id)
        return
    
    edit_message(
        message.chat.id,
        msg_id,
        "⏳ در حال تایید پسورد...",
        None
    )
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(verify_password_async(message, client, user_id, password, msg_id))
            loop.close()
        except Exception as e:
            logger.error(f"Error in password async: {e}")
            edit_message(
                message.chat.id,
                msg_id,
                f"❌ خطا!\n\n{str(e)}",
                main_menu()
            )
    
    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

async def verify_password_async(message, client, user_id, password, msg_id):
    try:
        await client.sign_in(password=password)
        await get_account_info(message, client, user_id, msg_id)
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        edit_message(
            message.chat.id,
            msg_id,
            f"❌ پسورد اشتباه!\n\n{str(e)}",
            back_to_main()
        )

async def get_account_info(message, client, user_id, msg_id):
    try:
        me = await client.get_me()
        
        account = {
            "phone": me.phone,
            "username": me.username,
            "first_name": me.first_name,
            "last_name": me.last_name,
            "user_id": me.id,
            "session_file": client.session.filename,
            "created_at": datetime.now().isoformat(),
            "is_active": True
        }
        
        if any(a.get('user_id') == me.id for a in data["accounts"]):
            edit_message(
                message.chat.id,
                msg_id,
                "⚠️ این اکانت قبلاً ثبت شده!",
                main_menu()
            )
            if user_id in user_temp:
                del user_temp[user_id]
            await client.disconnect()
            return
        
        data["accounts"].append(account)
        save_data(data)
        
        edit_message(
            message.chat.id,
            msg_id,
            f"✅ <b>اکانت با موفقیت اضافه شد!</b>\n\n"
            f"📱 شماره: <code>{account['phone']}</code>\n"
            f"👤 نام: {account['first_name']} {account.get('last_name', '')}\n"
            f"🆔 آیدی: <code>{account['user_id']}</code>\n\n"
            "🎉 اکانت آماده استفاده است!",
            main_menu()
        )
        
        if user_id in user_temp:
            del user_temp[user_id]
        
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"Error getting account: {e}")
        edit_message(
            message.chat.id,
            msg_id,
            f"❌ خطا: {str(e)}",
            main_menu()
        )

# ==================== ادامه کد ====================

# [قسمت‌های لیست اکانت‌ها، ریپورت، مدیریت ادمین و راهنما]

@bot.callback_query_handler(func=lambda call: call.data == "list_accounts")
def list_accounts(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    if not data["accounts"]:
        edit_message(
            call.message.chat.id,
            call.message.message_id,
            "📭 <b>هیچ اکانتی ثبت نشده!</b>\n\n"
            "برای افزودن اکانت، روی دکمه <b>'➕ افزودن اکانت'</b> کلیک کن.",
            back_button()
        )
        bot.answer_callback_query(call.id)
        return
    
    text = "📋 <b>لیست اکانت‌های فعال:</b>\n\n"
    for i, acc in enumerate(data["accounts"], 1):
        status = "✅" if acc.get('is_active', True) else "❌"
        text += f"{status} <b>{i}.</b> 📱 <code>{acc.get('phone', 'نامشخص')}</code>\n"
        text += f"   👤 {acc.get('first_name', '')} {acc.get('last_name', '')}\n"
        if acc.get('username'):
            text += f"   🆔 @{acc.get('username')}\n"
        text += f"   📅 {acc.get('created_at', 'نامشخص')[:10]}\n"
        text += "─" * 25 + "\n"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🗑 حذف اکانت", callback_data="delete_account_menu"))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu"))
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        text,
        markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "delete_account_menu")
def delete_account_menu(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    if not data["accounts"]:
        edit_message(
            call.message.chat.id,
            call.message.message_id,
            "📭 اکانتی برای حذف نیست!",
            back_button()
        )
        bot.answer_callback_query(call.id)
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for i, acc in enumerate(data["accounts"]):
        markup.add(InlineKeyboardButton(
            f"🗑 {acc.get('phone', 'نامشخص')}",
            callback_data=f"delete_acc_{i}"
        ))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="list_accounts"))
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        "🗑 <b>انتخاب اکانت برای حذف:</b>\n\n"
        "روی اکانت مورد نظر کلیک کن:",
        markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_acc_"))
def delete_account(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    index = int(call.data.split("_")[2])
    
    if index >= len(data["accounts"]):
        bot.answer_callback_query(call.id, "❌ یافت نشد!", show_alert=True)
        return
    
    account = data["accounts"][index]
    phone = account.get('phone', 'نامشخص')
    
    session_file = account.get('session_file')
    if session_file and os.path.exists(session_file):
        try:
            os.remove(session_file)
        except:
            pass
    
    data["accounts"].pop(index)
    save_data(data)
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        f"✅ اکانت {phone} با موفقیت حذف شد!",
        back_button()
    )
    bot.answer_callback_query(call.id, "✅ حذف شد")

# ==================== ریپورت گروهی ====================

@bot.callback_query_handler(func=lambda call: call.data == "report_group")
def report_group_start(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    if len(data["accounts"]) < 1:
        edit_message(
            call.message.chat.id,
            call.message.message_id,
            "⚠️ <b>هیچ اکانتی ثبت نشده!</b>\n\n"
            "برای ریپورت گروهی، حداقل ۱ اکانت نیاز داری.\n"
            "اول روی <b>'➕ افزودن اکانت'</b> کلیک کن.",
            back_button()
        )
        bot.answer_callback_query(call.id)
        return
    
    if user_id in report_temp:
        del report_temp[user_id]
    report_temp[user_id] = {}
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        "🛡 <b>ریپورت گروهی/کانال</b>\n\n"
        "برای ریپورت یک گروه یا کانال، مراحل زیر رو طی کن:\n\n"
        "1️⃣ لینک گروه یا کانال رو بفرست\n"
        "2️⃣ لینک پست مورد نظر رو بفرست\n"
        "3️⃣ متن ریپورت رو وارد کن\n"
        "4️⃣ تعداد اکانت‌ها رو مشخص کن\n"
        "5️⃣ تعداد دفعات ریپورت رو تعیین کن\n\n"
        "📎 <b>لینک گروه</b> رو بفرست:\n"
        "مثال: <code>@username</code> یا <code>https://t.me/username</code>",
        back_to_main()
    )
    bot.answer_callback_query(call.id)
    bot.register_next_step_handler(call.message, process_group_link)

def process_group_link(message):
    user_id = message.from_user.id
    msg_id = user_message_ids.get(user_id)
    link = message.text.strip()
    
    username = link
    if 't.me/' in link:
        username = link.split('t.me/')[-1]
    if username.startswith('@'):
        username = username[1:]
    username = username.split('/')[0]
    
    if not username:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ لینک نامعتبر! لطفاً دوباره بفرست:\n"
            "مثال: <code>@username</code>",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_group_link)
        return
    
    report_temp[user_id]["group"] = username
    
    edit_message(
        message.chat.id,
        msg_id,
        f"✅ لینک گروه ثبت شد.\n\n"
        "📝 <b>لینک پست</b> رو بفرست:\n"
        "مثال: <code>https://t.me/username/123</code>",
        back_to_main()
    )
    bot.register_next_step_handler(message, process_post_link)

def process_post_link(message):
    user_id = message.from_user.id
    msg_id = user_message_ids.get(user_id)
    post_link = message.text.strip()
    
    if not re.match(r'https?://t\.me/[\w_]+/\d+', post_link):
        edit_message(
            message.chat.id,
            msg_id,
            "❌ لینک پست نامعتبر!\n"
            "لطفاً یک لینک معتبر بفرست:\n"
            "مثال: <code>https://t.me/username/123</code>",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_post_link)
        return
    
    report_temp[user_id]["post_link"] = post_link
    
    try:
        msg_id_post = int(post_link.split('/')[-1])
        report_temp[user_id]["msg_id"] = msg_id_post
    except:
        pass
    
    edit_message(
        message.chat.id,
        msg_id,
        f"✅ لینک پست ثبت شد.\n\n"
        "📄 <b>متن ریپورت</b> رو وارد کن:\n"
        "این متنی که برای گزارش ارسال میشه.\n"
        "مثال: <i>این گروه کلاهبرداری است</i>",
        back_to_main()
    )
    bot.register_next_step_handler(message, process_report_text)

def process_report_text(message):
    user_id = message.from_user.id
    msg_id = user_message_ids.get(user_id)
    report_text = message.text.strip()
    
    if len(report_text) < 10:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ متن خیلی کوتاه! حداقل ۱۰ کاراکتر وارد کن:",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_report_text)
        return
    
    report_temp[user_id]["text"] = report_text
    
    available = len(data["accounts"])
    
    edit_message(
        message.chat.id,
        msg_id,
        f"✅ متن ریپورت ثبت شد.\n\n"
        f"📊 <b>تعداد اکانت‌های موجود:</b> {available}\n\n"
        f"🔢 <b>تعداد اکانت‌ها</b> (حداکثر {available}):",
        back_to_main()
    )
    bot.register_next_step_handler(message, process_account_count)

def process_account_count(message):
    user_id = message.from_user.id
    msg_id = user_message_ids.get(user_id)
    try:
        count = int(message.text.strip())
        available = len(data["accounts"])
        
        if count < 1 or count > available:
            edit_message(
                message.chat.id,
                msg_id,
                f"❌ تعداد باید بین ۱ تا {available} باشه! دوباره وارد کن:",
                back_to_main()
            )
            bot.register_next_step_handler(message, process_account_count)
            return
        
        report_temp[user_id]["count"] = count
        
        edit_message(
            message.chat.id,
            msg_id,
            f"✅ تعداد اکانت‌ها: {count}\n\n"
            "🔄 <b>تعداد دفعات</b> (۱ تا ۵):\n"
            "هر اکانت چند بار ریپورت بزنه؟",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_repeat_count)
        
    except ValueError:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ لطفاً یک عدد معتبر وارد کن!",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_account_count)

def process_repeat_count(message):
    user_id = message.from_user.id
    msg_id = user_message_ids.get(user_id)
    try:
        repeat = int(message.text.strip())
        
        if repeat < 1 or repeat > 5:
            edit_message(
                message.chat.id,
                msg_id,
                "❌ تعداد دفعات باید بین ۱ تا ۵ باشه! دوباره وارد کن:",
                back_to_main()
            )
            bot.register_next_step_handler(message, process_repeat_count)
            return
        
        report_temp[user_id]["repeat"] = repeat
        
        show_summary(user_id, message)
        
    except ValueError:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ لطفاً یک عدد معتبر وارد کن!",
            back_to_main()
        )
        bot.register_next_step_handler(message, process_repeat_count)

def show_summary(user_id, message):
    msg_id = user_message_ids.get(user_id)
    temp = report_temp.get(user_id, {})
    
    summary = f"""
📋 <b>خلاصه ریپورت:</b>

🎯 <b>گروه:</b> {temp.get('group', 'نامشخص')}
📝 <b>لینک پست:</b> {temp.get('post_link', 'نامشخص')}
📄 <b>متن ریپورت:</b> {temp.get('text', 'نامشخص')}
🔢 <b>تعداد اکانت‌ها:</b> {temp.get('count', 0)}
🔄 <b>تعداد دفعات:</b> {temp.get('repeat', 0)}

⚠️ <b>آیا از انجام این ریپورت مطمئنی؟</b>
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ تایید و اجرا", callback_data=f"execute_report_{user_id}"),
        InlineKeyboardButton("❌ لغو", callback_data="cancel_report")
    )
    
    edit_message(
        message.chat.id,
        msg_id,
        summary,
        markup
    )

# ==================== اجرای ریپورت ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith("execute_report_"))
def execute_report(call):
    user_id = int(call.data.split("_")[2])
    user_message_ids[user_id] = call.message.message_id
    temp = report_temp.get(user_id, {})
    
    if not temp:
        bot.answer_callback_query(call.id, "❌ اطلاعات یافت نشد!")
        return
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        "⏳ <b>در حال اجرای ریپورت...</b>\n\n"
        "لطفاً صبر کن...",
        None
    )
    
    def run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(execute_report_async(user_id, call.message))
            loop.close()
        except Exception as e:
            logger.error(f"Error in report: {e}")
            edit_message(
                call.message.chat.id,
                call.message.message_id,
                f"❌ خطا در اجرا!\n\n{str(e)}",
                main_menu()
            )
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
    
    bot.answer_callback_query(call.id, "✅ در حال اجرا...")

async def execute_report_async(user_id, message):
    msg_id = user_message_ids.get(user_id)
    temp = report_temp.get(user_id, {})
    
    group = temp.get("group")
    post_link = temp.get("post_link")
    text = temp.get("text", "گزارش کلاهبرداری")
    count = temp.get("count", 1)
    repeat = temp.get("repeat", 1)
    msg_id_post = temp.get("msg_id")
    
    accounts = data["accounts"][:count]
    
    if len(accounts) < count:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ تعداد اکانت کافی نیست!",
            main_menu()
        )
        return
    
    success = 0
    fail = 0
    results = []
    
    for idx, account in enumerate(accounts):
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
            except:
                fail += 1
                results.append(f"❌ {account.get('phone')}: گروه یافت نشد")
                await client.disconnect()
                continue
            
            for i in range(repeat):
                try:
                    await client(functions.messages.ReportRequest(
                        peer=entity,
                        id=[msg_id_post],
                        reason=types.InputReportReasonSpam(),
                        message=text
                    ))
                    success += 1
                    results.append(f"✅ {account.get('phone')}: موفق {i+1}")
                    await asyncio.sleep(1.5)
                except:
                    fail += 1
                    results.append(f"❌ {account.get('phone')}: خطا {i+1}")
            
            await client.disconnect()
            
        except:
            fail += 1
            results.append(f"❌ {account.get('phone')}: خطا")
    
    report_data = {
        "group": group,
        "post": post_link,
        "text": text,
        "accounts": count,
        "repeat": repeat,
        "success": success,
        "fail": fail,
        "total": success + fail,
        "results": results,
        "date": datetime.now().isoformat()
    }
    
    data["reports"].append(report_data)
    save_data(data)
    
    result_text = f"""
📊 <b>نتیجه ریپورت:</b>

🎯 گروه: {group}
✅ موفق: {success}
❌ ناموفق: {fail}
📋 مجموع: {success + fail}

📋 <b>جزئیات:</b>
"""
    
    for r in results[:5]:
        result_text += f"\n{r}"
    
    if len(results) > 5:
        result_text += f"\n\n<i>... و {len(results)-5} نتیجه دیگر</i>"
    
    edit_message(
        message.chat.id,
        msg_id,
        result_text,
        main_menu()
    )
    
    if user_id in report_temp:
        del report_temp[user_id]

# ==================== بقیه بخش‌ها ====================

@bot.callback_query_handler(func=lambda call: call.data == "reports")
def show_reports(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    if not data["reports"]:
        edit_message(
            call.message.chat.id,
            call.message.message_id,
            "📭 <b>هیچ گزارشی ثبت نشده!</b>\n\n"
            "بعد از انجام ریپورت‌ها، گزارشات اینجا نمایش داده میشن.",
            back_button()
        )
        bot.answer_callback_query(call.id)
        return
    
    text = "📊 <b>تاریخچه ریپورت‌ها:</b>\n\n"
    for i, r in enumerate(reversed(data["reports"][-5:]), 1):
        text += f"{i}. 🎯 {r.get('group', 'نامشخص')}\n"
        text += f"   ✅ موفق: {r.get('success', 0)}\n"
        text += f"   ❌ ناموفق: {r.get('fail', 0)}\n"
        text += f"   📅 {r.get('date', '')[:10]}\n"
        text += "─" * 25 + "\n"
    
    if len(data["reports"]) > 5:
        text += f"\n<i>نمایش ۵ گزارش آخر از {len(data['reports'])} گزارش</i>"
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        text,
        back_button()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "manage_admins")
def manage_admins(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ افزودن ادمین", callback_data="add_admin"),
        InlineKeyboardButton("🗑 حذف ادمین", callback_data="remove_admin")
    )
    markup.add(InlineKeyboardButton("📋 لیست ادمین‌ها", callback_data="list_admins"))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu"))
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        "👥 <b>مدیریت ادمین‌ها</b>\n\n"
        "🔹 <b>افزودن ادمین:</b> کاربر جدید رو به لیست ادمین‌ها اضافه کن\n"
        "🔸 <b>حذف ادمین:</b> یک ادمین رو از لیست حذف کن\n"
        "📋 <b>لیست ادمین‌ها:</b> مشاهده لیست کامل ادمین‌ها",
        markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "add_admin")
def add_admin(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        "➕ <b>افزودن ادمین جدید</b>\n\n"
        "🆔 <b>آیدی عددی</b> کاربر مورد نظر رو وارد کن:\n\n"
        "⚠️ فقط کاربری که آیدی‌ش رو وارد کنی، به ربات دسترسی پیدا میکنه.",
        back_button()
    )
    bot.answer_callback_query(call.id)
    bot.register_next_step_handler(call.message, process_add_admin)

def process_add_admin(message):
    user_id = message.from_user.id
    msg_id = user_message_ids.get(user_id)
    
    try:
        admin_id = int(message.text.strip())
        
        if admin_id in data["admins"]:
            edit_message(
                message.chat.id,
                msg_id,
                "⚠️ این کاربر قبلاً ادمین هست!",
                main_menu()
            )
            return
        
        if admin_id in ALLOWED_USERS:
            edit_message(
                message.chat.id,
                msg_id,
                "⚠️ این کاربر در لیست اصلی هست!",
                main_menu()
            )
            return
        
        data["admins"].append(admin_id)
        save_data(data)
        
        edit_message(
            message.chat.id,
            msg_id,
            f"✅ ادمین <code>{admin_id}</code> با موفقیت اضافه شد!",
            main_menu()
        )
        
        try:
            bot.send_message(
                admin_id,
                "🎉 شما به عنوان ادمین به ربات اضافه شدید!\n"
                "حالا می‌تونی از تمام امکانات ربات استفاده کنی.",
                parse_mode='HTML'
            )
        except:
            pass
            
    except ValueError:
        edit_message(
            message.chat.id,
            msg_id,
            "❌ لطفاً یک آیدی عددی معتبر وارد کن!",
            main_menu()
        )

@bot.callback_query_handler(func=lambda call: call.data == "remove_admin")
def remove_admin(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    if not data["admins"]:
        edit_message(
            call.message.chat.id,
            call.message.message_id,
            "📭 هیچ ادمینی ثبت نشده!",
            back_button()
        )
        bot.answer_callback_query(call.id)
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for admin in data["admins"]:
        markup.add(InlineKeyboardButton(
            f"🗑 {admin}",
            callback_data=f"remove_adm_{admin}"
        ))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="manage_admins"))
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        "🗑 <b>انتخاب ادمین برای حذف:</b>\n\n"
        "روی ادمین مورد نظر کلیک کن:",
        markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_adm_"))
def remove_admin_confirm(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    admin_id = int(call.data.split("_")[2])
    
    if admin_id in data["admins"]:
        data["admins"].remove(admin_id)
        save_data(data)
        
        edit_message(
            call.message.chat.id,
            call.message.message_id,
            f"✅ ادمین <code>{admin_id}</code> حذف شد!",
            back_button()
        )
        bot.answer_callback_query(call.id, "✅ حذف شد")
    else:
        bot.answer_callback_query(call.id, "❌ یافت نشد!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "list_admins")
def list_admins(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    text = "👥 <b>لیست ادمین‌ها:</b>\n\n"
    text += "🔹 <b>ادمین‌های اصلی:</b>\n"
    for uid in ALLOWED_USERS:
        text += f"   • <code>{uid}</code> (دسترسی دائمی)\n"
    
    if data["admins"]:
        text += "\n🔸 <b>ادمین‌های اضافه شده:</b>\n"
        for admin in data["admins"]:
            text += f"   • <code>{admin}</code>\n"
    else:
        text += "\n📭 <i>هیچ ادمین اضافه‌ای ثبت نشده.</i>"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="manage_admins"))
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        text,
        markup
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def help_menu(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    help_text = """
❓ <b>راهنمای کامل ربات</b>

<b>🛡 ریپورت گروهی:</b>
برای گزارش گروه‌ها و کانال‌های متخلف
مراحل: لینک گروه → لینک پست → متن ریپورت → تعداد اکانت → تعداد دفعات

<b>➕ افزودن اکانت:</b>
اضافه کردن اکانت تلگرام با سشن
مراحل: شماره → API ID → API Hash → کد تایید

<b>📋 لیست اکانت‌ها:</b>
مشاهده همه اکانت‌های ثبت شده و حذف اکانت‌های اضافی

<b>📊 گزارشات:</b>
مشاهده تاریخچه ریپورت‌های انجام شده

<b>👤 مدیریت ادمین:</b>
افزودن یا حذف ادمین‌های جدید

⚠️ <b>نکات مهم:</b>
• برای ریپورت حداقل ۱ اکانت نیاز دارید
• API ID و Hash رو از my.telegram.org بگیر
• کد تایید رو به صورت ۱.۲.۳.۴.۵ وارد کن
"""
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        help_text,
        back_button()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        "🌟 <b>منوی اصلی</b>\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن:",
        main_menu()
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_report")
def cancel_report(call):
    user_id = call.from_user.id
    user_message_ids[user_id] = call.message.message_id
    
    if user_id in report_temp:
        del report_temp[user_id]
    
    edit_message(
        call.message.chat.id,
        call.message.message_id,
        "❌ عملیات ریپورت لغو شد!",
        main_menu()
    )
    bot.answer_callback_query(call.id)

# ==================== اجرا ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 ربات مدیریت تلگرام")
    print("=" * 50)
    print(f"📊 اکانت‌ها: {len(data['accounts'])}")
    print(f"👥 ادمین‌ها: {len(data['admins'])}")
    print(f"📋 گزارش‌ها: {len(data['reports'])}")
    print("=" * 50)
    print("🔄 در حال اجرا...")
    print("✅ تمام پیام‌ها ویرایشی هستند")
    
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"❌ خطا: {e}")
