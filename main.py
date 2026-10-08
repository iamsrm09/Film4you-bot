import os, time, requests, json, re
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus

app = Flask('')
@app.route('/')
def home(): return "🎬 Bot is Live!"
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def keep_alive():
    Thread(target=run_flask, daemon=True).start()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_KEY = os.environ.get('TMDB_API_KEY')
DATABASE_CHANNEL_ID = -1004341107282

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
DB_FILE = "database.json"
CAP_FILE = "captions.json"

def load_db():
    if not os.path.exists(DB_FILE): return {}
    try:
        with open(DB_FILE,'r') as f: return json.load(f)
    except: return {}

def save_db(data):
    with open(DB_FILE,'w') as f: json.dump(data, f)

def load_caps():
    if not os.path.exists(CAP_FILE): return {}
    try:
        with open(CAP_FILE,'r') as f: return json.load(f)
    except: return {}

def save_caps(data):
    with open(CAP_FILE,'w') as f: json.dump(data, f, ensure_ascii=False)

def clean_name(text):
    if not text: return ""
    text = text.split('\n')[0]
    text = re.sub(r'http\S+|t\.me/\S+|@\w+', '', text)
    text = re.sub(r'Join.*|Search.*|More.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'1080p|720p|480p|2160p|4K|HDRip|WEB-DL|BluRay|ESub|x264|x265', '', text, flags=re.IGNORECASE)
    text = re.sub(r'S\d+|Season \d+|Part \d+|20\d{2}|19\d{2}', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^a-zA-Z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower().strip()

def get_tmdb(query):
    if not TMDB_KEY: return None
    q = clean_name(query)
    if len(q) < 2: q = query
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(q)}"
        r = requests.get(url, timeout=10).json()
        if not r.get('results'): return None
        item = None
        for x in r['results']:
            if x.get('media_type') in ['movie','tv']:
                item = x
                break
        if not item: return None
        mtype = item['media_type']
        mid = item['id']
        d = requests.get(f"https://api.themoviedb.org/3/{mtype}/{mid}?api_key={TMDB_KEY}", timeout=10).json()
        title = d.get('title') or d.get('name') or q
        poster_path = item.get('poster_path')
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        rating = round(d.get('vote_average',0),1)
        genres_list = [g['name'] for g in d.get('genres',[])][:2]
        genres = ", ".join(genres_list) if genres_list else "N/A"
        date = d.get('release_date') or d.get('first_air_date') or "N/A"
        year = date[:4] if len(date)>=4 else "N/A"
        runtime_val = d.get('runtime',0)
        if mtype == 'movie':
            runtime = f"{runtime_val//60}H {runtime_val%60}M" if runtime_val else "N/A"
        else:
            runtime = f"{d.get('number_of_seasons',1)} Seasons"
        story = d.get('overview','')[:700] or "N/A"
        seasons = d.get('seasons',[]) if mtype=='tv' else []
        return {"title":title,"year":year,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype,"seasons":seasons}
    except Exception as e:
        print(f"TMDB Error: {e}")
        return None

@bot.message_handler(content_types=['video', 'document'])
def save_handler(message):
    raw_caption = message.caption or ""
    if not raw_caption:
        bot.reply_to(message, "❌ Caption me movie name likho! 🎬")
        return
    file_id = message.video.file_id if message.video else message.document.file_id
    c_name = clean_name(raw_caption)
    if not c_name: c_name = raw_caption[:20].lower()

    db = load_db()
    if c_name not in db: db[c_name] = []
    db[c_name].append(file_id)
    save_db(db)

    caps = load_caps()
    caps[file_id] = raw_caption
    save_caps(caps)

    info = get_tmdb(raw_caption)
    thumb_path = None
    if info and info['poster']:
        try:
            resp = requests.get(info['poster'], timeout=15)
            thumb_path = f"/tmp/{file_id}.jpg"
            with open(thumb_path, 'wb') as f: f.write(resp.content)
        except: thumb_path = None

    if info:
        db_caption = f"{raw_caption}\n\n🎬 {info['title']} ({info['year']})\n⭐ {info['rating']}/10 | 🎭 {info['genres']}\n"
    else:
        db_caption = raw_caption

    try:
        if message.video:
            if thumb_path:
                with open(thumb_path, 'rb') as tf:
                    bot.send_video(DATABASE_CHANNEL_ID, file_id, thumb=tf, caption=db_caption)
            else:
                bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=db_caption)
        else:
            bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=db_caption)
        bot.reply_to(message, f"✅ Saved! 🎉\n🎬 Name: {c_name}\n🖼️ Thumb: {'Yes ✅' if thumb_path else 'No ❌'}\n📦 Total: {len(db[c_name])} Files")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Channel error: {e}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "🎬✨ *Film4you Bot Live!* ✨🎬\n\n🔍 Movie name bhejo search karne ke liye\n💾 Video bhejo caption ke saath save karne ke liye", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    query = message.text.strip()
    if len(query) < 2: return
    clean_q = clean_name(query)
    db = load_db()
    info = get_tmdb(query)

    found_key = None
    for saved_name in db.keys():
        if clean_q in saved_name or saved_name in clean_q:
            found_key = saved_name
            break
        if len(set(clean_q.split()) & set(saved_name.split())) >= 1 and len(clean_q) > 4:
            found_key = saved_name
            break

    if not found_key and info:
        tmdb_clean = clean_name(info['title'])
        for saved_name in db.keys():
            if tmdb_clean in saved_name or saved_name in tmdb_clean:
                found_key = saved_name
                break
