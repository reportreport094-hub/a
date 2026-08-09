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
from telethon.tl.types import MessageEntityTextUrl

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# توکن ربات
TOKEN = "8986723154:AAH1qTObY9bo0A-csQFnSDYVcRhYr_DtsJ0"

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

# کلاس مدیریت سشن
class SessionManager:
    def __init__(self):
        self.active_sessions = {}
    
    async def create_session(self, phone, api_id, api_hash, password=None):
        try:
            session_file = os.path.join(SESSIONS_DIR, f"{phone}.session")
            client = TelegramClient(session_file, int(api_id), api_hash)
            
            await client.connect()
            
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
                    "phone": phone,
                    "client": client
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
            
            data["accounts"].append(account_info)
            save_data(data)
            
            return {
                "status": "success",
                "account": account_info,
                "client": client
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

# ==================== منوهای اصلی ====================

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
🌟 <b>به ربات حرفه‌ای ریپورت گروهی خوش آمدید!</b> 🌟

<b>🤖 رباتی قدرتمند برای مدیریت و ریپورت گروه‌های تلگرام</b>

✨ <b>قابلیت‌های ویژه:</b>
• 🛡 ریپورت گروهی با چندین اکانت
• ➕ افزودن اکانت‌های تلگرام با سشن
• 📊 مدیریت و گزارش‌گیری
• 👥 مدیریت ادمین‌ها
• 📋 لیست کامل اکانت‌ها

<b>📌 راهنمای سریع:</b>
برای ریپورت یک گروه یا کانال:
1️⃣ روی دکمه <b>"🛡 ریپورت گروهی"</b> کلیک کنید
2️⃣ لینک گروه یا کانال را بفرستید
3️⃣ پست مورد نظر برای ریپورت را بفرستید
4️⃣ متن ریپورت را وارد کنید
5️⃣ تعداد اکانت‌های مورد نیاز را مشخص کنید
6️⃣ تعداد دفعات ریپورت را تعیین کنید

⚠️ <b>نکات مهم:</b>
• حتماً ابتدا اکانت‌های خود را اضافه کنید
• برای ریپورت حداقل به ۳ اکانت نیاز دارید
• ریپورت‌ها به صورت خودکار انجام می‌شوند
"""
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=main_menu()
    )

# ==================== دکمه ریپورت گروهی ====================

# متغیرهای موقت برای ریپورت
report_temp = {}

@bot.callback_query_handler(func=lambda call: call.data == "report_group")
def report_group_start(call):
    user_id = call.from_user.id
    
    # بررسی تعداد اکانت‌ها
    if len(data["accounts"]) < 3:
        bot.edit_message_text(
            "⚠️ <b>تعداد اکانت‌ها کافی نیست!</b>\n\n"
            f"شما {len(data['accounts'])} اکانت دارید.\n"
            "برای ریپورت گروهی حداقل به <b>۳ اکانت</b> نیاز دارید.\n\n"
            "لطفاً ابتدا اکانت‌های خود را اضافه کنید.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)
        return
    
    report_temp[user_id] = {}
    
    bot.edit_message_text(
        "🛡 <b>ریپورت گروهی/کانال</b>\n\n"
        "لطفاً <b>لینک گروه یا کانال</b> مورد نظر را ارسال کنید:\n\n"
        "مثال:\n"
        "<code>https://t.me/username</code>\n"
        "یا\n"
        "<code>@username</code>\n\n"
        "⚠️ <i>گروه یا کانال می‌تواند عمومی یا خصوصی باشد.</i>",
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
    username = username.split('/')[0]  # حذف بخش‌های اضافی
    
    if not username:
        bot.send_message(
            message.chat.id,
            "❌ <b>لینک نامعتبر!</b>\n\n"
            "لطفاً یک لینک معتبر ارسال کنید:\n"
            "مثال: <code>https://t.me/username</code>",
            reply_markup=back_button_with_text("cancel_report"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_report_group_link)
        return
    
    report_temp[user_id]["group_username"] = username
    report_temp[user_id]["group_link"] = link
    
    bot.send_message(
        message.chat.id,
        f"✅ لینک گروه ثبت شد: <code>{link}</code>\n\n"
        "📝 حالا <b>لینک پست</b> مورد نظر برای ریپورت را ارسال کنید:\n\n"
        "مثال: <code>https://t.me/username/123</code>\n"
        "⚠️ <i>این لینک باید به یک پست خاص در گروه یا کانال اشاره کند.</i>",
        reply_markup=back_button_with_text("cancel_report"),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_report_post_link)

def process_report_post_link(message):
    user_id = message.from_user.id
    post_link = message.text.strip()
    
    # بررسی لینک پست
    if not re.match(r'https?://t\.me/[\w_]+/\d+', post_link):
        bot.send_message(
            message.chat.id,
            "❌ <b>لینک پست نامعتبر!</b>\n\n"
            "لطفاً یک لینک معتبر ارسال کنید:\n"
            "مثال: <code>https://t.me/username/123</code>",
            reply_markup=back_button_with_text("cancel_report"),
            parse_mode='HTML'
        )
        bot.register_next_step_handler(message, process_report_post_link)
        return
    
    report_temp[user_id]["post_link"] = post_link
    
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
    
    # نمایش تعداد اکانت‌های موجود
    available_accounts = len(data["accounts"])
    
    bot.send_message(
        message.chat.id,
        f"✅ متن ریپورت ثبت شد.\n\n"
        f"📊 <b>تعداد اکانت‌های موجود:</b> {available_accounts}\n\n"
        "🔢 <b>تعداد اکانت‌هایی که می‌خواهید ریپورت بزنند را وارد کنید:</b>\n"
        f"(حداکثر: {available_accounts})",
        reply_markup=back_button_with_text("cancel_report"),
        parse_mode='HTML'
    )
    bot.register_next_step_handler(message, process_report_account_count)

def process_report_account_count(message):
    user_id = message.from_user.id
    try:
        count = int(message.text.strip())
        available = len(data["accounts"])
        
        if count < 1:
            bot.send_message(
                message.chat.id,
                "❌ <b>تعداد نامعتبر!</b>\n\n"
                "حداقل ۱ اکانت برای ریپورت نیاز است.",
                reply_markup=back_button_with_text("cancel_report"),
                parse_mode='HTML'
            )
            bot.register_next_step_handler(message, process_report_account_count)
            return
        
        if count > available:
            bot.send_message(
                message.chat.id,
                f"❌ <b>تعداد بیشتر از اکانت‌های موجود است!</b>\n\n"
                f"شما {available} اکانت دارید.\n"
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
            "(تعداد دفعات ارسال ریپورت)\n"
            "پیشنهاد: ۱ تا ۳ بار",
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
        
        # نمایش خلاصه و تایید نهایی
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
    
    # ارسال پیام در حال اجرا
    status_msg = bot.edit_message_text(
        "⏳ <b>در حال اجرای ریپورت...</b>\n\n"
        "لطفاً صبر کنید...",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        parse_mode='HTML'
    )
    
    # اجرا در ترد جداگانه
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
    report_text = temp.get("report_text")
    account_count = temp.get("account_count", 0)
    repeat_count = temp.get("repeat_count", 1)
    
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
    
    # گزارش نتایج
    results = []
    success_count = 0
    fail_count = 0
    
    # بروزرسانی وضعیت
    bot.edit_message_text(
        f"⏳ <b>در حال ریپورت...</b>\n\n"
        f"📊 تعداد اکانت‌ها: {len(accounts)}\n"
        f"🔄 تعداد دفعات: {repeat_count}\n"
        f"✅ موفق: 0\n"
        f"❌ ناموفق: 0",
        chat_id=message.chat.id,
        message_id=status_msg.message_id,
        parse_mode='HTML'
    )
    
    # ریپورت با هر اکانت
    for idx, account in enumerate(accounts):
        try:
            # اتصال با اکانت
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
            
            # دریافت گروه
            try:
                entity = await client.get_entity(f"@{group_username}")
            except Exception as e:
                results.append(f"❌ اکانت {account.get('phone')}: گروه یافت نشد - {str(e)}")
                fail_count += 1
                await client.disconnect()
                continue
            
            # استخراج message_id از لینک
            message_id = None
            if '/post/' in post_link:
                message_id = int(post_link.split('/post/')[-1])
            elif '/' in post_link:
                parts = post_link.split('/')
                if parts[-1].isdigit():
                    message_id = int(parts[-1])
            
            if not message_id:
                results.append(f"❌ اکانت {account.get('phone')}: لینک پست نامعتبر")
                fail_count += 1
                await client.disconnect()
                continue
            
            # ریپورت با تکرار
            for i in range(repeat_count):
                try:
                    # گزارش به عنوان اسکم و کلاهبرداری
                    report_type = types.InputReportReasonSpam()  # اسکم و اسپم
                    
                    # ارسال گزارش
                    await client(functions.messages.ReportRequest(
                        peer=entity,
                        id=[message_id],
                        reason=report_type,
                        message=report_text
                    ))
                    
                    success_count += 1
                    results.append(f"✅ اکانت {account.get('phone')}: ریپورت {i+1} با موفقیت")
                    
                    # تاخیر بین هر ریپورت
                    await asyncio.sleep(2)
                    
                except Exception as e:
                    results.append(f"❌ اکانت {account.get('phone')}: خطا در ریپورت {i+1} - {str(e)}")
                    fail_count += 1
                
                # بروزرسانی وضعیت
                bot.edit_message_text(
                    f"⏳ <b>در حال ریپورت...</b>\n\n"
                    f"📊 تعداد اکانت‌ها: {len(accounts)}\n"
                    f"🔄 تعداد دفعات: {repeat_count}\n"
                    f"✅ موفق: {success_count}\n"
                    f"❌ ناموفق: {fail_count}\n\n"
                    f"🔄 در حال پردازش: {idx+1}/{len(accounts)}",
                    chat_id=message.chat.id,
                    message_id=status_msg.message_id,
                    parse_mode='HTML'
                )
            
            await client.disconnect()
            
        except Exception as e:
            results.append(f"❌ اکانت {account.get('phone')}: خطا - {str(e)}")
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
        "results": results,
        "user_id": user_id,
        "date": datetime.now().isoformat()
    }
    
    data["reports"].append(report_record)
    save_data(data)
    
    # نمایش نتیجه نهایی
    result_text = f"""
📊 <b>نتیجه ریپورت:</b>

🎯 گروه: {group_username}
✅ ریپورت موفق: {success_count}
❌ ریپورت ناموفق: {fail_count}
📊 مجموع: {success_count + fail_count}

📋 <b>جزئیات:</b>
"""
    
    for res in results[:10]:  # حداکثر ۱۰ نتیجه
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
    
    # پاک کردن دیتای موقت
    if user_id in report_temp:
        del report_temp[user_id]

# ==================== لغو ریپورت ====================

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

# ==================== بقیه بخش‌ها (ادمین، اکانت‌ها، و ...) ====================

# [ادامه کدهای مدیریت اکانت و ادمین از نسخه قبلی]

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

# ==================== اجرا ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 ربات حرفه‌ای ریپورت گروهی")
    print("=" * 50)
    print(f"📊 تعداد اکانت‌ها: {len(data['accounts'])}")
    print(f"👥 تعداد ادمین‌ها: {len(data['admins'])}")
    print(f"📦 تعداد سفارشات: {len(data['orders'])}")
    print(f"📋 تعداد گزارش‌ها: {len(data['reports'])}")
    print("=" * 50)
    print("🔄 ربات در حال اجراست...")
    
    try:
        bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        logger.error(f"Error in main: {e}")
        print(f"❌ خطا: {e}")
