"""

ULTIMATE MOVIE DATABASE BOT - WORLD'S BIGGEST CODE
Version: 10.0 - All Features Included
Channel: -1004341107282
Request ID: @Iamsrm0
Language: English

"""

import os
import telebot
import threading
import json
import requests
import urllib.parse
import time
import logging
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# ===================== FLASK SERVER FOR RENDER =====================
app = Flask(__name__)

@app.route('/')
def home():
    return """
    <h1>ULTIMATE MOVIE BOT IS RUNNING</h1>
    <p>Status: Online</p>
    <p>Database Channel: -1004341107282</p>
    <p>Request Contact: @Iamsrm0</p>
    <p>Version: 10.0 Ultimate</p>
    """

@app.route('/health')
def health():
    return {"status": "ok", "movies": len(MOVIES_DB), "users": len(USERS_DB)}

def run_flask():
    app.run(host='0.0.0.0', port=8099)

threading.Thread(target=run_flask, daemon=True).start()

# ===================== CONFIGURATION =====================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TMDB_KEY = os.environ.get("TMDB_KEY")
CHANNEL_ID = -1004341107282
ADMIN_ID = 123456789 # CHANGE THIS - Get from @userinfobot
DB_FILE = "database.json"
USERS_FILE = "users.json"
REQUEST_USERNAME = "Iamsrm0" # Your Request ID

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ===================== DATABASE LOAD =====================
def load_json(file, default):
    try:
        if os.path.exists(file):
            with open(file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logging.error(f"Load Error {file}: {e}")
    return default

def save_json(file, data):
    try:
        with open(file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logging.error(f"Save Error {file}: {e}")
        return False

MOVIES_DB = load_json(DB_FILE, {})
USERS_DB = load_json(USERS_FILE, {})

print(f"==========================================")
print(f"ULTIMATE BOT STARTED")
print(f"Movies in DB: {len(MOVIES_DB)}")
print(f"Total Users: {len(USERS_DB)}")
print(f"Database Channel: {CHANNEL_ID}")
print(f"Request ID: @{REQUEST_USERNAME}")
print(f"==========================================")

# ===================== TMDB API FUNCTIONS =====================
def search_tmdb_movie(query):
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={urllib.parse.quote(query)}&include_adult=false"
        response = requests.get(url, timeout=15)
        data = response.json()
        if data.get('results'):
            for item in data['results']:
                if item.get('media_type') in ['movie', 'tv'] or 'title' in item or 'name' in item:
                    return item
            return data['results'][0]
    except Exception as e:
        logging.error(f"TMDB Search Error: {e}")
    return None

# ===================== USER TRACKING =====================
def add_user(user):
    uid = str(user.id)
    if uid not in USERS_DB:
        USERS_DB[uid] = {
            "id": user.id,
            "first_name": user.first_name,
            "username": user.username,
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "search_count": 0
        }
        save_json(USERS_FILE, USERS_DB)
        try:
            bot.send_message(ADMIN_ID, f"🆕 New User Joined\n\n👤 {user.first_name}\n🆔 {user.id}\n🔗 @{user.username}\nTotal: {len(USERS_DB)}")
        except:
            pass

def increment_search(user_id):
    uid = str(user_id)
    if uid in USERS_DB:
        USERS_DB[uid]['search_count'] = USERS_DB[uid].get('search_count', 0) + 1
        save_json(USERS_FILE, USERS_DB)

# ===================== ADMIN UPLOADS FILE TO BOT -> SAVE + SEND TO CHANNEL =====================
@bot.message_handler(content_types=['document', 'video'], func=lambda m: m.from_user.id == ADMIN_ID)
def handle_admin_upload(message):
    caption_raw = (message.caption or "").strip()
    if not caption_raw:
        bot.reply_to(message, "❌ *Error:* Please send file with movie name in caption.\n\nExample:\n`animal 2023 hindi`")
        return

    caption = caption_raw.lower()
    file_id = message.document.file_id if message.document else message.video.file_id
    file_name = message.document.file_name if message.document and message.document.file_name else getattr(message.video, 'file_name', 'video.mp4')
    file_size = f"{message.document.file_size / (1024*1024):.2f} MB" if message.document else f"{message.video.file_size / (1024*1024):.2f} MB"

    bot.send_chat_action(message.chat.id, 'upload_document')
    tmdb_info = search_tmdb_movie(caption)
    year = ""
    rating = "N/A"
    overview = ""
    if tmdb_info:
        year = (tmdb_info.get('release_date') or tmdb_info.get('first_air_date') or "")[:4]
        rating = tmdb_info.get('vote_average', 'N/A')
        overview = tmdb_info.get('overview', '')[:300]

    MOVIES_DB[caption] = {
        "file_id": file_id,
        "file_name": file_name,
        "file_size": file_size,
        "title": caption.title(),
        "real_title": tmdb_info.get('title') if tmdb_info else caption.title(),
        "year": year,
        "rating": str(rating),
        "added_at": datetime.now().strftime("%Y-%m-%d"),
        "message_id": None
    }
    save_json(DB_FILE, MOVIES_DB)

    channel_caption = f"""
🎬 *{caption.title()}* ({year})

⭐ *Rating:* {rating}/10
📁 *File:* {file_name}
💾 *Size:* {file_size}
📅 *Year:* {year}

📝 *Story:* {overview}...

✅ *Available in Bot*
🔗 *Search in Bot:* {caption}
    """

    try:
        if message.document:
            sent = bot.send_document(CHANNEL_ID, file_id, caption=channel_caption, parse_mode="Markdown")
        else:
            sent = bot.send_video(CHANNEL_ID, file_id, caption=channel_caption, parse_mode="Markdown")

        MOVIES_DB[caption]['message_id'] = sent.message_id
        save_json(DB_FILE, MOVIES_DB)

        bot.reply_to(message, f"✅ *SUCCESSFULLY SAVED & UPLOADED*\n\n🎬 *Movie:* {caption.title()}\n📁 *File:* {file_name}\n💾 *Size:* {file_size}\n🆔 *Channel ID:* {CHANNEL_ID}\n💬 *Message ID:* {sent.message_id}\n📊 *Total Movies:* {len(MOVIES_DB)}", parse_mode="Markdown")

    except Exception as e:
        bot.reply_to(message, f"❌ *Failed to send to Channel*\nMake Bot ADMIN in Channel {CHANNEL_ID}\nError: `{e}`", parse_mode="Markdown")

# ===================== AUTO SAVE FROM CHANNEL =====================
@bot.channel_post_handler(content_types=['document', 'video'])
def auto_save_from_channel(message):
    caption = (message.caption or "").lower().strip()
    if caption:
        key = caption.split('\n')[0].lower().strip()
        key = key.replace('🎬', '').replace('*', '').strip()
    else:
        key = f"movie_{message.message_id}"
    file_id = message.document.file_id if message.document else message.video.file_id
    if key not in MOVIES_DB:
        MOVIES_DB[key] = {"file_id": file_id, "file_name": key, "title": key.title(), "message_id": message.message_id, "added_at": datetime.now().strftime("%Y-%m-%d")}
        save_json(DB_FILE, MOVIES_DB)

# ===================== ADMIN COMMANDS =====================
@bot.message_handler(commands=['stats'])
def stats_cmd(m):
    if m.from_user.id!= ADMIN_ID: return
    text = f"📊 *BOT STATISTICS*\n\n🎬 *Total Movies:* {len(MOVIES_DB)}\n👥 *Total Users:* {len(USERS_DB)}\n📢 *Channel:* {CHANNEL_ID}\n📩 *Request ID:* @{REQUEST_USERNAME}\n"
    for i, (k, v) in enumerate(list(MOVIES_DB.items())[-5:]):
        text += f"{i+1}. {k.title()}\n"
    bot.send_message(m.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(m):
    if m.from_user.id!= ADMIN_ID: return
    msg = m.text.replace('/broadcast', '').strip()
    if not msg:
        bot.reply_to(m, "Usage: /broadcast Your message")
        return
    sent = 0
    for uid in USERS_DB:
        try:
            bot.send_message(uid, f"📢 *Broadcast:*\n\n{msg}", parse_mode="Markdown")
            sent += 1
            time.sleep(0.05)
        except: pass
    bot.reply_to(m, f"✅ Broadcast sent to {sent} users")

# ===================== START & HELP =====================
@bot.message_handler(commands=['start', 'help'])
def start_cmd(m):
    add_user(m.from_user)
    text = f"""
🎬 *Welcome to Ultimate Movie Bot* 🎬

👋 Hello {m.from_user.first_name}!

*How to use:*
Send any movie name. Example:
`Animal`
`Jawan`

*Database:* {len(MOVIES_DB)} Movies
*Request:* @{REQUEST_USERNAME}

Send movie name now 👇
    """
    bot.send_message(m.chat.id, text, parse_mode="Markdown")

# ===================== MAIN SEARCH LOGIC =====================
@bot.message_handler(func=lambda m: True, content_types=['text'])
def ultimate_search(m):
    if m.text.startswith('/'): return
    query = m.text.lower().strip()
    if len(query) < 2 or len(query) > 100: return

    add_user(m.from_user)
    increment_search(m.from_user.id)
    bot.send_chat_action(m.chat.id, 'typing')

    tmdb_data = search_tmdb_movie(query)
    if not tmdb_data:
        bot.send_message(m.chat.id, f"❌ *No results for* `{m.text}`", parse_mode="Markdown")
        return

    real_title = tmdb_data.get('title') or tmdb_data.get('name') or m.text
    title_lower = real_title.lower()
    overview = tmdb_data.get('overview', 'No overview available.')[:350]
    rating = tmdb_data.get('vote_average', 'N/A')
    year = (tmdb_data.get('release_date') or tmdb_data.get('first_air_date') or "")[:4]
    poster_path = tmdb_data.get('poster_path')

    found_movie = None
    if query in MOVIES_DB:
        found_movie = MOVIES_DB[query]
    else:
        for db_key, db_data in MOVIES_DB.items():
            if query in db_key or db_key in title_lower or title_lower in db_key:
                found_movie = db_data
                break

    markup = InlineKeyboardMarkup(row_width=2)

    if found_movie:
        file_id = found_movie['file_id']
        markup.row(InlineKeyboardButton("💾 DOWNLOAD NOW - HD", callback_data=f"dl_{file_id}"))
        markup.row(
            InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={urllib.parse.quote(real_title + ' official trailer')}"),
            InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={urllib.parse.quote(real_title)}")
        )
        markup.row(
            InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={urllib.parse.quote(real_title)}"),
            InlineKeyboardButton("🎬 TMDB Details", url=f"https://www.themoviedb.org/search?query={urllib.parse.quote(real_title)}")
        )
        markup.row(
            InlineKeyboardButton("🔍 Google Info", url=f"https://www.google.com/search?q={urllib.parse.quote(real_title + ' movie')}"),
            InlineKeyboardButton("📢 Request Movie", url=f"https://t.me/{REQUEST_USERNAME}")
        )
        caption_text = f"🎬 *{real_title}* ({year})\n⭐ *Rating:* {rating}/10\n\n📝 *Story:*\n{overview}...\n\n✅ *Status:* Download Available\n📁 *File:* {found_movie.get('file_name', 'HD')}\n💾 *Size:* {found_movie.get('file_size', 'HD')}\n\n👇 *Click Download Below*"

    else:
        markup.row(
            InlineKeyboardButton("▶️ Watch Trailer", url=f"https://www.youtube.com/results?search_query={urllib.parse.quote(real_title + ' official trailer')}"),
            InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={urllib.parse.quote(real_title)}")
        )
        markup.row(
            InlineKeyboardButton("⭐ IMDb Rating", url=f"https://www.imdb.com/find?q={urllib.parse.quote(real_title)}"),
            InlineKeyboardButton("🎬 Full Details", url=f"https://www.themoviedb.org/search?query={urllib.parse.quote(real_title)}")
        )
        markup.row(
            InlineKeyboardButton("🔍 Search Google", url=f"https://www.google.com/search?q={urllib.parse.quote(real_title + ' movie watch')}"),
            InlineKeyboardButton("📢 Request Movie", url=f"https://t.me/{REQUEST_USERNAME}")
        )
        caption_text = f"🎬 *{real_title}* ({year})\n⭐ *Rating:* {rating}/10\n\n📝 *Story:*\n{overview}...\n\n❌ *Status:* Not Available in Database\n💡 *Request to:* @{REQUEST_USERNAME}\n\n👇 *Check Options Below*"

    try:
        if poster_path:
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            bot.send_photo(m.chat.id, poster_url, caption=caption_text, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(m.chat.id, caption_text, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        bot.send_message(m.chat.id, caption_text.replace('*', ''), reply_markup=markup)

# ===================== CALLBACK - DOWNLOAD HANDLER =====================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("dl_"):
        file_id = call.data.replace("dl_", "")
        try:
            bot.answer_callback_query(call.id, "📤 Sending File...")
            bot.send_chat_action(call.message.chat.id, 'upload_document')
            bot.send_document(call.message.chat.id, file_id, caption=f"🎬 Here is your movie!\n\n✅ From Database {CHANNEL_ID}\n📩 Request: @{REQUEST_USERNAME}")
        except Exception as e:
            bot.answer_callback_query(call.id, "❌ File Not Found")

# ===================== START POLLING =====================
if __name__ == "__main__":
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
        except Exception as e:
            logging.error(f"Polling Error: {e}")
            time.sleep(5)
