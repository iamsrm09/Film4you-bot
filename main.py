import os
import re
import sqlite3
import logging
from pathlib import Path

import httpx
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ChatType
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ============================================================
# CONFIG
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TMDB_TOKEN = os.getenv("TMDB_TOKEN")

ARCHIVE_CHANNEL_ID = int(
    os.getenv("ARCHIVE_CHANNEL_ID", "-1001004341107282")
)

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
}

DATABASE = os.getenv("DATABASE", "movies.db")

TMDB_BASE = "https://api.themoviedb.org/3"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing in .env")

if not TMDB_TOKEN:
    raise RuntimeError("TMDB_TOKEN missing in .env")


# ============================================================
# LOGGING
# ============================================================

Path("logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("Film4you")


# ============================================================
# DATABASE
# ============================================================

def db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tmdb_id INTEGER,
            title TEXT NOT NULL,
            original_title TEXT,
            year TEXT,
            message_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(channel_id, message_id)
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_movies_title
        ON movies(title)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_movies_tmdb
        ON movies(tmdb_id)
    """)

    conn.commit()
    conn.close()


def save_movie(
    title,
    message_id,
    channel_id,
    tmdb_id=None,
    original_title=None,
    year=None,
):
    conn = db()

    try:
        conn.execute("""
            INSERT OR IGNORE INTO movies
            (
                tmdb_id,
                title,
                original_title,
                year,
                message_id,
                channel_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            tmdb_id,
            title,
            original_title,
            year,
            message_id,
            channel_id,
        ))

        conn.commit()

    except Exception:
        logger.exception("Failed to save movie")

    finally:
        conn.close()


def find_movie(query):
    conn = db()

    row = conn.execute("""
        SELECT *
        FROM movies
        WHERE title LIKE ?
           OR original_title LIKE ?
        ORDER BY id DESC
        LIMIT 1
    """, (
        f"%{query}%",
        f"%{query}%",
    )).fetchone()

    conn.close()
    return row


def movie_count():
    conn = db()

    count = conn.execute(
        "SELECT COUNT(*) FROM movies"
    ).fetchone()[0]

    conn.close()

    return count


# ============================================================
# HELPERS
# ============================================================

def is_admin(user_id):
    return user_id in ADMIN_IDS


def extract_year(text):
    if not text:
        return None

    match = re.search(r"\b(19|20)\d{2}\b", text)

    if match:
        return match.group(0)

    return None


def clean_title(text):
    if not text:
        return ""

    text = re.sub(
        r"https?://\S+",
        "",
        text
    )

    text = re.sub(
        r"[@#]\S+",
        "",
        text
    )

    text = re.sub(
        r"\b(1080p|720p|480p|2160p|4k|web[- ]?dl|webrip|bluray|"
        r"x264|x265|h264|h265|hevc|hdr|dual audio|"
        r"multi audio|hindi|english)\b",
        "",
        text,
        flags=re.I,
    )

    text = re.sub(
        r"[\[\]\(\)\{\}_|]+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# TMDB
# ============================================================

async def tmdb_search(query):
    headers = {
        "Authorization": f"Bearer {TMDB_TOKEN}",
        "accept": "application/json",
    }

    params = {
        "query": query,
        "include_adult": "false",
        "language": "en-US",
        "page": 1,
    }

    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(
            f"{TMDB_BASE}/search/movie",
            headers=headers,
            params=params,
        )

        response.raise_for_status()

        data = response.json()

    return data.get("results", [])


# ============================================================
# START / WELCOME
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    name = user.first_name or "Friend"

    text = f"""
🎬 <b>Welcome {name}!</b>

━━━━━━━━━━━━━━━━━━
🍿 <b>Film4you Movie Bot</b>
━━━━━━━━━━━━━━━━━━

🔎 Send me a movie name and I'll search for it.

You can get:

🎬 Movie information
⭐ Rating
📅 Release year
📝 Story
🎞 Trailer
📥 Available authorized content

━━━━━━━━━━━━━━━━━━
💡 <b>Example:</b>
<code>Spider-Man</code>

Enjoy! 🍿
"""

    await update.message.reply_text(
        text,
        parse_mode="HTML",
    )


# ============================================================
# ARCHIVE CHANNEL INDEXER
# ============================================================

async def archive_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.channel_post

    if not message:
        return

    if message.chat.id != ARCHIVE_CHANNEL_ID:
        return

    raw_text = (
        message.caption
        or message.text
        or ""
    )

    if not raw_text:
        return

    title = clean_title(raw_text)

    if not title:
        return

    year = extract_year(raw_text)

    try:
        results = await tmdb_search(title)

        tmdb_id = None
        original_title = None
        final_title = title

        if results:
            movie = results[0]

            tmdb_id = movie.get("id")
            original_title = movie.get("original_title")

            if movie.get("title"):
                final_title = movie["title"]

            if movie.get("release_date"):
                year = movie["release_date"][:4]

        save_movie(
            title=final_title,
            original_title=original_title,
            year=year,
            tmdb_id=tmdb_id,
            message_id=message.message_id,
            channel_id=message.chat.id,
        )

        logger.info(
            "Indexed: %s | message=%s",
            final_title,
            message.message_id,
        )

    except Exception:
        logger.exception(
            "Archive indexing failed"
        )


# ============================================================
# MOVIE SEARCH
# ============================================================

async def search_movie(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    query = update.message.text.strip()

    if len(query) < 2:
        return

    # Don't process commands
    if query.startswith("/"):
        return

    try:

        results = await tmdb_search(query)

        if not results:
            await update.message.reply_text(
                "❌ Movie nahi mili.\n\n"
                "Dusra naam try karein."
            )
            return

        movie = results[0]

        title = movie.get(
            "title",
            query
        )

        overview = movie.get(
            "overview",
            "Story available nahi hai."
        )

        rating = movie.get(
            "vote_average",
            0
        )

        release_date = movie.get(
            "release_date",
            ""
        )

        year = (
            release_date[:4]
            if release_date
            else "N/A"
        )

        archive = find_movie(title)

        if archive:

            callback = (
                f"dl:{archive['id']}:{update.message.message_id}"
            )

            keyboard = [
                [
                    InlineKeyboardButton(
                        "📥 Download",
                        callback_data=callback,
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⭐ IMDb/TMDB Rating",
                        callback_data=f"info:{movie['tmdb_id'] if 'tmdb_id' in movie else movie['id']}",
                    )
                ],
            ]

            status = "✅ Available"

        else:

            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔎 Search Google",
                        url=(
                            "https://www.google.com/search?q="
                            + title.replace(" ", "+")
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "📩 Request Movie",
                        callback_data="request",
                    )
                ],
            ]

            status = "❌ Not Available in Database"

        text = f"""
🎬 <b>{title}</b> ({year})

⭐ <b>Rating:</b> {float(rating):.1f}/10

📝 <b>Story:</b>
{overview[:900]}

━━━━━━━━━━━━━━━━━━

📌 <b>Status:</b> {status}

👇 <b>Options:</b>
"""

        await update.message.reply_text(
            text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )

    except Exception:
        logger.exception(
            "Movie search failed"
        )

        await update.message.reply_text(
            "⚠️ Search karte waqt error aa gaya.\n"
            "Thodi der baad dobara try karein."
        )


