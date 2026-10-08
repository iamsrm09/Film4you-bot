import os, time, requests, json, re
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus

app = Flask('')
@app.route('/')
def home(): return "Bot is Live!"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def keep_alive(): Thread(target=run_flask, daemon=True).start()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_KEY = os.environ.get('TMDB_API_KEY')
DATABASE_CHANNEL_ID = -1004341107282

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
DB_FILE = "database.json"

def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE,'r') as f: return json.load(f)
    except: return {}
def save_db(data):
    with open(DB_FILE,'w') as f: json.dump(data, f)

# --- CLEAN MOVIE NAME FROM MESSY CAPTION ---
def clean_movie_name(text):
    if not text: return ""
    # Remove URLs
    text = re.sub(r'http\S+|t\.me/\S+|@\w+', '', text)
    # Remove Join For More etc
    text = re.sub(r'Join For More.*', '', text, flags=re.IGNORECASE)
    # Take only first line
    text = text.split('\n')[0]
    # Remove quality tags
    text = re.sub(r'\b(1080p|720p|480p|2160p|4K|HDRip|WEB-DL|BluRay|ESub|x264|x265|HEVC|AAC)\b', '', text, flags=re.IGNORECASE)
    # Remove year with extra spaces and keep only movie name
    # SpiderMan Brand New Day 2026 1080p -> SpiderMan Brand New Day
    text = re.sub(r'\b(19|20)\d{2}\b', '', text) # Remove year for search
    text = re.sub(r'\s+', ' ', text).strip()
    return text.strip()

def get_tmdb(query):
    if not TMDB_KEY: return None
    clean_q = clean_movie_name(query)
    if not clean_q: clean_q = query
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(clean_q)}"
        r = requests.get(url, timeout=10).json()
        if not r.get('results'): return None
        item = next((x for x in r['results'] if x.get('media_type') in ['movie','tv']), None)
        if not item: return None
        mtype = item['media_type']
        d = requests.get(f"https://api.themoviedb.org/3/{mtype}/{item['id']}?api_key={TMDB_KEY}", timeout=10).json()
        title = d.get('title') or d.get('name') or clean_q
        poster = f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get('poster_path') else None
        rating = round(d.get('vote_average',0),1)
        genres = ", ".join([g['name'] for g in d.get('genres',[])][:2]) or "N/A"
        date = d.get('release_date') or d.get('first_air_date') or "N/A"
        year = date[:4] if len(date)>=4 else "N/A"
        runtime = f"{d.get('runtime',0)//60}H {d.get('runtime',0)%60}M" if mtype=='movie' else f"{d.get('number_of_seasons',1)} Seasons"
        story = (d.get('overview','')[:800]) or "N/A"
        seasons = d.get('seasons',[]) if mtype=='tv' else []
        return {"title":title,"year":year,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype,"seasons":seasons, "clean_name": clean_q}
    except Exception as e:
        print("TMDB Error:", e)
        return None

