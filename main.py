import os
import threading
import logging
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
DATABASE_CHANNEL = -1006053499724
TMDB_KEY = os.getenv("TMDB_KEY") or os.getenv("TMDB_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)

# --- Ye tumhara Database banega ---
movie_database = {}

@bot.channel_post_handler(content_types=['document', 'video'])
def save_movie(message):
    # Jab tum channel me movie daloge to bot yaad kar lega
    file_name = ""
    if message.document:
        file_name = message.document.file_name
    elif message.video:
        file_name = message.caption or message.video.file_name or ""
    else:
        file_name = message.caption or ""

    if file_name:
        key = file_name.lower()
        movie_database[key] = message.message_id
        # Short name bhi save karo
        short = file_name.split('.')[0].lower()
        movie_database[short] = message.message_id
        logger.info(f"Saved: {file_name} -> {message.message_id}")

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
    q = query.lower()
    for name, msg_id in movie_database.items():
        if q in name:
            return msg_id
    return None

@bot.message_handler(commands=['start', 'help'])
def start_cmd(message):
    bot.send_message(message.chat.id,
        "🎬 *Film4you Bot Ready!*\n\nKoi bhi Movie ka naam bhejo.\nEx: KGF, Avengers, Pathaan\n\nTrending ke liye /trending bhejo",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['trending'])
def trending_cmd(message):
    try:
        url = f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_KEY}"
        data = requests.get(url, timeout=15).json()
        movies = data.get("results", [])[:10]
        text = "🔥 *Trending Movies Today:*\n\n"
        for i, m in enumerate(movies, 1):
            text += f"{i}. {m.get('title')} - ⭐ {m.get('vote_average')}/10\n"
        text += "\nNaam bhejo download ke liye!"
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

    # 1. Pehle apne Channel Database me dhoondo
    db_msg_id = find_in_database(query)

    movie = search_tmdb_movie(query)
    if not movie:
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
        # Direct download link
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
        @bot.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
def download_callback(call):
    try:
        msg_id = int(call.data.replace('dl_', ''))
        logger.info(f"Trying to forward {msg_id} from {DATABASE_CHANNEL} to {call.message.chat.id}")
        bot.forward_message(call.message.chat.id, DATABASE_CHANNEL, msg_id)
        # Copy bhi try karo agar forward fail ho
    except Exception as e:
        logger.error(f"FORWARD FAILED: {e}")
        try:
            # Dusra tareeka - copy message
            bot.copy_message(call.message.chat.id, DATABASE_CHANNEL, msg_id)
            bot.answer_callback_query(call.id, "File bhej diya! ✅")
            return
        except Exception as e2:
            logger.error(f"COPY FAILED: {e2}")
            bot.send_message(call.message.chat.id, f"Error: Bot ko channel me Admin banao aur 'Post Message' ka permission do. Error: {e2}")
        return
    bot.answer_callback_query(call.id, "File bhej diya! ✅")
        bot.forward_message(call.message.chat.id, DATABASE_CHANNEL, msg_id)
        bot.answer_callback_query(call.id, "File bhej diya! ✅")
    except Exception as e:
        bot.answer_callback_query(call.id, "Error, Admin se contact karo.")
        logger.error(f"Download Error: {e}")

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("Bot Starting...")
    bot.infinity_polling()
