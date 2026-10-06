import os, threading, logging, json
from flask import Flask
import telebot, requests
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus
from PIL import Image
import io

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot Alive"

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_CHANNEL = -1004341107282
TMDB_KEY = os.getenv("TMDB_KEY") or os.getenv("TMDB_TOKEN")
ADMIN_ID = None

bot = telebot.TeleBot(BOT_TOKEN)

DB_FILE = "movies.json"
movie_db = {}
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, 'r') as f:
            movie_db = json.load(f)
    except: pass

def save_db():
    with open(DB_FILE, 'w') as f:
        json.dump(movie_db, f)

def search_tmdb(query):
    try:
        r = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={query}", timeout=15).json()
        if r.get("results"): return r["results"][0]
    except: pass
    return None

def find_file(query):
    q = query.lower()
    if q in movie_db: return movie_db[q]
    for name, mid in movie_db.items():
        if q in name or name in q:
            return mid
    return None

# --- ONLY THIS PART CHANGED FOR THUMBNAIL + DESCRIPTION ---
@bot.message_handler(content_types=['document', 'video'])
def handle_file(message):
    raw_name = message.caption or (message.document.file_name if message.document else "video")
    clean_name = raw_name.split('.')[0].replace('_',' ').replace('-',' ').strip()

    tmdb = search_tmdb(clean_name)

    try:
        thumb_path = None
        final_caption = f"🎬 {raw_name}" # Default caption if TMDB not found

        if tmdb:
            title = tmdb.get('title')
            rating = tmdb.get('vote_average')
            date = tmdb.get('release_date','')
            overview = tmdb.get('overview','')[:800]
            final_caption = f"🎬 *{title}*\n⭐ {rating}/10 | 📅 {date}\n\n{overview}"

            # Thumbnail banane ke liye poster download
            poster = tmdb.get('poster_path')
            if poster:
                try:
                    url = f"https://image.tmdb.org/t/p/w500{poster}"
                    data = requests.get(url, timeout=20).content
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                    img.thumbnail((320, 320))
                    img.save("thumb.jpg", "JPEG", quality=80)
                    thumb_path = "thumb.jpg"
                except:
                    thumb_path = None

        thumb_file = open(thumb_path, "rb") if thumb_path else None

        # File wahi hai, bas thumb + caption TMDB wala
        if message.document:
            sent = bot.send_document(DATABASE_CHANNEL, message.document.file_id, thumb=thumb_file, caption=final_caption, parse_mode="Markdown")
        else:
            sent = bot.send_video(DATABASE_CHANNEL, message.video.file_id, thumb=thumb_file, caption=final_caption, parse_mode="Markdown", supports_streaming=True)

        if thumb_file:
            thumb_file.close()
            if os.path.exists(thumb_path):
                os.remove(thumb_path)

        movie_db[raw_name.lower()] = sent.message_id
        movie_db[clean_name.lower()] = sent.message_id
        save_db()

        bot.reply_to(message, f"✅ Saved: {clean_name}\nNow download will show TMDB Thumbnail + Description.")

    except Exception as e:
        bot.reply_to(message, f"❌ Failed: {e}")

@bot.message_handler(commands=['start','help','db'])
def cmds(message):
    if message.text.startswith('/db'):
        if not movie_db:
            bot.send_message(message.chat.id, "Database is empty. Send me a movie file directly.")
        else:
            txt = "Saved Movies:\n"
            for k in list(movie_db.keys())[:30]:
                txt += f"- {k}\n"
            bot.send_message(message.chat.id, txt)
        return
    bot.send_message(message.chat.id, "🎬 Film4you Ready!\nSend any movie name.\n\nTo add a movie, send me a video/file directly with the movie name in caption.")

@bot.message_handler(func=lambda m: True)
def search_handle(message):
    if not message.text or message.text.startswith('/'): return
    query = message.text.strip()
    bot.send_chat_action(message.chat.id, 'typing')
    file_id = find_file(query)
    tmdb = search_tmdb(query)
    if not tmdb:
        if file_id:
            bot.copy_message(message.chat.id, DATABASE_CHANNEL, file_id)
            return
        bot.send_message(message.chat.id, f"❌ '{query}' not found.")
        return
    title = tmdb.get('title')
    caption = f"🎬 *{title}*\n⭐ {tmdb.get('vote_average')}/10\n📅 {tmdb.get('release_date')}\n\n{tmdb.get('overview','')[:400]}"
    markup = InlineKeyboardMarkup()
    if file_id:
        caption += "\n\n✅ Download Available!"
        markup.row(InlineKeyboardButton("📥 DOWNLOAD NOW", callback_data=f"dl_{file_id}"))
    else:
        caption += "\n\n❌ File for this movie is not added yet."
    markup.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(title+' trailer')}"))
    poster = tmdb.get('poster_path')
    if poster:
        bot.send_photo(message.chat.id, f"https://image.tmdb.org/t/p/w500{poster}", caption=caption, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
def dl(call):
    try:
        mid = int(call.data.split('_')[1])
        # Yahi se download hota hai - ab isme TMDB wala thumb + description ayega
        bot.copy_message(call.message.chat.id, DATABASE_CHANNEL, mid)
        bot.answer_callback_query(call.id, "File sent ✅")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {e}")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling()
