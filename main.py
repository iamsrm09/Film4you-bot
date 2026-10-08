import os, time, requests, json
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus

app = Flask('')
@app.route('/')
def home(): return "Film4you Bot is Live!"
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
        with open(DB_FILE, 'r') as f: return json.load(f)
    except: return {}
def save_db(data):
    with open(DB_FILE, 'w') as f: json.dump(data, f)

def get_tmdb(query):
    if not TMDB_KEY: return None
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(query)}"
        res = requests.get(url, timeout=10).json()
        if not res.get('results'): return None
        item = next((r for r in res['results'] if r.get('media_type') in ['movie','tv']), None)
        if not item: return None
        mtype = item['media_type']
        mid = item['id']
        details = requests.get(f"https://api.themoviedb.org/3/{mtype}/{mid}?api_key={TMDB_KEY}", timeout=10).json()
        title = details.get('title') or details.get('name')
        poster = f"https://image.tmdb.org/t/p/w500{item.get('poster_path')}" if item.get('poster_path') else None
        rating = round(details.get('vote_average',0),1)
        genres = ", ".join([g['name'] for g in details.get('genres',[])]) or "N/A"
        date = details.get('release_date') or details.get('first_air_date') or "N/A"
        year = date[:4] if date!="N/A" else "N/A"
        runtime = f"{details.get('runtime',0)//60} Hrs {details.get('runtime',0)%60} Mins" if mtype=='movie' else f"{details.get('number_of_seasons',1)} Seasons"
        cast_res = requests.get(f"https://api.themoviedb.org/3/{mtype}/{mid}/credits?api_key={TMDB_KEY}", timeout=10).json()
        starcast = ", ".join([c['name'] for c in cast_res.get('cast',[])[:5]]) or "N/A"
        story = details.get('overview','')[:700] or "N/A"
        seasons = details.get('seasons', []) if mtype=='tv' else []
        return {"title":title,"year":year,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"starcast":starcast,"poster":poster,"story":story,"type":mtype,"seasons":seasons}
    except Exception as e:
        print(e)
        return None

@bot.message_handler(content_types=['video','document'])
def save_movie(message):
    movie_name = message.caption
    if not movie_name:
        bot.reply_to(message, "⚠️ Write name in caption\nExample: `The Hangover` or `Money Heist S01`")
        return
    file_id = message.video.file_id if message.video else message.document.file_id
    db = load_db()
    db[movie_name.lower().strip()] = file_id
    save_db(db)
    try:
        if message.video:
            bot.send_video(DATABASE_CHANNEL_ID, file_id, caption=f"🎬 {movie_name}\nKey: {movie_name.lower()}")
        else:
            bot.send_document(DATABASE_CHANNEL_ID, file_id, caption=f"🎬 {movie_name}\nKey: {movie_name.lower()}")
        bot.reply_to(message, f"✅ Saved: *{movie_name}*", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Make bot ADMIN in channel: {e}")

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/'))
def search_movie(message):
    query = message.text.strip()
    db = load_db()
    info = get_tmdb(query)
    if not info:
        bot.send_message(message.chat.id, f"❌ No results for *{query}*", parse_mode="Markdown")
        return

    caption = (
        f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()}\n"
        f"⭐ *Rating:* {info['rating']}/10\n"
        f"🎭 *Genres:* {info['genres']}\n"
        f"⏱ *Length:* {info['runtime']}\n"
        f"📅 *Release Date:* {info['date']}\n"
        f"🌟 *Starcast:* {info['starcast']}\n\n"
        f"📝 *Story:* {info['story']}\n\n"
        f"✅ *Details Found!*"
    )

    markup = InlineKeyboardMarkup(row_width=1)

    if info['type'] == 'movie':
        # MOVIE - Big Download & Watch Button
        qlow = query.lower()
        found = qlow if qlow in db else next((k for k in db if qlow in k or k in qlow), None)
        if found:
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH", callback_data=f"get_{found}"))
        else:
            markup.add(InlineKeyboardButton(f"📥 DOWNLOAD & WATCH", callback_data=f"notfound_{qlow}"))
    else:
        # SERIES - Only Season Buttons
        for s in info['seasons']:
            season_num = s.get('season_number')
            if season_num == 0: continue
            
            possible_keys = [
                f"{info['title'].lower()} s{season_num:02d}",
                f"{info['title'].lower()} s{season_num}",
                f"{info['title'].lower()} season {season_num}",
                f"{query.lower()} s{season_num:02d}",
            ]
            found_key = None
            for pk in possible_keys:
                if pk in db:
                    found_key = pk
                    break
                for dbk in db.keys():
                    if pk in dbk:
                        found_key = dbk
                        break
                if found_key: break

            if found_key:
                markup.add(InlineKeyboardButton(f"📥 SEASON {season_num}", callback_data=f"get_{found_key}"))
            else:
                markup.add(InlineKeyboardButton(f"📥 SEASON {season_num}", callback_data=f"notfound_season_{season_num}"))

    markup.row(
        InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"),
        InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}")
    )
    markup.row(
        InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={quote_plus(info['title'])}"),
        InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={quote_plus(info['title'])}+movie")
    )

    try:
        if info['poster']:
            bot.send_photo(message.chat.id, info['poster'], caption=caption, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)
    except:
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    db = load_db()
    if call.data.startswith('get_'):
        key = call.data.replace('get_', '', 1)
        file_id = db.get(key)
        if not file_id:
            for k,v in db.items():
               
