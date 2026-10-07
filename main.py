import logging
import sqlite3
import requests
import re
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
# CONFIGURATION & KEYS
# ==============================================================================
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"      # Aapka Bot Token
TMDB_KEY = "YOUR_TMDB_API_KEY_HERE"            # TMDB API Key
DB_CHANNEL_ID = -1001234567890                  # Database Channel Numeric ID

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================================================================
# DATABASE MANAGEMENT
# ==============================================================================
def init_db():
    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT UNIQUE,
            clean_name TEXT,
            message_id INTEGER,
            caption TEXT
        )
    """)
    conn.commit()
    conn.close()

def clean_text(text: str) -> str:
    """Special characters aur spaces ko clean karne ke liye."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[\._\-\[\}\]\(\)]', ' ', text)
    return ' '.join(text.split())

def save_movie_to_db(file_name: str, message_id: int, caption: str):
    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    c_name = clean_text(file_name)
    cursor.execute("""
        INSERT OR REPLACE INTO movies (file_name, clean_name, message_id, caption)
        VALUES (?, ?, ?, ?)
    """, (file_name, c_name, message_id, caption))
    conn.commit()
    conn.close()

def search_movies_db(query: str):
    conn = sqlite3.connect("movies.db")
    cursor = conn.cursor()
    clean_q = clean_text(query)
    
    # Flexible keyword matching
    keywords = clean_q.split()
    sql_conditions = " AND ".join(["clean_name LIKE ?" for _ in keywords])
    params = [f"%{kw}%" for kw in keywords]
    
    cursor.execute(f"""
        SELECT file_name, message_id, caption FROM movies
        WHERE {sql_conditions} OR clean_name LIKE ?
        LIMIT 10
    """, (*params, f"%{clean_q}%"))
    
    results = cursor.fetchall()
    conn.close()
    return results

# ==============================================================================
# TMDB API HELPER
# ==============================================================================
def fetch_tmdb_info(query: str):
    if not TMDB_KEY or TMDB_KEY == "YOUR_TMDB_API_KEY_HERE":
        return None
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={query}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            results = data.get("results", [])
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
# BOT HANDLERS
# ==============================================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name if update.effective_user else "User"
    msg = (
        f"👋 **Hello {user_name}!**\n\n"
        "🎬 **Welcome to Film4You Movie Search Bot!**\n\n"
        "• Kisi bhi movie ka naam likh kar bhejiye ya `/search <movie_name>` use karein."
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Bot to Group", url=f"https://t.me/{context.bot.username}?startgroup=true")]
    ])
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=keyboard)

async def channel_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def process_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str):
    try:
        # Search Local DB
        matched_files = search_movies_db(query)
        # Fetch TMDB Details
        tmdb_info = fetch_tmdb_info(query)

        if not matched_files and not tmdb_info:
            await update.message.reply_text("❌ **Movie nahi mili.** Kripya spelling check karke dubara try karein.")
            return

        text = ""
        if tmdb_info:
            release_yr = tmdb_info['release_date'][:4] if len(tmdb_info['release_date']) >= 4 else "N/A"
            text += (
                f"🎬 *{tmdb_info['title']}* ({release_yr})\n"
                f"⭐ **Rating:** {tmdb_info['rating']}/10\n\n"
                f"📝 {tmdb_info['overview'][:200]}...\n\n"
            )
        else:
            text += f"🔎 **Results for:** `{query}`\n\n"

        buttons = []
        if matched_files:
            text += "📂 **Available Downloads:**\n"
            for idx, (f_name, msg_id, _) in enumerate(matched_files, 1):
                btn_label = f"📁 Download File #{idx} ({f_name[:20]}...)"
                buttons.append([InlineKeyboardButton(btn_label, callback_data=f"get_{msg_id}")])
        else:
            text += "❌ **Status: Not Available in Database**\n💡 Request to Admin for upload."

        keyboard = InlineKeyboardMarkup(buttons) if buttons else None

        if tmdb_info and tmdb_info.get("poster"):
            await update.message.reply_photo(photo=tmdb_info["poster"], caption=text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Search Handler Error: {e}")
        await update.message.reply_text("⚠️ Processing me error aaya, kripya dubara try karein.")

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ **Usage:** `/search <movie_name>`", parse_mode="Markdown")
        return
    query = " ".join(context.args)
    await process_search(update, context, query)

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.text:
        if update.message.text.startswith("/"):
            return
        await process_search(update, context, update.message.text.strip())

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
        await query.message.reply_text("❌ Error: Verify karein ki Bot Database Channel me Admin hai.")

# ==============================================================================
# MAIN EXECUTION
# ==============================================================================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("find", search_command))
    app.add_handler(CallbackQueryHandler(file_download_callback, pattern=r"^get_"))
    app.add_handler(MessageHandler(filters.Chat(DB_CHANNEL_ID), channel_post_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, text_message_handler))

    logger.info("Bot fully running...")
    app.run_polling()

if __name__ == "__main__":
    main()
