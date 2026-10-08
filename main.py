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

ALBUM_CACHE = {}

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
    text = re.sub(r'\b(1080p|720p|480p|2160p|4K|HDRip|WEB-DL|BluRay|ESub|x264|x265|Hindi|AAC|2\.0|mkv|mp4|Full Movie|Dubbed|Combined)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^a-zA-Z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower().strip()

def normalize_search(text):
    return text.lower().replace(" ", "").replace("-", "").strip()

def get_tmdb(query):
    if not TMDB_KEY: return None
    q = clean_name(query)
    if len(q) < 2: q = query
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(q)}"
        r = requests.get(url, timeout=10).json()
        if not r.get('results'): return None
        best = [x for x in r['results'] if x.get('media_type') in ['movie','tv']][0]
        mtype = best['media_type']
        mid = best['id']
        d = requests.get(f"https://api.themoviedb.org/3/{mtype}/{mid}?api_key={TMDB_KEY}", timeout=10).json()
        title = d.get('title') or d.get('name') or q
        poster_path = best.get('poster_path')
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        rating = round(d.get('vote_average',0),1)
        genres = ", ".join([g['name'] for g in d.get('genres',[])][:2]) or "N/A"
        date = d.get('release_date') or d.get('first_air_date') or "N/A"
        year = date[:4] if len(date)>=4 else "N/A"
        story = d.get('overview','')[:600] or "N/A"
        return {"title":title,"year":year,"rating":rating,"genres":genres,"date":date,"poster":poster,"story":story,"type":mtype}
    except: return None

def background_channel_send(file_id, raw_caption, is_video):
    try:
        info = get_tmdb(raw_caption)
        thumb_path = None
        if info and info['poster']:
            try:
                resp = requests.get(info['poster'], timeout=15)
                thumb_path = f"/tmp/{file_id}.jpg"
                with open(thumb_path, 'wb') as f: f.write(resp.content)
            except: thumb_path = None

        db_caption = f"🎬 {info['title']} ({info['year']}) | ⭐ {info['rating']}/10\n\n{raw_caption}" if info else raw_caption

        time.sleep(1)
        if is_video:
            if thumb_path:
                with open(thumb_path, 'rb') as tf:
                    bot.send_video(DATABASE_CHANNEL_ID, file_id, thumb=tf, caption=db_caption)
            else:
                bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=db_caption)
        else:
            bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=db_caption)
    except Exception as e:
        print(f"Channel send fail {raw_caption[:20]} : {e}")
        # 2GB wali file hogi to fail hogi par local me save rahegi

@bot.message_handler(content_types=['video', 'document'])
def save_handler(message):
    raw_caption = message.caption or ""
    media_group = getattr(message, 'media_group_id', None)

    if media_group:
        if raw_caption:
            ALBUM_CACHE[media_group] = raw_caption
        elif media_group in ALBUM_CACHE:
            raw_caption = ALBUM_CACHE[media_group]

    if not raw_caption:
        # Album ki baaki files ke liye caption nahi hai to ignore mat karo, cache wala use karo
        if media_group and media_group in ALBUM_CACHE:
            raw_caption = ALBUM_CACHE[media_group]
        else:
            return # Bina caption wali single file ignore

    file_id = message.video.file_id if message.video else message.document.file_id
    is_video = True if message.video else False
    c_name = clean_name(raw_caption)
    if not c_name: c_name = raw_caption[:30].lower()

    # --- TURBO SAVE: Turant DB me save ---
    db = load_db()
    if c_name not in db: db[c_name] = []
    if file_id not in db[c_name]:
        db[c_name].append(file_id)
        save_db(db)

    caps = load_caps()
    caps[file_id] = raw_caption
    save_caps(caps)

    # Reply turant
    try:
        bot.reply_to(message, f"✅ Saved! {c_name} | Total: {len(db[c_name])}")
    except: pass

    # Channel me bhejna background me hoga, bot rukega nahi
    Thread(target=background_channel_send, args=(file_id, raw_caption, is_video), daemon=True).start()

@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "🎬 Turbo Mode ON! 100 files ek saath bhejo, sab save hongi!")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    query = message.text.strip()
    if len(query) < 2: return
    clean_q = clean_name(query)
    norm_q = normalize_search(clean_q)
    db = load_db()
    info = get_tmdb(query)

    matched = []
    for k in db.keys():
        if clean_q in k or k in clean_q or norm_q in normalize_search(k) or normalize_search(k) in norm_q:
            matched.append(k)
        elif all(w in k for w in clean_q.split() if len(w)>2):
            matched.append(k)
    matched = list(set(matched))[:5]

    markup = InlineKeyboardMarkup(row_width=1)
    if matched:
        for k in matched:
            markup.add(InlineKeyboardButton(f"📥 {k.title()} ({len(db[k])} Files) 🔥", callback_data=f"get_{k}"))
    else:
        markup.add(InlineKeyboardButton(f"📥 WATCH 🎬", callback_data=f"nof_{query}"))

    if info and info['poster']:
        caption = f"🎬 *{info['title']} ({info['year']})* ✨\n⭐ {info['rating']}/10 | 🎭 {info['genres']}\n\n📝 {info['story']}"
        try:
            bot.send_photo(message.chat.id, info['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup)
            return
        except: pass

    bot.send_message(message.chat.id, f"🎬 *{query}* - {len(matched)} found", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    db = load_db()
    caps = load_caps()
    if call.data.startswith('get_'):
        key = call.data[4:]
        data = db.get(key)
        if not data:
            for k,v in db.items():
                if key in k or k in key:
                    data = v; key = k; break
        if data:
            files = data if isinstance(data, list) else [data]
            bot.answer_callback_query(call.id, f"Sending {len(files)} files...")
            for fid in files:
                cap = caps.get(fid, key.title())
                time.sleep(1)
                try: bot.send_document(call.message.chat.id, fid, caption=cap)
                except:
                    try: bot.send_video(call.message.chat.id, fid, caption=cap)
                    except Exception as e: bot.send_message(call.message.chat.id, f"Error: {e}")
        else:
            bot.answer_callback_query(call.id, "Not found!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "Not added yet!", show_alert=True)

if __name__ == "__main__":
    keep_alive()
    try: bot.remove_webhook(); time.sleep(1)
    except: pass
    while True:
        try: bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(e); time.sleep(5)