# --- SAVE WITHOUT KEY SYSTEM ---
@bot.message_handler(content_types=['video', 'document'])
def save_handler(message):
    raw_caption = message.caption or ""
    if not raw_caption:
        bot.reply_to(message, "❌ Please add caption! Example: `Rango`")
        return

    clean_name = clean_movie_name(raw_caption)
    if not clean_name:
        clean_name = raw_caption.split('\n')[0][:30]

    file_id = message.video.file_id if message.video else message.document.file_id
    db_key = clean_name.lower().strip() # Use clean name as key, not full messy caption

    db = load_db()
    if db_key in db:
        if isinstance(db[db_key], list):
            db[db_key].append(file_id)
        else:
            db[db_key] = [db[db_key], file_id]
    else:
        db[db_key] = [file_id]

    save_db(db)
    count = len(db[db_key])

    bot.reply_to(message, f"🔍 Cleaned name: *{clean_name}*\nFetching TMDB...", parse_mode="Markdown")
    info = get_tmdb(raw_caption)

    if info:
        beautiful_caption = (
            f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()}\n"
            f"⭐ {info['rating']}/10 | 🎭 {info['genres']} | ⏱ {info['runtime']}\n"
            f"📅 {info['date']}\n\n"
            f"📝 {info['story']}\n\n"
            f"✅ @Film4you1bot"
        )
        poster_url = info['poster']
    else:
        # If TMDB not found, still use clean name
        beautiful_caption = f"🎬 *{clean_name}*\n\n✅ @Film4you1bot"
        poster_url = None

    try:
        if message.video:
            bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=beautiful_caption, parse_mode="Markdown")
        else:
            bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=beautiful_caption, parse_mode="Markdown")

        if poster_url:
            bot.send_photo(DATABASE_CHANNEL_ID, poster_url, caption=beautiful_caption, parse_mode="Markdown")

        bot.reply_to(message, f"✅ **Saved!**\n\nMovie Name Detected: *{clean_name}*\nTotal Parts: {count}\n\nSaved with caption:\n{beautiful_caption}", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Error: {e}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "🎬 Send movie name to search.\nSave: Send video with any caption, I will auto-detect name.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    query = message.text.strip()
    if len(query) < 2: return

    clean_q = clean_movie_name(query).lower()
    db = load_db()
    info = get_tmdb(query)

    # Find movie by name (fuzzy search, no key)
    found_key = None
    for db_name in db.keys():
        # Check if clean query is inside saved movie name or vice versa
        if clean_q in db_name or db_name in clean_q:
            found_key = db_name
            break
        # Also check word by word
        if any(word in db_name for word in clean_q.split() if len(word) > 3):
            found_key = db_name
            break

    if not info:
        markup = InlineKeyboardMarkup(row_width=1)
        if found_key:
            files = db[found_key] if isinstance(db[found_key], list) else [db[found_key]]
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH ({len(files)} Files)", callback_data=f"get_{found_key}"))
        else:
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH", callback_data=f"nof_{query}"))
        markup.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(query)}+trailer"), InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(query)}"))
        markup.row(InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(query)}"), InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={quote_plus(query)}"))
        bot.send_message(message.chat.id, f"🎬 *{query}*\n\nFile {'found' if found_key else 'not found'}", parse_mode="Markdown", reply_markup=markup)
        return

    caption = f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()}\n⭐ {info['rating']}/10 | 🎭 {info['genres']} | ⏱ {info['runtime']}\n\n📝 {info['story']}\n"
    markup = InlineKeyboardMarkup(row_width=1)

    if info['type'] == 'movie':
        if found_key:
            files = db[found_key] if isinstance(db[found_key], list) else [db[found_key]]
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH ({len(files)} Files)", callback_data=f"get_{found_key}"))
        else:
            # Try to find by TMDB title also
            tmdb_key = info['title'].lower()
            found_by_title = next((k for k in db if tmdb_key in k or k in tmdb_key), None)
            if found_by_title:
                files = db[found_by_title] if isinstance(db[found_by_title], list) else [db[found_by_title]]
                markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH ({len(files)} Files)", callback_data=f"get_{found_by_title}"))
            else:
                markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH", callback_data=f"nof_{query}"))
    else:
        for s in info['seasons']:
            sn = s.get('season_number')
            if sn == 0: continue
            s_key = next((k for k in db if f"s{sn:02d}" in k or f"season {sn}" in k), None)
            if s_key:
                markup.add(InlineKeyboardButton(f"📥 SEASON {sn}", callback_data=f"get_{s_key}"))
            else:
                markup.add(InlineKeyboardButton(f"📥 SEASON {sn}", callback_data=f"nof_{sn}"))

    markup.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"), InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}"))
    markup.row(InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(info['title'])}"), InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={quote_plus(info['title'])}"))

    if info['poster']:
        bot.send_photo(message.chat.id, info['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup
