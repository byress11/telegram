import telebot
from telebot import types
import datetime
import json
import locale
import threading
import random
import re
from apscheduler.schedulers.background import BackgroundScheduler

# Locale ayarı
try:
    locale.setlocale(locale.LC_ALL, 'tr_TR.UTF-8')
except locale.Error:
    print("Turkish locale not available, using default.")

# Bot configuration
TOKEN = '7325699470:AAEvHcYFqpxk34d4lspofDHkfoPUZgxoV48'  # Gerçek tokenınızı buraya yerleştirin
bot = telebot.TeleBot(TOKEN)

# Global variables
user_states = {}
tasks = {}

# Constants
CATEGORIES = {
    '⭕️ Hatırlatma': 'reminder',
    '📋 Proje': 'project',
    '🔧 Tadilat': 'renovation',
    '⭐ Diğer': 'other'
}

MOTIVATIONAL_MESSAGES = [
    "🌟 Bugün harika işler başaracaksın!",
    "💪 Her görev, başarıya giden yolda bir adımdır!",
    "🎯 Hedeflerine odaklan ve başaracaksın!",
    "⭐ Sen yapabilirsin, kendine güven!",
    "🌈 Zorluklar seni daha güçlü yapacak!",
    "🚀 Küçük adımlar, büyük başarıların temelidir!",
]

FUNNY_MESSAGES = [
    "🎭 Hey! Görevlerini check etmeyi unutma, yoksa üzülürüm! 😢",
    "🎪 Görevler seni bekliyor, kaçış yok! 😅",
    "🎨 Bugün süper kahraman gibisin, görevlerin senden korkuyor! 💪",
    "🎮 Görevleri tamamlamak bir oyun gibi, ve sen en iyi oyuncusun! 🏆",
    "🎯 Görevler liste yapıyor: 'En sevdiğimiz insan geliyor!' 😄",
]

# Zaman Dilimi Farkı (Sunucu UTC+0, Kullanıcı UTC+3)
TIMEZONE_OFFSET_HOURS = 3
USER_TIMEZONE = datetime.timezone(datetime.timedelta(hours=TIMEZONE_OFFSET_HOURS))

# Helper functions
def save_tasks():
    with open('tasks.json', 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False)

def load_tasks():
    try:
        with open('tasks.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

tasks = load_tasks()

def is_valid_date(year, month, day):
    try:
        datetime.datetime(year, month, day)
        return True
    except ValueError:
        return False

def adjust_date(year, month, day):
    while month > 12:
        year += 1
        month -= 12
    while month < 1:
        year -= 1
        month += 12
    while not is_valid_date(year, month, day):
        day -= 1
    return year, month, day

def create_picker(selected_date=None, picker_type='date'):
    markup = types.InlineKeyboardMarkup(row_width=3)

    if picker_type == 'date':
        selected_date = selected_date or datetime.datetime.now()
        year, month, day = selected_date.year, selected_date.month, selected_date.day

        markup.row(
            types.InlineKeyboardButton("◀️", callback_data=f"day_prev_{year}_{month}_{day}"),
            types.InlineKeyboardButton(f"{day:02d}", callback_data="ignore"),
            types.InlineKeyboardButton("▶️", callback_data=f"day_next_{year}_{month}_{day}")
        )
        markup.row(
            types.InlineKeyboardButton("◀️", callback_data=f"month_prev_{year}_{month}_{day}"),
            types.InlineKeyboardButton(f"{month:02d}", callback_data="ignore"),
            types.InlineKeyboardButton("▶️", callback_data=f"month_next_{year}_{month}_{day}")
        )
        markup.row(
            types.InlineKeyboardButton("◀️", callback_data=f"year_prev_{year}_{month}_{day}"),
            types.InlineKeyboardButton(f"{year}", callback_data="ignore"),
            types.InlineKeyboardButton("▶️", callback_data=f"year_next_{year}_{month}_{day}")
        )
        markup.row(types.InlineKeyboardButton("İleri ➡️", callback_data=f"date_confirm_{year}_{month}_{day}"))

    return markup

# Define menu options for distinguishing user actions
MENU_OPTIONS = ['📋 Görevlerim', '✅ Tamamlandı', '🗑 Görev Sil', '📊 Rapor']

# Bot command handlers

@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        '📋 Görevlerim',
        '✅ Tamamlandı',
        '🗑 Görev Sil',
        '📊 Rapor'
    ]
    markup.add(*buttons)
    bot.send_message(
        message.chat.id,
        "👋 Hoş geldiniz! Görev yönetimi botuna hoş geldiniz.\nGörevlerinizi eklemek için doğrudan mesaj yazabilirsiniz.\nNe yapmak istersiniz?",
        reply_markup=markup
    )

