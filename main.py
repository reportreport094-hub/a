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
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_menu()
    )

# ==================== افزودن اکانت ====================

@bot.callback_query_handler(func=lambda call: call.data == "add_account")
def add_account_start(call):
    user_id = call.from_user.id
    
    if user_id in user_temp:
        del user_temp[user_id]
    user_temp[user_id] = {}
    
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass
    
    msg = bot.send_message(
        call.message.chat.id,
        "➕ <b>افزودن اکانت جدید</b>\n\n"
        "برای اضافه کردن اکانت، اطلاعات زیر رو وارد کن:\n\n"
        "1️⃣ شماره تلفن (با کد کشور)\n"
        "   مثال: <code>+989123456789</code>\n\n"
        "2️⃣ API ID (از my.telegram.org)\n"
        "3️⃣ API Hash (از my.telegram.org)\n"
        "4️⃣ کد تایید (به تلگرامت ارسال میشه)\n\n"
        "📱 <b>شماره تلفن</b> رو وارد کن:",
        reply_markup=back_to_main(),
        parse_mode='HTML'
    )
    
    bot.register_next_step_handler(msg, process_phone)
    bot.answer_callback_query(call.id)

def process_phone(message):
    user_id = message.from_user.id
    phone = message.text.strip()
    
    if not re.match(r'^\+?[0-9]{10,15}$', phone):
        msg = bot.send_message(
            message.chat.id,
            "❌ شماره نامعتبر! لطفاً با کد کشور وارد کن.\n"
            "مثال: <code>+989123456789</code>",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_phone)
        return
    
    user_temp[user_id]['phone'] = phone
    
    msg = bot.send_message(
        message.chat.id,
        f"✅ شماره <code>{phone}</code> ثبت شد.\n\n"
        "🔑 <b>API ID</b> رو وارد کن:\n"
        "(از سایت my.telegram.org دریافت کن)\n"
        "⚠️ API ID باید عددی بین 1 تا 2147483647 باشه.",
        reply_markup=back_to_main(),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_api_id)

def process_api_id(message):
    user_id = message.from_user.id
    api_id = message.text.strip()
    
    try:
        api_id_int = int(api_id)
        if api_id_int > 2147483647:
            msg = bot.send_message(
                message.chat.id,
                "❌ عدد خیلی بزرگه! API ID باید بین 1 تا 2147483647 باشه.",
                reply_markup=back_to_main(),
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, process_api_id)
            return
    except:
        msg = bot.send_message(
            message.chat.id,
            "❌ API ID باید عدد باشه! لطفاً دوباره وارد کن.",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_api_id)
        return
    
    user_temp[user_id]['api_id'] = api_id
    
    msg = bot.send_message(
        message.chat.id,
        f"✅ API ID ثبت شد.\n\n"
        "🔐 <b>API Hash</b> رو وارد کن:\n"
        "(از my.telegram.org دریافت کن)",
        reply_markup=back_to_main(),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_api_hash)

def process_api_hash(message):
    user_id = message.from_user.id
    api_hash = message.text.strip()
    
    if len(api_hash) < 20:
        msg = bot.send_message(
            message.chat.id,
            "❌ API Hash نامعتبر! لطفاً دوباره وارد کن.",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_api_hash)
        return
    
    user_temp[user_id]['api_hash'] = api_hash
    
    status_msg = bot.send_message(
        message.chat.id,
        "⏳ در حال ارسال کد تایید به تلگرام...\n"
        "لطفاً صبر کن...",
        parse_mode='HTML'
    )
    
    start_connection(user_id, message, status_msg)

