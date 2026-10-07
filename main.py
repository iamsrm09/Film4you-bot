import os
import requests
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# --- 1. FLASK FOR RENDER ---
app = Flask('')
@app.route('/')
def home(): return "Film4you Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# --- 2. CONFIG ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
# TMDB key ka naam kuch bhi ho sakta hai, sab check kar lenge
TMDB_KEY = os.environ.get('TMDB_API_KEY') or os.environ.get('MOVIE_API_KEY') or os.environ.get('TMDB_KEY') or os.environ.get('API_KEY')

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN missing in Render Environment")
if not TMDB_KEY:
    print("WARNING: TMDB_API_KEY missing, bot will use dummy data")

bot = telebot.TeleBot(BOT_TOKEN)

# --- 3. TMDB SEARCH FUNCTION ---
def get_movie_details(movie_name):
    try:
        # Search movie
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={movie_name}"
        res = requests.get(url).json()
        if not res.get('results'):
            return None

        movie = res['results'][0]
        movie_id = movie['id']

        # Get full details + videos for trailer
        detail_url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_KEY}&append_to_response=videos,credits"
        details = requests.get(detail_url).json()

        title = details.get('title', movie_name)
        year = (details.get('release_date') or 'N/A')[:4]
        rating = round(details.get('vote_average', 0), 1)
        overview = details.get('overview', 'Story not available.')[:700] + "..."
        poster_path = details.get('poster_path')
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else "https://i.imgur.com/3j3U2i8.jpeg"

        # Trailer link
        trailer_key = ""
        for vid in details.get('videos', {}).get('results', []):
            if vid['type'] == 'Trailer' and vid['site'] == 'YouTube':
                trailer_key = vid['key']
                break
        trailer_url = f"https://www.youtube.com/watch?v={trailer_key}" if trailer_key else f"https://www.youtube.com/results?search_query={title}+trailer"

        return {
            "title": title, "year": year, "rating": rating,
            "overview": overview, "poster": poster_url,
            "trailer": trailer_url, "id": movie_id
        }
    except Exception as e:
        print(f"TMDB Error: {e}")
        return None

# --- 4. WELCOME HANDLER FOR GROUPS ---
@bot.message_handler(content_types=['new_chat_members'])
def welcome_new(message):
    for new_user in message.new_chat_members:
        name = new_user.first_name
        text = (
            f"Hey {name}! 👋 Welcome to *{message.chat.title}* \n\n"
            f"🎬 Yaha movie ka naam bhejo, mai puri details dunga!\n"
            f"Example: `Avengers`, `Vinland Saga`\n\n"
            f"Bot by @Iamsrm0"
        )
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

# --- 5. MAIN MOVIE HANDLER ---
@bot.message_handler(commands=['start'])
def start_cmd(message):
    bot.send_message(
        message.chat.id,
        "🎬 *Welcome to Film4you Bot!* 🎬\n\n"
        "Bas koi bhi movie ka naam bhejo aur mai apko:\n"
        "⭐ Rating, Poster, Story\n"
        "▶️ Trailer, 📍 Where to Watch\n"
        "📥 Download Links dunga!\n\n"
        "Try karo: `KGF`, `Pushpa`, `Inception`",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: True)
def movie_handler(message):
    if message.text.startswith('/'): # ignore other commands
        if not message.text.startswith('/start'):
            return

    query = message.text.replace('/movie','').replace('/search','').replace('/start','').strip()
    if not query:
        query = "Vinland Saga" # default if only /start pressed

    # Typing...
    bot.send_chat_action(message.chat.id, 'typing')
    data = get_movie_details(query)

    if not data:
        bot.send_message(message.chat.id, f"❌ *{query}* nahi mila. Dusra naam try karo.", parse_mode="Markdown")
        return

    caption = (
        f"🎬 *{data['title']} ({data['year']})*\n"
        f"⭐ *Rating:* {data['rating']}/10 | *Powered by TMDB*\n\n"
        f"📝 *Story:*\n{data['overview']}\n\n"
        f"✅ *Status:* Details Found!\n"
        f"💡 *Request to:* @Iamsrm0"
    )

    # Buttons
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("▶️ Watch Trailer", url=data['trailer']),
        InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={data['title']}")
    )
    markup.add(
        InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={data['title']}"),
        InlineKeyboardButton("🎬 Full Details", url=f"https://www.themoviedb.org/movie/{data['id']}")
    )
    # Download Options - Search link
    markup.add(
        InlineKeyboardButton("📥 Filmyzilla Link", url=f"https://www.filmyzilla72.com/?s={data['title'].replace(' ', '+')}"),
        InlineKeyboardButton("📥 Cinevood Link", url=f"https://cinevood.com/?s={data['title'].replace(' ', '+')}")
    )

    try:
        bot.send_photo(message.chat.id, data['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

# --- 6. RUN ---
if __name__ == "__main__":
    keep_alive()
    print("Bot Starting...")
    bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