def show_tasks_markup(message, action, button_callback):
    user_id = str(message.from_user.id)
    user_tasks = tasks.get(user_id, [])
    if not user_tasks:
        bot.reply_to(message, f"{action.capitalize()} bulunmuyor!")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    for i, task in enumerate(user_tasks):
        markup.add(types.InlineKeyboardButton(task['name'], callback_data=f"{button_callback}_{i}"))

    bot.send_message(message.chat.id, f"{action} olarak işaretlemek istediğiniz görevi seçin:", reply_markup=markup)

# ### Durum Bazlı Mesaj İşleyiciler ###

# Hatırlatma saatini bekleyen kullanıcılar için
@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('step') == 'waiting_reminder_time')
def get_reminder_time(message):
    user_id = str(message.from_user.id)
    time_input = message.text.strip()

    # Geçerli zaman formatlarını kontrol et (HHMM veya HH:MM)
    match = re.match(r'^([01]\d|2[0-3])[:]?([0-5]\d)$', time_input)
    if not match:
        bot.reply_to(message, "Geçersiz zaman formatı. Lütfen saat ve dakikayı `HHMM` veya `HH:MM` formatında girin (örn: `1224` veya `12:24`):")
        return

    hour, minute = int(match.group(1)), int(match.group(2))

    reminder_date = user_states[user_id].get('reminder_date')
    if not reminder_date:
        bot.reply_to(message, "Tarih seçilmemiş. Lütfen tekrar deneyin.")
        user_states.pop(user_id, None)
        return

    reminder_time_local = reminder_date.replace(hour=hour, minute=minute)
    reminder_time_utc = reminder_time_local.astimezone(datetime.timezone.utc)

    task_name = user_states[user_id]['task_name']
    category = user_states[user_id]['category']

    tasks.setdefault(user_id, []).append({
        'name': task_name,
        'category': category,
        'reminder': reminder_time_utc.strftime('%Y-%m-%d %H:%M')  # UTC formatında sakla
    })
    save_tasks()

    user_states.pop(user_id, None)  # Durumu temizle

    bot.reply_to(
        message,
        f"✅ Görev başarıyla eklendi!\n📝 Görev: {task_name}\n⏰ Hatırlatma: {reminder_time_local.strftime('%d.%m.%Y %H:%M')}"
    )

