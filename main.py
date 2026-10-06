import os, telebot, threading, json, requests
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import urllib.parse

app = Flask('')
@app.route('/')
def home(): return "Bot Running"
threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8099)).start()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TMDB_KEY = os.environ.get("TMDB_KEY") # Render me add karna
CHANNEL_ID = -1004341107282
ADMIN_ID = 123456789 # Yaha apni Telegram ID daalo @userinfobot se le lo
DB_FILE = "database.json"

bot = telebot.TeleBot(BOT_TOKEN)

try:
    with open(DB_FILE, 'r') as f: MOVIES_DB = json.load(f)
except: MOVIES_DB = {}

def save_db():
    with open(DB_FILE, 'w') as f: json.dump(MOVIES_DB, f)

# TMDB Search for Poster/Info
def search_tmdb(q):
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={urllib.parse.quote(q)}"
        r = requests.get(url).json()
        return r['results'][0] if r.get('results') else None
    except: return None

# ===== 1. AGAR TUM BOT ME FILE UPLOAD KAROGE TO =====
@bot.message_handler(content_types=['document', 'video'], func=lambda m: m.from_user.id == ADMIN_ID)
def upload_from_bot(m):
    caption = (m.caption or m.text or "movie").lower()
    file_id = m.document.file_id if m.document else m.video.file_id
    file_name = m.document.file_name if m.document else "video.mp4"

    # DB me Save
    MOVIES_DB[caption] = {"file_id": file_id, "file_name": file_name}
    save_db()

    # Channel pe Thumbnail + Description ke saath bhejo
    thumb = None
    desc = f"🎬 {caption.title()}\n\n📁 {file_name}\n💾 Powered by Bot"

    # TMDB se poster nikal ke thumbnail banao
    info = search_tmdb(caption)
    poster_url = f"https://image.tmdb.org/t/p/w500{info['poster_path']}" if info and info.get('poster_path') else None

    try:
        if m.document:
            bot.send_document(CHANNEL_ID, file_id, caption=desc, thumb=thumb)
        else:
            bot.send_video(CHANNEL_ID, file_id, caption=desc, thumb=thumb)

        bot.reply_to(m, f"✅ Saved & Sent to Channel!\nName: {caption}\nID: {CHANNEL_ID}")
    except Exception as e:
        bot.reply_to(m, f"❌ Channel me Admin banao! Error: {e}")

# ===== 2. USER SEARCH KAREGA TO =====
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_search(m):
    if m.text.startswith('/'): return
    query = m.text.lower().strip()
    if len(query) < 2: return
    if m.from_user.id == ADMIN_ID: return

    info = search_tmdb(query)
    if not info:
        bot.send_message(m.chat.id, "❌ Movie nahi mili")
        return

    real_title = info.get('title') or info.get('name')
    title_lower = real_title.lower()

    # Check karo DB me hai ya nahi
    found_data = None
    for name, data in MOVIES_DB.items():
        if query in name or name in title_lower or title_lower in name:
            found_data = data
            break

    markup = InlineKeyboardMarkup()

    if found_data:
        # AGAR DB ME HAI TO DOWNLOAD DIKHEGA
        markup.row(InlineKeyboardButton("💾 DOWNLOAD NOW", callback_data=f"dl_{found_data['file_id']}"))
        markup.row(InlineKeyboardButton("📦 MovieBox", url=f"https://moviebox.ph/web/searchResult?keyword={urllib.parse.quote(real_title)}"))
        cap = f"🎬 *{real_title}*\n⭐ {info.get('vote_average', 'N/A')}\n\n✅ Download Available"
    else:
        # AGAR DB ME NAHI HAI TO DOWNLOAD HAT JAYEGA
        markup.row(InlineKeyboardButton("❌ Not Available", callback_data="no"))
        markup.row(InlineKeyboardButton("📦 Check on MovieBox", url=f"https://moviebox.ph/web/searchResult?keyword={urllib.parse.quote(real_title)}"))
        cap = f"🎬 *{real_title}*\n⭐ {info.get('vote_average', 'N/A')}\n\n❌ Download abhi available nahi hai."

    poster = info.get('poster_path')
    if poster:
        bot.send_photo(m.chat.id, f"https://image.tmdb.org/t/p/w500{poster}", caption=cap, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(m.chat.id, cap, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if c.data.startswith("dl_"):
        file_id = c.data.replace("dl_", "")
        bot.send_document(c.message.chat.id, file_id)
        bot.answer_callback_query(c.id, "Sending...")

print("Bot Started - Smart Mode")
bot.infinity_polling()
