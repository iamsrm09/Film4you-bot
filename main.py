import os, threading, logging, json
from flask import Flask
import telebot, requests
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot Alive"

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_CHANNEL = -1004341107282
TMDB_KEY = os.getenv("TMDB_KEY") or os.getenv("TMDB_TOKEN")
ADMIN_ID = None # apna telegram ID yahan daal sakte ho

bot = telebot.TeleBot(BOT_TOKEN)

DB_FILE = "movies.json"
movie_db = {}
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, 'r') as f:
            movie_db = json.load(f)
    except: pass

def save_db():
    with open(DB_FILE, 'w') as f:
        json.dump(movie_db, f)

# 1. AGAR TUM BOT KO DIRECT MOVIE BHEJTE HO
@bot.message_handler(content_types=['document', 'video'])
def handle_file(message):
    file_name = message.caption or (message.document.file_name if message.document else "video")
    # Channel me bhejo
    try:
        sent = bot.copy_message(DATABASE_CHANNEL, message.chat.id, message.message_id)
        movie_db[file_name.lower()] = sent.message_id
        # short name
        short = file_name.split('.')[0].lower()
        movie_db[short] = sent.message_id
        save_db()
        bot.reply_to(message, f"✅ Save ho gayi: {file_name}\nID: {sent.message_id}\nAb koi bhi us naam se search karega to Download ayega.")
    except Exception as e:
        bot.reply_to(message, f"❌ Channel me forward nahi hua. Bot ko channel -1004341107282 me Admin banao.\nError: {e}")

def search_tmdb(query):
    try:
        r = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={query}", timeout=15).json()
        if r.get("results"): return r["results"][0]
    except: pass
    return None

def find_file(query):
    q = query.lower()
    if q in movie_db: return movie_db[q]
    for name, mid in movie_db.items():
        if q in name or name in q:
            return mid
    return None

@bot.message_handler(commands=['start','help','db'])
def cmds(message):
    if message.text.startswith('/db'):
        if not movie_db:
            bot.send_message(message.chat.id, "Database khali hai. Mujhe direct movie bhejo.")
        else:
            txt = "Saved Movies:\n"
            for k in list(movie_db.keys())[:30]:
                txt += f"- {k}\n"
            bot.send_message(message.chat.id, txt)
        return
    bot.send_message(message.chat.id, "🎬 Film4you Ready!\nMovie ka naam bhejo.\n\nMovie add karne ke liye mujhe direct video/file bhejo caption ke saath.")

@bot.message_handler(func=lambda m: True)
def search_handle(message):
    if not message.text or message.text.startswith('/'): return
    query = message.text.strip()
    bot.send_chat_action(message.chat.id, 'typing')

    file_id = find_file(query)
    tmdb = search_tmdb(query)

    if not tmdb:
        if file_id:
            bot.copy_message(message.chat.id, DATABASE_CHANNEL, file_id)
            return
        bot.send_message(message.chat.id, f"'{query}' nahi mili")
        return

    title = tmdb.get('title')
    caption = f"🎬 *{title}*\n⭐ {tmdb.get('vote_average')}/10\n📅 {tmdb.get('release_date')}\n\n{tmdb.get('overview','')[:400]}"

    markup = InlineKeyboardMarkup()
    if file_id:
        caption += "\n\n✅ Download Available!"
        markup.row(InlineKeyboardButton("📥 DOWNLOAD NOW", callback_data=f"dl_{file_id}"))
    else:
        caption += "\n\n❌ Is movie ka file abhi add nahi hai."

    markup.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(title+' trailer')}"))

    poster = tmdb.get('poster_path')
    if poster:
        bot.send_photo(message.chat.id, f"https://image.tmdb.org/t/p/w500{poster}", caption=caption, reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, caption, reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
def dl(call):
    try:
        mid = int(call.data.split('_')[1])
        bot.copy_message(call.message.chat.id, DATABASE_CHANNEL, mid)
        bot.answer_callback_query(call.id, "Bhej diya ✅")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {e}")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling()
