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

def extract_year(text):
    m = re.search(r'\b(19|20)\d{2}\b', text)
    return m.group(0) if m else None

def clean_name(text):
    if not text: return ""
    text = text.split('\n')[0]
    text = re.sub(r'http\S+|t\.me/\S+|@\w+', '', text)
    text = re.sub(r'Join.*|Search.*|More.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\b(1080p|720p|480p|2160p|4K|HDRip|WEB-DL|BluRay|ESub|x264|x265|Hindi|AAC|2\.0|mkv|mp4|Full Movie|Dubbed)\b', '', text, flags=re.IGNORECASE)
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
        if not best_item:
            best_item = results[0]

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
        seasons = d.get('seasons',[]) if mtype=='tv' else []
        return {"title":title,"year":year_out,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype,"seasons":seasons}
    except Exception as e:
        print(f"TMDB Error {e}")
        return None

@bot.message_handler(content_types=['video', 'document'])
def save_handler(message):
    raw_caption = message.caption or ""
    if not raw_caption:
        bot.reply_to(message, "❌ Caption me movie name likho! 🎬")
        return
    file_id = message.video.file_id if message.video else message.document.file_id

    # Name se save - clean name nikalo
    c_name = clean_name(raw_caption)
    if not c_name: c_name = raw_caption[:30].lower()

    db = load_db()
    if c_name not in db: db[c_name] = []
    if file_id not in db[c_name]: db[c_name].append(file_id)
    save_db(db)

    caps = load_caps()
    caps[file_id] = raw_caption
    save_caps(caps)

    # Description + Thumbnail auto change
    info = get_tmdb(raw_caption, raw_caption)
    thumb_path = None
    if info and info['poster']:
        try:
            resp = requests.get(info['poster'], timeout=15)
            thumb_path = f"/tmp/{file_id}.jpg"
            with open(thumb_path, 'wb') as f: f.write(resp.content)
        except: thumb_path = None

    if info:
        db_caption = f"🎬 *{info['title']} ({info['year']})* ✨\n⭐ {info['rating']}/10 | 🎭 {info['genres']}\n\n📝 {info['story'][:400]}...\n\n{raw_caption}"
    else:
        db_caption = raw_caption

    try:
        if message.video:
            if thumb_path:
                with open(thumb_path, 'rb') as tf:
                    bot.send_video(DATABASE_CHANNEL_ID, file_id, thumb=tf, caption=db_caption, parse_mode="Markdown")
            else:
                bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=db_caption, parse_mode="Markdown")
        else:
            bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=db_caption, parse_mode="Markdown")
        bot.reply_to(message, f"✅ Saved by Name! 🎉\n🎬 Name: `{c_name}`\n🖼️ Thumb + Desc: {'Changed ✅' if thumb_path else 'Original'}\n📦 Files: {len(db[c_name])}")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Channel error: {e}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "🎬✨ Film4you Bot Live! ✨🎬\n\n🔍 `the paradise` likho to `the paradise` se shuru hone wali saari movies aa jayengi!", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    query = message.text.strip()
    if len(query) < 2: return

    clean_q = clean_name(query)
    norm_q = normalize_search(clean_q)
    db = load_db()
    info = get_tmdb(query, query)

    # --- THE PARADISE LOGIC: Name ke aage kuch bhi ho to bhi mile ---
    matched_keys = []
    for saved_name in db.keys():
        norm_saved = normalize_search(saved_name)
        # 1. the paradise in the paradise 2026 hindi dubbed
        if clean_q in saved_name or saved_name in clean_q:
            matched_keys.append(saved_name)
        # 2. theparadise in theparadise2026
        elif norm_q in norm_saved or norm_saved in norm_q:
            matched_keys.append(saved_name)
        # 3. Word match: the paradise word match
        elif all(w in saved_name for w in clean_q.split() if len(w) > 2):
            matched_keys.append(saved_name)

    # Remove duplicates and sort by best match (smallest length diff first)
    matched_keys = list(set(matched_keys))
    matched_keys.sort(key=lambda x: abs(len(x) - len(clean_q)))

    print(f"Search: {query} -> matched: {matched_keys}")

    markup = InlineKeyboardMarkup(row_width=1)

    if not info:
        if matched_keys:
            for key in matched_keys[:5]: # Max 5 buttons
                files = db[key]
                markup.add(InlineKeyboardButton(f"📥 {key.title()} ({len(files)} Files) 🔥", callback_data=f"get_{key}"))
        else:
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH 🎬💾", callback_data=f"nof_{query}"))
        bot.send_message(message.chat.id, f"🎬 *{query}* 🔍\n\n{len(matched_keys)} results found! 👇", parse_mode="Markdown", reply_markup=markup)
        return

    caption = f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()} ✨\n⭐ {info['rating']}/10 🌟 | 🎭 {info['genres']} | ⏱️ {info['runtime']}\n📅 {info['date']}\n\n📝 {info['story']}\n"

    # Agar matched keys hai to unke buttons dikhao
    if matched_keys:
        for key in matched_keys[:5]:
            files = db[key]
            # Exact naam dikhao
            markup.add(InlineKeyboardButton(f"📥 {key.title()} - WATCH ({len(files)} Files) 🔥", callback_data=f"get_{key}"))
    else:
        markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH 🎬💾", callback_data=f"nof_{query}"))

    markup.row(
        InlineKeyboardButton("▶️ Trailer 🎥", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"),
        InlineKeyboardButton("📍 Where to Watch 🍿", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}")
    )
    markup.row(
        InlineKeyboardButton("⭐ IMDb Top 🏆", url=f"https://www.imdb.com/find?q={quote_plus(info['title'])}"),
        InlineKeyboardButton("🎬 Google 🔎", url=f"https://www.google.com/search?q={quote_plus(info['title'])}")
    )

    if info['poster']:
        try: bot.send_photo(message.chat.id, info['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup)
        except: bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    db = load_db()
    caps = load_caps()
    if call.data.startswith('get_'):
        key = call.data[4:]
        data = db.get(key)
        if not data:
            # Fuzzy fallback for old keys
            for k,v in db.items():
                if key in k or k in key or normalize_search(key) == normalize_search(k):
                    data = v
                    key = k
                    break
        if data:
            files = data if isinstance(data, list) else [data]
            bot.answer_callback_query(call.id, f"🎬 {key.title()} - {len(files)} files 📤")
            for i, fid in enumerate(files, 1):
                orig_cap = caps.get(fid, f"🎬 {key.title()} Part {i} ✨")
                time.sleep(0.8)
                try: bot.send_document(call.message.chat.id, fid, caption=orig_cap)
                except:
                    try: bot.send_video(call.message.chat.id, fid, caption=orig_cap)
                    except Exception as e: bot.send_message(call.message.chat.id, f"❌ Error: {e}")
        else:
            bot.answer_callback_query(call.id, "❌ File not found! 😔", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "⚠️ File not added yet! 📭", show_alert=True)

if __name__ == "__main__":
    keep_alive()
    try: bot.remove_webhook(); time.sleep(1)
    except: pass
    while True:
        try: bot.polling(none_stop=True, timeout=60)
        except Exception as e: print(e); time.sleep(5)
