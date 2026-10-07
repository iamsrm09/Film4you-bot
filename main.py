import os
import re
import sqlite3
import logging
import unicodedata
from pathlib import Path
from difflib import SequenceMatcher

import httpx
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
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

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TMDB_TOKEN = os.getenv("TMDB_TOKEN", "").strip()

ARCHIVE_CHANNEL_ID = int(
    os.getenv("ARCHIVE_CHANNEL_ID", "-1004341107282")
)

DATABASE = os.getenv("DATABASE", "movies.db")

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip()
}

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
        logging.FileHandler(
            "logs/bot.log",
            encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger("Film4you")


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(
        DATABASE,
        timeout=30
    )

    conn.row_factory = sqlite3.Row

    return conn


def init_db():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            title TEXT NOT NULL,
            normalized_title TEXT NOT NULL,

            original_title TEXT,
            year TEXT,

            tmdb_id INTEGER,

            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(channel_id, message_id)
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_movies_normalized_title
        ON movies(normalized_title)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_movies_tmdb_id
        ON movies(tmdb_id)
    """)

    conn.commit()
    conn.close()

    logger.info("Database initialized")


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_title(text: str) -> str:

    if not text:
        return ""

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    # Remove URLs
    text = re.sub(
        r"https?://\S+",
        " ",
        text,
        flags=re.I
    )

    # Remove common release tags
    text = re.sub(
        r"""
        \b(
            2160p|
            1080p|
            720p|
            480p|
            360p|
            4k|
            web[-_. ]?dl|
            web[-_. ]?rip|
            bluray|
            blu[-_. ]?ray|
            brrip|
            hdr|
            x264|
            x265|
            h264|
            h265|
            hevc|
            dv|
            dual[-_. ]?audio|
            multi[-_. ]?audio|
            hindi|
            english|
            tamil|
            telugu
        )\b
        """,
        " ",
        text,
        flags=re.I | re.X
    )

    # Year
    text = re.sub(
        r"\b(19|20)\d{2}\b",
        " ",
        text
    )

    # Remove emojis/special chars
    text = re.sub(
        r"[^\w\s]",
        " ",
        text,
        flags=re.UNICODE
    )

    text = text.lower()

    # Remove extra spaces
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def display_title(text: str) -> str:

    if not text:
        return ""

    text = re.sub(
        r"https?://\S+",
        "",
        text,
        flags=re.I
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def extract_year(text: str):

    if not text:
        return None

    match = re.search(
        r"\b(19|20)\d{2}\b",
        text
    )

    if match:
        return match.group(0)

    return None


# ============================================================
# DATABASE SAVE
# ============================================================

def save_movie(
    title,
    message_id,
    channel_id,
    tmdb_id=None,
    original_title=None,
    year=None,
):

    clean = display_title(title)

    normalized = normalize_title(clean)

    if not normalized:
        return False

    conn = get_db()

    try:

        conn.execute("""
            INSERT INTO movies (
                title,
                normalized_title,
                original_title,
                year,
                tmdb_id,
                channel_id,
                message_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(channel_id, message_id)
            DO UPDATE SET

                title = excluded.title,
                normalized_title =
                    excluded.normalized_title,

                original_title =
                    excluded.original_title,

                year =
                    excluded.year,

                tmdb_id =
                    excluded.tmdb_id
        """, (
            clean,
            normalized,
            original_title,
            year,
            tmdb_id,
            channel_id,
            message_id,
        ))

        conn.commit()

        logger.info(
            "INDEXED | %s | msg=%s",
            clean,
            message_id
        )

        return True

    except Exception:
        logger.exception(
            "Database save failed"
        )

        return False

    finally:
        conn.close()


# ============================================================
# DATABASE SEARCH
# ============================================================

def search_database(query):

    normalized_query = normalize_title(
        query
    )

    if not normalized_query:
        return None

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM movies
        WHERE
            normalized_title LIKE ?
            OR normalized_title LIKE ?
            OR normalized_title LIKE ?
        ORDER BY id DESC
        LIMIT 30
    """, (
        normalized_query,
        f"{normalized_query}%",
        f"%{normalized_query}%"
    )).fetchall()

    conn.close()

    if not rows:
        return None

    best = None
    best_score = 0

    query_words = set(
        normalized_query.split()
    )

    for row in rows:

        db_title = row["normalized_title"]

        if db_title == normalized_query:
            return row

        db_words = set(
            db_title.split()
        )

        if query_words and db_words:

            common = len(
                query_words & db_words
            )

            word_score = (
                common /
                max(len(query_words), 1)
            )
        else:
            word_score = 0

        similarity = SequenceMatcher(
            None,
            normalized_query,
            db_title
        ).ratio()

        score = (
            similarity * 0.7
            + word_score * 0.3
        )

        if normalized_query in db_title:
            score += 0.25

        if score > best_score:

            best_score = score
            best = row

    # Avoid unrelated results
    if best_score >= 0.55:
        return best

    return None


def get_movie_by_id(movie_id):

    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM movies
        WHERE id = ?
    """, (
        movie_id,
    )).fetchone()

    conn.close()

    return row


def get_movie_count():

    conn = get_db()

    count = conn.execute(
        "SELECT COUNT(*) FROM movies"
    ).fetchone()[0]

    conn.close()

    return count


# ============================================================
# TMDB
# ============================================================

async def tmdb_search(query):

    headers = {
        "Authorization":
            f"Bearer {TMDB_TOKEN}",

        "accept":
            "application/json",
    }

    params = {
        "query": query,
        "include_adult": "false",
        "language": "en-US",
        "page": 1,
    }

    async with httpx.AsyncClient(
        timeout=20
    ) as client:

        response = await client.get(
            f"{TMDB_BASE}/search/movie",
            headers=headers,
            params=params,
        )

        response.raise_for_status()

        data = response.json()

    return data.get(
        "results",
        []
    )


async def tmdb_details(tmdb_id):

    headers = {
        "Authorization":
            f"Bearer {TMDB_TOKEN}",

        "accept":
            "application/json",
    }

    params = {
        "language": "en-US"
    }

    async with httpx.AsyncClient(
        timeout=20
    ) as client:

        response = await client.get(
            f"{TMDB_BASE}/movie/{tmdb_id}",
            headers=headers,
            params=params,
        )

        response.raise_for_status()

        return response.json()


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    name = (
        user.first_name
        or "Friend"
    )

    text = f"""
🎬 <b>Welcome {name}!</b>

━━━━━━━━━━━━━━━━━━
🍿 <b>FILM4YOU</b>
━━━━━━━━━━━━━━━━━━

🔎 <b>Movie Search</b>
Send me a movie name.

🎬 Get movie information
⭐ Rating
📅 Release year
📝 Story
🎞 Trailer / details
📥 Authorized archive content

━━━━━━━━━━━━━━━━━━
💡 Example:

<code>Spider Man</code>

Enjoy your movie search! 🍿
"""

    await update.message.reply_text(
        text,
        parse_mode="HTML"
    )


# ============================================================
# ARCHIVE CHANNEL
# ============================================================

async def archive_post(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    message = update.channel_post

    if not message:
        return

    logger.info(
        "CHANNEL POST | chat_id=%s | message_id=%s",
        message.chat.id,
        message.message_id
    )

    if message.chat.id != ARCHIVE_CHANNEL_ID:

        logger.warning(
            "Wrong channel ID: %s",
            message.chat.id
        )

        return

    raw_text = (
        message.caption
        or message.text
        or ""
    )

    if not raw_text:

        logger.warning(
            "Archive post has no caption/text | msg=%s",
            message.message_id
        )

        return

    title = display_title(
        raw_text
    )

    year = extract_year(
        raw_text
    )

    # Save FIRST.
    # TMDB failure must never prevent indexing.
    save_movie(
        title=title,
        message_id=message.message_id,
        channel_id=message.chat.id,
        year=year,
    )


# ============================================================
# ADMIN: INDEX AN EXISTING ARCHIVE POST
#
# How:
# 1. Forward an old archive post to bot.
# 2. Reply to that forwarded message with /index
#
# ============================================================

async def index_existing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user

    if not user or not user.id in ADMIN_IDS:

        await update.message.reply_text(
            "⛔ Admin only."
        )

        return

    if not update.message.reply_to_message:

        await update.message.reply_text(
            "❌ Pehle archive channel ka "
            "post forward karo.\n\n"
            "Phir us forwarded post ko reply karke:\n"
            "<code>/index</code>",
            parse_mode="HTML"
        )

        return

    msg = update.message.reply_to_message

    # Try to identify original channel post
    origin = getattr(
        msg,
        "forward_origin",
        None
    )

    if not origin:

        await update.message.reply_text(
            "❌ Ye forwarded channel post nahi lag raha."
        )

        return

    origin_chat = getattr(
        origin,
        "chat",
        None
    )

    origin_message_id = getattr(
        origin,
        "message_id",
        None
    )

    if not origin_chat or not origin_message_id:

        await update.message.reply_text(
            "❌ Original channel message ID "
            "nahi mil saka."
        )

        return

    if origin_chat.id != ARCHIVE_CHANNEL_ID:

        await update.message.reply_text(
            "❌ Ye post configured archive channel "
            "se nahi hai."
        )

        return

    raw_text = (
        msg.caption
        or msg.text
        or ""
    )

    if not raw_text:

        await update.message.reply_text(
            "❌ Forwarded post me title/caption nahi hai."
        )

        return

    title = display_title(
        raw_text
    )

    year = extract_year(
        raw_text
    )

    success = save_movie(
        title=title,
        message_id=origin_message_id,
        channel_id=origin_chat.id,
        year=year,
    )

    if success:

        await update.message.reply_text(
            f"""
✅ <b>Indexed Successfully</b>

🎬 <b>{title}</b>

🆔 Message ID:
<code>{origin_message_id}</code>
""",
            parse_mode="HTML"
        )

    else:

        await update.message.reply_text(
            "❌ Database me save nahi hua."
        )


# ============================================================
# SEARCH
# ============================================================

async def search_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    query = (
        update.message.text
        or ""
    ).strip()

    if not query:
        return

    if query.startswith("/"):
        return

    try:

        # ----------------------------------------------------
        # STEP 1: DATABASE FIRST
        # ----------------------------------------------------

        archive_movie = search_database(
            query
        )

        # ----------------------------------------------------
        # STEP 2: TMDB
        # ----------------------------------------------------

        tmdb_results = await tmdb_search(
            query
        )

        tmdb_movie = (
            tmdb_results[0]
            if tmdb_results
            else None
        )

        # Nothing anywhere
        if not archive_movie and not tmdb_movie:

            await update.message.reply_text(
                f"❌ No results for "
                f"<b>{query}</b>",
                parse_mode="HTML"
            )

            return

        # ----------------------------------------------------
        # TMDB DETAILS
        # ----------------------------------------------------

        title = query
        year = "N/A"
        rating = "N/A"
        overview = (
            "Story information "
            "available nahi hai."
        )

        tmdb_id = None
        poster = None

        if tmdb_movie:

            tmdb_id = tmdb_movie.get(
                "id"
            )

            title = tmdb_movie.get(
                "title",
                query
            )

            release_date = (
                tmdb_movie.get(
                    "release_date",
                    ""
                )
            )

            if release_date:
                year = release_date[:4]

            vote = tmdb_movie.get(
                "vote_average"
            )

            if vote is not None:
                rating = f"{vote:.1f}"

            overview = (
                tmdb_movie.get(
                    "overview"
                )
                or overview
            )

            poster_path = (
                tmdb_movie.get(
                    "poster_path"
                )
            )

            if poster_path:
                poster = (
                    "https://image.tmdb.org/t/p/"
                    "w780"
                    + poster_path
                )

        # ----------------------------------------------------
        # DATABASE MOVIE OVERRIDES
        # ----------------------------------------------------

        if archive_movie:

            archive_title = (
                archive_movie["title"]
            )

            if archive_title:
                title = archive_title

            if archive_movie["year"]:
                year = archive_movie["year"]

            if archive_movie["tmdb_id"]:
                tmdb_id = (
                    archive_movie["tmdb_id"]
                )

        # ----------------------------------------------------
        # BUTTONS
        # ----------------------------------------------------

        buttons = []

        if archive_movie:

            # Store DB ID + original request
            callback = (
                f"download:"
                f"{archive_movie['id']}:"
                f"{update.message.message_id}"
            )

            buttons.append([
                InlineKeyboardButton(
                    "📥 Download",
                    callback_data=callback
                )
            ])

        if tmdb_id:

            buttons.append([
                InlineKeyboardButton(
                    "⭐ TMDB Details",
                    callback_data=f"tmdb:{tmdb_id}"
                )
            ])

        google_url = (
            "https://www.google.com/search?q="
            + query.replace(" ", "+")
        )

        buttons.append([
            InlineKeyboardButton(
                "🔎 Search Google",
                url=google_url
            )
        ])

        if archive_movie:

            status = (
                "✅ Available in Database"
            )

        else:

            status = (
                "❌ Not Available in Database"
            )

        text = f"""
🎬 <b>{title}</b> ({year})

⭐ <b>Rating:</b> {rating}/10

📝 <b>Story:</b>
{overview[:1000]}

━━━━━━━━━━━━━━━━━━

📌 <b>Status:</b> {status}

👇 <b>Choose an option:</b>
"""

        # ----------------------------------------------------
        # SEND POSTER
        # ----------------------------------------------------

        if poster:

            await update.message.reply_photo(
                photo=poster,
                caption=text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    buttons
                )
            )

        else:

            await update.message.reply_text(
                text,
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    buttons
                ),
                disable_web_page_preview=True
            )

    except Exception:

        logger.exception(
            "Search failed for: %s",
            query
        )

        await update.message.reply_text(
            "⚠️ Search me temporary error aa gaya.\n"
            "Please try again."
        )


# ============================================================
# DOWNLOAD / COPY AUTHORIZED ARCHIVE CONTENT
# ============================================================

async def download_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    try:

     
