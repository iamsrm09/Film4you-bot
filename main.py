import os
import threading
import logging
import json
from flask import Flask
import telebot
import requests
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return "Film4you Bot is Alive! ✅"

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_CHANNEL = -1004341107282
TMDB_KEY = os.getenv("TMDB_KEY") or os.getenv("TMDB_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)

DB_FILE = "movies.json"
movie_database = {}

def load_db():
    global movie_database
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                movie_database = json.load(f)
        except:
            movie_database = {}

def save_db():
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(movie_database, f)
    except Exception as e:
        logger.error(f"DB Save Error: {e}")

load_db()

@bot.channel_post_handler(content_types=['document', 'video', 'photo'])
def save_movie(message):
    file_name = ""
    if message.document:
        file_name = message.document.file_name or message.caption or ""
    elif message.video:
        file_name = message.video.file_name or message.caption or ""
    else:
        file_name = message.caption or ""
    if file_name:
        key = file_name.lower()
        movie_database[key] = message.message_id
        short = file_name.split('.')[0].lower().strip()
        if short:
            movie_database[short] = message.message_id
        save_db()
        logger.info(f"SAVED: {file_name} -> {message.message_id}")

def search_tmdb_movie(query):
    try:
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={query}"
        data = requests.get(url, timeout=15).json()
        results = data.get("results")
        if results:
            return results[0]
    except Exception as e:
        logger.error(f"TMDB Error: {e}")
    return None

def find_in_database(query):
    q = query.lower().strip()
    if q in movie_database:
        return movie_database[q]
    for name, msg_id in movie_database.items():
        if q in name:
            return msg_id
    return None

@bot.message_handler(commands=['start', 'help'])
def start_cmd(message):
    bot.send_message(message.chat.id, "🎬 *Film4you Bot Ready!*\n\nKoi bhi Movie ka naam bhejo.\nEx: KGF, Avengers, Pathaan", parse_mode="Markdown")

@bot.message_handler(commands=['trending'])
def trending_cmd(message):
    try:
        url = f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_KEY}"
        data = requests.get(url, timeout=15).json()
        movies = data.get("results", [])[:10]
        text = "🔥 *Trending Movies Today:*\n\n"
        for i, m in enumerate(movies, 1):
            text += f"{i}. {m.get('title')} - ⭐ {m.get('vote_average')}/10\n"
        bot.send_message(message.chat.id, text, parse_mode="Markdown")
    except:
        bot.send_message(message.chat.id, "Error aa gaya trending me.")

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    if not message.text or message.text.startswith('/'):
        return
    query = message.text.strip()
    if len(query) < 2:
        return
    bot.send_chat_action(message.chat.id, 'typing')
    db_msg_id = find_in_database(query)
    movie = search_tmdb_movie(query)
    if not movie:
        if db_msg_id:
            try:
                bot.copy_message(message.chat.id, DATABASE_CHANNEL, db_msg_id)
                return
            except Exception as e:
                logger.error(f"Direct send failed: {e}")
        bot.send_message(message.chat.id, f"❌ '{query}' nahi mili.")
        return
    title = movie.get('title')
    rating = movie.get('vote_average')
    date = movie.get('release_date', 'N/A')
    overview = (movie.get('overview') or 'Story available nahi hai.')[:450]
    poster_path = movie.get('poster_path')
    caption = f"🎬 *{title}*\n⭐ Rating: {rating}/10\n📅 Release: {date}\n\n📖 {overview}"
    if db_msg_id:
        caption += f"\n\n✅ *Download Available Hai!*"
    markup = InlineKeyboardMarkup()
    if db_msg_id:
        markup.row(InlineKeyboardButton("📥 DOWNLOAD NOW", callback_data=f"dl_{db_msg_id}"))
    markup.row(InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(title)}"))
    markup.row(InlineKeyboardButton("▶️ Trailer Dekho", url=f"https://www.youtube.com/results?search_query={quote_plus(title + ' trailer')}"))
    try:
        if poster_path:
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            bot.send_photo(message.chat.id, poster_url, caption=caption, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
def download_callback(call):
    try:
        msg_id = int(call.data.replace('dl_', ''))
        bot.copy_message(call.message.chat.id, DATABASE_CHANNEL, msg_id)
        bot.answer_callback_query(call.id, "File bhej diya! ✅")
    except Exception as e:
        logger.error(f"COPY FAILED: {e}")
        try:
            bot.forward_message(call.message.chat.id, DATABASE_CHANNEL, msg_id)
            bot.answer_callback_query(call.id, "File bhej diya! ✅")
        except Exception as e2:
            bot.send_message(call.message.chat.id, f"❌ Forward nahi ho raha. Bot ko channel -1004341107282 me Admin banao.\nError: {e2}")

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("Bot Starting...")
    bot.infinity_polling()
