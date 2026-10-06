import os, threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Flask(__name__)
@app.route('/')
def home(): return "Movie Bot Alive"

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = "@TumharaChannel" # yaha apne channel ka username
bot = telebot.TeleBot(BOT_TOKEN)

# --- YE TUMHARA MOVIE DATABASE HAI ---
# Format: "code": {"file_id": "...", "name": "..."}
# file_id tumhe tab milega jab tum bot ko koi movie forward karoge, bot console me uska file_id bata dega

MOVIES = {
    "animal_2023": {
        "file_id": "BAACAgQAAxkBAA...", # isko change karna
        "name": "Animal 2023 Hindi 1080p",
        "caption": "Animal (2023) Hindi Dubbed\nQuality: 1080p\nSize: 2.1GB"
    },
    "jawan_2023": {
        "file_id": "BAACAgQAAxkBAA...2",
        "name": "Jawan 2023 Hindi",
        "caption": "Jawan (2023) Hindi\nQuality: 1080p"
    }
}

# 1. START + DEEP LINK FEATURE (Naya wala)
@bot.message_handler(commands=['start'])
def handle_start(message):
    args = message.text.split()

    # Case 1: User link se aaya hai - /start animal_2023
    if len(args) > 1:
        movie_code = args[1].lower()
        if movie_code in MOVIES:
            movie = MOVIES[movie_code]
            bot.send_message(message.chat.id, f"🎬 **{movie['name']}** mil gayi!\nBhej raha hu...", parse_mode="Markdown")
            try:
                bot.send_document(message.chat.id, movie["file_id"], caption=movie["caption"])
            except:
                bot.send_video(message.chat.id, movie["file_id"], caption=movie["caption"])
        else:
            bot.send_message(message.chat.id, "❌ Ye movie hamare database me nahi hai.")
        return

    # Case 2: Normal /start
    bot.send_message(message.chat.id,
        "🎬 **Welcome to Movie Bot!**\n\n"
        "Movie ka naam bhejo jaise `animal` ya `jawan`\n"
        "Main search karke bhej dunga.",
        parse_mode="Markdown"
    )

# 2. OLD SEARCH FEATURE
@bot.message_handler(func=lambda m: True)
def search_movie(message):
    # Agar command hai to ignore
    if message.text.startswith('/'): return

    query = message.text.lower()
    found = False

    for code, movie in MOVIES.items():
        if query in movie["name"].lower() or query in code:
            found = True
            # Deep Link Button banao
            markup = InlineKeyboardMarkup()
            deep_link = f"https://t.me/{bot.get_me().username}?start={code}"
            markup.add(InlineKeyboardButton("📥 Download / Share Link", url=deep_link))

            bot.send_message(message.chat.id,
                f"✅ **Mili Gayi:** {movie['name']}\n\n{movie['caption']}\n\n"
                f"Is link se direct download hogi:\n`{deep_link}`",
                parse_mode="Markdown",
                reply_markup=markup
            )
            # File bhi bhej do
            try:
                bot.send_document(message.chat.id, movie["file_id"], caption=movie["caption"])
            except:
                bot.send_video(message.chat.id, movie["file_id"], caption=movie["caption"])

    if not found:
        bot.send_message(message.chat.id, "❌ Movie nahi mili. Dusra naam try karo.")

# 3. File ID nikalne ke liye - jab tum admin movie bhejoge to file_id dega
@bot.message_handler(content_types=['video', 'document'])
def get_file_id(message):
    if message.video:
        fid = message.video.file_id
    else:
        fid = message.document.file_id
    bot.reply_to(message, f"File ID:\n`{fid}`\n\nIsko MOVIES me daal do.", parse_mode="Markdown")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling(none_stop=True)
