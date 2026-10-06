import os, telebot, threading, json
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

app = Flask('')
@app.route('/')
def home(): return "Bot Running - DB Channel Source"
threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8099)).start()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

CHANNEL_ID = -1004341107282 # Tumhara Database Channel
DB_FILE = "database.json"

# Load Database
try:
    with open(DB_FILE, 'r') as f:
        MOVIES_DB = json.load(f)
except:
    MOVIES_DB = {}

def save_db():
    with open(DB_FILE, 'w') as f:
        json.dump(MOVIES_DB, f)

# 1. Jab tum Channel me video daaloge, Bot Auto Save kar lega
@bot.channel_post_handler(content_types=['document', 'video'])
def auto_save(m):
    caption = (m.caption or "").lower()
    file_name = ""
    if m.document:
        file_name = m.document.file_name.lower()
    elif m.video:
        file_name = (m.video.file_name or "").lower()

    # File name ya caption se key banao
    key = caption if caption else file_name
    if not key:
        key = f"file_{m.message_id}"

    MOVIES_DB[key] = m.message_id
    save_db()
    print(f"SAVED: {key} -> {m.message_id}")

@bot.message_handler(commands=['start'])
def start(m):
    bot.reply_to(m, "🎬 Movie ka naam bhejo\nBot Database Channel se video dega.")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search(m):
    if not m.text or m.text.startswith('/'): return
    query = m.text.lower().strip()
    if len(query) < 2: return

    found_id = None
    found_name = None

    # Database me search karo
    for name, msg_id in MOVIES_DB.items():
        if query in name or name in query:
            found_id = msg_id
            found_name = name
            break

    if found_id:
        # MIL GAYA - Channel se utha ke bhejo
        bot.send_message(m.chat.id, f"✅ *{found_name}* mil gayi! Channel se bhej raha hu...", parse_mode="Markdown")
        try:
            bot.copy_message(m.chat.id, CHANNEL_ID, found_id)

            markup = InlineKeyboardMarkup()
            markup.row(InlineKeyboardButton("📦 MovieBox", url=f"https://moviebox.ph/web/searchResult?keyword={found_name}"))
            bot.send_message(m.chat.id, "☝️ Upar wali file download karo", reply_markup=markup)

        except Exception as e:
            bot.send_message(m.chat.id, f"❌ Bot ko Channel {CHANNEL_ID} me ADMIN banao!\nError: {e}")
    else:
        bot.send_message(m.chat.id, f"❌ *{m.text}* Database Channel me nahi hai.\nPehle Channel me upload karo.", parse_mode="Markdown")

print("Bot Started")
bot.infinity_polling()
