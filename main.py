import os
import time
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus

app = Flask('')
@app.route('/')
def home(): return "Film4you Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_KEY = os.environ.get('TMDB_API_KEY') or os.environ.get('MOVIE_API_KEY')
if not BOT_TOKEN: raise SystemExit("BOT_TOKEN missing")
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def get_full_movie_data(query):
    try:
        if not TMDB_KEY:
            return None

        # 1. Search Movie
        search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={quote_plus(query)}"
        search_res = requests.get(search_url, timeout=10).json()
        if not search_res.get('results'): return None

        movie = search_res['results'][0]
        movie_id = movie['id']

        # 2. Get Details (for Runtime, Genres, Release Date)
        detail_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_KEY}"
        details = requests.get(detail_url, timeout=10).json()

        # 3. Get Cast (for Starcast)
        cast_url = f"https://api.themoviedb.org/3/movie/{movie_id}/credits?api_key={TMDB_KEY}"
        cast_res = requests.get(cast_url, timeout=10).json()
        cast_list = [c['name'] for c in cast_res.get('cast', [])[:5]] # Top 5 cast
        starcast = ", ".join(cast_list) if cast_list else "N/A"

        genres = ", ".join([g['name'] for g in details.get('genres', [])]) or "N/A"
        runtime_min = details.get('runtime', 0)
        runtime = f"{runtime_min // 60} Hrs {runtime_min % 60} Mins" if runtime_min else "N/A"

        poster = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie.get('poster_path') else None

        return {
            "title": details.get('title', query),
            "year": (details.get('release_date') or "N/A")[:4],
            "release_date": details.get('release_date', 'N/A'),
            "rating": round(details.get('vote_average', 0), 1),
            "genres": genres,
            "runtime": runtime,
            "starcast": starcast,
            "poster": poster,
            "story": details.get('overview') or movie.get('overview') or "Story not available."
        }
    except Exception as e:
        print(f"TMDB Error: {e}")
        return None

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🎬 *Film4you Bot is Live!*\n\nSend any movie name.\nExample: `Vadala`, `Rango`, `KGF`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def all_movies(message):
    query = message.text.strip()
    if len(query) < 2: return

    bot.send_chat_action(message.chat.id, 'typing')
    data = get_full_movie_data(query)

    if not data:
        bot.send_message(message.chat.id, f"❌ No results for *{query}*. Check TMDB_API_KEY in Render.", parse_mode="Markdown")
        return

    # New Upgraded Card like your screenshot
    caption = (
        f"🎬 *{data['title']} ({data['year']})*\n"
        f"⭐ *Rating:* {data['rating']}/10\n"
        f"🎭 *Genres:* {data['genres']}\n"
        f"⏱ *Length:* {data['runtime']}\n"
        f"📅 *Release Date:* {data['release_date']}\n"
        f"🌟 *Starcast:* {data['starcast']}\n\n"
        f"📝 *Story:* {data['story'][:500]}\n\n"
        f"✅ *Details Found!*"
    )

    markup = InlineKeyboardMarkup(row_width=2)
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
        print(e)
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

if __name__ == "__main__":
    keep_alive()
    try: bot.remove_webhook(); time.sleep(2)
    except: pass
    while True:
        try: bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e: print(e); time.sleep(5)
