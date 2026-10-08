import os, time, requests, json, re, queue
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
CAP_FILE = "captions.json"
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
    q = clean_name(query)
    year = extract_year(original_text or query)
    if len(q) < 2: q = query
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(q)}"
        r = requests.get(url, timeout=10).json()
        if not r.get('results'): return None
        results = [x for x in r['results'] if x.get('media_type') in ['movie','tv']][:10]
        best_item = None
        if year:
            for item in results:
                r_date = item.get('release_date') or item.get('first_air_date') or ""
                if year in r_date:
                    best_item = item
                    break
        if not best_item:
            q_norm = normalize_search(q)
            for item in results:
                title = (item.get('title') or item.get('name') or "").lower()
                if normalize_search(title) == q_norm:
                    best_item = item
                    break
        if not best_item: best_item = results[0]
        mtype = best_item['media_type']
        mid = best_item['id']
        d = requests.get(f"https://api.themoviedb.org/3/{mtype}/{mid}?api_key={TMDB_KEY}", timeout=10).json()
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
        story = d.get('overview','')[:700] or "N/A"
        return {"title":title,"year":year_out,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype}
    except Exception as e:
        print(f"TMDB Error {e}")
        return None

def build_search_markup(chat_id, page=0):
    data = SEARCH_CACHE.get(chat_id)
    if not data: return None,0,0
    matched_keys = data["keys"]
    db = load_db()
    total = len(matched_keys)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE or 1
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_keys = matched_keys[start:end]
    markup = InlineKeyboardMarkup(row_width=1)
    for key in page_keys:
        files = db.get(key, [])
        btn_name = key.title()[:35]
        markup.add(InlineKeyboardButton(f"📥 {btn_name} ({len(files)} Files)", callback_data=f"get_{key}_0"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"spage_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"spage_{page+1}"))
    if total > PAGE_SIZE:
        markup.row(*nav)
    if page == 0 and data.get("info"):
        info = data["info"]
        markup.row(
            InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"),
            InlineKeyboardButton("📍 Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}")
        )
    return markup, total, total_pages

def build_file_markup(chat_id, key, page=0):
    files = FILE_CACHE.get(chat_id, {}).get("files", [])
    total = len(files)
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE or 1
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_files = files[start:end]
    markup = InlineKeyboardMarkup(row_width=1)
    for idx, fid in enumerate(page_files, start=start+1):
        markup.add(InlineKeyboardButton(f"📦 Part {idx} - Download", callback_data=f"send_{key}_{idx-1}"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"fpage_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"fpage_{page+1}"))
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
                err = str(e)
                if "429" in err:
                    m = re.search(r'retry after (\d+)', err)
                    wait = int(m.group(1)) + 2 if m else 35
                    time.sleep(wait)
                    CHANNEL_QUEUE.put((file_id, db_caption, is_video, thumb_path))
            time.sleep(3.5)
            CHANNEL_QUEUE.task_done()
        except: time.sleep(3)
Thread(target=channel_worker, daemon=True).start()

@bot.message_handler(content_types=['video', 'document'])
def save_handler(message):
    if is_duplicate(message.message_id): return
    raw_caption = message.caption or ""
    media_group = getattr(message, 'media_group_id', None)
    if media_group:
        if raw_caption: ALBUM_CACHE[media_group] = raw_caption
        elif media_group in ALBUM_CACHE: raw_caption = ALBUM_CACHE[media_group]
    if not raw_caption:
        bot.reply_to(message, "❌ Caption me movie name likho! 🎬")
        return
    file_id = message.video.file_id if message.video else message.document.file_id
    c_name = clean_name(raw_caption)
    if not c_name: c_name = raw_caption[:30].lower()
    db = load_db()
    if c_name not in db: db[c_name] = []
    if file_id not in db[c_name]: db[c_name].append(file_id)
    save_db(db)
    caps = load_caps()
    caps[file_id] = raw_caption
    save_caps(caps)
    info = get_tmdb(raw_caption, raw_caption)
    thumb_path = None
    if info and info['poster']:
        try:
            resp = requests.get(info['poster'], timeout=15)
            thumb_path = f"/tmp/{file_id}.jpg"
            with open(thumb_path, 'wb') as f: f.write(resp.content)
        except: thumb_path = None
    if info:
        db_caption = f"{raw_caption}\n\n🎬 {info['title']} ({info['year']}) | ⭐ {info['rating']}/10 | {info['genres']}\n\n{info['story'][:400]}"
    else:
        db_caption = raw_caption
    is_video = True if message.video else False
    CHANNEL_QUEUE.put((file_id, db_caption, is_video, thumb_path))
    bot.reply_to(message, f"✅ Saved! Name: {c_name} | Files: {len(db[c_name])}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    if is_duplicate(message.message_id): return
    name = message.from_user.first_name or "Friend"
    bot.send_message(message.chat.id, f"🎬✨ Film4you Bot Live! ✨🎬\n\n👋 Hello {name}! Welcome! ❤️\n\n🔍 Send Movie Name 👇")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    if is_duplicate(message.message_id): return
    query = message.text.strip()
    if len(query) < 2: return
    def strip_series(text):
        text = re.sub(r'\b[sS]\d{1,2}\s*[eE]\d{1,2}\b', '', text)
        text = re.sub(r'\b[sS]\d{1,2}\b', '', text)
        text = re.sub(r'\bseason\s*\d+\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\bepisode\s*\d+\b', '', text, flags=re.IGNORECASE)
        return text
    clean_q = clean_name(strip_series(query))
    db = load_db()
    try: info = get_tmdb(query, query)
    except: info = None
    matched_keys = []
    search_words = [w for w in clean_q.split() if len(w) > 1]
    for saved_name in db.keys():
        if len(saved_name) < 2: continue
        if "bt_movies" in saved_name or "filmsclub" in saved_name: continue
        saved_stripped = clean_name(strip_series(saved_name))
        if not saved_stripped: continue
        norm_saved = normalize_search(saved_stripped)
        norm_q = normalize_search(clean_q)
        if clean_q and (clean_q in saved_stripped or saved_stripped in clean_q):
            matched_keys.append(saved_name)
        elif norm_q and (norm_q in norm_saved or norm_saved in norm_q):
            matched_keys.append(saved_name)
        elif search_words and all(w in saved_stripped for w in search_words):
            matched_keys.append(saved_name)
    matched_keys = list(set(matched_keys))
    matched_keys.sort(key=lambda x: abs(len(x) - len(clean_q)))
    SEARCH_CACHE[message.chat.id] = {"keys": matched_keys, "query": query, "info": info}
    markup, total, total_pages = build_search_markup(message.chat.id, 0)
    if not info:
        if matched_keys:
            bot.send_message(message.chat.id, f"🎬 *{query}* 🔍\n\n{total} results - Page 1/{total_pages} 👇", parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, f"❌ *{query}* not found!", parse_mode="Markdown")
        return
    caption = f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()} ✨\n⭐ {info['rating']}/10 | 🎭 {info['genres']} | ⏱️ {info['runtime']}\n📅 {info['date']}\n\n📝 {info['story']}\n\n🔍 {total} results - Page 1/{total_pages}"
    try:
        if info['poster']:
            bot.send_photo(message.chat.id, info['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, caption, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    chat_id = call.message.chat.id
    db = load_db()
    caps = load_caps()

    if call.data == "noop":
        bot.answer_callback_query(call.id)
        return

    if call.data.startswith("spage_"):
        page = int(call.data.split("_")[1])
        markup, total, total_pages = build_search_markup(chat_id, page)
        if markup:
            try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=markup)
            except: pass
        bot.answer_callback_query(call.id, f"Page {page+1}/{total_pages}")
        return

    if call.data.startswith("fpage_"):
        page = int(call.data.split("_")[1])
        key = FILE_CACHE.get(chat_id, {}).get("key", "")
        markup, total, total_pages = build_file_markup(chat_id, key, page)
        try:
            bot.edit_message_text(f"🎬 *{key.title()}* - {total} Files\n\n📄 Page {page+1}/{total_pages}", chat_id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
        except: pass
        bot.answer_callback_query(call.id, f"Page {page+1}/{total_pages}")
        return

    if call.data.startswith("send_"):
        _, key, idx = call.data.split("_")
        idx = int(idx)
        files = FILE_CACHE.get(chat_id, {}).get("files", [])
        if idx < len(files):
            fid = files[idx]
            orig_cap = caps.get(fid, f"🎬 {key.title()} Part {idx+1}")
            try: bot.send_document(chat_id, fid, caption=orig_cap)
            except:
                try: bot.send_video(chat_id, fid, caption=orig_cap)
                except Exception as e: bot.send_message(chat_id, f"❌ Error: {e}")
        bot.answer_callback_query(call.id)
        return

    if call.data.startswith("sendall_"):
        key = call.data.split("_",1)[1]
        files = FILE_CACHE.get(chat_id, {}).get("files", [])
        bot.answer_callback_query(call.id, f"Sending {len(files)} files...")
        for fid in files:
            orig_cap = caps.get(fid, f"🎬 {key.title()} ✨")
            time.sleep(0.8)
            try: bot.send_document(chat_id, fid, caption=orig_cap)
            except:
                try: bot.send_video(chat_id, fid, caption=orig_cap)
                except: pass
        return

    if call.data.startswith("get_"):
        parts = call.data.rsplit("_",1)
        key = parts[0][4:]
        data = db.get(key)
        if not data:
            for k,v in db.items():
                if key in k or k in key or normalize_search(key) == normalize_search(k):
                    data = v; key = k; break
        if data:
            files = data if isinstance(data, list) else [data]
            FILE_CACHE[chat_id] = {"key": key, "files": files}
            markup, total, total_pages = build_file_markup(chat_id, key, 0)
            bot.send_message(chat_id, f"🎬 *{key.title()}* - {total} Files\n\n📄 Page 1/{total_pages} 👇", parse_mode="Markdown", reply_markup=markup)
            bot.answer_callback_query(call.id, f"{total} files - Page 1/{total_pages}")
        else:
            bot.answer_callback_query(call.id, "❌ File not found!", show_alert=True)
        return

    bot.answer_callback_query(call.id, "⚠️ Not found!")

if __name__ == "__main__":
    keep_alive()
    try: bot.remove_webhook(); time.sleep(1)
    except: pass
    while True:
        try: bot.polling(none_stop=True, timeout=60)
        except Exception as e: print(e); time.sleep(5)
