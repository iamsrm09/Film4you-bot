import os, time, requests, json, re, queue
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus
from pymongo import MongoClient

# --- AI IMPORTS (Free, no API key) ---
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    AI_AVAILABLE = True
except:
    AI_AVAILABLE = False
    print("AI lib not found, using fuzzy fallback")

MONGO_URL = os.environ.get('MONGO_URL')
TMDB_CACHE = {}
RAM_DB = {}
CLEAN_CACHE = {}

# AI Engine Global
AI_VECTORIZER = None
AI_MATRIX = None
AI_KEYS_LIST = [] # original keys

if MONGO_URL:
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
        mongo_db = client['film4you']
        movies_col = mongo_db['movies']
        caps_col = mongo_db['captions']
        print("Mongo Connected!")
    except Exception as e:
        print(f"Mongo Error: {e}")

app = Flask('')
@app.route('/')
def home(): return "Active ✅ AI Enabled"
def run_flask(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
def keep_alive(): Thread(target=run_flask, daemon=True).start()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_KEY = os.environ.get('TMDB_API_KEY')
DATABASE_CHANNEL_ID = -1004341107282

bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=10)

CHANNEL_QUEUE = queue.Queue()
ALBUM_CACHE = {}
PROCESSED = set()
SEARCH_CACHE = {}
FILE_CACHE = {}
PAGE_SIZE = 5

def is_duplicate(msg_id):
    if msg_id in PROCESSED: return True
    PROCESSED.add(msg_id)
    if len(PROCESSED) > 300: PROCESSED.clear()
    return False

def clean_name(text):
    if not text: return ""
    text = text.split('\n')[0]
    text = re.sub(r'@\w+|Bt_Movies_Hd|Filmsclub|Film4you', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'http\S+|t\.me/\S+', '', text)
    text = re.sub(r'Join.*|Search.*|More.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(1080p|720p|480p|2160p|4K|HDRip|WEB-DL|BluRay|ESub|x264|x265|Hindi|AAC|2\.0|mkv|mp4|Full Movie|Dubbed|Hevc|Hdtc|10Bit|Webrip|Psa|Combined|Webr)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^a-zA-Z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower().strip()

def init_ram_cache():
    global RAM_DB, CLEAN_CACHE
    if MONGO_URL:
        try:
            print("Loading DB into RAM...")
            temp = {}
            temp_clean = {}
            for doc in movies_col.find():
                key = doc['_id']
                cleaned = clean_name(key)
                if not cleaned or len(cleaned) < 3: continue
                if '[' in key or ']' in key:
                    new_key = cleaned
                    if new_key not in temp:
                        temp[new_key] = doc.get('files', [])
                        temp_clean[new_key] = new_key
                    continue
                temp[key] = doc.get('files', [])
                temp_clean[key] = cleaned
            RAM_DB = temp
            CLEAN_CACHE = temp_clean
            print(f"Loaded: {len(RAM_DB)} movies")
            build_ai_index()
        except Exception as e:
            print(f"RAM Error: {e}")

def build_ai_index():
    global AI_VECTORIZER, AI_MATRIX, AI_KEYS_LIST
    if not AI_AVAILABLE or not CLEAN_CACHE:
        return
    try:
        AI_KEYS_LIST = list(CLEAN_CACHE.keys())
        corpus = [CLEAN_CACHE[k] for k in AI_KEYS_LIST]
        AI_VECTORIZER = TfidfVectorizer(stop_words='english')
        AI_MATRIX = AI_VECTORIZER.fit_transform(corpus)
        print(f"AI Index Built: {len(AI_KEYS_LIST)} movies")
    except Exception as e:
        print(f"AI Build Error: {e}")

def ai_smart_search(query, top_k=10):
    """Return list of original_keys that match via AI"""
    if not query or len(query) < 2:
        return []
    if AI_AVAILABLE and AI_VECTORIZER is not None:
        try:
            q_vec = AI_VECTORIZER.transform([clean_name(query)])
            scores = cosine_similarity(q_vec, AI_MATRIX).flatten()
            ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            results = []
            for idx, score in ranked:
                if score > 0.18: # threshold
                    results.append(AI_KEYS_LIST[idx])
                if len(results) >= top_k:
                    break
            return results
        except:
            pass
    # Fallback fuzzy if sklearn not available
    import difflib
    clean_q = clean_name(query)
    all_cleaned = list(CLEAN_CACHE.values())
    close = difflib.get_close_matches(clean_q, all_cleaned, n=top_k, cutoff=0.4)
    # map back to original keys
    res_keys = []
    for c in close:
        for orig, cl in CLEAN_CACHE.items():
            if cl == c and orig not in res_keys:
                res_keys.append(orig)
                break
    return res_keys

def load_db():
    if RAM_DB: return RAM_DB
    if MONGO_URL:
        try:
            data = {}
            for doc in movies_col.find():
                cleaned = clean_name(doc['_id'])
                if not cleaned or len(cleaned) < 3: continue
                data[doc['_id']] = doc.get('files', [])
            return data
        except: return {}
    if not os.path.exists("database.json"): return {}
    try:
        with open("database.json",'r') as f: return json.load(f)
    except: return {}

def save_db_file_id(key, file_id):
    if not key or len(key) < 3: return
    if key not in RAM_DB: RAM_DB[key] = []
    if file_id not in RAM_DB[key]: RAM_DB[key].append(file_id)
    CLEAN_CACHE[key] = clean_name(key)
    # Rebuild AI partially - rebuild full for simplicity (fast for <5k movies)
    if len(RAM_DB) % 20 == 0:
        build_ai_index()
    if MONGO_URL:
        try:
            movies_col.update_one({"_id": key}, {"$addToSet": {"files": file_id}}, upsert=True)
        except: pass
    return

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
        try:
            caps_col.update_one({"_id": file_id}, {"$set": {"caption": caption}}, upsert=True)
        except: pass
    return

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
        if not results: return None
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
        runtime = f"{rt//60}H {rt%60}M" if mtype=='movie' and rt else "N/A"
        story = d.get('overview','')[:500] or "N/A"
        res = {"title":title,"year":year_out,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype}
        TMDB_CACHE[cache_key] = res
        return res
    except: return None

def build_search_markup(chat_id, page=0):
    data = SEARCH_CACHE.get(chat_id)
    if not data: return None,0,0
    matched_keys = data["keys"]
    db = RAM_DB if RAM_DB else load_db()
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
        markup.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"), InlineKeyboardButton("📍 Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}"))
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
                    else:
                        bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=db_caption)
                else:
                    bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=db_caption)
            except Exception as e:
                if "429" in str(e):
                    time.sleep(35)
                    CHANNEL_QUEUE.put((file_id, db_caption, is_video, thumb_path))
            time.sleep(3.5)
            CHANNEL_QUEUE.task_done()
        except: time.sleep(3)

