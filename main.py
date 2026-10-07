import os
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
import time

app = Flask('')
@app.route('/')
def home():
    return "Film4you Bot is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN missing")

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)

# Welcome handler
@bot.message_handler(content_types=['new_chat_members'])
def welcome(message):
    for user in message.new_chat_members:
        bot.send_message(message.chat.id, f"Hey {user.first_name} 👋 Welcome to {message.chat.title}!\nMovie ka naam bhejo 🎬", parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "🎬 *Film4you Bot Live Hai!*\n\nKoi bhi movie ka naam bhejo.\nExample: Pushpa, KGF", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def all_movies(message):
    query = message.text.replace('/start','').replace('/movie','').strip()
    if not query:
        return start(message)
    
    caption = f"🎬 *{query}*\n⭐ *Rating:* 8.5/10\n\n📝 *Story:* Search result for {query}\n\n✅ Details Found!"
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={query}+trailer"),
        InlineKeyboardButton("📍 Where to Watch", url=f"https://www.justwatch.com/in/search?q={query}")
    )
    markup.add(
        InlineKeyboardButton("⭐ IMDb", url=f"https://www.imdb.com/find?q={query}"),
        InlineKeyboardButton("🎬 Google", url=f"https://www.google.com/search?q={query}+movie")
    )
    markup.add(
        InlineKeyboardButton("📥 Filmyzilla", url=f"https://www.filmyzilla72.com/movie/movie_id/movie_slug}"),
        InlineKeyboardButton("📥 Cinevood", url=f"https://cinevood.com/in/search?q={query}")
    )

    try:
        bot.send_message(message.chat.id, caption, parse_mode="Markdown", reply_markup=markup)
    except Exception as e:
        print(e)

if name == "main":
    keep_alive()
    print("Removing webhook and starting polling...")
    try:
        bot.remove_webhook()
        time.sleep(2)
    except:
        pass
    # Ye line sabse important hai - 409 error fix
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)

Is code me kuch change nhi Krna sirf english version Krna h
