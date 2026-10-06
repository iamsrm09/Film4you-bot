import os
import time
import threading
from flask import Flask
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

app = Flask(__name__)
@app.route('/')
def home():
    return "Movie Bot Running"

BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# ================= OLD MOVIE DATABASE - SAME FORMAT =================
MOVIES = {
    "animal": {
        "file_id": "BAACAgQAAxkBAA...", # Replace with your real file_id
        "name": "Animal 2023",
        "caption": (
            "🎬 **Movie: Animal (2023)**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📀 Quality: 1080p HDRip\n"
            "🔊 Language: Hindi Dubbed\n"
            "⭐ IMDb Rating: 7.2/10\n"
            "📁 Size: 2.1GB\n"
            "🎭 Genre: Action, Crime\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⏰ Note: File will auto-delete in 10 minutes\n"
            "💾 Please save/forward it"
        )
    },
    "jawan": {
        "file_id": "BAACAgQAAxkBAA...2",
        "name": "Jawan 2023",
        "caption": (
            "🎬 **Movie: Jawan (2023)**\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📀 Quality: 1080p HDRip\n"
            "🔊 Language: Hindi\n"
            "⭐ IMDb Rating: 7.5/10\n"
            "📁 Size: 1.9GB\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "⏰ Note: Auto-delete in 10 minutes"
        )
    }
}
# ===================================================================

def delete_after_10_min(chat_id, message_id):
    time.sleep(600) # 600 seconds = 10 minutes
    try:
        bot.delete_message(chat_id, message_id)
        bot.send_message(chat_id, "⏰ File auto-deleted after 10 minutes. Search again or click poster link to get it back.")
    except Exception as e:
        print(e)

@bot.message_handler(commands=['start'])
def handle_start(message):
    parts = message.text.split()

    # NEW FEATURE: Deep link from poster - /start animal
    if len(parts) > 1:
        code = parts[1].lower()
        if code in MOVIES:
            movie = MOVIES[code]
            sent_msg = bot.send_document(
                message.chat.id,
                movie["file_id"],
                caption=movie["caption"],
                parse_mode="Markdown"
            )
            threading.Thread(target=delete_after_10_min, args=(message.chat.id, sent_msg.message_id), daemon=True).start()
            return
        else:
            bot.send_message(message.chat.id, "Movie not found.")
            return

    bot.send_message(message.chat.id, "👋 Welcome!\n\nSend movie name like `animal` or `jawan`", parse_mode="Markdown")

@bot.message_handler(content_types=['text'])
def handle_search(message):
    if message.text.startswith('/'):
        return

    query = message.text.lower().strip()

    for code, movie in MOVIES.items():
        if query in movie["name"].lower() or query == code:

            # Deep link for poster button
            bot_username = bot.get_me().username
            deep_link = f"https://t.me/{bot_username}?start={code}"

            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📥 Direct Download Link", url=deep_link))

            # OLD FORMAT: Send with full caption + details
            sent_msg = bot.send_document(
                message.chat.id,
                movie["file_id"],
                caption=movie["caption"],
                parse_mode="Markdown",
                reply_markup=markup
            )

            # Auto delete after 10 min
            threading.Thread(target=delete_after_10_min, args=(message.chat.id, sent_msg.message_id), daemon=True).start()
            return

    bot.send_message(message.chat.id, "❌ Movie not found. Try: animal, jawan")

# Helper to get file_id
@bot.message_handler(content_types=['video', 'document'])
def handle_file(message):
    fid = message.video.file_id if message.video else message.document.file_id
    bot.reply_to(message, f"File ID:\n`{fid}`", parse_mode="Markdown")

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    bot.infinity_polling(none_stop=True)
