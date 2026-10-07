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
# ENVIRONMENT
# ============================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()

# Telegram channel ID should normally be -100XXXXXXXXXX
ARCHIVE_CHANNEL_ID = int(
    os.getenv(
        "ARCHIVE_CHANNEL_ID",
        "-1004341107282"
    )
)

DATABASE = os.getenv(
    "DATABASE",
    "movies.db"
)

ADMIN_IDS = {
    int(x.strip())
    for x in os.getenv(
        "ADMIN_IDS",
        ""
    ).split(",")
    if x.strip()
}

TMDB_BASE = "https://api.themoviedb.org/3"

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN missing in .env"
    )

if not TMDB_API_KEY:
    raise RuntimeError(
        "TMDB_API_KEY missing in .env"
    )


# ============================================================
# LOGGING
# ============================================================

Path("logs").mkdir(
    exist_ok=True
)

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
    handlers=[
        logging.FileHandler(
            "logs/bot.log",
            encoding="utf-8"
        ),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(
    "Film4you"
)


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

            UNIQUE(
                channel_id,
                message_id
            )
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_movies_normalized
        ON movies(normalized_title)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_movies_tmdb
        ON movies(tmdb_id)
    """)

    conn.commit()
    conn.close()

    logger.info(
        "SQLite database ready"
    )


# ============================================================
# TEXT CLEANING
# ============================================================

def normalize_title(text):

    if not text:
        return ""

    text = unicodedata.normalize(
        "NFKD",
        text
    )

    # URLs
    text = re.sub(
        r"https?://\S+",
        " ",
        text,
        flags=re.I
    )

    # Common release tags
    text = re.sub(
        r"\b("
        r"2160p|1080p|720p|480p|360p|"
        r"4k|8k|"
        r"web[-_. ]?dl|"
        r"web[-_. ]?rip|"
        r"webrip|"
        r"bluray|"
        r"blu[-_. ]?ray|"
        r"brrip|"
        r"hdr|"
        r"dolby|"
        r"vision|"
        r"x264|x265|"
        r"h264|h265|"
        r"hevc|"
        r"10bit|"
        r"dual[-_. ]?audio|"
        r"multi[-_. ]?audio|"
        r"hindi|english|"
        r"tamil|telugu|"
        r"malayalam|kannada"
        r")\b",
        " ",
        text,
        flags=re.I
    )

    # Year
    text = re.sub(
        r"\b(19|20)\d{2}\b",
        " ",
        text
    )

    # Lowercase
    text = text.lower()

    # Keep only letters/numbers
    text = re.sub(
        r"[^a-z0-9]",
        "",
        text
    )

    return text


def clean_display_title(text):

    if not text:
        return ""

    # Remove URLs
    text = re.sub(
        r"https?://\S+",
        "",
        text,
        flags=re.I
    )

    # Remove common beginning emojis/symbols
    text = re.sub(
        r"^[^\w]+",
        "",
        text,
        flags=re.UNICODE
    )

    # Remove excessive spaces
    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def extract_year(text):

    if not text:
        return None

    match = re.search(
        r"\b(19|20)\d{2}\b",
        text
    )

    if match:
        return match.group(0)

    return None


def extract_title_from_message(message):

    """
    Tries:
    1. caption
    2. text
    3. document filename
    4. video filename
    5. audio filename
    """

    text = (
        message.caption
        or message.text
        or ""
    )

    if text.strip():

        lines = [
            x.strip()
            for x in text.splitlines()
            if x.strip()
        ]

        if lines:

            title = lines[0]

            title = clean_display_title(
                title
            )

            # Remove common labels
            title = re.sub(
                r"^(movie|film|title|name)"
                r"\s*[:\-]\s*",
                "",
                title,
                flags=re.I
            )

            return title.strip()

    # Document filename
    if message.document:
        filename = (
            message.document.file_name
            or ""
        )

        if filename:
            return clean_display_title(
                Path(filename).stem
            )

    # Video filename
    if message.video:

        filename = (
            message.video.file_name
            or ""
        )

        if filename:
            return clean_display_title(
                Path(filename).stem
            )

    # Audio filename
    if message.audio:

        filename = (
            message.audio.file_name
            or ""
        )

        if filename:
            return clean_display_title(
                Path(filename).stem
            )

    return ""


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

    title = clean_display_title(
        title
    )

    normalized = normalize_title(
        title
    )

    if not normalized:

        logger.warning(
            "Cannot save empty title"
        )

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

            VALUES (
                ?, ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(
                channel_id,
                message_id
            )

            DO UPDATE SET

                title =
                    excluded.title,

                normalized_title =
                    excluded.normalized_title,

                original_title =
                    excluded.original_title,

                year =
                    excluded.year,

                tmdb_id =
                    excluded.tmdb_id
        """, (
            title,
            normalized,
            original_title,
            year,
            tmdb_id,
            channel_id,
            message_id,
        ))

        conn.commit()

        logger.info(
            "INDEXED | %s | message=%s",
            title,
            message_id
        )

        return True

    except Exception:

        logger.exception(
            "Database save error"
        )

        return False

    finally:
        conn.close()


# ============================================================
# DATABASE SEARCH
# ============================================================

def find_movie(query):

    query_normalized = normalize_title(
        query
    )

    if not query_normalized:
        return None

    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM movies
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    if not rows:
        return None

    best = None
    best_score = 0.0

    for row in rows:

        db_title = normalize_title(
            row["title"]
        )

        if not db_title:
            continue

        # Exact
        if db_title == query_normalized:
            return row

        # Contains
        if query_normalized in db_title:

            score = 0.96

        elif db_title in query_normalized:

            score = 0.92

        else:

            score = SequenceMatcher(
                None,
                query_normalized,
                db_title
            ).ratio()

        # Word-like bonus
        query_words = set(
            re.findall(
                r"[a-z0-9]+",
                query_normalized
            )
        )

        db_words = set(
            re.findall(
                r"[a-z0-9]+",
                db_title
            )
        )

        if query_words and db_words:

            common = len(
                query_words & db_words
            )

            score += (
                common /
                max(len(query_words), 1)
            ) * 0.05

        if score > best_score:

            best_score = score
            best = row

    # Don't return completely unrelated movie
    if best_score >= 0.55:
        return best

    return None


def get_movie(movie_id):

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