Thread(target=channel_worker, daemon=True).start()

# --- NEW WELCOME HANDLER WITH USERNAME ---
@bot.message_handler(content_types=['new_chat_members'])
def welcome_handler(message):
    for new_user in message.new_chat_members:
        try:
            first_name = new_user.first_name or "Friend"
            username = f"@{new_user.username}" if new_user.username else first_name
            chat_title = message.chat.title or "Film4You"

            welcome_text = (
                f"🎬 Welcome {first_name}! ✨\n\n"
                f"Hey {username} 👋 Welcome to **{chat_title}** ❤️\n\n"
                f"🔍 Just send any movie name\n"
                f"🤖 AI will find it even if spelling is wrong\n"
                f"📥 Example: `avengers`, `bhoot wali movie`, `pushpa`\n\n"
                f"Enjoy! 🍿"
            )
            bot.send_message(
                message.chat.id,
                welcome_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎬 Search Movies", callback_data="noop")]
                ])
            )
        except Exception as e:
            print(f"Welcome Error: {e}")

@bot.message_handler(content_types=['video', 'document'])
def save_handler(message):
    if is_duplicate(message.message_id): return
    raw_caption = message.caption or ""
    media_group = getattr(message, 'media_group_id', None)
    if media_group:
        if raw_caption: ALBUM_CACHE[media_group] = raw_caption
        elif media_group in ALBUM_CACHE: raw_caption = ALBUM_CACHE[media_group]
    if not raw_caption:
        bot.reply_to(message, "❌ Caption me movie name likho! 🎬"); return
    file_id = message.video.file_id if message.video else message.document.file_id
    c_name = clean_name(raw_caption)
    if not c_name or len(c_name) < 3:
        bot.reply_to(message, f"❌ Invalid name after cleaning: {raw_caption[:30]}")
        return
    save_db_file_id(c_name, file_id)
    save_caps_single(file_id, raw_caption)
    db = RAM_DB if RAM_DB else load_db()
    bot.reply_to(message, f"✅ Saved! Name: {c_name} | Files: {len(db.get(c_name, []))} | AI Index: {len(CLEAN_CACHE)}")
    def bg_post():
        info = get_tmdb(raw_caption, raw_caption)
        thumb_path = None
        if info and info['poster']:
            try:
                resp = requests.get(info['poster'], timeout=10)
                thumb_path = f"/tmp/{file_id}.jpg"
                with open(thumb_path, 'wb') as f: f.write(resp.content)
            except: thumb_path = None
        if info:
            db_caption = f"{raw_caption}\n\n🎬 {info['title']} ({info['year']}) | ⭐ {info['rating']}/10"
        else:
            db_caption = raw_caption
        is_video = True if message.video else False
        CHANNEL_QUEUE.put((file_id, db_caption, is_video, thumb_path))
    Thread(target=bg_post, daemon=True).start()

@bot.message_handler(commands=['start', 'srart', 'sart', 'strt', 'Start'])
def start_handler(message):
    name = message.from_user.first_name or "Friend"
    username = f"@{message.from_user.username}" if message.from_user.username else name
    bot.send_message(message.chat.id, f"🎬✨ Film4you Bot Live! ✨🎬\n\n👋 Hello {name} ({username})! Welcome! ❤️\n\n🔍 Send Movie Name 👇\n🤖 AI Search Enabled - Wrong spelling also works!", parse_mode="Markdown")

