import os
import re
import logging
import asyncio
import sqlite3
import requests
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

# ==============================================================================
# CONFIGURATION & KEYS
# ==============================================================================
API_ID = int(os.getenv("API_ID", "1234567"))           # my.telegram.org se API ID
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")      # my.telegram.org se API Hash
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")   # BotFather Token
TMDB_KEY = os.getenv("TMDB_KEY", "YOUR_TMDB_KEY")       # TMDB API Key

DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID", "-1001234567890")) # Database Channel ID
ADMIN_ID = int(os.getenv("ADMIN_ID", "123456789"))                 # Aapki Telegram User ID

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Initialize Pyrogram Bot Client
app = Client(
    "Film4You_AutoStore_Bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Lock to handle concurrent bulk files (100+ files safely)
FILE_LOCK = asyncio.Lock()

# ==============================================================================
# DATABASE MANAGEMENT (SQLite)
# ==============================================================================
def init_db():
    conn = sqlite3.connect("movies_db.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name TEXT,
            clean_name TEXT,
            db_msg_id INTEGER,
            file_id TEXT,
            poster_url TEXT,
            caption TEXT
        )
    """)
    conn.commit()
    conn.close()

def clean_movie_title(raw_title: str) -> str:
    """Cleans movie filename to extract search query (e.g., Avatar.2009.720p.mkv -> avatar)."""
    if not raw_title:
        return ""
    # Remove file extensions
    title = re.sub(r'\.(mkv|mp4|avi|mov|flv|webm)$', '', raw_title, flags=re.IGNORECASE)
    # Remove quality terms, brackets, dots, dashes
    title = re.sub(r'[\._\-\[\}\]\(\)]', ' ', title)
    title = re.sub(r'\b(720p|1080p|4k|2160p|bluray|web-dl|hdrip|x264|x265|hevc|hindi|english|dual audio|esub|sub)\b', '', title, flags=re.IGNORECASE)
    return ' '.join(title.split()).strip().lower()

def save_to_db(file_name: str, clean_name: str, db_msg_id: int, file_id: str, poster_url: str, caption: str):
    conn = sqlite3.connect("movies_db.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO movies (file_name, clean_name, db_msg_id, file_id, poster_url, caption)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (file_name, clean_name, db_msg_id, file_id, poster_url, caption))
    conn.commit()
    conn.close()

def search_in_db(query: str):
    conn = sqlite3.connect("movies_db.db")
    cursor = conn.cursor()
    clean_q = clean_movie_title(query)
    keywords = clean_q.split()
    
    if not keywords:
        conn.close()
        return []

    sql_conditions = " AND ".join(["clean_name LIKE ?" for _ in keywords])
    params = [f"%{kw}%" for kw in keywords]

    cursor.execute(f"""
        SELECT file_name, db_msg_id, poster_url, caption FROM movies
        WHERE {sql_conditions} OR clean_name LIKE ?
        LIMIT 10
    """, (*params, f"%{clean_q}%"))

    results = cursor.fetchall()
    conn.close()
    return results

# ==============================================================================
# TMDB API HELPER
# ==============================================================================
def fetch_tmdb_details(movie_name: str):
    """Fetches official poster, title, rating, and description from TMDB."""
    if not TMDB_KEY:
        return None
    
    clean_query = clean_movie_title(movie_name)
    url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_KEY}&query={clean_query}"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            results = res.json().get("results", [])
            if results:
                movie = results[0]
                poster_path = movie.get("poster_path")
                return {
                    "title": movie.get("title", movie_name),
                    "year": movie.get("release_date", "N/A")[:4],
                    "rating": movie.get("vote_average", "N/A"),
                    "overview": movie.get("overview", "Official description not available."),
                    "poster": f"https://image.tmdb.org/t5/p/w500{poster_path}" if poster_path else None
                }
    except Exception as e:
        logger.error(f"TMDB Fetch Error: {e}")
    return None

# ==============================================================================
# BULK FILE PROCESSOR (Admin Private Upload)
# ==============================================================================
@app.on_message(filters.private & filters.user(ADMIN_ID) & (filters.document | filters.video))
async def auto_process_and_store(client: Client, message: Message):
    """Admin jab 1 ya 100 files forward/upload karega, toh auto description add karke DB channel me bhejega."""
    async with FILE_LOCK:
        # Extract File Name
        file_obj = message.document or message.video
        raw_file_name = file_obj.file_name or message.caption or "Unknown_Movie"
        clean_name = clean_movie_title(raw_file_name)

        status_msg = await message.reply_text(f"⏳ **Processing & Fetching Description...**\n📁 `{raw_file_name}`")

        # Fetch Official TMDB Description & Poster
        tmdb_info = fetch_tmdb_details(raw_file_name)

        if tmdb_info:
            formatted_caption = (
                f"🎬 **{tmdb_info['title']} ({tmdb_info['year']})**\n"
                f"⭐ **Rating:** {tmdb_info['rating']}/10\n\n"
                f"📝 **Description:**\n{tmdb_info['overview'][:300]}...\n\n"
                f"📁 **File Name:** `{raw_file_name}`\n"
                f"⚡ **Uploaded via Film4You Auto Store**"
            )
            poster_url = tmdb_info.get("poster")
        else:
            formatted_caption = (
                f"🎬 **{raw_file_name}**\n\n"
                f"📁 **File Name:** `{raw_file_name}`\n"
                f"⚡ **Uploaded via Film4You Auto Store**"
            )
            poster_url = None

        try:
            # 1. Forward/Send File to Database Channel
            sent_msg = await client.copy_message(
                chat_id=DB_CHANNEL_ID,
                from_chat_id=message.chat.id,
                message_id=message.id,
                caption=formatted_caption
            )

            # 2. Save metadata to SQLite Database
            save_to_db(
                file_name=raw_file_name,
                clean_name=clean_name,
                db_msg_id=sent_msg.id,
                file_id=file_obj.file_id,
                poster_url=poster_url,
                caption=formatted_caption
            )

            # 3. Send Notification to Admin
            await status_msg.edit_text(
                f"✅ **File Saved Successfully!**\n\n"
                f"🎬 **Title:** `{tmdb_info['title'] if tmdb_info else raw_file_name}`\n"
                f"📌 **DB Message ID:** `{sent_msg.id}`\n"
                f"📢 **Channel:** Saved in Database Channel"
            )

        except Exception as e:
            logger.error(f"Store Error: {e}")
            await status_msg.edit_text(f"❌ **Failed to Save File:** `{e}`")

# ==============================================================================
# USER SEARCH HANDLERS
# ==============================================================================
@app.on_message(filters.command("start") & (filters.private | filters.group))
async def start_handler(client: Client, message: Message):
    welcome_text = (
        f"👋 **Hello {message.from_user.first_name}!**\n\n"
        "🎬 **Welcome to Film4You Movie Bot!**\n\n"
        "Movie ka naam likh kar bhejiye ya `/search <movie_name>` command use karein."
    )
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{client.me.username}?startgroup=true")]
    ])
    await message.reply_text(welcome_text, reply_markup=buttons)

@app.on_message((filters.private | filters.group) & filters.text & ~filters.command(["start", "search"]))
async def user_search_handler(client: Client, message: Message):
    query = message.text.strip()
    results = search_in_db(query)

    if not results:
        # Fallback TMDB Info if file not in DB
        tmdb_info = fetch_tmdb_details(query)
        if tmdb_info:
            text = (
                f"🎬 **{tmdb_info['title']} ({tmdb_info['year']})**\n"
                f"⭐ **Rating:** {tmdb_info['rating']}/10\n\n"
                f"📝 **Description:**\n{tmdb_info['overview'][:250]}...\n\n"
                f"❌ **Status: Not Available in Database Channel**"
            )
            buttons = InlineKeyboardMarkup([
                [InlineKeyboardButton("🍿 Watch Trailer", url=f"https://www.youtube.com/results?search_query={query}+trailer")],
                [InlineKeyboardButton("🔍 Search Google", url=f"https://www.google.com/search?q={query}")]
            ])
            if tmdb_info.get("poster"):
                await message.reply_photo(photo=tmdb_info["poster"], caption=text, reply_markup=buttons)
            else:
                await message.reply_text(text, reply_markup=buttons)
        else:
            await message.reply_text("❌ **Movie nahi mili.** Kripya spelling check karke try karein.")
        return

    # If Movies Found in Local DB
    f_name, db_msg_id, poster_url, caption = results[0]

    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📁 Get Movie File", callback_data=f"getfile_{db_msg_id}")],
        [InlineKeyboardButton("🍿 Watch Trailer", url=f"https://www.youtube.com/results?search_query={query}+trailer")]
    ])

    if poster_url:
        await message.reply_photo(photo=poster_url, caption=caption, reply_markup=buttons)
    else:
        await message.reply_text(caption, reply_markup=buttons)

@app.on_callback_query(filters.regex(r"^getfile_"))
async def deliver_movie_file(client: Client, callback: CallbackQuery):
    msg_id = int(callback.data.split("_")[1])
    await callback.answer("⚡ Sending Movie File...")
    try:
        await client.copy_message(
            chat_id=callback.message.chat.id,
            from_chat_id=DB_CHANNEL_ID,
            message_id=msg_id
        )
    except Exception as e:
        logger.error(f"File Delivery Error: {e}")
        await callback.message.reply_text("❌ File bhejane me issue aaya. Ensure karein ki Bot Database Channel me Admin hai.")

# ==============================================================================
# MAIN APPLICATION RUNNER
# ==============================================================================
if __name__ == "__main__":
    init_db()
    app.run()