# Hatırlatma saatini ve dakikasını bekleyen kullanıcılar için (Kategori seçimi)
@bot.callback_query_handler(func=lambda call: call.data.startswith('category_'))
def handle_category(call):
    user_id = str(call.from_user.id)
    if user_id not in user_states or user_states[user_id].get('step') != 'waiting_category':
        bot.answer_callback_query(call.id, "Bu işlemi yapma yetkiniz yok.")
        return

    category = call.data.split('_')[1]
    user_states[user_id]['category'] = category

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Evet", callback_data="set_reminder_yes"),
        types.InlineKeyboardButton("Hayır", callback_data="set_reminder_no")
    )

    bot.edit_message_text(
        "⏰ Hatırlatıcı eklemek ister misiniz?",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

# Hatırlatıcı ekleme seçeneğini işleyen callback
@bot.callback_query_handler(func=lambda call: call.data in ['set_reminder_yes', 'set_reminder_no'])
def handle_set_reminder(call):
    user_id = str(call.from_user.id)
    if user_id not in user_states:
        bot.answer_callback_query(call.id, "Bu işlemi yapma yetkiniz yok.")
        return

    if call.data == 'set_reminder_yes':
        user_states[user_id]['step'] = 'waiting_reminder_date'
        markup = create_picker(picker_type='date')
        bot.edit_message_text(
            "📅 Hatırlatma tarihini seçin:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    else:
        task_name = user_states[user_id]['task_name']
        category = user_states[user_id]['category']

        tasks.setdefault(user_id, []).append({
            'name': task_name,
            'category': category,
            'reminder': None
        })
        save_tasks()

        user_states.pop(user_id, None)  # Durumu temizle

        bot.edit_message_text(
            f"✅ Görev başarıyla eklendi!\n📝 Görev: {task_name}",
            call.message.chat.id,
            call.message.message_id
        )

# Tarih seçimini işleyen callback
@bot.callback_query_handler(func=lambda call: call.data.startswith(('day_', 'month_', 'year_')))
def handle_date_navigation(call):
    user_id = str(call.from_user.id)
    if user_id not in user_states or user_states[user_id].get('step') != 'waiting_reminder_date':
        bot.answer_callback_query(call.id, "Bu işlemi yapma yetkiniz yok.")
        return

    parts = call.data.split('_')
    action, direction, year, month, day = parts[0], parts[1], int(parts[2]), int(parts[3]), int(parts[4])

    if action == 'day':
        day += 1 if direction == 'next' else -1
    elif action == 'month':
        month += 1 if direction == 'next' else -1
    elif action == 'year':
        year += 1 if direction == 'next' else -1

    year, month, day = adjust_date(year, month, day)
    selected_date = datetime.datetime(year, month, day)
    markup = create_picker(selected_date)

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)

# Tarih onayını işleyen callback
@bot.callback_query_handler(func=lambda call: call.data.startswith('date_confirm_'))
def handle_date_confirm(call):
    parts = call.data.split('_')
    if len(parts) != 5:
        bot.answer_callback_query(call.id, "Geçersiz tarih formatı.")
        return

    _, _, year, month, day = parts
    year, month, day = int(year), int(month), int(day)

    user_id = str(call.from_user.id)
    if user_id not in user_states or user_states[user_id].get('step') != 'waiting_reminder_date':
        bot.answer_callback_query(call.id, "Bu işlemi yapma yetkiniz yok.")
        return

    reminder_date = datetime.datetime(year, month, day, tzinfo=USER_TIMEZONE)
    user_states[user_id]['reminder_date'] = reminder_date
    user_states[user_id]['step'] = 'waiting_reminder_time'  # Yeni adım

    bot.edit_message_text(
        "🕒 Hatırlatma saatini ve dakikasını girin (örn: `1224` veya `12:24`):",
        call.message.chat.id,
        call.message.message_id
    )

# ### Genel Mesaj İşleyicisi ###

@bot.message_handler(func=lambda message: (
    str(message.from_user.id) not in user_states and
    message.text not in MENU_OPTIONS and
    not message.text.startswith('/')
))
def handle_new_task(message):
    user_id = str(message.from_user.id)
    task_name = message.text.strip()
    if not task_name:
        bot.reply_to(message, "Görev adı boş olamaz. Lütfen geçerli bir görev adı girin:")
        return

    user_states[user_id] = {'step': 'waiting_category', 'task_name': task_name}

    markup = types.InlineKeyboardMarkup(row_width=2)
    for category_name, category_value in CATEGORIES.items():
        markup.add(types.InlineKeyboardButton(category_name, callback_data=f"category_{category_value}"))

    bot.send_message(
        message.chat.id,
        "📁 Görev kategorisini seçin:",
        reply_markup=markup
    )

# ### Diğer Mesaj İşleyiciler ###

@bot.callback_query_handler(func=lambda call: call.data.startswith(('complete_', 'delete_')))
def handle_task_actions(call):
    user_id = str(call.from_user.id)
    action, task_index = call.data.split('_')
    task_index = int(task_index)

    user_tasks = tasks.get(user_id, [])
    if 0 <= task_index < len(user_tasks):
        task = user_tasks.pop(task_index)
        save_tasks()
        if action == 'complete':
            message = f"✅ '{task['name']}' görevi tamamlandı olarak işaretlendi!"
        else:
            message = f"🗑 '{task['name']}' görevi silindi!"
        bot.edit_message_text(message, call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Görev bulunamadı!")

@bot.message_handler(func=lambda message: message.text in ['✅ Tamamlandı', '🗑 Görev Sil'])
def handle_mark_or_delete(message):
    action = 'Tamamlanacak görev' if message.text == '✅ Tamamlandı' else 'Silinecek görev'
    button_callback = 'complete' if message.text == '✅ Tamamlandı' else 'delete'
    show_tasks_markup(message, action, button_callback)

@bot.message_handler(func=lambda message: message.text == '📋 Görevlerim')
def show_tasks(message):
    user_id = str(message.from_user.id)
    user_tasks = tasks.get(user_id, [])
    if not user_tasks:
        bot.reply_to(message, "Henüz görev eklenmemiş!")
        return

    response = "📋 Görevleriniz:\n\n"
    for task in user_tasks:
        category_name = next(k for k, v in CATEGORIES.items() if v == task['category'])
        reminder = f"\n⏰ Hatırlatma: {task['reminder']}" if task.get('reminder') else ""
        response += f"• {task['name']} ({category_name}){reminder}\n\n"

    bot.reply_to(message, response)

@bot.message_handler(func=lambda message: message.text == '📊 Rapor')
def show_report(message):
    user_id = str(message.from_user.id)
    user_tasks = tasks.get(user_id, [])
    if not user_tasks:
        bot.reply_to(message, "Henüz görev bulunmuyor!")
        return

    categorized_tasks = {}
    for task in user_tasks:
        category = task['category']
        categorized_tasks.setdefault(category, []).append(task['name'])

    response = "📊 Görevler - Kategoriye Göre:\n\n"
    for category, task_list in categorized_tasks.items():
        category_name = next(k for k, v in CATEGORIES.items() if v == category)
        response += f"📌 {category_name}:\n" + "\n".join(f"• {name}" for name in task_list) + "\n\n"

    bot.reply_to(message, response)

# ### Hatırlatmalar ve Zamanlanmış Mesajlar ###

def check_reminders():
    current_time_utc = datetime.datetime.now(datetime.timezone.utc)
    print(f"[DEBUG] Current UTC Time: {current_time_utc}")

    for user_id, user_tasks in tasks.items():
        for task in user_tasks[:]:  # Listeyi kopyalayarak döngüyü güvenli hale getir
            reminder_str = task.get('reminder')
            if reminder_str:
                try:
                    reminder_time_utc = datetime.datetime.strptime(reminder_str, '%Y-%m-%d %H:%M').replace(tzinfo=datetime.timezone.utc)
                    time_diff = (reminder_time_utc - current_time_utc).total_seconds()

                    print(f"[DEBUG] Task: {task['name']}, Reminder UTC Time: {reminder_time_utc}, Time Diff: {time_diff}")

                    # Görev zamanı geldiğinde (±30 saniye tolerans)
                    if -30 <= time_diff <= 30:
                        reminder_time_local = reminder_time_utc.astimezone(USER_TIMEZONE)
                        message = (
                            f"⏰ Görev Zamanı Geldi!\n\n"
                            f"📝 Görev: {task['name']}\n"
                            f"🕒 Zaman: {reminder_time_local.strftime('%d.%m.%Y %H:%M')}"
                        )
                        bot.send_message(int(user_id), message)
                        # Hatırlatmayı tek seferlik yapmak için sil
                        user_tasks.remove(task)
                        save_tasks()

                    # Yaklaşan hatırlatma (1 saat önce ±30 saniye tolerans)
                    elif 3570 <= time_diff <= 3630:
                        reminder_time_local = reminder_time_utc.astimezone(USER_TIMEZONE)
                        message = (
                            f"⚠️ Yaklaşan Görev Hatırlatması!\n\n"
                            f"📝 Görev: {task['name']}\n"
                            f"🕒 Kalan Süre: 1 saat\n"
                            f"📅 Planlanan: {reminder_time_local.strftime('%d.%m.%Y %H:%M')}"
                        )
                        bot.send_message(int(user_id), message)
                except Exception as e:
                    print(f"Hatırlatma gönderilirken hata oluştu: {e}")

def send_daily_message():
    for user_id, user_tasks in tasks.items():
        if user_tasks:
            message = random.choice(MOTIVATIONAL_MESSAGES)
            try:
                bot.send_message(int(user_id), message)
            except Exception as e:
                print(f"Günlük mesaj gönderilirken hata oluştu: {e}")

def send_funny_message():
    for user_id, user_tasks in tasks.items():
        if user_tasks:
            message = random.choice(FUNNY_MESSAGES)
            try:
                bot.send_message(int(user_id), message)
            except Exception as e:
                print(f"Komik mesaj gönderilirken hata oluştu: {e}")

def send_reminder_messages():
    check_reminders()

# Scheduler Ayarları
scheduler = BackgroundScheduler(timezone="UTC")
scheduler.add_job(check_reminders, 'interval', minutes=1, id='check_reminders')
scheduler.add_job(send_daily_message, 'cron', hour=9, minute=0, id='send_daily_message')
scheduler.add_job(send_funny_message, 'cron', hour=15, minute=0, id='send_funny_message')
scheduler.start()

# Bot'u başlat
if __name__ == "__main__":
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"Bot'ta bir hata oluştu: {e}")
        # Gerekirse botu yeniden başlatmak için loglama veya başka işlemler ekleyebilirsiniz
