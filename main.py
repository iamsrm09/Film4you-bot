import os, time, requests, json, re, queue
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus
from pymongo import MongoClient

MONGO_URL = os.environ.get('MONGO_URL')
TMDB_CACHE = {}

if MONGO_URL:
    client = MongoClient(MONGO_URL)
    mongo_db = client['film4you']
    movies_col = mongo_db['movies']
    caps_col = mongo_db['captions']
    print("Mongo Connected!")
else:
    client = None

app = Flask('')
@app.route('/')
def home():
    return "Bot Live ✅"
def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def keep_alive():
    Thread(target=run_flask, daemon=True).start()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_KEY = os.environ.get('TMDB_API_KEY')
DATABASE_CHANNEL_ID = -1004341107282
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

CHANNEL_QUEUE = queue.Queue()
ALBUM_CACHE = {}
PROCESSED = set()
SEARCH_CACHE = {}
FILE_CACHE = {}
PAGE_SIZE = 5

def is_duplicate(msg_id):
    if msg_id in PROCESSED: return True
    PROCESSED.add(msg_id)
    if len(PROCESSED) > 200: PROCESSED.clear()
    return False

def load_db():
    if MONGO_URL:
        try:
            data = {}
            for doc in movies_col.find():
                data[doc['_id']] = doc.get('files', [])
            return data
        except: return {}
    if not os.path.exists("database.json"): return {}
    try:
        with open("database.json",'r') as f: return json.load(f)
    except: return {}

def save_db_file_id(key, file_id):
    if MONGO_URL:
        movies_col.update_one({"_id": key}, {"$addToSet": {"files": file_id}}, upsert=True)
        return
    db = load_db()
    if key not in db: db[key] = []
    if file_id not in db[key]:
        db[key].append(file_id)
        with open("database.json",'w') as f: json.dump(db, f)

def load_caps():
    if MONGO_URL:
        try:
            data = {}
            for doc in caps_col.find():
                data[doc['_id']] = doc.get('caption','')
            return data
        except: return {}
    if not os.path.exists("captions.json"): return {}
    try:
        with open("captions.json",'r') as f: return json.load(f)
    except: return {}

def save_caps_single(file_id, caption):
    if MONGO_URL:
        caps_col.update_one({"_id": file_id}, {"$set": {"caption": caption}}, upsert=True)
        return
    caps = load_caps()
    caps[file_id] = caption
    with open("captions.json",'w') as f: json.dump(caps, f, ensure_ascii=False)

def extract_year(text):
    m = re.search(r'\b(19|20)\d{2}\b', text)
    return m.group(0) if m else None

def clean_name(text):
    if not text: return ""
    text = text.split('\n')[0]
    text = re.sub(r'@\w+|Bt_Movies_Hd|Filmsclub', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'http\S+|t\.me/\S+', '', text)
    text = re.sub(r'Join.*|Search.*|More.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(1080p|720p|480p|2160p|4K|HDRip|WEB-DL|BluRay|ESub|x264|x265|Hindi|AAC|2\.0|mkv|mp4|Full Movie|Dubbed|Hevc|Hdtc|Cinevood|CineVood)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^a-zA-Z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower().strip()

def normalize_search(text):
    return text.lower().replace(" ", "").replace("-", "").strip()

def get_tmdb(query, original_text=""):
    if not TMDB_KEY: return None
    cache_key = clean_name(query)[:40]
    if cache_key in TMDB_CACHE: return TMDB_CACHE[cache_key]
    q = clean_name(query)
    if len(q) < 2: q = query
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(q)}"
        r = requests.get(url, timeout=5).json()
        if not r.get('results'): return None
        results = [x for x in r['results'] if x.get('media_type') in ['movie','tv']][:3]
        best_item = results[0]
        mtype = best_item['media_type']; mid = best_item['id']
        d = requests.get(f"https://api.themoviedb.org/3/{mtype}/{mid}?api_key={TMDB_KEY}", timeout=5).json()
        title = d.get('title') or d.get('name') or q
        poster_path = best_item.get('poster_path')
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        rating = round(d.get('vote_average',0),1)
        glist = [g['name'] for g in d.get('genres',[])][:2]
        genres = ", ".join(glist) if glist else "N/A"
        date = d.get('release_date') or d.get('first_air_date') or "N/A"
        year_out = date[:4] if len(date)>=4 else "N/A"
        rt = d.get('runtime',0)
        runtime = f"{rt//60}H {rt%60}M" if mtype=='movie' and rt else f"{d.get('number_of_seasons',1)} Seasons" if mtype=='tv' else "N/A"
        story = d.get('overview','')[:500] or "N/A"
        res = {"title":title,"year":year_out,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype}
        TMDB_CACHE[cache_key] = res
        return res
    except: return None

def build_search_markup(chat_id, page=0):
    data = SEARCH_CACHE.get(chat_id)
    if not data: return None,0,0
    matched_keys = data["keys"]
    db = load_db()
    total = len(matched_keys)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE or 1
    start = page * PAGE_SIZE; end = start + PAGE_SIZE
    page_keys = matched_keys[start:end]
    markup = InlineKeyboardMarkup(row_width=1)
    for key in page_keys:
        files = db.get(key, [])
        btn_name = key.title()[:35]
        markup.add(InlineKeyboardButton(f"📥 {btn_name} ({len(files)} Files)", callback_data=f"get_{key}_0"))
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"spage_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1: nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"spage_{page+1}"))
    if total > PAGE_SIZE: markup.row(*nav)
    if page == 0 and data.get("info"):
        info = data["info"]
        markup.row( InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"), InlineKeyboardButton("📍 Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}") )
    return markup, total, total_pages

def build_file_markup(chat_id, key, page=0):
    files = FILE_CACHE.get(chat_id, {}).get("files", [])
    total = len(files)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE or 1
    start = page * PAGE_SIZE; end = start + PAGE_SIZE
    page_files = files[start:end]
    markup = InlineKeyboardMarkup(row_width=1)
    for idx, fid in enumerate(page_files, start=start+1):
        markup.add(InlineKeyboardButton(f"📦 Part {idx} - Download", callback_data=f"send_{key}_{idx-1}"))
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"fpage_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1: nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"fpage_{page+1}"))
    markup.row(*nav)
    markup.add(InlineKeyboardButton(f"📥 Send All {total} Files", callback_data=f"sendall_{key}"))
    return markup, total, total_pages

def channel_worker():
    while True:
        try:
            file_id, db_caption, is_video, thumb_path = CHANNEL_QUEUE.get()
            try:
                if is_video:
                    if thumb_path and os.path.exists(thumb_path):
                        with open(thumb_path, 'rb') as tf:
                            bot.send_video(DATABASE_CHANNEL_ID, file_id, thumb=tf, caption=db_caption)
                    else: bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=db_caption)
else:
