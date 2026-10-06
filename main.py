import os, threading, logging, json, time, io, re
from flask import Flask
import telebot, requests
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus
from PIL import Image

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot Alive"

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_CHANNEL = -1004341107282
TMDB_KEY = os.getenv("TMDB_KEY") or os.getenv("TMDB_TOKEN")

bot = telebot.TeleBot(BOT_TOKEN)

DB_FILE = "movies.json"
movie_db = {}
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, 'r') as f:
            movie_db = json.load(f)
    except:
        pass

def save_db():
    with open(DB_FILE, 'w') as f:
        json.dump(movie_db, f)

def search_tmdb(query):
    try:
        clean_q = query.split('.')[0].replace('_',' ').strip()
        r = requests.get(f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={quote_plus(clean_q)}", timeout=15).json()
        if r.get("results"):
            return r["results"][0]
    except Exception as e:
        print(f"TMDB Error: {e}")
    return None

def find_file(query):
    q = query.lower().strip()
    if q in movie_db:
        return movie_db[q]

    best_match = None
    best_score = 0

    for name, mid in movie_db.items():
        name_low = name.lower()
        if q == name_low:
            return mid

        q_words = q.split()
        score = 0
        for word in q_words:
            if word in name_low:
                score += 1

        if score == len(q_words):
            q_num = re.findall(r'\d+', q)
            name_num = re.findall(r'\d+', name_low)

            if q_num and name_num:
                if q_num[0] == name_num[0]:
                    return mid
                else:
                    continue

            if score > best_score:
                best_score = score
                best_match = mid

    return best_match

@bot.message_handler(content_types=['document', 'video'])
def handle_file(message):
    raw_name = message.caption or (message.document.file_name if message.document else "video")
    clean_name = raw_name.split('.')[0].replace('_',' ').replace('-',' ').strip()

    tmdb = search_tmdb(clean_name)

    try:
        thumb_path = None
        final_caption = f"🎬 {raw_name}"

        if tmdb:
            title = tmdb.get('title', clean_name)
            rating = tmdb.get('vote_average', 'N/A')
            date = tmdb.get('release_date', 'N/A')
            overview = tmdb.get('overview', '')[:800]
            final_caption = f"🎬 {title}\n⭐ Rating: {rating}/10\n📅 Release: {date}\n\n{overview}"

            poster = tmdb.get('poster_path')
            if poster:
                try:
                    url = f"https://image.tmdb.org/t/p/w500{poster}"
                    data = requests.get(url, timeout=20).content
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                    img.thumbnail((320, 320))
                    img.save("thumb.jpg", "JPEG", quality=80)
                    thumb_path = "thumb.jpg"
                except Exception as e:
                    print(f"Thumb error: {e}")
                    thumb_path = None

        thumb_file = open(thumb_path, "rb") if thumb_path and os.path.exists(thumb_path) else None

        sent = None
        for attempt in range(4):
            try:
                if message.document:
                    sent = bot.send_document(DATABASE_CHANNEL, message.document.file_id, thumb=thumb_file, caption=final_caption)
                else:
                    sent = bot.send_video(DATABASE_CHANNEL, message.video.file_id, thumb=thumb_file, caption=final_caption, supports_streaming=True)
                break
            except Exception as e:
                err = str(e)
                if "429" in err or "Too Many Requests" in err:
                    wait_time = 15
                    try:
                        if "retry after" in err:
                            wait_time = int(err.split("retry after ")[1].split()[0]) + 2
                    except:
                        wait_time = 15
                    print(f"Flood limit, waiting {wait_time}s attempt {attempt+1}")
                    time.sleep(wait_time)
                    continue
                else:
                    raise e

        if thumb_file:
            try:
                thumb_file.close()
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
            except:
                pass

        if not sent:
            bot.reply_to(message, "Telegram is busy (429). Please try again after 1 minute.")
            return

        movie_db[raw_name.lower()] = sent.message_id
        movie_db[clean_name.lower()] = sent.message_id
        save_db()

        bot.reply_to(message, f"Saved: {clean_name}\nNow thumbnail + description will come on download.")

    except Exception as e:
        print(f"Handle file error: {e}")
        bot.reply_to(message, f"Failed: {e}")

@bot.message_handler(commands=['start','help'])
def welcome(message):
    text = (
        "🎬 Welcome to Film4you Bot!\n\n"
        "Just send me any movie name and I will send you the movie.\n\n"
        "Example: KGF 2, Avatar 2, Pathaan\n\n"
        "Search is now 100% accurate for parts like KGF 1 and KGF 2."
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['db'])
def db_cmd(message):
    if not movie_db:
        bot.send_message(message.chat.id, "Database is empty. Send me a movie file directly.")
    else:
        txt = "Saved Movies:\n"
        for k in list(movie_db.keys())[:30]:
            txt += f"- {k}\n"
        bot.send_message(message.chat.id, txt)

@bot.message_handler(func=lambda m: True)
def search_handle(message):
    if not message.text or message.text.startswith('/'):
        return
    query = message.text.strip()
    bot.send_chat_action(message.chat.id, 'typing')

    file_id = find_file(query)
    tmdb = search_tmdb(query)

    if not tmdb:
        if file_id:
            bot.copy_message(message.chat.id, DATABASE_CHANNEL, file_id)
            return
        bot.send_message(message.chat.id, f"'{query}' not found in database.")
        return

    title = tmdb.get('title')
    overview = tmdb.get('overview','')[:400]
    caption = f"🎬 {title}\n⭐ {tmdb.get('vote_average')}/10\n📅 {tmdb.get('release_date')}\n\n{overview}"

    markup = InlineKeyboardMarkup()
    if file_id:
        caption += "\n\n✅ Download Available!"
        markup.row(InlineKeyboardButton("📥 DOWNLOAD NOW", callback_data=f"dl_{file_id}"))
    else:
        caption += "\n\n❌ File for this movie is not added yet."

    markup.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(title+' trailer')}"))

    poster = tmdb.get('poster_path')
    if poster:
        bot.send_photo(message.chat.id, f"https://image.tmdb.org/t/p/w500{poster}", caption=caption, reply_markup=markup)
    else:
        bot.send_message(message.chat.id, caption, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('dl_'))
def dl(call):
    try:
        mid = int(call.data.split('_')[1])
        bot.copy_message(call.message.chat.id, DATABASE_CHANNEL, mid)
        bot.answer_callback_query(call.id, "File sent")
    except Exception as e:
        bot.answer_callback_query(call.id, f"Error: {e}")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling(none_stop=True, interval=2, timeout=60)
