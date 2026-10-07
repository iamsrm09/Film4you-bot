import os
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

# ----------------------------------------------------
# 1. FLASK SERVER SETUP (Replit me Bot KO Active Rakhne Ke Liye)
# ----------------------------------------------------
app = Flask('')

@app.route('/')
def home():
    return "Film4you Bot is Alive and Running!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()


# ----------------------------------------------------
# 2. TELEGRAM BOT SETUP
# ----------------------------------------------------
# Apka Bot Token (Replit Secrets / Environment Variables se lega ya direct string)
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN_HERE')
bot = telebot.TeleBot(BOT_TOKEN)


# ----------------------------------------------------
# 3. /start AUR /movie COMMAND HANDLER
# ----------------------------------------------------
@bot.message_handler(commands=['start', 'movie', 'search'])
def send_movie_response(message):
    # Caption Message Layout
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

    # Movie Poster Image Link
    photo_url = "https://m.media-amazon.com/images/M/MVBBMjA4OGM2NTEtZTRmOC00M2I2LWI3M2UtMTM2NTlhNDlhNTYxXkEyXkFqcGdeQXVyMTEzMTI1Mjk3._V1_.jpg"

    # Inline Keyboard Layout Setup
    keyboard = InlineKeyboardMarkup(row_width=2)

    # Row 1 Buttons
    btn_trailer = InlineKeyboardButton("▶️ Watch Trailer", url="https://www.youtube.com/")
    btn_where = InlineKeyboardButton("📍 Where to Watch", url="https://www.justwatch.com/")

    # Row 2 Buttons
    btn_imdb = InlineKeyboardButton("⭐ IMDb Rating", url="https://www.imdb.com/")
    btn_details = InlineKeyboardButton("🎬 Full Details", url="https://www.google.com/")

    # Row 3 Buttons (Request Movie ki jagah Filmyzilla Download Link)
    btn_google = InlineKeyboardButton("🔍 Search Google", url="https://www.google.com")
    btn_download = InlineKeyboardButton("📥 Download Movie", url="https://www.filmyzilla72.com/")

    # Adding Buttons to Keyboard
    keyboard.add(btn_trailer, btn_where)
    keyboard.add(btn_imdb, btn_details)
    keyboard.add(btn_google, btn_download)

    # Send Photo with Caption & Buttons
    bot.send_photo(
        chat_id=message.chat.id,
        photo=photo_url,
        caption=caption_text,
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# Fallback Message Handler for Text Searches
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    send_movie_response
