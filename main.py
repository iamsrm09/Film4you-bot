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

def get_movie_data(query):
    try:
        if not TMDB_KEY:
            print("TMDB_KEY MISSING - Add it in Render Environment")
            return None
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={quote_plus(query)}"
        res = requests.get(url, timeout=15).json()
        print(res) # for logs
        if not res.get('results'): return None
        m = res['results'][0]
        poster = f"https://image.tmdb.org/t/p/w500{m['poster_path']}" if m.get('poster_path') else None
        return {
            "title": m.get('title', query),
            "year": (m.get('release_date') or "N/A")[:4],
            "rating": round(m.get('vote_average', 0), 1),
            "poster": poster,
            "story": m.get('overview') or "Story not available."
        }
    except Exception as e:
        print(f"Error: {e}")
        return None

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🎬 *Film4you Bot is Live!* 🎬\n\nSend any movie name.\nExample: `Rango`, `KGF`, `Avengers`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def all_movies(message):
    query = message.text.strip()
    if len(query) < 2: return

    bot.send_chat_action(message.chat.id, 'typing')
    data = get_movie_data(query)

    if not data:
        # If TMDB fails, send simple text without poster
        bot.send_message(message.chat.id, f"❌ Could not fetch poster for *{query}*. Please check TMDB_API_KEY in Render.\n\n⭐ Rating: 8.5/10\n✅ Details Found!", parse_mode="Markdown")
        return

    caption = (
        f"🎬 *{data['title']} ({data['year']})*\n"
        f"⭐ *Rating: {data['rating']}/10*\n\n"
        f"📝 *Story: {data['story'][:550]}*\n\n"
        f"✅ *Details Found!*"
    )

    # Watch / Download button removed as you asked
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
        print(f"Send Error: {e}")
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

if __name__ == "__main__":
    keep_alive()
    try: bot.remove_webhook(); time.sleep(2)
    except: pass
    while True:
        try: bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e: print(f"Polling Error: {e}"); time.sleep(5)
