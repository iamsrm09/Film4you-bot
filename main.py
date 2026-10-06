import os, telebot, requests, threading, urllib.parse
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# Keep bot alive
app = Flask('')
@app.route('/')
def home(): return "Film4you Bot Running - All Features OK"
threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8099)).start()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
TMDB_KEY = os.environ.get("TMDB_KEY")
DOWNLOAD_SITE = os.environ.get("DOWNLOAD_SITE") or "https://t.me/FSearch4ubot"

bot = telebot.TeleBot(BOT_TOKEN)

# --- TMDB Functions ---
def tmdb_get(path, params={}):
    params['api_key'] = TMDB_KEY
    try:
        r = requests.get(f"https://api.themoviedb.org/3{path}", params=params, timeout=10)
        return r.json()
    except:
        return {}

def get_trailer(movie_id, mtype="movie"):
    data = tmdb_get(f"/{mtype}/{movie_id}/videos")
    for v in data.get('results', []):
        if v['type'] == 'Trailer' and v['site'] == 'YouTube':
            return f"https://youtu.be/{v['key']}"
    return None

def search_best(query):
    # 1. Movie pehle dhoondo
    mov = tmdb_get("/search/movie", {"query": query})
    if mov.get('results'):
        mov['results'][0]['_type'] = 'movie'
        return mov['results'][0]
    # 2. Nahi mila to Web Series dhoondo
    tv = tmdb_get("/search/tv", {"query": query})
    if tv.get('results'):
        tv['results'][0]['_type'] = 'tv'
        return tv['results'][0]
    return None

# --- Welcome ---
@bot.message_handler(content_types=['new_chat_members'])
def welcome(m):
    for u in m.new_chat_members:
        if u.id == bot.get_me().id:
            bot.send_message(m.chat.id, "Thanks for adding me! Movie naam bhejo, mai sab dunga.")
            continue
        bot.send_message(m.chat.id, f"🎉 Welcome {u.first_name}!\n📽️ Film4you me swagat hai!\n🎬 Koi bhi Movie/Series ka naam likho.")

@bot.message_handler(commands=['start','help'])
def start(m):
    bot.reply_to(m, "🎬 *Film4you Bot*\n\nMovie ya Web Series ka naam bhejo\nExample: `KGF, Mirzapur, Avengers`\n\nMai dunga:\n✅ Poster\n✅ Trailer\n✅ Release Date\n✅ Rating\n✅ Download\n✅ Where to Watch", parse_mode="Markdown")

# --- Main Search ---
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle(m):
    if not m.text or m.text.startswith('/'): return
    text = m.text.strip()
    if len(text) < 2 or len(text) > 60: return
    if 'http' in text: return

    item = search_best(text)
    if not item:
        return

    title = item.get('title') or item.get('name')
    is_movie = item['_type'] == 'movie'
    release_date = item.get('release_date') or item.get('first_air_date') or "N/A"
    year = release_date[:4] if len(release_date) >= 4 else "N/A"
    rating = item.get('vote_average', 0)
    overview = item.get('overview', 'Story not available.')[:400]
    poster = item.get('poster_path')

    # Trailer nikalo
    trailer_url = get_trailer(item['id'], item['_type'])

    # --- BUTTONS ---
    markup = InlineKeyboardMarkup()

    # Download button - Tumhare DOWNLOAD_SITE Secret se
    download_link = f"{DOWNLOAD_SITE}?start={urllib.parse.quote(title)}" if "t.me" in DOWNLOAD_SITE else DOWNLOAD_SITE
    markup.row(InlineKeyboardButton("💾 DOWNLOAD", url=download_link))

    if trailer_url:
        markup.row(InlineKeyboardButton("▶️ TRAILER", url=trailer_url))
    else:
        yt_search = f"https://www.youtube.com/results?search_query={urllib.parse.quote(title + ' trailer')}"
        markup.row(InlineKeyboardButton("▶️ TRAILER (YouTube)", url=yt_search))

    # Where to Watch
    ott_link = f"https://www.justwatch.com/in/search?q={urllib.parse.quote(title)}"
    markup.row(InlineKeyboardButton("📍 WHERE TO WATCH (OTT)", url=ott_link))

    google_link = f"https://www.google.com/search?q={urllib.parse.quote(title + ' movie')}"
    markup.row(InlineKeyboardButton("🔍 MORE INFO (Google)", url=google_link))

    # --- CAPTION ---
    type_icon = "🎬 MOVIE" if is_movie else "📺 WEB SERIES"
    cap = f"""
{type_icon}: *{title}*

📅 *Release Date:* {release_date}
⭐ *Rating:* {rating}/10
🎭 *Type:* {'Movie' if is_movie else 'Web Series'}
📆 *Year:* {year}

📖 *Story:*
_{overview}..._

🔎 *You Searched:* `{text}`
"""

    try:
        if poster:
            bot.send_photo(m.chat.id, f"https://image.tmdb.org/t/p/w500{poster}", caption=cap, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(m.chat.id, cap, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        print(e)
        try:
            bot.send_message(m.chat.id, cap, parse_mode="Markdown", reply_markup=markup)
        except: pass

print("✅ Bot Started with Trailer + Release Date + Download + OTT")
bot.infinity_polling()