def start_connection(user_id, message, status_msg):
    temp = user_temp.get(user_id, {})
    phone = temp.get("phone")
    api_id = temp.get("api_id")
    api_hash = temp.get("api_hash")
    
    if not all([phone, api_id, api_hash]):
        bot.edit_message_text(
            "❌ اطلاعات کامل نیست! دوباره تلاش کن.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        return
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(connect_to_telegram(user_id, message, status_msg))
            loop.close()
        except Exception as e:
            logger.error(f"Error in async thread: {e}")
            try:
                bot.edit_message_text(
                    f"❌ خطا در اتصال!\n\n{str(e)}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    reply_markup=main_menu(),
                    parse_mode='HTML'
                )
            except:
                pass
    
    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

async def connect_to_telegram(user_id, message, status_msg):
    temp = user_temp.get(user_id, {})
    phone = temp.get("phone")
    api_id = temp.get("api_id")
    api_hash = temp.get("api_hash")
    
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{phone}.session")
        client = TelegramClient(session_file, int(api_id), api_hash, loop=asyncio.get_running_loop())
        
        await client.connect()
        
        if not await client.is_user_authorized():
            await client.send_code_request(phone)
            
            user_temp[user_id]['client'] = client
            
            # استفاده از bot.edit_message_text در async با asyncio
            def edit_message():
                try:
                    bot.edit_message_text(
                        f"📨 <b>کد تایید ارسال شد!</b>\n\n"
                        f"📱 شماره: <code>{phone}</code>\n\n"
                        "🔑 کد تایید رو به صورت <b>۱.۲.۳.۴.۵</b> وارد کن:\n"
                        "(مثلاً اگر کد ۱۲۳۴۵ است، عدد ۱۲۳۴۵ رو وارد کن)\n\n"
                        "⚠️ توجه: کد باید ۵ رقم باشه",
                        chat_id=message.chat.id,
                        message_id=status_msg.message_id,
                        reply_markup=back_to_main(),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error editing message: {e}")
            
            await asyncio.get_event_loop().run_in_executor(None, edit_message)
            
            bot.register_next_step_handler(message, verify_code, client, user_id)
        else:
            await get_account_info(message, client, user_id, status_msg)
            
    except PhoneNumberInvalidError:
        def edit_message():
            bot.edit_message_text(
                "❌ شماره وارد شده معتبر نیست!",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)
        
    except FloodWaitError as e:
        def edit_message():
            bot.edit_message_text(
                f"⏳ لطفاً {e.seconds} ثانیه صبر کن و دوباره تلاش کن.",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)
        
    except Exception as e:
        logger.error(f"Error connecting: {e}")
        def edit_message():
            bot.edit_message_text(
                f"❌ خطا در اتصال!\n\n{str(e)}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)

def verify_code(message, client, user_id):
    code_input = message.text.strip()
    code = code_input.replace('.', '').replace('،', '').replace(' ', '').strip()
    
    if not code.isdigit() or len(code) != 5:
        msg = bot.send_message(
            message.chat.id,
            "❌ کد باید ۵ رقم باشه! لطفاً کد رو به صورت ۱.۲.۳.۴.۵ وارد کن:\n"
            "مثال: <code>12345</code> یا <code>1.2.3.4.5</code>",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, verify_code, client, user_id)
        return
    
    status_msg = bot.send_message(
        message.chat.id,
        "⏳ در حال تایید کد...",
        parse_mode='HTML'
    )
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(verify_code_async(message, client, user_id, code, status_msg))
            loop.close()
        except Exception as e:
            logger.error(f"Error in verify async: {e}")
            try:
                bot.edit_message_text(
                    f"❌ خطا!\n\n{str(e)}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    reply_markup=main_menu(),
                    parse_mode='HTML'
                )
            except:
                pass
    
    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

async def verify_code_async(message, client, user_id, code, status_msg):
    try:
        await client.sign_in(code=code)
        await get_account_info(message, client, user_id, status_msg)
        
    except SessionPasswordNeededError:
        def edit_message():
            bot.edit_message_text(
                "🔑 <b>این اکانت پسورد (Two-Factor) داره!</b>\n\n"
                "لطفاً پسورد اکانت رو وارد کن:",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=back_to_main(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)
        bot.register_next_step_handler(message, process_password, client, user_id)
        
    except PhoneCodeExpiredError:
        def edit_message():
            bot.edit_message_text(
                "❌ کد تایید منقضی شده!\n\n"
                "در حال ارسال کد جدید...",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=back_to_main(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)
        
        try:
            phone = user_temp.get(user_id, {}).get("phone")
            await client.send_code_request(phone)
            
            def send_message():
                bot.send_message(
                    message.chat.id,
                    "📨 کد جدید ارسال شد! لطفاً وارد کن:",
                    reply_markup=back_to_main(),
                    parse_mode='HTML'
                )
            await asyncio.get_event_loop().run_in_executor(None, send_message)
            bot.register_next_step_handler(message, verify_code, client, user_id)
            
        except Exception as e:
            def edit_error():
                bot.edit_message_text(
                    f"❌ خطا در ارسال کد جدید: {str(e)}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    reply_markup=main_menu(),
                    parse_mode='HTML'
                )
            await asyncio.get_event_loop().run_in_executor(None, edit_error)
        
    except PhoneCodeInvalidError:
        def edit_message():
            bot.edit_message_text(
                "❌ کد اشتباه!\n\n"
                "لطفاً کد رو دقیق وارد کن.\n"
                "کد رو به صورت <b>۱.۲.۳.۴.۵</b> وارد کن.",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=back_to_main(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)
        bot.register_next_step_handler(message, verify_code, client, user_id)
        
    except Exception as e:
        logger.error(f"Error verifying: {e}")
        def edit_message():
            bot.edit_message_text(
                f"❌ خطا در تایید کد!\n\n{str(e)}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)

def process_password(message, client, user_id):
    password = message.text.strip()
    
    if len(password) < 4:
        msg = bot.send_message(
            message.chat.id,
            "❌ پسورد حداقل ۴ کاراکتر! دوباره وارد کن:",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_password, client, user_id)
        return
    
    status_msg = bot.send_message(
        message.chat.id,
        "⏳ در حال تایید پسورد...",
        parse_mode='HTML'
    )
    
    def run_async():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(verify_password_async(message, client, user_id, password, status_msg))
            loop.close()
        except Exception as e:
            logger.error(f"Error in password async: {e}")
            try:
                bot.edit_message_text(
                    f"❌ خطا!\n\n{str(e)}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    reply_markup=main_menu(),
                    parse_mode='HTML'
                )
            except:
                pass
    
    thread = threading.Thread(target=run_async)
    thread.daemon = True
    thread.start()

async def verify_password_async(message, client, user_id, password, status_msg):
    try:
        await client.sign_in(password=password)
        await get_account_info(message, client, user_id, status_msg)
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        def edit_message():
            bot.edit_message_text(
                f"❌ پسورد اشتباه!\n\n{str(e)}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=back_to_main(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)

async def get_account_info(message, client, user_id, status_msg):
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
            def edit_message():
                bot.edit_message_text(
                    "⚠️ این اکانت قبلاً ثبت شده!",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    reply_markup=main_menu(),
                    parse_mode='HTML'
                )
            await asyncio.get_event_loop().run_in_executor(None, edit_message)
            
            if user_id in user_temp:
                del user_temp[user_id]
            await client.disconnect()
            return
        
        data["accounts"].append(account)
        save_data(data)
        
        def edit_message():
            bot.edit_message_text(
                f"✅ <b>اکانت با موفقیت اضافه شد!</b>\n\n"
                f"📱 شماره: <code>{account['phone']}</code>\n"
                f"👤 نام: {account['first_name']} {account.get('last_name', '')}\n"
                f"🆔 آیدی: <code>{account['user_id']}</code>\n\n"
                "🎉 اکانت آماده استفاده است!",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)
        
        if user_id in user_temp:
            del user_temp[user_id]
        
        await client.disconnect()
        
    except Exception as e:
        logger.error(f"Error getting account: {e}")
        def edit_message():
            bot.edit_message_text(
                f"❌ خطا: {str(e)}",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
        await asyncio.get_event_loop().run_in_executor(None, edit_message)

# ==================== ادامه کد (لیست اکانت‌ها، ریپورت، مدیریت ادمین و ...) ====================

@bot.callback_query_handler(func=lambda call: call.data == "list_accounts")
def list_accounts(call):
    if not data["accounts"]:
        bot.edit_message_text(
            "📭 <b>هیچ اکانتی ثبت نشده!</b>\n\n"
            "برای افزودن اکانت، روی دکمه <b>'➕ افزودن اکانت'</b> کلیک کن.",
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
            text += f"   🆔 @{acc.get('username')}\n"
        text += f"   📅 {acc.get('created_at', 'نامشخص')[:10]}\n"
        text += "─" * 25 + "\n"
    
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
        "🗑 <b>انتخاب اکانت برای حذف:</b>\n\n"
        "روی اکانت مورد نظر کلیک کن:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_acc_"))
def delete_account(call):
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
        f"✅ اکانت {phone} با موفقیت حذف شد!",
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
    
    if len(data["accounts"]) < 1:
        bot.edit_message_text(
            "⚠️ <b>هیچ اکانتی ثبت نشده!</b>\n\n"
            "برای ریپورت گروهی، حداقل ۱ اکانت نیاز داری.\n"
            "اول روی <b>'➕ افزودن اکانت'</b> کلیک کن.",
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
        "برای ریپورت یک گروه یا کانال، مراحل زیر رو طی کن:\n\n"
        "1️⃣ لینک گروه یا کانال رو بفرست\n"
        "2️⃣ لینک پست مورد نظر رو بفرست\n"
        "3️⃣ متن ریپورت رو وارد کن\n"
        "4️⃣ تعداد اکانت‌ها رو مشخص کن\n"
        "5️⃣ تعداد دفعات ریپورت رو تعیین کن\n\n"
        "📎 <b>لینک گروه</b> رو بفرست:\n"
        "مثال: <code>@username</code> یا <code>https://t.me/username</code>",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_to_main(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)
    bot.register_next_step_handler(call.message, process_group_link)

def process_group_link(message):
    user_id = message.from_user.id
    link = message.text.strip()
    
    username = link
    if 't.me/' in link:
        username = link.split('t.me/')[-1]
    if username.startswith('@'):
        username = username[1:]
    username = username.split('/')[0]
    
    if not username:
        msg = bot.send_message(
            message.chat.id,
            "❌ لینک نامعتبر! لطفاً دوباره بفرست:\n"
            "مثال: <code>@username</code>",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_group_link)
        return
    
    report_temp[user_id]["group"] = username
    
    msg = bot.send_message(
        message.chat.id,
        f"✅ لینک گروه ثبت شد.\n\n"
        "📝 <b>لینک پست</b> رو بفرست:\n"
        "مثال: <code>https://t.me/username/123</code>",
        reply_markup=back_to_main(),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_post_link)

def process_post_link(message):
    user_id = message.from_user.id
    post_link = message.text.strip()
    
    if not re.match(r'https?://t\.me/[\w_]+/\d+', post_link):
        msg = bot.send_message(
            message.chat.id,
            "❌ لینک پست نامعتبر!\n"
            "لطفاً یک لینک معتبر بفرست:\n"
            "مثال: <code>https://t.me/username/123</code>",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_post_link)
        return
    
    report_temp[user_id]["post_link"] = post_link
    
    try:
        msg_id = int(post_link.split('/')[-1])
        report_temp[user_id]["msg_id"] = msg_id
    except:
        pass
    
    msg = bot.send_message(
        message.chat.id,
        f"✅ لینک پست ثبت شد.\n\n"
        "📄 <b>متن ریپورت</b> رو وارد کن:\n"
        "این متنی که برای گزارش ارسال میشه.\n"
        "مثال: <i>این گروه کلاهبرداری است</i>",
        reply_markup=back_to_main(),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_report_text)

def process_report_text(message):
    user_id = message.from_user.id
    report_text = message.text.strip()
    
    if len(report_text) < 10:
        msg = bot.send_message(
            message.chat.id,
            "❌ متن خیلی کوتاه! حداقل ۱۰ کاراکتر وارد کن:",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_report_text)
        return
    
    report_temp[user_id]["text"] = report_text
    
    available = len(data["accounts"])
    
    msg = bot.send_message(
        message.chat.id,
        f"✅ متن ریپورت ثبت شد.\n\n"
        f"📊 <b>تعداد اکانت‌های موجود:</b> {available}\n\n"
        f"🔢 <b>تعداد اکانت‌ها</b> (حداکثر {available}):",
        reply_markup=back_to_main(),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(msg, process_account_count)

def process_account_count(message):
    user_id = message.from_user.id
    try:
        count = int(message.text.strip())
        available = len(data["accounts"])
        
        if count < 1 or count > available:
            msg = bot.send_message(
                message.chat.id,
                f"❌ تعداد باید بین ۱ تا {available} باشه! دوباره وارد کن:",
                reply_markup=back_to_main(),
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, process_account_count)
            return
        
        report_temp[user_id]["count"] = count
        
        msg = bot.send_message(
            message.chat.id,
            f"✅ تعداد اکانت‌ها: {count}\n\n"
            "🔄 <b>تعداد دفعات</b> (۱ تا ۵):\n"
            "هر اکانت چند بار ریپورت بزنه؟",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_repeat_count)
        
    except ValueError:
        msg = bot.send_message(
            message.chat.id,
            "❌ لطفاً یک عدد معتبر وارد کن!",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_account_count)

def process_repeat_count(message):
    user_id = message.from_user.id
    try:
        repeat = int(message.text.strip())
        
        if repeat < 1 or repeat > 5:
            msg = bot.send_message(
                message.chat.id,
                "❌ تعداد دفعات باید بین ۱ تا ۵ باشه! دوباره وارد کن:",
                reply_markup=back_to_main(),
                parse_mode='HTML'
            )
            bot.register_next_step_handler(msg, process_repeat_count)
            return
        
        report_temp[user_id]["repeat"] = repeat
        
        show_summary(user_id, message)
        
    except ValueError:
        msg = bot.send_message(
            message.chat.id,
            "❌ لطفاً یک عدد معتبر وارد کن!",
            reply_markup=back_to_main(),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(msg, process_repeat_count)

def show_summary(user_id, message):
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
        bot.answer_callback_query(call.id, "❌ اطلاعات یافت نشد!")
        return
    
    status_msg = bot.edit_message_text(
        "⏳ <b>در حال اجرای ریپورت...</b>\n\n"
        "لطفاً صبر کن...",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    def run():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(execute_report_async(user_id, call.message, status_msg))
            loop.close()
        except Exception as e:
            logger.error(f"Error in report: {e}")
            try:
                bot.edit_message_text(
                    f"❌ خطا در اجرا!\n\n{str(e)}",
                    chat_id=call.message.chat.id,
                    message_id=status_msg.message_id,
                    reply_markup=main_menu(),
                    parse_mode='HTML'
                )
            except:
                pass
    
    thread = threading.Thread(target=run)
    thread.daemon = True
    thread.start()
    
    bot.answer_callback_query(call.id, "✅ در حال اجرا...")

async def execute_report_async(user_id, message, status_msg):
    temp = report_temp.get(user_id, {})
    
    group = temp.get("group")
    post_link = temp.get("post_link")
    text = temp.get("text", "گزارش کلاهبرداری")
    count = temp.get("count", 1)
    repeat = temp.get("repeat", 1)
    msg_id = temp.get("msg_id")
    
    accounts = data["accounts"][:count]
    
    if len(accounts) < count:
        bot.edit_message_text(
            "❌ تعداد اکانت کافی نیست!",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        return
    
    success = 0
    fail = 0
    results = []
    
    bot.edit_message_text(
        f"⏳ در حال ریپورت...\n\n"
        f"📊 اکانت‌ها: {len(accounts)}\n"
        f"🔄 دفعات: {repeat}\n"
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
                fail += 1
                results.append(f"❌ {account.get('phone')}: سشن یافت نشد")
                continue
            
            client = TelegramClient(session_file, 0, 0, loop=asyncio.get_running_loop())
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
                    results.append(f"✅ {account.get('phone')}: موفق {i+1}")
                    await asyncio.sleep(1.5)
                except Exception as e:
                    fail += 1
                    results.append(f"❌ {account.get('phone')}: خطا {i+1}")
            
            await client.disconnect()
            
        except Exception as e:
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
    
    bot.edit_message_text(
        result_text,
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        reply_markup=main_menu(),
        parse_mode='HTML'
    )
    
    if user_id in report_temp:
        del report_temp[user_id]

# ==================== گزارشات ====================

@bot.callback_query_handler(func=lambda call: call.data == "reports")
def show_reports(call):
    if not data["reports"]:
        bot.edit_message_text(
            "📭 <b>هیچ گزارشی ثبت نشده!</b>\n\n"
            "بعد از انجام ریپورت‌ها، گزارشات اینجا نمایش داده میشن.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
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
    markup.add(
        InlineKeyboardButton("➕ افزودن ادمین", callback_data="add_admin"),
        InlineKeyboardButton("🗑 حذف ادمین", callback_data="remove_admin")
    )
    markup.add(InlineKeyboardButton("📋 لیست ادمین‌ها", callback_data="list_admins"))
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu"))
    
    bot.edit_message_text(
        "👥 <b>مدیریت ادمین‌ها</b>\n\n"
        "🔹 <b>افزودن ادمین:</b> کاربر جدید رو به لیست ادمین‌ها اضافه کن\n"
        "🔸 <b>حذف ادمین:</b> یک ادمین رو از لیست حذف کن\n"
        "📋 <b>لیست ادمین‌ها:</b> مشاهده لیست کامل ادمین‌ها",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "add_admin")
def add_admin(call):
    bot.edit_message_text(
        "➕ <b>افزودن ادمین جدید</b>\n\n"
        "🆔 <b>آیدی عددی</b> کاربر مورد نظر رو وارد کن:\n\n"
        "⚠️ فقط کاربری که آیدی‌ش رو وارد کنی، به ربات دسترسی پیدا میکنه.",
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
                "⚠️ این کاربر قبلاً ادمین هست!",
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            return
        
        if admin_id in ALLOWED_USERS:
            bot.send_message(
                message.chat.id,
                "⚠️ این کاربر در لیست اصلی هست!",
                reply_markup=main_menu(),
                parse_mode='HTML'
            )
            return
        
        data["admins"].append(admin_id)
        save_data(data)
        
        bot.send_message(
            message.chat.id,
            f"✅ ادمین <code>{admin_id}</code> با موفقیت اضافه شد!",
            reply_markup=main_menu(),
            parse_mode='HTML'
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
        bot.send_message(
            message.chat.id,
            "❌ لطفاً یک آیدی عددی معتبر وارد کن!",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )

@bot.callback_query_handler(func=lambda call: call.data == "remove_admin")
def remove_admin(call):
    if not data["admins"]:
        bot.edit_message_text(
            "📭 هیچ ادمینی ثبت نشده!",
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
        "🗑 <b>انتخاب ادمین برای حذف:</b>\n\n"
        "روی ادمین مورد نظر کلیک کن:",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("remove_adm_"))
def remove_admin_confirm(call):
    admin_id = int(call.data.split("_")[2])
    
    if admin_id in data["admins"]:
        data["admins"].remove(admin_id)
        save_data(data)
        
        bot.edit_message_text(
            f"✅ ادمین <code>{admin_id}</code> حذف شد!",
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
    
    bot.edit_message_text(
        text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button_with_callback("manage_admins"),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

# ==================== راهنما ====================

@bot.callback_query_handler(func=lambda call: call.data == "help")
def help_menu(call):
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
    
    bot.edit_message_text(
        help_text,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=back_button(),
        parse_mode='HTML'
    )
    bot.answer_callback_query(call.id)

# ==================== دکمه‌های عمومی ====================

def back_button_with_callback(callback):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data=callback))
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    bot.edit_message_text(
        "🌟 <b>منوی اصلی</b>\n\n"
        "یکی از گزینه‌های زیر رو انتخاب کن:",
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
        "❌ عملیات ریپورت لغو شد!",
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
