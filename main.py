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
def home():
    return "Film4you Bot is Live!"

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    Thread(target=run_flask, daemon=True).start()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_KEY = os.environ.get('TMDB_API_KEY')
DATABASE_CHANNEL_ID = -1004341107282  # Your Database Channel ID

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN missing")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def get_tmdb_info(query):
    """Fetch movie/series info from TMDB for beautiful caption"""
    if not TMDB_KEY:
        return None
    try:
        search_url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(query)}"
        res = requests.get(search_url, timeout=15).json()
        if not res.get('results'):
            return None

        item = next((r for r in res['results'] if r.get('media_type') in ['movie', 'tv']), None)
        if not item:
            return None

        media_type = item['media_type']
        media_id = item['id']

        detail_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}?api_key={TMDB_KEY}"
        details = requests.get(detail_url, timeout=15).json()

        title = details.get('title') or details.get('name') or query
        poster = f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get('poster_path') else None
        rating = round(details.get('vote_average', 0), 1)
        genres = ", ".join([g['name'] for g in details.get('genres', [])][:3]) or "N/A"
        
        release_date = details.get('release_date') or details.get('first_air_date') or "N/A"
        year = release_date[:4] if release_date != "N/A" else "N/A"
        
        if media_type == 'movie':
            runtime_min = details.get('runtime', 0)
            runtime = f"{runtime_min // 60}H {runtime_min % 60}M" if runtime_min else "N/A"
        else:
            runtime = f"{details.get('number_of_seasons', 1)} Season(s)"

        story = details.get('overview', '')[:500] or "Story not available."

        return {
            "title": title,
            "year": year,
            "rating": rating,
            "genres": genres,
            "runtime": runtime,
            "release_date": release_date,
            "poster": poster,
            "story": story,
            "type": media_type
        }
    except Exception as e:
        print(f"TMDB Error: {e}")
        return None

# --- ADMIN: SAVE MOVIE TO DATABASE CHANNEL WITH TMDB CAPTION ---
@bot.message_handler(content_types=['video', 'document'])
def save_movie_handler(message):
    original_caption = message.caption
    if not original_caption:
        bot.reply_to(message, "⚠️ Please send video with caption as movie name.\nExample: `Rango` or `House of the Dragon S01`")
        return

    search_name = original_caption.strip()
    bot.reply_to(message, f"🔍 Fetching TMDB details for *{search_name}*...", parse_mode="Markdown")

    info = get_tmdb_info(search_name)

    if info:
        beautiful_caption = (
            f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()}\n"
            f"⭐ *Rating:* {info['rating']}/10\n"
            f"🎭 *Genres:* {info['genres']}\n"
            f"⏱ *Length:* {info['runtime']}\n"
            f"📅 *Release:* {info['release_date']}\n\n"
            f"📝 *Story:* {info['story']}\n\n"
            f"🔑 *Search Key:* `{search_name.lower()}`\n"
            f"✅ @Film4you1bot"
        )
    else:
        beautiful_caption = (
            f"🎬 *{search_name}*\n\n"
            f"🔑 *Search Key:* `{search_name.lower()}`\n"
            f"✅ @Film4you1bot"
        )

    # Forward/Save to Database Channel with new beautiful caption
    try:
        file_id = message.video.file_id if message.video else message.document.file_id
        if message.video:
            bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=beautiful_caption, parse_mode="Markdown")
        else:
            bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=beautiful_caption, parse_mode="Markdown")
        
        bot.reply_to(message, f"✅ *Saved Successfully to Database Channel!*\n\n{beautiful_caption}", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ *Failed to save.*\nMake @Film4you1bot ADMIN in database channel -1004341107282\n\nError: {e}", parse_mode="Markdown")

# --- USER: SEARCH AND GET MOVIE ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🎬 *Film4you Bot is Live!*\n\nSend any movie name to get details.\nAdmin can send video with caption to save.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'))
def search_handler(message):
    query = message.text.strip()
    info = get_tmdb_info(query)
    if not info:
        bot.send_message(message.chat.id, f"❌ No results for *{query}*", parse_mode="Markdown")
        return

    caption = (
        f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()}\n"
        f"⭐ *Rating:* {info['rating']}/10\n"
        f"🎭 *Genres:* {info['genres']}\n"
        f"⏱ *Length:* {info['runtime']}\n"
        f"📅 *Release Date:* {info['release_date']}\n\n"
        f"📝 *Story:* {info['story']}\n\n"
        f"✅ *File Available in Database Channel*"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📥 Download / Watch", url="https://t.me/c/4341107282"),
        InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer")
    )
    markup.add(
        InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(info['title'])}"),
        InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}")
    )

    try:
        if info['poster']:
            bot.send_photo(message.chat.id, info['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        print(e)
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

if __name__ == "__main__":
    keep_alive()
    try:
        bot.remove_webhook()
        time.sleep(2)
    except:
        pass
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Polling Error: {e}")
            time.sleep(5)
