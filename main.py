import os
import re
from threading import Thread
from flask import Flask, render_template_string
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
import time

# ---------------------------------------------------------
# 1. FLASK WEB APP & MOVIE DATABASE SETUP
# ---------------------------------------------------------
app = Flask(__name__)

# Replit/Domain URL (Apna Replit URL yahan badal sakte hain)
DOMAIN_URL = os.environ.get('DOMAIN_URL', 'https://telegram-movie-bot--imshahrun.replit.app')

# Sample Movie Database
MOVIES_DB = {
    101: {
        "title": "Drishyam 2",
        "slug": "drishyam-2",
        "poster": "https://image.tmdb.org/t/p/w500/v1L19cst2N8fR19aU44uG4oJ66S.jpg",
        "rating": "8.5/10",
        "genre": "Drama / Thriller",
        "year": "2022",
        "story:"
        "story": "Pushpa Raj continues to rule the red sandalwood smuggling market while facing aggressive opposition from his rivals and law enforcement.",
        "download_720p": "https://example.com/download/pushpa2-720p",
        "download_1080p": "https://example.com/download/pushpa2-1080p"
    },
    102: {
        "title": "K.G.F: Chapter 2",
        "slug": "kgf-chapter-2",
        "poster": "https://image.tmdb.org/t/p/w500/bkA11x3IAt4BipH3mQk851K00Jg.jpg",
        "rating": "8.4/10",
        "genre": "Action / Crime",
        "year": "2022",
        "story": "In the blood-soaked Kolar Gold Fields, Rocky's name strikes fear into his foes while he battles government troops and rivals.",
        "download_720p": "https://example.com/download/kgf2-720p",
        "download_1080p": "https://example.com/download/kgf2-1080p"
    }
}

# Web Home Route
@app.route('/')
def home():
    return "Film4you Bot & Web Server is Live!"

# Dynamic Web Movie Page Route (HTML Display)
@app.route('/movie/<int:movie_id>/<string:movie_slug>')
def get_movie_page(movie_id, movie_slug):
    movie = MOVIES_DB.get(movie_id)
    
    # Check if movie exists and slug matches
    if not movie or movie['slug'] != movie_slug:
        return "<h1>404 - Movie Not Found</h1>", 404

    # HTML Web Page Template
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{{ movie.title }} - Film4you</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #121212; color: #ffffff; margin: 0; padding: 20px; }
            .container { max-width: 700px; margin: 30px auto; background: #1e1e1e; padding: 25px; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.6); text-align: center; }
            .poster { width: 100%; max-width: 320px; border-radius: 10px; margin-bottom: 20px; }
            h1 { color: #e50914; margin-bottom: 5px; }
            .meta { color: #aaa; font-size: 14px; margin-bottom: 15px; }
            .story { line-height: 1.6; text-align: left; background: #2a2a2a; padding: 15px; border-radius: 8px; margin-bottom: 25px; }
            .btn { display: inline-block; background-color: #e50914; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 5px; transition: 0.3s; }
            .btn:hover { background-color: #b80710; }
        </style>
    </head>
    <body>
        <div class="container">
            <img src="{{ movie.poster }}" alt="{{ movie.title }}" class="poster">
            <h1>{{ movie.title }}</h1>
            <div class="meta">⭐ {{ movie.rating }} | {{ movie.genre }} | {{ movie.year }}</div>
            <div class="story">
                <strong>Storyline:</strong><br>
                {{ movie.story }}
            </div>
            <h3>Download Links:</h3>
            <a href="{{ movie.download_720p }}" class="btn" target="_blank">📥 Download 720p HD</a>
            <a href="{{ movie.download_1080p }}" class="btn" target="_blank">📥 Download 1080p Full HD</a>
        </div>
    </body>
    </html>
    """
    return render_template_string(html_content, movie=movie)

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# ---------------------------------------------------------
# 2. TELEGRAM BOT SETUP
# ---------------------------------------------------------
BOT_TOKEN = os.environ.get('BOT_TOKEN')
DOMAIN_URL = os.environ.get('DOMAIN_URL', 'http://127.0.0.1:8080')  # Apna Replit / Domain URL yahan set karein

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN missing")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

def create_slug(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    return re.sub(r'[\s_-]+', '-', text)

# Welcome Handler
@bot.message_handler(content_types=['new_chat_members'])
def welcome(message):
    for user in message.new_chat_members:
        bot.send_message(
            message.chat.id, 
            f"Hey {user.first_name} 👋 Welcome to {message.chat.title}!\nMovie ka naam bhejo 🎬", 
            parse_mode="Markdown"
        )

# Start Command
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id, 
        "🎬 *Film4you Bot Live Hai!*\n\nKoi bhi movie ka naam bhejo.\nExample: *Pushpa* ya *KGF*", 
        parse_mode="Markdown"
    )

# All Movies Search Handler
@bot.message_handler(func=lambda m: True)
def all_movies(message):
    query = message.text.replace('/start','').replace('/movie','').strip()
    if not query:
        return start(message)
    
    # Database Search
    matched_movie_id = None
    matched_movie = None

    for m_id, m_data in MOVIES_DB.items():
        if query.lower() in m_data['title'].lower():
            matched_movie_id = m_id
            matched_movie = m_data
            break

    # Direct Web Link / Slug Generator
    if matched_movie:
        movie_title = matched_movie['title']
        rating = matched_movie['rating']
        story = matched_movie['story']
        poster_url = matched_movie['poster']
        movie_web_url = f"{DOMAIN_URL}/movie/{matched_movie_id}/{matched_movie['slug']}"
    else:
        # Fallback agar movie DB me match na ho
        query_slug = create_slug(query)
        movie_title = query.title()
        rating = "8.5/10"
        story = f"Search details and stream options found for {query}."
        poster_url = "https://via.placeholder.com/500x750.png?text=Movie+Poster"
        movie_web_url = f"{DOMAIN_URL}/movie/101/pushpa-2-the-rule"

    caption = (
        f"🎬 *{movie_title}*\n"
        f"⭐ *Rating:* {rating}\n\n"
        f"📝 *Story:* {story}\n\n"
        f"✅ *Details Found! Below button se movie page par jayein.*"
    )

    markup = InlineKeyboardMarkup(row_width=2)
    
    # Primary Button: Dynamic HTML Web Page Link
    markup.add(
        InlineKeyboardButton("🌐 Watch / Download Page"https://www.filmyzilla72.com/('/movie/<int:movie_id>/<string:movie_slug>')
def get_movie(movie_id, movie_slug):
    return f"Movie ID: {movie_id}, Slug: {movie_slug}")
    )
    markup.add(
        InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={query}+trailer"),
        InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={query}")
    )
    markup.add(
        InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={query}"),
        InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={query}+movie")
    )

    try:
        # Telegram Message me Photo + Caption Bhejega
        bot.send_photo(
            message.chat.id, 
            photo=poster_url, 
            caption=caption, 
            parse_mode="Markdown", 
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error sending photo message: {e}")
        # Poster load na hone par plain message fallback
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

# ---------------------------------------------------------
# 3. BOT RUNNER & POLLING
# ---------------------------------------------------------
if __name__ == "__main__":
    keep_alive()
    print("Removing webhook and starting polling...")
    try:
        bot.remove_webhook()
        time.sleep(2)
    except Exception as e:
        print(f"Webhook remove note: {e}")

    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)
