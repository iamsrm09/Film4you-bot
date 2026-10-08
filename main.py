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
CAPTION_FILE = "captions.json"

def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE,'r') as f: return json.load(f)
    except: return {}

def save_db(data):
    with open(DB_FILE,'w') as f: json.dump(data, f)

def load_captions():
    if not os.path.exists(CAPTION_FILE): return {}
    try:
        with open(CAPTION_FILE,'r') as f: return json.load(f)
    except: return {}

def save_captions(data):
    with open(CAPTION_FILE,'w') as f: json.dump(data, f, ensure_ascii=False)

# --- CLEAN NAME FROM ANY MESSY CAPTION ---
def clean_movie_name(text):
    if not text: return ""
    text = text.split('\n')[0] # Only first line
    text = re.sub(r'http\S+|t\.me/\S+|@\w+', '', text) # Remove links
    text = re.sub(r'Join.*|Search.*|More.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(1080p|720p|480p|2160p|4K|HDRip|WEB-DL|BluRay|ESub|x264|x265|HEVC|AAC|Hindi|English|Dual)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\bS\d+|Season \d+|Part \d+\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(19|20)\d{2}\b', '', text) # Remove year for matching
    text = re.sub(r'[^a-zA-Z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower().strip()

def get_tmdb(query):
    if not TMDB_KEY: return None
    q = clean_movie_name(query)
    if len(q) < 2: q = query
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(q)}"
        r = requests.get(url, timeout=10).json()
        if not r.get('results'): return None
        item = next((x for x in r['results'] if x.get('media_type') in ['movie','tv']), None)
        if not item: return None
        mtype = item['media_type']
        d = requests.get(f"https://api.themoviedb.org/3/{mtype}/{item['id']}?api_key={TMDB_KEY}", timeout=10).json()
        title = d.get('title') or d.get('name') or q
        poster = f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get('poster_path') else None
        rating = round(d.get('vote_average',0),1)
        genres = ", ".join([g['name'] for g in d.get('genres',[])][:2]) or "N/A"
        date = d.get('release_date') or d.get('first_air_date') or "N/A"
        year = date[:4] if len(date)>=4 else "N/A"
        runtime = f"{d.get('runtime',0)//60}H {d.get('runtime',0)%60}M" if mtype=='movie' else f"{d.get('number_of_seasons',1)} Seasons"
        story = (d.get('overview','')[:700]) or "N/A"
        seasons = d.get('seasons',[]) if mtype=='tv' else []
        return {"title":title,"year":year,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype,"seasons":seasons}
    except Exception as e:
        print(e)
        return None

# --- SAVE: NO KEY, ONLY MOVIE NAME ---
@bot.message_handler(content_types=['video', 'document'])
def save_handler(message):
    raw_caption = message.caption or ""
    if not raw_caption:
        bot.reply_to(message, "❌ Caption me movie name likho!")
        return

    file_id = message.video.file_id if message.video else message.document.file_id
    clean_name = clean_movie_name(raw_caption)
    if not clean_name:
        clean_name = raw_caption[:20].lower()

    # Database: clean_name -> list of file_ids
    db = load_db()
    if clean_name not in db:
        db[clean_name] = []
    db[clean_name].append(file_id)
    save_db(db)

    # Save original caption for this file_id
    caps = load_captions()
    caps[file_id] = raw_caption # Jo database me caption hai wahi save
    save_captions(caps)

    info = get_tmdb(raw_caption)

    # --- THUMBNAIL CHANGE LOGIC ---
    thumb_path = None
    if info and info['poster']:
        try:
            # Download TMDB poster as thumbnail
            resp = requests.get(info['poster'], timeout=15)
            thumb_path = f"/tmp/{file_id}.jpg"
            with open(thumb_path, 'wb') as f:
                f.write(resp.content)
        except:
            thumb_path = None

    # Caption jo database channel me jayega - AAPKA ORIGINAL CAPTION + TMDB INFO
    if info:
        db_caption = f"{raw_caption}\n\n🎬 {info['title']} ({info['year']})\n⭐ {info['rating']}/10 | {info['genres']}\n📝 {info['story'][:300]}..."
    else:
        db_caption = raw_caption

    try:
        # Send to Database Channel WITH THUMBNAIL CHANGED
        if message.video:
            if thumb_path:
                with open(thumb_path, 'rb') as thumb_file:
                    bot.send_video(DATABASE_CHANNEL_ID, file_id, thumb=thumb_file, caption=db_caption)
            else:
                bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=db_caption)
        else:
            bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=db_caption)

        bot.reply_to(message, f"✅ Saved!\n\nDetected Name: `{clean_name}`\nOriginal Caption Saved: Yes\nThumbnail Changed: {'Yes' if thumb_path else 'No (TMDB not found)'}\nTotal files for this movie: {len(db[clean_name])}")

    except Exception as e:
        bot.reply_to(message, f"⚠️ Saved locally but channel error: {e}\nMake bot ADMIN in channel")

