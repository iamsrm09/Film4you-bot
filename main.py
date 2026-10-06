import os
import time
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Keep bot alive for Render
app = Flask(__name__)
@app.route('/')
def home():
    return "Movie Bot is Running!"

# YOUR BOT TOKEN FROM ENV
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# ================= MOVIE DATABASE =================
# To get file_id: Send any movie to this bot, it will reply with file_id
# Then copy that file_id here
MOVIES = {
    "animal_2023": {
        "file_id": "BAACAgQAAxkBA...",
        "name": "Animal 2023",
        "caption": "🎬 Animal (2023) Hindi 1080p\n\nQuality: 1080p\nSize: 2.1GB\n\n⏰ Note: This file will auto-delete in 10 minutes. Save it!"
    },
    "jawan_2023": {
        "file_id": "BAACAgQAAxkBB...",
        "name": "Jawan 2023",
        "caption": "🎬 Jawan (2023) Hindi 1080p\n\n⏰ Note: Auto-delete in 10 minutes"
    }
}
# ===================================================

def auto_delete_message(chat_id, message_id, delay=600):
    """Delete message after delay (600 sec = 10 min)"""
    time.sleep(delay)
    try:
        bot.delete_message(chat_id, message_id)
        bot.send_message(chat_id, "⏰ File deleted after 10 mins.\nTo get again, click the poster button or search again.")
    except Exception as e:
        print(f"Delete error: {e}")

# 1. /start COMMAND + DEEP LINK
@bot.message_handler(commands=['start'])
def start_command(message):
    args = message.text.split()

    # If user came from poster link: /start animal_2023
    if len(args) > 1:
        movie_code = args[1].lower()
        if movie_code in MOVIES:
            movie = MOVIES[movie_code]
            sent = bot.send_document(
                message.chat.id,
                movie["file_id"],
                caption=movie["caption"]
            )
            # Start auto-delete timer
            threading.Thread(target=auto_delete_message, args=(message.chat.id, sent.message_id, 600), daemon=True).start()
        else:
            bot.send_message(message.chat.id, "❌ Movie not found in database.")
        return

    # Normal /start
    bot.send_message(message.chat.id,
        "👋 Welcome to Movie Bot!\n\n"
        "Just send movie name like:\n"
        "`animal` or `jawan`\n\n"
        "I will send you the movie.",
        parse_mode="Markdown"
    )

# 2. SEARCH MOVIE BY NAME
@bot.message_handler(content_types=['text'])
def search_handler(message):
    if message.text.startswith('/'):
        return

    query = message.text.lower().strip()
    found = False

    for code, movie in MOVIES.items():
        if query in code.lower() or query in movie["name"].lower():
            found = True
            # Create deep link for sharing
            bot_username = bot.get_me().username
            deep_link = f"https://t.me/{bot_username}?start={code}"

            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📥 Get Download Link", url=deep_link))

            bot.send_message(message.chat.id, f"✅ Found: {movie['name']}\nShareable Link: {deep_link}", reply_markup=markup)

            sent = bot.send_document(message.chat.id, movie["file_id"], caption=movie["caption"])
            threading.Thread(target=auto_delete_message, args=(message.chat.id, sent.message_id, 600), daemon=True).start()
            break

    if not found:
        bot.send_message(message.chat.id, "❌ Not found. Try another name.")

# 3. GET FILE_ID WHEN YOU SEND MOVIE
@bot.message_handler(content_types=['video', 'document'])
def get_file_id_handler(message):
    file_id = message.video.file_id if message.video else message.document.file_id
    bot.reply_to(message, f"Your File ID is:\n`{file_id}`\n\nCopy this and paste in MOVIES dict.", parse_mode="Markdown")

# RUN
def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("Bot Started...")
    bot.infinity_polling(none_stop=True, skip_pending=True)
