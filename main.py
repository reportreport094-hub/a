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
user_msg_ids = {}  # برای ویرایش پیام‌ها

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

# ==================== بررسی دسترسی ====================

def is_allowed(user_id):
    return user_id in ALLOWED_USERS or user_id in data["admins"]

# ==================== شروع ====================

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    if not is_allowed(user_id):
        bot.send_message(message.chat.id, "🚫 دسترسی غیرمجاز!", parse_mode='HTML')
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
    
    msg = bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu(), parse_mode='HTML')
    user_msg_ids[user_id] = msg.message_id

# ==================== افزودن اکانت ====================

@bot.callback_query_handler(func=lambda call: call.data == "add_account")
def add_account_start(call):
    user_id = call.from_user.id
    
    if user_id in user_temp:
        del user_temp[user_id]
    user_temp[user_id] = {}
    
    user_msg_ids[user_id] = call.message.message_id
    
    # حذف دکمه‌ها و ویرایش پیام
    bot.edit_message_text(
        "➕ <b>افزودن اکانت جدید</b>\n\n"
        "📱 <b>شماره تلفن</b> رو با کد کشور وارد کن:\n"
        "مثال: <code>+989123456789</code>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    bot.register_next_step_handler(call.message, process_phone)
    bot.answer_callback_query(call.id)

def process_phone(message):
    user_id = message.from_user.id
    phone = message.text.strip()
    msg_id = user_msg_ids.get(user_id)
    
    # حذف پیام شماره کاربر
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        bot.edit_message_text(
            "❌ شماره نامعتبر! لطفاً با کد کشور وارد کن.\n"
            "مثال: <code>+989123456789</code>",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_phone)
        return
    
    user_temp[user_id]['phone'] = phone
    
    bot.edit_message_text(
        f"✅ شماره ثبت شد.\n\n"
        "🔑 <b>API ID</b> رو وارد کن:\n"
        "(از my.telegram.org)\n"
        "⚠️ عددی بین 1 تا 2147483647",
        chat_id=message.chat.id,
        message_id=msg_id,
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_api_id)

def process_api_id(message):
    user_id = message.from_user.id
    api_id = message.text.strip()
    msg_id = user_msg_ids.get(user_id)
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    try:
        api_id_int = int(api_id)
        if api_id_int > 2147483647:
            bot.edit_message_text(
                "❌ عدد خیلی بزرگه! API ID باید بین 1 تا 2147483647 باشه.",
                chat_id=message.chat.id,
                message_id=msg_id,
                parse_mode='HTML'
            )
            bot.register_next_step_handler(message, process_api_id)
            return
    except:
        bot.edit_message_text(
            "❌ API ID باید عدد باشه! لطفاً دوباره وارد کن.",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_api_id)
        return
    
    user_temp[user_id]['api_id'] = api_id
    
    bot.edit_message_text(
        f"✅ API ID ثبت شد.\n\n"
        "🔐 <b>API Hash</b> رو وارد کن:\n"
        "(از my.telegram.org)",
        chat_id=message.chat.id,
        message_id=msg_id,
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_api_hash)

def process_api_hash(message):
    user_id = message.from_user.id
    api_hash = message.text.strip()
    msg_id = user_msg_ids.get(user_id)
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    if len(api_hash) < 20:
        bot.edit_message_text(
            "❌ API Hash نامعتبر! لطفاً دوباره وارد کن.",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_api_hash)
        return
    
    user_temp[user_id]['api_hash'] = api_hash
    
    bot.edit_message_text(
        "⏳ در حال ارسال کد تایید...",
        chat_id=message.chat.id,
        message_id=msg_id,
        parse_mode='HTML'
    )
    
    start_connection(user_id, message, msg_id)

def start_connection(user_id, message, msg_id):
    temp = user_temp.get(user_id, {})
    phone = temp.get("phone")
    api_id = temp.get("api_id")
    api_hash = temp.get("api_hash")
    
    if not all([phone, api_id, api_hash]):
        bot.edit_message_text(
            "❌ اطلاعات کامل نیست! دوباره تلاش کن.",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        return
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(connect_to_telegram(user_id, message, msg_id))
            loop.close()
        except Exception as e:
            logger.error(f"Error: {e}")
            bot.edit_message_text(
                f"❌ خطا: {str(e)}",
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
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
            
            bot.edit_message_text(
                f"📨 <b>کد تایید ارسال شد!</b>\n\n"
                f"📱 شماره: <code>{phone}</code>\n\n"
                "🔑 کد ۵ رقمی رو وارد کن:\n"
                "مثال: <code>12345</code> یا <code>1.2.3.4.5</code>",
                chat_id=message.chat.id,
                message_id=msg_id,
                parse_mode='HTML'
            )
            
            bot.register_next_step_handler(message, verify_code, client, user_id)
        else:
            await get_account_info(message, client, user_id, msg_id)
            
    except PhoneNumberInvalidError:
        bot.edit_message_text(
            "❌ شماره وارد شده معتبر نیست!",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
    except FloodWaitError as e:
        bot.edit_message_text(
            f"⏳ لطفاً {e.seconds} ثانیه صبر کن.",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Error connecting: {e}")
        bot.edit_message_text(
            f"❌ خطا: {str(e)}",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

def verify_code(message, client, user_id):
    code_input = message.text.strip()
    code = code_input.replace('.', '').replace('،', '').replace(' ', '').strip()
    msg_id = user_msg_ids.get(user_id)
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    if not code.isdigit() or len(code) != 5:
        bot.edit_message_text(
            "❌ کد باید ۵ رقم باشه! مثال: <code>12345</code>",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, verify_code, client, user_id)
        return
    
    bot.edit_message_text(
        "⏳ در حال تایید کد...",
        chat_id=message.chat.id,
        message_id=msg_id,
        parse_mode='HTML'
    )
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(verify_code_async(message, client, user_id, code, msg_id))
            loop.close()
        except Exception as e:
            logger.error(f"Error: {e}")
            bot.edit_message_text(
                f"❌ خطا: {str(e)}",
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
    
    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

async def verify_code_async(message, client, user_id, code, msg_id):
    try:
        await client.sign_in(code=code)
        await get_account_info(message, client, user_id, msg_id)
        
    except SessionPasswordNeededError:
        bot.edit_message_text(
            "🔑 <b>این اکانت پسورد داره!</b>\n\n"
            "لطفاً پسورد رو وارد کن:",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_password, client, user_id)
        
    except PhoneCodeExpiredError:
        bot.edit_message_text(
            "❌ کد منقضی شد! در حال ارسال کد جدید...",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        try:
            phone = user_temp.get(user_id, {}).get("phone")
            await client.send_code_request(phone)
            bot.edit_message_text(
                "📨 کد جدید ارسال شد! لطفاً وارد کن:",
                chat_id=message.chat.id,
                message_id=msg_id,
                parse_mode='HTML'
            )
            bot.register_next_step_handler(message, verify_code, client, user_id)
        except Exception as e:
            bot.edit_message_text(
                f"❌ خطا: {str(e)}",
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
        
    except PhoneCodeInvalidError:
        bot.edit_message_text(
            "❌ کد اشتباه! لطفاً دوباره وارد کن:",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, verify_code, client, user_id)
        
    except Exception as e:
        logger.error(f"Error verifying: {e}")
        bot.edit_message_text(
            f"❌ خطا: {str(e)}",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

def process_password(message, client, user_id):
    password = message.text.strip()
    msg_id = user_msg_ids.get(user_id)
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    if len(password) < 4:
        bot.edit_message_text(
            "❌ پسورد حداقل ۴ کاراکتر! دوباره وارد کن:",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_password, client, user_id)
        return
    
    bot.edit_message_text(
        "⏳ در حال تایید پسورد...",
        chat_id=message.chat.id,
        message_id=msg_id,
        parse_mode='HTML'
    )
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(verify_password_async(message, client, user_id, password, msg_id))
            loop.close()
        except Exception as e:
            logger.error(f"Error: {e}")
            bot.edit_message_text(
                f"❌ خطا: {str(e)}",
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
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
        bot.edit_message_text(
            f"❌ پسورد اشتباه! {str(e)}",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
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
            bot.edit_message_text(
                "⚠️ این اکانت قبلاً ثبت شده!",
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            if user_id in user_temp:
                del user_temp[user_id]
            await client.disconnect()
            return
        
        data["accounts"].append(account)
        save_data(data)
        
        bot.edit_message_text(
            f"✅ <b>اکانت با موفقیت اضافه شد!</b>\n\n"
            f"📱 شماره: <code>{account['phone']}</code>\n"
            f"👤 نام: {account['first_name']}\n"
            f"🆔 آیدی: <code>{account['user_id']}</code>\n\n"
            "🎉 اکانت آماده استفاده است!",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        
        if user_id in user_temp:
            del user_temp[user_id]
        
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"Error getting account: {e}")
        bot.edit_message_text(
            f"❌ خطا: {str(e)}",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

# ==================== لیست اکانت‌ها ====================

@bot.callback_query_handler(func=lambda call: call.data == "list_accounts")
def list_accounts(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    if not data["accounts"]:
        bot.edit_message_text(
            "📭 هیچ اکانتی ثبت نشده!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        return
    
    text = "📋 <b>لیست اکانت‌ها:</b>\n\n"
    for i, acc in enumerate(data["accounts"], 1):
        text += f"{i}. 📱 <code>{acc.get('phone', 'نامشخص')}</code>\n"
        text += f"   👤 {acc.get('first_name', '')}\n"
        if acc.get('username'):
            text += f"   @{acc.get('username')}\n"
        text += "─" * 20 + "\n"
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🗑 حذف اکانت", callback_data="delete_account_menu"))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu"))
    
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "delete_account_menu")
def delete_account_menu(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    if not data["accounts"]:
        bot.edit_message_text(
            "📭 اکانتی برای حذف نیست!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
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
    
    bot.edit_message_text(
        "🗑 انتخاب کن:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_acc_"))
def delete_account(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
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
    
    bot.edit_message_text(
        f"✅ {phone} حذف شد!",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id, "✅ حذف شد")

# ==================== ریپورت گروهی ====================

@bot.callback_query_handler(func=lambda call: call.data == "report_group")
def report_group_start(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    if len(data["accounts"]) < 1:
        bot.edit_message_text(
            "⚠️ اول اکانت اضافه کن!",
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
        "🛡 <b>لینک گروه</b> رو بفرست:\nمثال: <code>@username</code>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)
    bot.register_next_step_handler(call.message, process_group_link)

def process_group_link(message):
    user_id = message.from_user.id
    msg_id = user_msg_ids.get(user_id)
    link = message.text.strip()
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    username = link
    if 't.me/' in link:
        username = link.split('t.me/')[-1]
    if username.startswith('@'):
        username = username[1:]
    username = username.split('/')[0]
    
    if not username:
        bot.edit_message_text(
            "❌ لینک نامعتبر! دوباره بفرست:",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_group_link)
        return
    
    report_temp[user_id]["group"] = username
    
    bot.edit_message_text(
        f"✅ لینک ثبت شد.\n\n"
        "📝 <b>لینک پست</b> رو بفرست:\n"
        "مثال: <code>https://t.me/username/123</code>",
        chat_id=message.chat.id,
        message_id=msg_id,
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_post_link)

def process_post_link(message):
    user_id = message.from_user.id
    msg_id = user_msg_ids.get(user_id)
    post_link = message.text.strip()
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    if not re.match(r'https?://t\.me/[\w_]+/\d+', post_link):
        bot.edit_message_text(
            "❌ لینک نامعتبر! دوباره بفرست:",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_post_link)
        return
    
    report_temp[user_id]["post_link"] = post_link
    
    try:
        msg_id_post = int(post_link.split('/')[-1])
        report_temp[user_id]["msg_id"] = msg_id_post
    except:
        pass
    
    bot.edit_message_text(
        f"✅ لینک پست ثبت شد.\n\n"
        "📄 <b>متن ریپورت</b> رو وارد کن:",
        chat_id=message.chat.id,
        message_id=msg_id,
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_report_text)

def process_report_text(message):
    user_id = message.from_user.id
    msg_id = user_msg_ids.get(user_id)
    report_text = message.text.strip()
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    if len(report_text) < 10:
        bot.edit_message_text(
            "❌ متن حداقل ۱۰ کاراکتر! دوباره بنویس:",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_report_text)
        return
    
    report_temp[user_id]["text"] = report_text
    available = len(data["accounts"])
    
    bot.edit_message_text(
        f"✅ متن ثبت شد.\n\n"
        f"📊 تعداد اکانت‌ها: {available}\n\n"
        f"🔢 <b>تعداد اکانت‌ها</b> (حداکثر {available}):",
        chat_id=message.chat.id,
        message_id=msg_id,
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_account_count)

def process_account_count(message):
    user_id = message.from_user.id
    msg_id = user_msg_ids.get(user_id)
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    try:
        count = int(message.text.strip())
        available = len(data["accounts"])
        
        if count < 1 or count > available:
            bot.edit_message_text(
                f"❌ بین ۱ تا {available} وارد کن!",
                chat_id=message.chat.id,
                message_id=msg_id,
                parse_mode='HTML'
            )
            bot.register_next_step_handler(message, process_account_count)
            return
        
        report_temp[user_id]["count"] = count
        
        bot.edit_message_text(
            f"✅ تعداد: {count}\n\n"
            "🔄 <b>تعداد دفعات</b> (۱ تا ۵):",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_repeat_count)
        
    except ValueError:
        bot.edit_message_text(
            "❌ عدد وارد کن!",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_account_count)

def process_repeat_count(message):
    user_id = message.from_user.id
    msg_id = user_msg_ids.get(user_id)
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    try:
        repeat = int(message.text.strip())
        
        if repeat < 1 or repeat > 5:
            bot.edit_message_text(
                "❌ بین ۱ تا ۵ وارد کن!",
                chat_id=message.chat.id,
                message_id=msg_id,
                parse_mode='HTML'
            )
            bot.register_next_step_handler(message, process_repeat_count)
            return
        
        report_temp[user_id]["repeat"] = repeat
        
        show_summary(user_id, message)
        
    except ValueError:
        bot.edit_message_text(
            "❌ عدد وارد کن!",
            chat_id=message.chat.id,
            message_id=msg_id,
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_repeat_count)

def show_summary(user_id, message):
    msg_id = user_msg_ids.get(user_id)
    temp = report_temp.get(user_id, {})
    
    summary = f"""
📋 <b>خلاصه ریپورت:</b>

🎯 گروه: {temp.get('group', 'نامشخص')}
📝 پست: {temp.get('post_link', 'نامشخص')}
📄 متن: {temp.get('text', 'نامشخص')}
🔢 تعداد اکانت‌ها: {temp.get('count', 0)}
🔄 تعداد دفعات: {temp.get('repeat', 0)}

⚠️ تایید میکنی؟
"""
    
    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ اجرا", callback_data=f"execute_report_{user_id}"),
        InlineKeyboardButton("❌ لغو", callback_data="cancel_report")
    )
    
    bot.edit_message_text(
        summary,
        chat_id=message.chat.id,
        message_id=msg_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

# ==================== اجرای ریپورت ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith("execute_report_"))
def execute_report(call):
    user_id = int(call.data.split("_")[2])
    user_msg_ids[user_id] = call.message.message_id
    temp = report_temp.get(user_id, {})
    
    if not temp:
        bot.answer_callback_query(call.id, "❌ یافت نشد!")
        return
    
    bot.edit_message_text(
        "⏳ در حال اجرا...",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    def run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(execute_report_async(user_id, call.message))
            loop.close()
        except Exception as e:
            logger.error(f"Error: {e}")
            bot.edit_message_text(
                f"❌ خطا: {str(e)}",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
    
    bot.answer_callback_query(call.id, "✅ در حال اجرا...")

async def execute_report_async(user_id, message):
    msg_id = user_msg_ids.get(user_id)
    temp = report_temp.get(user_id, {})
    
    group = temp.get("group")
    text = temp.get("text", "گزارش کلاهبرداری")
    count = temp.get("count", 1)
    repeat = temp.get("repeat", 1)
    msg_id_post = temp.get("msg_id")
    
    accounts = data["accounts"][:count]
    
    if len(accounts) < count:
        bot.edit_message_text(
            "❌ تعداد اکانت کافی نیست!",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        return
    
    success = 0
    fail = 0
    results = []
    
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
        "text": text,
        "accounts": count,
        "repeat": repeat,
        "success": success,
        "fail": fail,
        "results": results,
        "date": datetime.now().isoformat()
    }
    
    data["reports"].append(report_data)
    save_data(data)
    
    result_text = f"""
📊 <b>نتیجه:</b>

✅ موفق: {success}
❌ ناموفق: {fail}
"""
    
    for r in results[:5]:
        result_text += f"\n{r}"
    
    if len(results) > 5:
        result_text += f"\n... {len(results)-5} نتیجه دیگر"
    
    bot.edit_message_text(
        result_text,
        chat_id=message.chat.id,
        message_id=msg_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    
    if user_id in report_temp:
        del report_temp[user_id]

# ==================== بقیه بخش‌ها ====================

@bot.callback_query_handler(func=lambda call: call.data == "reports")
def show_reports(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    if not data["reports"]:
        bot.edit_message_text(
            "📭 گزارشی نیست!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        return
    
    text = "📊 <b>گزارشات:</b>\n\n"
    for i, r in enumerate(reversed(data["reports"][-5:]), 1):
        text += f"{i}. 🎯 {r.get('group', 'نامشخص')}\n"
        text += f"   ✅ {r.get('success', 0)} | ❌ {r.get('fail', 0)}\n"
        text += f"   📅 {r.get('date', '')[:10]}\n"
        text += "─" * 20 + "\n"
    
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "manage_admins")
def manage_admins(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ افزودن", callback_data="add_admin"),
        InlineKeyboardButton("🗑 حذف", callback_data="remove_admin")
    )
    markup.add(InlineKeyboardButton("📋 لیست", callback_data="list_admins"))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu"))
    
    bot.edit_message_text(
        "👥 مدیریت ادمین:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "add_admin")
def add_admin(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    bot.edit_message_text(
        "🆔 آیدی عددی رو وارد کن:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)
    bot.register_next_step_handler(call.message, process_add_admin)

def process_add_admin(message):
    user_id = message.from_user.id
    msg_id = user_msg_ids.get(user_id)
    
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass
    
    try:
        admin_id = int(message.text.strip())
        
        if admin_id in data["admins"]:
            bot.edit_message_text(
                "⚠️ قبلاً ادمین هست!",
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            return
        
        if admin_id in ALLOWED_USERS:
            bot.edit_message_text(
                "⚠️ در لیست اصلی هست!",
                chat_id=message.chat.id,
                message_id=msg_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            return
        
        data["admins"].append(admin_id)
        save_data(data)
        
        bot.edit_message_text(
            f"✅ ادمین {admin_id} اضافه شد!",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        
        try:
            bot.send_message(admin_id, "🎉 شما ادمین شدید!", parse_mode='HTML')
        except:
            pass
            
    except ValueError:
        bot.edit_message_text(
            "❌ عدد وارد کن!",
            chat_id=message.chat.id,
            message_id=msg_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

@bot.callback_query_handler(func=lambda call: call.data == "remove_admin")
def remove_admin(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    if not data["admins"]:
        bot.edit_message_text(
            "📭 ادمینی نیست!",
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
            f"🗑 {admin}",
            callback_data=f"remove_adm_{admin}"
        ))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="manage_admins"))
    
    bot.edit_message_text(
        "🗑 انتخاب کن:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_adm_"))
def remove_admin_confirm(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    admin_id = int(call.data.split("_")[2])
    
    if admin_id in data["admins"]:
        data["admins"].remove(admin_id)
        save_data(data)
        
        bot.edit_message_text(
            f"✅ ادمین {admin_id} حذف شد!",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id, "✅ حذف شد")
    else:
        bot.answer_callback_query(call.id, "❌ یافت نشد!", show_alert=True)

@bot.callback_query_handler(func=lambda call: call.data == "list_admins")
def list_admins(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    text = "👥 <b>ادمین‌ها:</b>\n\n"
    text += "🔹 اصلی:\n"
    for uid in ALLOWED_USERS:
        text += f"   • <code>{uid}</code>\n"
    
    if data["admins"]:
        text += "\n🔸 اضافه شده:\n"
        for admin in data["admins"]:
            text += f"   • <code>{admin}</code>\n"
    else:
        text += "\n📭 اضافه‌ای نیست."
    
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="manage_admins"))
    
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "help")
def help_menu(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    help_text = """
❓ <b>راهنما:</b>

<b>➕ افزودن اکانت:</b>
شماره → API ID → API Hash → کد تایید

<b>🛡 ریپورت:</b>
لینک گروه → لینک پست → متن → تعداد اکانت → تعداد دفعات

<b>📋 مدیریت:</b>
لیست اکانت‌ها، حذف، مدیریت ادمین
"""
    
    bot.edit_message_text(
        help_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    bot.edit_message_text(
        "🌟 <b>منوی اصلی</b>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "cancel_report")
def cancel_report(call):
    user_id = call.from_user.id
    user_msg_ids[user_id] = call.message.message_id
    
    if user_id in report_temp:
        del report_temp[user_id]
    
    bot.edit_message_text(
        "❌ لغو شد!",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
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
    
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Error: {e}")
        print(f"❌ خطا: {e}")
