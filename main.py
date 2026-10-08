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
        story = (d.get('overview','')[:800]) or "N/A"
        seasons = d.get('seasons',[]) if mtype=='tv' else []
        return {"title":title,"year":year,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype,"seasons":seasons}
    except Exception as e:
        print("TMDB Error:", e)
        return None

# --- SAVE WITH TMDB CAPTION + THUMBNAIL ---
@bot.message_handler(content_types=['video', 'document'])
def save_handler(message):
    caption_input = message.caption or ""
    if not caption_input:
        bot.reply_to(message, "❌ Please add caption! Example: `Rango`")
        return
    file_id = message.video.file_id if message.video else message.document.file_id
    key = caption_input.lower().strip()

    db = load_db()
    db[key] = file_id
    save_db(db)

    bot.reply_to(message, f"🔍 Fetching TMDB for *{caption_input}*...", parse_mode="Markdown")
    info = get_tmdb(caption_input)

    if info:
        beautiful_caption = (
            f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()}\n"
            f"⭐ {info['rating']}/10 | 🎭 {info['genres']} | ⏱ {info['runtime']}\n"
            f"📅 {info['date']}\n\n"
            f"📝 {info['story']}\n\n"
            f"🔑 `{key}`\n"
            f"✅ @Film4you1bot"
        )
        poster_url = info['poster']
    else:
        beautiful_caption = f"🎬 *{caption_input}*\n\n🔑 `{key}`\n✅ @Film4you1bot"
        poster_url = None

    try:
        # Send with beautiful caption to Database Channel
        if message.video:
            bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=beautiful_caption, parse_mode="Markdown")
        else:
            bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=beautiful_caption, parse_mode="Markdown")

        # Also send poster separately for thumbnail preview
        if poster_url:
            bot.send_photo(DATABASE_CHANNEL_ID, poster_url, caption=beautiful_caption, parse_mode="Markdown")

        bot.reply_to(message, f"✅ **Saved with TMDB Caption!**\nDatabase channel me ab TMDB wala caption chala gaya hai.\n\n{beautiful_caption}", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Error sending to channel: {e}\nMake bot ADMIN in {DATABASE_CHANNEL_ID}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, "🎬 Send movie name to search.\nTo save: Send video with caption `Rango`", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    query = message.text.strip()
    if len(query) < 2: return
    db = load_db()
    info = get_tmdb(query)
    if not info:
        markup = InlineKeyboardMarkup(row_width=1)
        qlow = query.lower()
        found = qlow if qlow in db else next((k for k in db if qlow in k), None)
        if found: markup.add(InlineKeyboardButton("📥 DOWNLOAD & WATCH", callback_data=f"get_{found}"))
        else: markup.add(InlineKeyboardButton("📥 DOWNLOAD & WATCH", callback_data=f"nof_{qlow}"))
        markup.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(query)}+trailer"), InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(query)}"))
        markup.row(InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(query)}"), InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={quote_plus(query)}"))
        bot.send_message(message.chat.id, f"🎬 *{query}*", parse_mode="Markdown", reply_markup=markup)
        return

    caption = f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()}\n⭐ {info['rating']}/10 | 🎭 {info['genres']} | ⏱ {info['runtime']}\n\n📝 {info['story']}\n"
    markup = InlineKeyboardMarkup(row_width=1)
    if info['type'] == 'movie':
        qlow = query.lower()
        found = qlow if qlow in db else next((k for k in db if qlow in k or k in qlow), None)
        if found: markup.add(InlineKeyboardButton("📥 DOWNLOAD & WATCH", callback_data=f"get_{found}"))
        else: markup.add(InlineKeyboardButton("📥 DOWNLOAD & WATCH", callback_data=f"nof_{qlow}"))
    else:
        for s in info['seasons']:
            sn = s.get('season_number')
            if sn == 0: continue
            fkey = next((k for k in db if f"s{sn:02d}" in k or f"season {sn}" in k), None)
            if fkey: markup.add(InlineKeyboardButton(f"📥 SEASON {sn}", callback_data=f"get_{fkey}"))
            else: markup.add(InlineKeyboardButton(f"📥 SEASON {sn}", callback_data=f"nof_{sn}"))
    markup.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"), InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}"))
    markup.row(InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(info['title'])}"), InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={quote_plus(info['title'])}"))
    if info['poster']:
        bot.send_photo(message.chat.id, info['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    db = load_db()
    if call.data.startswith('get_'):
        key = call.data[4:]
        fid = db.get(key)
        if not fid:
            for k,v in db.items():
                if key in k: fid=v; key=k; break
        if fid:
            bot.answer_callback_query(call.id, "Sending file...")
            try: bot.send_document(call.message.chat.id, fid, caption=f"🎬 *{key.title()}*\n✅ @Film4you1bot", parse_mode="Markdown")
            except:
                try: bot.send_video(call.message.chat.id, fid, caption=f"🎬 *{key.title()}*\n✅ @Film4you1bot", parse_mode="Markdown")
                except Exception as e: bot.send_message(call.message.chat.id, f"Error: {e}")
        else:
            bot.answer_callback_query(call.id, "File not found! Re-upload!", show_alert=True)
    else:
        bot.answer_callback_query(call.id, "⚠️ File not added yet!", show_alert=True)

if __name__ == "__main__":
    keep_alive()
    try: bot.remove_webhook(); time.sleep(1)
    except: pass
    while True:
        try: bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e: print(e); time.sleep(5)
