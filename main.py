import os, time, requests, json, re
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus

app = Flask('')
@app.route('/')
def home():
    return "Bot is Live!"
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
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE,'r') as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    with open(DB_FILE,'w') as f:
        json.dump(data, f)

def load_caps():
    if not os.path.exists(CAP_FILE):
        return {}
    try:
        with open(CAP_FILE,'r') as f:
            return json.load(f)
    except:
        return {}

def save_caps(data):
    with open(CAP_FILE,'w') as f:
        json.dump(data, f, ensure_ascii=False)

def clean_name(text):
    if not text:
        return ""
    text = text.split('\n')[0]
    text = re.sub(r'http\S+|t\.me/\S+|@\w+', '', text)
    text = re.sub(r'Join.*|Search.*|More.*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'1080p|720p|480p|2160p|4K|HDRip|WEB-DL|BluRay|ESub|x264|x265', '', text, flags=re.IGNORECASE)
    text = re.sub(r'S\d+|Season \d+|Part \d+|20\d{2}|19\d{2}', '', text, flags=re.IGNORECASE)
    text = re.sub(r'[^a-zA-Z0-9 ]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text.lower().strip()

def normalize_search(text):
    # spiderman = spider-man = spider man
    return text.lower().replace(" ", "").replace("-", "").strip()

def get_tmdb(query):
    if not TMDB_KEY:
        return None
    q = clean_name(query)
    if len(q) < 2:
        q = query
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(q)}"
        r = requests.get(url, timeout=10).json()
        if not r.get('results'):
            return None
        item = None
        for x in r['results']:
            if x.get('media_type') in ['movie','tv']:
                item = x
                break
        if not item:
            return None
        mtype = item['media_type']
        mid = item['id']
        d = requests.get(f"https://api.themoviedb.org/3/{mtype}/{mid}?api_key={TMDB_KEY}", timeout=10).json()
        title = d.get('title') or d.get('name') or q
        poster_path = item.get('poster_path')
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        rating = round(d.get('vote_average',0),1)
        glist = [g['name'] for g in d.get('genres',[])][:2]
        genres = ", ".join(glist) if glist else "N/A"
        date = d.get('release_date') or d.get('first_air_date') or "N/A"
        year = date[:4] if len(date)>=4 else "N/A"
        rt = d.get('runtime',0)
        if mtype == 'movie':
            runtime = f"{rt//60}H {rt%60}M" if rt else "N/A"
        else:
            runtime = f"{d.get('number_of_seasons',1)} Seasons"
        story = d.get('overview','')[:700] or "N/A"
        seasons = d.get('seasons',[]) if mtype=='tv' else []
        return {"title":title,"year":year,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype,"seasons":seasons}
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
    c_name = clean_name(raw_caption)
    if not c_name:
        c_name = raw_caption[:20].lower()

    db = load_db()
    if c_name not in db:
        db[c_name] = []
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
            with open(thumb_path, 'wb') as f:
                f.write(resp.content)
        except:
            thumb_path = None

    if info:
        db_caption = f"{raw_caption}\n\n🎬 {info['title']} ({info['year']}) | ⭐ {info['rating']}/10"
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
    bot.send_message(message.chat.id, "🎬✨ Film4you Bot Live! ✨🎬\n\n🔍 Movie name bhejo\n💾 Video bhejo caption ke saath", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    query = message.text.strip()
    if len(query) < 2:
        return

    clean_q = clean_name(query)
    norm_q = normalize_search(clean_q)
    db = load_db()
    info = get_tmdb(query)

    found_key = None
    for saved_name in db.keys():
        norm_saved = normalize_search(saved_name)
        # Fix for Spiderman vs Spider-man
        if clean_q in saved_name or saved_name in clean_q:
            found_key = saved_name
            break
        if norm_q in norm_saved or norm_saved in norm_q:
            found_key = saved_name
            break
        if len(set(clean_q.split()) & set(saved_name.split())) >= 1 and len(clean_q) > 3:
            found_key = saved_name
            break

    if not found_key and info:
        tmdb_clean = clean_name(info['title'])
        tmdb_norm = normalize_search(tmdb_clean)
        for saved_name in db.keys():
            if tmdb_clean in saved_name or saved_name in tmdb_clean:
                found_key = saved_name
                break
            if tmdb_norm in normalize_search(saved_name) or normalize_search(saved_name) in tmdb_norm:
                found_key = saved_name
                break

    markup = InlineKeyboardMarkup(row_width=1)

    if not info:
        if found_key:
            files = db[found_key]
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH ({len(files)} Files) 🔥", callback_data=f"get_{found_key}"))
        else:
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH 🎬💾", callback_data=f"nof_{query}"))
        markup.row(
            InlineKeyboardButton("▶️ Trailer 🎥", url=f"https://www.youtube.com/results?search_query={quote_plus(query)}+trailer"),
            InlineKeyboardButton("📍 Where to Watch 🍿", url=f"https://www.justwatch.com/in/search?q={quote_plus(query)}")
        )
        markup.row(
            InlineKeyboardButton("⭐ IMDb Top 🏆", url=f"https://www.imdb.com/find?q={quote_plus(query)}"),
            InlineKeyboardButton("🎬 Google 🔎", url=f"https://www.google.com/search?q={quote_plus(query)}")
        )
        bot.send_message(message.chat.id, f"🎬 *{query}* 🔍", parse_mode="Markdown", reply_markup=markup)
        return

    caption = f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()} ✨\n⭐ {info['rating']}/10 🌟 | 🎭 {info['genres']} | ⏱️ {info['runtime']}\n📅 {info['date']}\n\n📝 {info['story']}\n"

    if info['type'] == 'movie':
        if found_key:
            files = db[found_key]
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH ({len(files)} Files) 🔥", callback_data=f"get_{found_key}"))
        else:
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH 🎬💾", callback_data=f"nof_{query}"))
    else:
        for s in info['seasons']:
            sn = s.get('season_number')
            if sn == 0:
                continue
            s_key = None
            for saved_name in db.keys():
                if normalize_search(clean_name(info['title'])) in normalize_search(saved_name) or clean_q in saved_name:
                    s_key = saved_name
                    break
            if s_key:
                markup.add(InlineKeyboardButton(f"📥 SEASON {sn} 📺✨", callback_data=f"get_{s_key}"))
            else:
                markup.add(InlineKeyboardButton(f"📥 SEASON {sn} 📺", callback_data=f"nof_{sn}"))

    markup.row(
        InlineKeyboardButton("▶️ Trailer 🎥", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"),
        InlineKeyboardButton("📍 Where to Watch 🍿", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}")
    )
    markup.row(
        InlineKeyboardButton("⭐ IMDb Top 🏆", url=f"https://www.imdb.com/find?q={quote_plus(info['title'])}"),
        InlineKeyboardButton("🎬 Google 🔎", url=f"https://www.google.com/search?q={quote_plus(info['title'])}")
    )

    if info['poster']:
        try:
            bot.send_photo(message.chat.id, info['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup)
        except:
            bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)
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
            for k,v in db.items():
                if key in k or k in key or normalize_search(key) in normalize_search(k):
                    data = v
                    key = k
                    break
        if data:
            files = data if isinstance(data, list) else [data]
            bot.answer_callback_query(call.id, f"🎬 Sending {len(files)} files... 📤")
            for i, fid in enumerate(files, 1):
                orig_cap = caps.get(fid, f"🎬 {key.title()} Part {i} ✨")
                time.sleep(0.8)
                try:
                    bot.send_document(call.message.chat.id, fid, caption=orig_cap)
                except:
                    try:
                        bot.send_video(call.message.chat.id, fid, caption=orig_cap)
                    except Exception as e:
                        bot.send_message(call.message.chat.id, f"❌ Error: {e}")
        else:
            bot.answer_callback_query(call.id, "❌ File not found! 😔", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "⚠️ File not added yet! 📭", show_alert=True)

if __name__ == "__main__":
    keep_alive()
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(e)
            time.sleep(5)
