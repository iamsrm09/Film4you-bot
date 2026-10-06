import os, telebot, threading, json, requests, urllib.parse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# ===== FLASK KEEP ALIVE =====
app = Flask('')
@app.route('/')
def home(): return "Bot Running - Full Version"
threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8099)).start()

# ===== CONFIG =====
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TMDB_KEY = os.environ.get("TMDB_KEY") # Add this in Render Env
CHANNEL_ID = -1004341107282 # Your Database Channel
ADMIN_ID = 123456789 # Replace with your ID from @userinfobot
DB_FILE = "database.json"

bot = telebot.TeleBot(BOT_TOKEN)

# Load DB
try:
    with open(DB_FILE, 'r') as f: MOVIES_DB = json.load(f)
except: MOVIES_DB = {}

def save_db():
    with open(DB_FILE, 'w') as f: json.dump(MOVIES_DB, f, indent=2)

# ===== TMDB SEARCH =====
def search_tmdb(query):
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={urllib.parse.quote(query)}"
        r = requests.get(url, timeout=10).json()
        if r.get('results'):
            return r['results'][0]
    except Exception as e:
        print(f"TMDB Error: {e}")
    return None

# ===== 1. ADMIN UPLOADS FILE TO BOT -> SAVE + SEND TO CHANNEL =====
@bot.message_handler(content_types=['document', 'video'], func=lambda m: m.from_user.id == ADMIN_ID)
def admin_upload(m):
    caption = (m.caption or "").lower().strip()
    if not caption:
        bot.reply_to(m, "❌ Please send file with movie name in caption. Example: `animal 2023`")
        return

    file_id = m.document.file_id if m.document else m.video.file_id
    file_name = m.document.file_name if m.document and m.document.file_name else getattr(m.video, 'file_name', 'video.mp4')

    # Save to DB
    MOVIES_DB[caption] = {
        "file_id": file_id,
        "file_name": file_name,
        "title": caption.title()
    }
    save_db()

    # Create Channel Description
    info = search_tmdb(caption)
    if info:
        rating = info.get('vote_average', 'N/A')
        desc = f"🎬 {caption.title()}\n⭐ Rating: {rating}/10\n📁 {file_name}\n\n💾 Available in Bot Database"
    else:
        desc = f"🎬 {caption.title()}\n📁 {file_name}\n\n💾 Available in Bot Database"

    try:
        if m.document:
            bot.send_document(CHANNEL_ID, file_id, caption=desc)
        else:
            bot.send_video(CHANNEL_ID, file_id, caption=desc)
        bot.reply_to(m, f"✅ Saved!\nName: {caption}\nSent to Channel {CHANNEL_ID}\nTotal Movies: {len(MOVIES_DB)}")
    except Exception as e:
        bot.reply_to(m, f"❌ Make Bot ADMIN in Channel {CHANNEL_ID}\nError: {e}")

# ===== 2. AUTO SAVE IF YOU UPLOAD DIRECTLY TO CHANNEL =====
@bot.channel_post_handler(content_types=['document', 'video'])
def channel_save(m):
    caption = (m.caption or "").lower().strip()
    if not caption: return
    file_id = m.document.file_id if m.document else m.video.file_id
    MOVIES_DB[caption] = {"file_id": file_id, "file_name": caption, "title": caption.title()}
    save_db()
    print(f"AUTO SAVED FROM CHANNEL: {caption}")

# ===== 3. START =====
@bot.message_handler(commands=['start'])
def start(m):
    bot.send_message(m.chat.id, "🎬 Welcome!\n\nSend any movie name.\nBot will search and give download if available in database.")

# ===== 4. USER SEARCH - MAIN LOGIC =====
@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_movie(m):
    if m.text.startswith('/'): return
    if m.from_user.id == ADMIN_ID and m.content_type!= 'text': return

    query = m.text.lower().strip()
    if len(query) < 2: return

    bot.send_chat_action(m.chat.id, 'typing')
    info = search_tmdb(query)

    if not info:
        bot.send_message(m.chat.id, f"❌ No info found for *{m.text}*", parse_mode="Markdown")
        return

    real_title = info.get('title') or info.get('name') or m.text
    title_lower = real_title.lower()
    overview = info.get('overview', '')[:200]
    rating = info.get('vote_average', 'N/A')
    year = (info.get('release_date') or info.get('first_air_date') or "")[:4]

    # Check if in Database
    found = None
    found_key = None
    for key, data in MOVIES_DB.items():
        if query in key or key in title_lower or title_lower in key:
            found = data
            found_key = key
            break

    markup = InlineKeyboardMarkup()

    if found:
        # MOVIE IS IN DATABASE - SHOW DOWNLOAD
        markup.row(InlineKeyboardButton("💾 DOWNLOAD NOW", callback_data=f"dl_{found['file_id']}"))
        markup.row(InlineKeyboardButton("▶️ Watch Trailer", url=f"https://www.youtube.com/results?search_query={urllib.parse.quote(real_title + ' trailer')}"))
        markup.row(InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={urllib.parse.quote(real_title)}"))
        markup.row(InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={urllib.parse.quote(real_title)}"))
        markup.row(InlineKeyboardButton("🎬 TMDB Info", url=f"https://www.themoviedb.org/search?query={urllib.parse.quote(real_title)}"))
        markup.row(InlineKeyboardButton("🔍 Google", url=f"https://www.google.com/search?q={urllib.parse.quote(real_title + ' movie')}"))
        markup.row(InlineKeyboardButton("📢 Request Movie", url="https://t.me/FSearch4ubot"))
        caption = f"🎬 *{real_title}* ({year})\n⭐ *Rating:* {rating}/10\n\n📝 {overview}...\n\n✅ *Download Available in Database*"
    else:
        # MOVIE NOT IN DATABASE - HIDE DOWNLOAD
        markup.row(InlineKeyboardButton("▶️ Watch Trailer", url=f"https://www.youtube.com/results?search_query={urllib.parse.quote(real_title + ' trailer')}"))
        markup.row(InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={urllib.parse.quote(real_title)}"))
        markup.row(InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={urllib.parse.quote(real_title)}"))
        markup.row(InlineKeyboardButton("🎬 TMDB Info", url=f"https://www.themoviedb.org/search?query={urllib.parse.quote(real_title)}"))
        markup.row(InlineKeyboardButton("🔍 Google", url=f"https://www.google.com/search?q={urllib.parse.quote(real_title + ' movie')}"))
        markup.row(InlineKeyboardButton("📢 Request Movie", url="https://t.me/FSearch4ubot"))
        caption = f"🎬 *{real_title}* ({year})\n⭐ *Rating:* {rating}/10\n\n📝 {overview}...\n\n❌ *Download Not Available* - Request it."

    poster = info.get('poster_path')
    try:
        if poster:
            bot.send_photo(m.chat.id, f"https://image.tmdb.org/t/p/w500{poster}", caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(m.chat.id, caption, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        print(e)
        bot.send_message(m.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    if c.data.startswith("dl_"):
        file_id = c.data.replace("dl_", "")
        try:
            bot.send_document(c.message.chat.id, file_id)
            bot.answer_callback_query(c.id, "✅ File Sent!")
        except:
            bot.answer_callback_query(c.id, "❌ File Error")

print(f"✅ BIG BOT STARTED - {len(MOVIES_DB)} Movies in DB")
bot.infinity_polling()
