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

# --- ENV Variables from Render ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_KEY = os.getenv("TMDB_KEY") or os.getenv("TMDB_TOKEN")

if not BOT_TOKEN or not TMDB_KEY:
    logger.error("BOT_TOKEN or TMDB_KEY missing in Render Environment Variables!")

bot = telebot.TeleBot(BOT_TOKEN)

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

@bot.message_handler(commands=['start', 'help'])
def start_cmd(message):
    bot.send_message(message.chat.id,
        "🎬 *Film4you Bot Ready!*\n\n"
        "Koi bhi Movie ka naam bhejo.\n"
        "Ex: KGF, Avengers, Pathaan\n\n"
        "Trending ke liye /trending bhejo",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['trending'])
def trending_cmd(message):
    try:
        url = f"https://api.themoviedb.org/3/trending/movie/day?api_key={TMDB_KEY}"
        data = requests.get(url, timeout=15).json()
        movies = data.get("results", [])[:10]
        if not movies:
            bot.send_message(message.chat.id, "Trending nahi mili.")
            return

        text = "🔥 *Trending Movies Today:*\n\n"
        for i, m in enumerate(movies, 1):
            text += f"{i}. {m.get('title')} - ⭐ {m.get('vote_average')}/10\n"
        text += "\nNaam bhejo details ke liye!"
        bot.send_message(message.chat.id, text, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, "Error aa gaya trending me.")

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    if not message.text or message.text.startswith('/'):
        return

    query = message.text.strip()
    if len(query) < 2:
        return

    bot.send_chat_action(message.chat.id, 'typing')
    movie = search_tmdb_movie(query)

    if not movie:
        bot.send_message(message.chat.id, f"❌ '{query}' nahi mili. Sahi naam likho.")
        return

    title = movie.get('title')
    rating = movie.get('vote_average')
    date = movie.get('release_date', 'N/A')
    overview = (movie.get('overview') or 'Story available nahi hai.')[:450]
    poster_path = movie.get('poster_path')

    caption = f"🎬 *{title}*\n⭐ Rating: {rating}/10\n📅 Release: {date}\n\n📖 {overview}"

    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(title)}"))
    markup.row(InlineKeyboardButton("▶️ Trailer Dekho", url=f"https://www.youtube.com/results?search_query={quote_plus(title + ' trailer')}"))

    try:
        if poster_path:
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            bot.send_photo(message.chat.id, poster_url, caption=caption, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Send Error: {e}")
        bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")

# --- Render ke liye Flask + Bot Thread ---
def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    logger.info("Bot Starting...")
    bot.infinity_polling()