@bot.message_handler(commands=['stats', 'Stats', 'STATS'])
def stats_handler(message):
    try:
        if MONGO_URL and RAM_DB:
            total_movies = len(RAM_DB)
            total_files = sum(len(v) for v in RAM_DB.values())
        elif MONGO_URL:
            total_movies = movies_col.count_documents({})
            total_files = 0
            for doc in movies_col.find():
                total_files += len(doc.get('files', []))
        else:
            db = load_db()
            total_movies = len(db)
            total_files = sum(len(v) for v in db.values())
        bot.send_message(message.chat.id, f"📊 *Bot Stats*\n\nTotal Movies: {total_movies}\nTotal Files: {total_files}\nAI Indexed: {len(AI_KEYS_LIST)}\nAI Status: {'✅ Active' if AI_AVAILABLE else '⚠️ Fallback Mode'}\nStatus: ✅ Active", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Error: {e}")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    if message.text.startswith('/'): return
    if is_duplicate(message.message_id): return
    query = message.text.strip()
    if len(query) < 2: return
    if not RAM_DB: init_ram_cache()
    if not RAM_DB:
        bot.send_message(message.chat.id, "⏳ Database connect ho rahi hai, thoda wait karo...")
        return
    clean_q = clean_name(query)
    if not clean_q or len(clean_q) < 2: clean_q = query.lower().strip()

    matched_keys = []
    for original_key, cleaned_key in CLEAN_CACHE.items():
        if not cleaned_key or len(cleaned_key) < 3: continue
        if clean_q == cleaned_key: matched_keys.append(original_key)
        elif clean_q in cleaned_key: matched_keys.append(original_key)
        elif len(clean_q) >= 4 and cleaned_key in clean_q: matched_keys.append(original_key)
        if len(matched_keys) >= 30: break

    # --- AI FALLBACK IF NO MATCH ---
    ai_used = False
    if not matched_keys:
        ai_results = ai_smart_search(query, top_k=10)
        if ai_results:
            matched_keys = ai_results
            ai_used = True

    matched_keys.sort(key=lambda k: (0 if CLEAN_CACHE.get(k) == clean_q else 1))
    SEARCH_CACHE[message.chat.id] = {"keys": matched_keys, "query": query, "info": None}
    markup, total, total_pages = build_search_markup(message.chat.id, 0)

    if total == 0:
        sent_msg = bot.send_message(message.chat.id, f"❌ No results for *{query}*\n\nTry: `avengers`, `pushpa`, `bhoot`", parse_mode="Markdown")
    else:
        label = "🤖 AI Search" if ai_used else "🎬 Exact Search"
        sent_msg = bot.send_message(message.chat.id, f"{label} - *{query}* 🔍\n\n{total} results - Page 1/{total_pages} 👇", parse_mode="Markdown", reply_markup=markup)

    def fetch_tmdb_and_edit():
        try:
            info = get_tmdb(query, query)
            if not info: return
            SEARCH_CACHE[message.chat.id]["info"] = info
            markup2, total2, total_pages2 = build_search_markup(message.chat.id, 0)
            caption = f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()} ✨\n⭐ {info['rating']}/10 | 🎭 {info['genres']} | ⏱️ {info['runtime']}\n📅 {info['date']}\n\n📝 {info['story']}\n\n🔍 {total2} results - Page 1/{total_pages2}"
            try:
                if info['poster']:
                    bot.delete_message(message.chat.id, sent_msg.message_id)
                    bot.send_photo(message.chat.id, info['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup2)
                else:
                    bot.edit_message_text(caption, message.chat.id, sent_msg.message_id, parse_mode="Markdown", reply_markup=markup2)
            except: pass
        except: pass
    Thread(target=fetch_tmdb_and_edit, daemon=True).start()

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    chat_id = call.message.chat.id
    db = RAM_DB if RAM_DB else load_db()
    caps = load_caps()
    if call.data == "noop": bot.answer_callback_query(call.id); return
    if call.data.startswith("spage_"):
        page = int(call.data.split("_")[1])
        markup, total, total_pages = build_search_markup(chat_id, page)
        if markup:
            try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
            except: pass
        bot.answer_callback_query(call.id, f"Page {page+1}/{total_pages}"); return
    if call.data.startswith("fpage_"):
        page = int(call.data.split("_")[1])
        key = FILE_CACHE.get(chat_id, {}).get("key", "")
        markup, total, total_pages = build_file_markup(chat_id, key, page)
        try: bot.edit_message_text(f"🎬 *{key.title()}* - {total} Files\n\n📄 Page {page+1}/{total_pages}", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except: pass
        bot.answer_callback_query(call.id, f"Page {page+1}/{total_pages}"); return
    if call.data.startswith("send_"):
        _, key, idx = call.data.split("_"); idx = int(idx)
        files = FILE_CACHE.get(chat_id, {}).get("files", [])
        if idx < len(files):
            fid = files[idx]
            orig_cap = caps.get(fid, f"🎬 {key.title()} Part {idx+1}")
            try: bot.send_document(chat_id, fid, caption=orig_cap)
  
