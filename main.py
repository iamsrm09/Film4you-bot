import os
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# ----------------------------------------------------
# 1. FLASK SERVER SETUP (Render dynamic PORT fixed)
# ----------------------------------------------------
app = Flask('')

@app.route('/')
def home():
    return "Film4you Bot is Alive and Running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()

# ----------------------------------------------------
# 2. TELEGRAM BOT SETUP
# ----------------------------------------------------
BOT_TOKEN = os.environ.get('BOT_TOKEN')

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN not found in Environment Variables!")
    # Don't crash immediately, keep Flask alive to see logs
    raise SystemExit("BOT_TOKEN missing")

bot = telebot.TeleBot(BOT_TOKEN)

# ----------------------------------------------------
# 3. HANDLERS
# ----------------------------------------------------
@bot.message_handler(commands=['start', 'movie', 'search'])
def send_movie_response(message):
    caption_text = (
        "🎬 *Vinland Saga (2019)*\n"
        "⭐ *Rating:* 8.5/10\n\n"
        "📝 *Story:*\n"
        "For a thousand years, the Vikings have made quite a name and reputation "
        "for themselves as the strongest families with a thirst for violence. "
        "Thorfinn, the son of one of the Vikings' greatest warriors, spends his "
        "boyhood in a battlefield enhancing his skills in his adventure to redeem "
        "his most-desired revenge after his father was murdered....\n\n"
        "❌ *Status:* Not Available in Database\n"
        "💡 *Request to:* @Iamsrm0\n\n"
        "👇 *Check Options Below*"
    )
    photo_url = "https://i.imgur.com/3j3U2i8.jpeg"
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    btn_trailer = InlineKeyboardButton("▶️ Watch Trailer", url="https://www.youtube.com/")
    btn_where = InlineKeyboardButton("📍 Where to Watch", url="https://www.justwatch.com/")
    btn_imdb = InlineKeyboardButton("⭐ IMDb Rating", url="https://www.imdb.com/")
    btn_details = InlineKeyboardButton("🎬 Full Details", url="https://www.google.com/")
    btn_download1 = InlineKeyboardButton("📥 Filmyzilla Link", url="https://www.filmyzilla72.com/")
    btn_download2 = InlineKeyboardButton("📥 Cinevood Link", url="https://cinevood.com/")
    
    keyboard.add(btn_trailer, btn_where)
    keyboard.add(btn_imdb, btn_details)
    keyboard.add(btn_download1, btn_download2)

    try:
        bot.send_photo(
            chat_id=message.chat.id,
            photo=photo_url,
            caption=caption_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Photo send error: {e}")
        bot.send_message(
            chat_id=message.chat.id,
            text=caption_text,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    send_movie_response(message)

# ----------------------------------------------------
# 4. MAIN EXECUTION - THIS WAS MISSING
# ----------------------------------------------------
if __name__ == "__main__":
    keep_alive()
    print("Flask started, now starting bot polling...")
    # infinity_polling will keep the process alive
    bot.infinity_polling(skip_pending=True)
