import logging
import sqlite3
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==============================================================================
# CONFIGURATION & KEYS (Aapki Details Yahan Set Karein)
# ==============================================================================
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"      # BotFather se milne wala Bot Token
TMDB_KEY = "YOUR_TMDB_API_KEY_HERE"            # TMDB API Key
DB_CHANNEL_ID = -1001234567890                  # Apne Database Channel ka Numeric ID (-100 se shuru hota hai)
ADMIN_ID = 123456789                             # Aapka Telegram Numeric ID (Optional)

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================================================================
# DATABASE MANAGEMENT (SQLite)
# ==============================================================================
def init_db():
    """Database tables create karne ke liye."""
    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT UNIQUE,
            message_id INTEGER,
            caption TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_movie_to_db(file_name: str, message_id: int, caption: str):
    """Channel ki files ko local database me save/update karne ke liye."""
    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    clean_name = file_name.strip().lower()
    cursor.execute("""
        INSERT OR REPLACE INTO movies (file_name, message_id, caption)
        VALUES (?, ?, ?)
    """, (clean_name, message_id, caption))
    conn.commit()
    conn.close()

def search_movies_db(query: str):
    """Database me movie search karne ke liye."""
    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    search_query = f"%{query.strip().lower()}%"
    cursor.execute("""
        SELECT file_name, message_id, caption FROM movies
        WHERE file_name LIKE ? OR caption LIKE ?
        LIMIT 10
    """, (search_query, search_query))
    results = cursor.fetchall()
    conn.close()
    return results

# ==============================================================================
# TMDB API HELPER
# ==============================================================================
def fetch_tmdb_info(query: str):
    """TMDB API se movie details, rating aur poster fetch karta hai."""
    if not TMDB_KEY or TMDB_KEY == "YOUR_TMDB_API_KEY_HERE":
        return None
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={query}"
    try:
        res = requests.get(url, timeout=5).json()
        results = res.get("results", [])
        if results:
            movie = results[0]
            poster_path = movie.get("poster_path")
            return {
                "title": movie.get("title"),
                "release_date": movie.get("release_date", "N/A"),
                "rating": movie.get("vote_average", "N/A"),
                "overview": movie.get("overview", "No plot available."),
                "poster": f"https://image.tmdb.org/t5/p/w500{poster_path}" if poster_path else None
            }
    except Exception as e:
        logger.error(f"TMDB Fetch Error: {e}")
    return None

# ==============================================================================
# BOT HANDLERS & COMMANDS
# ==============================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name if update.effective_user else "User"
    msg = (
        f"👋 **Hello {user_name}!**\n\n"
        "🎬 **Welcome to World Largest Movie Search Bot!**\n\n"
        "• Group ya PM me `/search <movie_name>` type karke movie dhoondiye.\n"
        "• Direct Channel Files auto-deliver hongi."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Bot to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Database Channel me nayi ya forwarded posts/files automatically database me add hongi."""
    message = update.channel_post
    if not message or message.chat_id != DB_CHANNEL_ID:
        return

    file_name = None
    if message.document:
        file_name = message.document.file_name
    elif message.video:
        file_name = message.video.file_name
    elif message.caption:
        file_name = message.caption.split("\n")[0]

    if file_name:
        caption = message.caption or file_name
        save_movie_to_db(file_name, message.message_id, caption)
        logger.info(f"Database Updated: {file_name}")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ **Usage:** `/search <movie_name>`\nExample: `/search Avatar`", parse_mode="Markdown")
        return

    query = " ".join(context.args)
    msg = await update.message.reply_text("🔎 *Searching Movie in Database...*", parse_mode="Markdown")

    # 1. Local Database Search
    matched_files = search_movies_db(query)
    # 2. TMDB Details
    tmdb_info = fetch_tmdb_info(query)

    if not matched_files and not tmdb_info:
        await msg.edit_text("❌ **Movie nahi mili.** Kripya spelling check karke dubara search karein.")
        return

    text = ""
    if tmdb_info:
        release_yr = tmdb_info['release_date'][:4] if len(tmdb_info['release_date']) >= 4 else "N/A"
        text += (
            f"🎬 *{tmdb_info['title']}* ({release_yr})\n"
            f"⭐ **Rating:** {tmdb_info['rating']}/10\n\n"
            f"📝 {tmdb_info['overview'][:180]}...\n\n"
        )
    else:
        text += f"🔎 **Results for:** `{query}`\n\n"

    buttons = []
    if matched_files:
        text += "📂 **Available Downloads:**\n"
        for idx, (f_name, msg_id, _) in enumerate(matched_files, 1):
            btn_label = f"📁 Get Movie File #{idx}"
            buttons.append([InlineKeyboardButton(btn_label, callback_data=f"get_{msg_id}")])
    else:
        text += "⚠️ *Movie details mil gayi hain par download file DB channel me nahi hai.*"

    keyboard = InlineKeyboardMarkup(buttons) if buttons else None

    if tmdb_info and tmdb_info.get("poster"):
        await update.message.reply_photo(photo=tmdb_info["poster"], caption=text, parse_mode="Markdown", reply_markup=keyboard)
        await msg.delete()
    else:
        await msg.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def file_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⚡ Forwarding movie file...")
    msg_id = int(query.data.split("_")[1])

    try:
        await context.bot.copy_message(
            chat_id=query.message.chat_id,
            from_chat_id=DB_CHANNEL_ID,
            message_id=msg_id
        )
    except Exception as e:
        logger.error(f"Copy Message Error: {e}")
        await query.message.reply_text("❌ Error: Verification fail. Verify karein ki Bot Database Channel me Admin hai.")

# ==============================================================================
# MAIN APPLICATION RUNNER
# ==============================================================================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Register Handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("find", search_command))
    app.add_handler(CallbackQueryHandler(file_download_callback, pattern=r"^get_"))
    app.add_handler(MessageHandler(filters.Chat(DB_CHANNEL_ID), channel_post_handler))

    logger.info("Bot fully active and polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
