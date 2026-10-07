import os
import time
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus

# --- Flask Server to Keep Bot Live on Render ---
app = Flask('')
@app.route('/')
def home():
    return "Film4you Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# --- Config ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_KEY = os.environ.get('TMDB_API_KEY') or os.environ.get('MOVIE_API_KEY')

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is missing")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def get_movie_data(query):
    """Fetch movie details and poster from TMDB"""
    try:
        if not TMDB_KEY:
            return {
                "title": query, "year": "2024", "rating": "8.5",
                "poster": None,
                "story": f"Search details and stream options found for {query}."
            }
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={quote_plus(query)}"
        res = requests.get(url, timeout=15).json()
        if not res.get('results'):
            return None

        m = res['results'][0]
        poster_url = f"https://image.tmdb.org/t/p/w500{m['poster_path']}" if m.get('poster_path') else None

        return {
            "title": m.get('title', query),
            "year": (m.get('release_date') or "N/A")[:4],
            "rating": round(m.get('vote_average', 0), 1) if m.get('vote_average') else "8.5",
            "poster": poster_url,
            "story": m.get('overview') or f"Details and streaming info available for {query}."
        }
    except Exception as e:
        print(f"TMDB Error: {e}")
        return None

@bot.message_handler(content_types=['new_chat_members'])
def welcome(message):
    for user in message.new_chat_members:
        bot.send_message(
            message.chat.id,
            f"Hey {user.first_name}! 👋 Welcome to {message.chat.title}\nSend any movie name 🎬",
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "🎬 *Film4you Bot is Live!* 🎬\n\nSend any movie name and I will give you poster and details.\nExample: `Rango`, `Avengers`, `KGF`",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: True)
def all_movies(message):
    query = message.text.replace('/start', '').strip()
    if not query or len(query) < 2:
        return

    bot.send_chat_action(message.chat.id, 'typing')
    data = get_movie_data(query)

    if not data:
        bot.send_message(message.chat.id, f"❌ No results found for *{query}*", parse_mode="Markdown")
        return

    caption = (
        f"🎬 *{data['title']} ({data['year']})*\n"
        f"⭐ *Rating: {data['rating']}/10*\n\n"
        f"📝 *Story:* {data['story'][:600]}\n\n"
        f"✅ *Details Found! Click below buttons for movie page.*"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🌐 Watch / Download Page", url=f"https://www.justwatch.com/in/search?q={quote_plus(query)}")
    )
    markup.add(
        InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(query)}+trailer"),
        InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(query)}")
    )
    markup.add(
        InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(query)}"),
        InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={quote_plus(query)}+movie")
    )

    try:
        if data['poster']:
            bot.send_photo(message.chat.id, data['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        print(f"Send Error: {e}")
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

if __name__ == "__main__":
    keep_alive()
    print("Removing webhook and starting polling...")
    try:
        bot.remove_webhook()
        time.sleep(2)
    except:
        pass
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Polling Error: {e}")
            time.sleep(5)
