import os, time, requests, json
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

def get_tmdb(query):
    if not TMDB_KEY: return None
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(query)}"
        r = requests.get(url, timeout=10).json()
        if not r.get('results'): return None
        item = next((x for x in r['results'] if x.get('media_type') in ['movie','tv']), None)
        if not item: return None
        mtype = item['media_type']
        d = requests.get(f"https://api.themoviedb.org/3/{mtype}/{item['id']}?api_key={TMDB_KEY}", timeout=10).json()
        title = d.get('title') or d.get('name') or query
        poster = f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get('poster_path') else None
        rating = round(d.get('vote_average',0),1)
        genres = ", ".join([g['name'] for g in d.get('genres',[])][:2]) or "N/A"
        date = d.get('release_date') or d.get('first_air_date') or "N/A"
        year = date[:4] if len(date)>=4 else "N/A"
        runtime = f"{d.get('runtime',0)//60}H {d.get('runtime',0)%60}M" if mtype=='movie' else f"{d.get('number_of_seasons',1)} Seasons"
        story = (d.get('overview','')[:600]) or "N/A"
        seasons = d.get('seasons',[]) if mtype=='tv' else []
        return {"title":title,"year":year,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype,"seasons":seasons}
    except Exception as e:
        print("TMDB Error:", e)
        return None

# --- 1. SAVE VIDEO - GUARANTEED WORKING ---
@bot.message_handler(content_types=['video', 'document', 'video_note'])
def save_handler(message):
    print("Video received!") # for Render logs
    caption = message.caption or ""
    if not caption:
        bot.reply_to(message, "❌ Please add caption!\nExample: `Rango` or `Money Heist S01`", parse_mode="Markdown")
        return
    
    file_id = None
    if message.video: file_id = message.video.file_id
    elif message.document: file_id = message.document.file_id
    
    if not file_id:
        bot.reply_to(message, "❌ No file_id found")
        return

    # Save to local DB
    db = load_db()
    db[caption.lower().strip()] = file_id
    save_db(db)
    print(f"Saved: {caption.lower()} -> {file_id[:20]}")

    # Save to Database Channel
    try:
        bot.send_message(DATABASE_CHANNEL_ID, f"Saved: {caption}\nFile ID stored")
        if message.video:
            bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=caption)
        else:
            bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=caption)
        bot.reply_to(message, f"✅ **Saved to Database!**\n\nKey: `{caption.lower().strip()}`\nFile ID: `{file_id[:20]}...`", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Saved locally but failed to send to channel.\nMake bot ADMIN in channel -1004341107282\n\nError: {e}\n\nBut local save is done: `{caption.lower()}`", parse_mode="Markdown")

@bot.message_handler(commands=['start', 'help'])
def start_handler(message):
    bot.send_message(message.chat.id, "🎬 Send me movie name to search.\n\n**To Save Movie:** Just send video/document with caption as movie name.\nExample: `Rango` or `Money Heist S01`", parse_mode="Markdown")

# --- 2. SEARCH WITH 5 BUTTONS - BIG BUTTON LOGIC ---
@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    query = message.text.strip()
    if not query: return
    if len(query) < 2: return
    
    print(f"Searching: {query}")
    info = get_tmdb(query)
    db = load_db()

    if not info:
        # Even if TMDB fails, show 5 buttons with file
        caption = f"🎬 *{query}*\n\n✅ File check..."
        markup = InlineKeyboardMarkup()
        qlow = query.lower()
        found = qlow if qlow in db else next((k for k in db if qlow in k), None)
        if found:
            markup.add(InlineKeyboardButton("📥 DOWNLOAD & WATCH", callback_data=f"get_{found}"))
        else:
            markup.add(InlineKeyboardButton("📥 DOWNLOAD & WATCH", callback_data=f"nof_{qlow}"))
        markup.row(
            InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(query)}+trailer"),
            InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(query)}")
        )
        markup.row(
            InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(query)}"),
            InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={quote_plus(query)}")
        )
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)
        return

    caption = (
        f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()}\n"
        f"⭐ {info['rating']}/10 | 🎭 {info['genres']} | ⏱ {info['runtime']}\n\n"
        f"📝 {info['story']}\n"
    )

    markup = InlineKeyboardMarkup(row_width=1)

    if info['type'] == 'movie':
        # MOVIE = 1 BIG BUTTON ON TOP
        qlow = query.lower()
        found = None
        if qlow in db: found = qlow
        else:
            for k in db:
                if qlow in k or k in qlow:
                    found = k
                    break
        if found:
            markup.add(InlineKeyboardButton("📥 DOWNLOAD & WATCH", callback_data=f"get_{found}"))
        else:
            markup.add(InlineKeyboardButton("📥 DOWNLOAD & WATCH", callback_data=f"nof_{qlow}"))
    else:
        # SERIES = ONLY SEASON BUTTONS (BIG)
        for s in info['seasons']:
            sn = s.get('season_number')
            if sn == 0: continue
            # Find file for this season
            possible = [f"{query.lower()} s{sn:02d}", f"{query.lower()} season {sn}", f"{info['title'].lower()} s{sn:02d}"]
            fkey = None
            for p in possible:
                if p in db:
                    fkey = p
                    break
            if fkey:
                markup.add(InlineKeyboardButton(f"📥 SEASON {sn}", callback_data=f"get_{fkey}"))
            else:
                markup.add(InlineKeyboardButton(f"📥 SEASON {sn}", callback_data=f"nof_season_{sn}"))

    # 4 SMALL BUTTONS - 2 in each row = Total 5 buttons for movie
    markup.row(
        InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"),
        InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}")
    )
    markup.row(
        InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(info['title'])}"),
        InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={quote_plus(info['title'])}")
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
    print(f"Callback: {call.data}")
    if call.data.startswith('get_'):
        key = call.data[4:]
        fid = db.get(key)
        if not fid:
            for k,v in db.items():
                if key in k: fid=v; key=k; break
        if fid:
            bot.answer_callback_query(call.id, "Sending file...")
            try: bot.send_document(call.message.chat.id, fid, caption=f"🎬 {key.title()}\n@Film4you1bot")
            except:
                try: bot.send_video(call.message.chat.id, fid, caption=f"🎬 {key.title()}\n@Film4you1bot")
                except Exception as e: bot.send_message(call.message.chat.id, f"Error: {e}")
        else:
            bot.answer_callback_query(call.id, "File not found in DB. Re-upload!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "⚠️ File not added yet! Upload with caption like 'Rango' or 'Money Heist S01'", show_alert=True)

if __name__ == "__main__":
    keep_alive()
    try: bot.remove_webhook(); time.sleep(1)
    except: pass
    print("Bot started polling...")
    while True:
        try: bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e: print("Polling error:", e); time.sleep(5)