@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "🎬 Bot Ready!\nJust send video with any caption, I will auto detect name and change thumbnail.")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    query = message.text.strip()
    if len(query) < 2: return

    clean_q = clean_movie_name(query)
    db = load_db()
    caps = load_captions()
    info = get_tmdb(query)

    # --- FIND MOVIE BY NAME (FUZZY, NO KEY) ---
    found_key = None
    for saved_name in db.keys():
        if clean_q in saved_name or saved_name in clean_q:
            found_key = saved_name
            break
        # Check if 2 words match (for series)
        q_words = set(clean_q.split())
        s_words = set(saved_name.split())
        if len(q_words & s_words) >= 2:
            found_key = saved_name
            break
        if len(q_words & s_words) >= 1 and len(clean_q) > 5:
            found_key = saved_name
            break

    # If not found by cleaned name, try TMDB title
    if not found_key and info:
        tmdb_clean = clean_movie_name(info['title'])
        for saved_name in db.keys():
            if tmdb_clean in saved_name or saved_name in tmdb_clean:
                found_key = saved_name
                break

    if not info:
        markup = InlineKeyboardMarkup(row_width=1)
        if found_key:
            files = db[found_key]
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH ({len(files)} Files)", callback_data=f"get_{found_key}"))
        else:
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH", callback_data=f"nof_{query}"))
        markup.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(query)}+trailer"), InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(query)}"))
        markup.row(InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(query)}"), InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={quote_plus(query)}"))
        bot.send_message(message.chat.id, f"🎬 *{query}*", parse_mode="Markdown", reply_markup=markup)
        return

    caption = f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()}\n⭐ {info['rating']}/10 | 🎭 {info['genres']} | ⏱ {info['runtime']}\n\n📝 {info['story']}\n"
    markup = InlineKeyboardMarkup(row_width=1)

    if info['type'] == 'movie':
        if found_key:
            files = db[found_key]
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH ({len(files)} Files)", callback_data=f"get_{found_key}"))
        else:
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH", callback_data=f"nof_{query}"))
    else:
        # SERIES: Search any way name written
        for s in info['seasons']:
            sn = s.get('season_number')
            if sn == 0: continue
            # Find season file by series name
            s_key = None
            for saved_name in db.keys():
                if clean_q in saved_name or info['title'].lower() in saved_name:
                    if f"s{sn:02d}" in saved_name or f"season {sn}" in saved_name or f"s{sn}" in saved_name or clean_q == saved_name:
                        s_key = saved_name
                        break
            if not s_key:
                # Fallback: any file with series name
                for saved_name in db.keys():
                    if clean_movie_name(info['title']) in saved_name:
                        s_key = saved_name
                        break

            if s_key:
                markup.add(InlineKeyboardButton(f"📥 SEASON {sn}", callback_data=f"get_{s_key}"))
            else:
                markup.add(InlineKeyboardButton(f"📥 SEASON {sn}", callback_data=f"nof_{sn}"))

    markup.row(InlineKeyboardButton("