# ============================================================
# DOWNLOAD BUTTON
# ============================================================

async def download_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

        parts = query.data.split(":")

        if len(parts) != 3:
            return

        _, db_id, request_message_id = parts

        conn = db()

        movie = conn.execute("""
            SELECT *
            FROM movies
            WHERE id = ?
        """, (
            int(db_id),
        )).fetchone()

        conn.close()

        if not movie:
            await query.message.reply_text(
                "❌ Movie database me nahi mili."
            )
            return

        # Copy the authorized archive message
        # back into the same chat as a reply.
        await context.bot.copy_message(
            chat_id=query.message.chat.id,
            from_chat_id=movie["channel_id"],
            message_id=movie["message_id"],
            reply_to_message_id=int(
                request_message_id
            ),
        )

    except Exception:
        logger.exception(
            "Copy/download callback failed"
        )

        await query.message.reply_text(
            "⚠️ Content send nahi ho saka.\n"
            "Admin ko inform karein."
        )


# ============================================================
# REQUEST BUTTON
# ============================================================

async def request_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    await query.message.reply_text(
        "📩 <b>Movie Request</b>\n\n"
        "Movie ka exact naam bhej dein.\n"
        "Admin usse review karega.",
        parse_mode="HTML",
    )


# ============================================================
# ADMIN COMMANDS
# ============================================================

async def stats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    count = movie_count()

    await update.message.reply_text(
        f"""
👑 <b>Admin Panel</b>

🎬 Indexed Movies: <b>{count}</b>

🗄 Database: <code>{DATABASE}</code>

🤖 Bot: <b>Online</b>
""",
        parse_mode="HTML",
    )


async def myid(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        f"🆔 Your Telegram ID:\n<code>{update.effective_user.id}</code>",
        parse_mode="HTML",
    )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Unhandled exception:",
        exc_info=context.error,
    )


# ============================================================
# MAIN
# ============================================================

def main():

    init_db()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "stats",
            stats
        )
    )

    application.add_handler(
        CommandHandler(
            "myid",
            myid
        )
    )

    # Archive channel posts
    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST,
            archive_post,
        )
    )

    # Download button
    application.add_handler(
        CallbackQueryHandler(
            download_callback,
            pattern=r"^dl:",
        )
    )

    # Request button
    application.add_handler(
        CallbackQueryHandler(
            request_callback,
            pattern=r"^request$",
        )
    )

    # Group/private movie search
    application.add_handler(
        MessageHandler(
            filters.TEXT
            & ~filters.COMMAND,
            search_movie,
        )
    )

    application.add_error_handler(
        error_handler
    )

    logger.info(
        "Film4you bot starting..."
    )

    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=False,
    )


if __name__ == "__main__":
    main()
