import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os

# توکن ربات - لطفاً توکن جدید بگیرید
TOKEN = "8986723154:AAH1qTObY9bo0A-csQFnSDYVcRhYr_DtsJ0"  # این رو عوض کنید

# لیست ایدی های مجاز
ALLOWED_USERS = [7803165903, 7795617350]

# فایل برای ذخیره اطلاعات
DATA_FILE = "bot_data.json"

# ایجاد ربات
bot = telebot.TeleBot(TOKEN)

# ساختار داده
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "accounts": [],
        "admins": [],
        "reports": []
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

# تابع بررسی دسترسی
def is_allowed(user_id):
    return user_id in ALLOWED_USERS or user_id in data["admins"]

# منوی اصلی
def main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    btn1 = InlineKeyboardButton("📊 گزارشات", callback_data="reports")
    btn2 = InlineKeyboardButton("➕ افزودن اکانت", callback_data="add_account")
    btn3 = InlineKeyboardButton("⚙️ مدیریت اکانت", callback_data="manage_accounts")
    btn4 = InlineKeyboardButton("👤 افزودن ادمین", callback_data="add_admin")
    btn5 = InlineKeyboardButton("👥 مدیریت ادمین", callback_data="manage_admins")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    return markup

# شروع ربات
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    if not is_allowed(user_id):
        bot.send_message(message.chat.id, "❌ شما دسترسی به این ربات ندارید!")
        return
    
    bot.send_message(
        message.chat.id,
        f"👋 سلام {message.from_user.first_name}!\n"
        "به ربات ریپورتر خوش آمدید.\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=main_menu()
    )

# مدیریت دکمه‌ها
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    
    if not is_allowed(user_id):
        bot.answer_callback_query(call.id, "❌ شما دسترسی ندارید!")
        return
    
    if call.data == "reports":
        show_reports(call.message)
    
    elif call.data == "add_account":
        bot.send_message(call.message.chat.id, "📝 لطفاً آیدی عددی اکانت جدید را وارد کنید:")
        bot.register_next_step_handler(call.message, add_account_process)
    
    elif call.data == "manage_accounts":
        manage_accounts(call.message)
    
    elif call.data == "add_admin":
        bot.send_message(call.message.chat.id, "👤 لطفاً آیدی عددی ادمین جدید را وارد کنید:")
        bot.register_next_step_handler(call.message, add_admin_process)
    
    elif call.data == "manage_admins":
        manage_admins(call.message)
    
    elif call.data.startswith("remove_account_"):
        account_id = int(call.data.split("_")[2])
        remove_account(call.message, account_id)
    
    elif call.data.startswith("remove_admin_"):
        admin_id = int(call.data.split("_")[2])
        remove_admin(call.message, admin_id)
    
    elif call.data.startswith("report_account_"):
        account_id = int(call.data.split("_")[2])
        bot.send_message(call.message.chat.id, f"📝 لطفاً متن گزارش برای اکانت {account_id} را وارد کنید:")
        bot.register_next_step_handler(call.message, add_report, account_id)
    
    bot.answer_callback_query(call.id)

# نمایش گزارشات
def show_reports(message):
    if not data["reports"]:
        bot.send_message(message.chat.id, "📭 هیچ گزارشی ثبت نشده است.")
        return
    
    text = "📊 **لیست گزارشات:**\n\n"
    for i, report in enumerate(data["reports"], 1):
        text += f"{i}. اکانت: {report['account_id']}\n"
        text += f"   گزارش: {report['text']}\n"
        text += f"   تاریخ: {report['date']}\n\n"
    
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# افزودن اکانت
def add_account_process(message):
    try:
        account_id = int(message.text.strip())
        
        # بررسی تکراری نبودن
        if account_id in data["accounts"]:
            bot.send_message(message.chat.id, "❌ این اکانت قبلاً ثبت شده است!")
            return
        
        data["accounts"].append(account_id)
        save_data(data)
        bot.send_message(
            message.chat.id,
            f"✅ اکانت {account_id} با موفقیت اضافه شد!",
            reply_markup=main_menu()
        )
    except ValueError:
        bot.send_message(message.chat.id, "❌ لطفاً یک آیدی عددی معتبر وارد کنید!")

# مدیریت اکانت‌ها
def manage_accounts(message):
    if not data["accounts"]:
        bot.send_message(message.chat.id, "📭 هیچ اکانتی ثبت نشده است.")
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for acc in data["accounts"]:
        btn_text = f"🗑 حذف {acc} | 📝 گزارش"
        markup.add(InlineKeyboardButton(
            btn_text,
            callback_data=f"report_account_{acc}"
        ))
        markup.add(InlineKeyboardButton(
            f"❌ حذف {acc}",
            callback_data=f"remove_account_{acc}"
        ))
    
    bot.send_message(
        message.chat.id,
        "📋 لیست اکانت‌ها:\nبرای هر اکانت می‌توانید گزارش ثبت کنید یا حذف کنید.",
        reply_markup=markup
    )

# حذف اکانت
def remove_account(message, account_id):
    if account_id in data["accounts"]:
        data["accounts"].remove(account_id)
        save_data(data)
        bot.send_message(message.chat.id, f"✅ اکانت {account_id} حذف شد!")
    else:
        bot.send_message(message.chat.id, "❌ اکانت مورد نظر یافت نشد!")

# افزودن گزارش
def add_report(message, account_id):
    report_text = message.text.strip()
    
    data["reports"].append({
        "account_id": account_id,
        "text": report_text,
        "date": message.date
    })
    save_data(data)
    
    bot.send_message(
        message.chat.id,
        f"✅ گزارش برای اکانت {account_id} با موفقیت ثبت شد!",
        reply_markup=main_menu()
    )

# افزودن ادمین
def add_admin_process(message):
    try:
        admin_id = int(message.text.strip())
        
        if admin_id in data["admins"]:
            bot.send_message(message.chat.id, "❌ این کاربر قبلاً ادمین است!")
            return
        
        if admin_id in ALLOWED_USERS:
            bot.send_message(message.chat.id, "❌ این کاربر در لیست اصلی است!")
            return
        
        data["admins"].append(admin_id)
        save_data(data)
        bot.send_message(
            message.chat.id,
            f"✅ ادمین {admin_id} با موفقیت اضافه شد!",
            reply_markup=main_menu()
        )
    except ValueError:
        bot.send_message(message.chat.id, "❌ لطفاً یک آیدی عددی معتبر وارد کنید!")

# مدیریت ادمین‌ها
def manage_admins(message):
    if not data["admins"]:
        bot.send_message(message.chat.id, "📭 هیچ ادمینی ثبت نشده است.")
        return
    
    markup = InlineKeyboardMarkup(row_width=1)
    for admin in data["admins"]:
        markup.add(InlineKeyboardButton(
            f"❌ حذف {admin}",
            callback_data=f"remove_admin_{admin}"
        ))
    
    bot.send_message(
        message.chat.id,
        "👥 لیست ادمین‌ها:",
        reply_markup=markup
    )

# حذف ادمین
def remove_admin(message, admin_id):
    if admin_id in data["admins"]:
        data["admins"].remove(admin_id)
        save_data(data)
        bot.send_message(message.chat.id, f"✅ ادمین {admin_id} حذف شد!")
    else:
        bot.send_message(message.chat.id, "❌ ادمین مورد نظر یافت نشد!")

# اجرای ربات
if __name__ == "__main__":
    print("🤖 ربات ریپورتر راه‌اندازی شد...")
    bot.infinity_polling()
