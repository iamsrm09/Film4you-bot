import os, time, requests, re, queue
from threading import Thread
from flask import Flask
import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from urllib.parse import quote_plus
from pymongo import MongoClient

print("Starting V5 SHORT...", flush=True)

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    AI_OK = True
except:
    AI_OK = False

MONGO_URL = os.environ.get('MONGO_URL')
TMDB_CACHE = {}
RAM_DB = {}
CLEAN_CACHE = {}
AI_VEC = None
AI_MAT = None
AI_KEYS = []

app = Flask('')
@app.route('/')
def home():
    return "Active V5 SHORT"

def run_flask():
    p = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=p)

Thread(target=run_flask, daemon=True).start()

if MONGO_URL:
    try:
        cli = MongoClient(MONGO_URL, serverSelectionTimeoutMS=10000)
        mdb = cli['film4you']
        movies_col = mdb['movies']
        caps_col = mdb['captions']
        print("Mongo OK", flush=True)
    except Exception as e:
        print(f"Mongo Err {e}", flush=True)

BOT_TOKEN = os.environ.get('BOT_TOKEN')
TMDB_KEY = os.environ.get('TMDB_API_KEY')
DB_CH_ID = -1004341107282

bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=10)
CHANNEL_Q = queue.Queue()
ALBUM_CACHE = {}
PROCESSED = set()
SEARCH_CACHE = {}
FILE_CACHE = {}
PAGE_SIZE = 5

def is_dup(mid):
    if mid in PROCESSED:
        return True
    PROCESSED.add(mid)
    if len(PROCESSED) > 300:
        PROCESSED.clear()
    return False

def clean_name(t):
    if not t:
        return ""
    t = t.split('\n')[0]
    t = re.sub(r'@\w+|Bt_Movies_Hd|Filmsclub|Film4you', '', t, flags=re.I)
    t = re.sub(r'\[.*?\]', '', t)
    t = re.sub(r'http\S+|t\.me/\S+', '', t)
    t = re.sub(r'Join.*|Search.*|More.*', '', t, flags=re.I)
    t = re.sub(r'\b(1080p|720p|480p|2160p|4K|HDRip|WEB-DL|BluRay|ESub|x264|x265|Hindi|AAC|2\.0|mkv|mp4|Full Movie|Dubbed|Hevc|Hdtc|10Bit|Webrip|Psa|Combined|Webr)\b', '', t, flags=re.I)
    t = re.sub(r'[^a-zA-Z0-9 ]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t.lower().strip()

def build_ai():
    global AI_VEC, AI_MAT, AI_KEYS
    if not AI_OK or not CLEAN_CACHE:
        return
    try:
        AI_KEYS = list(CLEAN_CACHE.keys())
        corpus = [CLEAN_CACHE[k] for k in AI_KEYS]
        AI_VEC = TfidfVectorizer(analyzer='char_wb', ngram_range=(3,5))
        AI_MAT = AI_VEC.fit_transform(corpus)
        print(f"AI Built {len(AI_KEYS)}", flush=True)
    except Exception as e:
        print(f"AI Err {e}", flush=True)

def init_ram():
    global RAM_DB, CLEAN_CACHE
    if MONGO_URL:
        try:
            print("Loading DB...", flush=True)
            tmp = {}
            tmp_c = {}
            for doc in movies_col.find():
                key = doc['_id']
                cl = clean_name(key)
                if not cl or len(cl) < 3:
                    continue
                if '[' in key or ']' in key:
                    nk = cl
                    if nk not in tmp:
                        tmp[nk] = doc.get('files', [])
                        tmp_c[nk] = nk
                    continue
                tmp[key] = doc.get('files', [])
                tmp_c[key] = cl
            RAM_DB = tmp
            CLEAN_CACHE = tmp_c
            print(f"Loaded {len(RAM_DB)}", flush=True)
            build_ai()
        except Exception as e:
            print(f"RAM Err {e}", flush=True)

def ai_search(q, top_k=10):
    if not q or len(q) < 2:
        return []
    qq = q.lower().strip()
    for w in ["wali", "wala", "wale", "movie", "film", "bhejo"]:
        qq = qq.replace(w, " ")
    qq = re.sub(r'\s+', ' ', qq).strip()
    if len(qq) < 3:
        return []
    if AI_OK and AI_VEC is not None and AI_MAT is not None:
        try:
            qv = AI_VEC.transform([clean_name(qq)])
            scores = cosine_similarity(qv, AI_MAT).flatten()
            ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
            res = []
            for idx, sc in ranked:
                if sc >= 0.25:
                    res.append(AI_KEYS[idx])
                if len(res) >= top_k:
                    break
            return res
        except Exception as e:
            print(f"AI Err {e}", flush=True)
    import difflib
    cq = clean_name(qq)
    all_c = list(CLEAN_CACHE.values())
    close = difflib.get_close_matches(cq, all_c, n=top_k, cutoff=0.5)
    rk = []
    for c in close:
        for orig, cl in CLEAN_CACHE.items():
            if cl == c and orig not in rk:
                rk.append(orig)
                break
    return rk

def load_db():
    if RAM_DB:
        return RAM_DB
    return {}

def save_file_id(key, fid):
    if not key or len(key) < 3:
        return
    if key not in RAM_DB:
        RAM_DB[key] = []
    if fid not in RAM_DB[key]:
        RAM_DB[key].append(fid)
    CLEAN_CACHE[key] = clean_name(key)
    if MONGO_URL:
        try:
            movies_col.update_one({"_id": key}, {"$addToSet": {"files": fid}}, upsert=True)
        except:
            pass

def load_caps():
    if MONGO_URL:
        try:
            d = {}
            for doc in caps_col.find():
                d[doc['_id']] = doc.get('caption','')
            return d
        except:
            return {}
    return {}

def save_cap(fid, cap):
    if MONGO_URL:
        try:
            caps_col.update_one({"_id": fid}, {"$set": {"caption": cap}}, upsert=True)
        except:
            pass

def get_tmdb(q, orig=""):
    if not TMDB_KEY:
        return None
    ck = clean_name(q)[:40]
    if ck in TMDB_CACHE:
        return TMDB_CACHE[ck]
    qq = clean_name(q)
    if len(qq) < 2:
        qq = q
    try:
        url = f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_KEY}&query={quote_plus(qq)}"
        r = requests.get(url, timeout=5).json()
        if not r.get('results'):
            return None
        results = [x for x in r['results'] if x.get('media_type') in ['movie','tv']][:3]
        if not results:
            return None
        best = results[0]
        mtype = best['media_type']
        mid = best['id']
        d = requests.get(f"https://api.themoviedb.org/3/{mtype}/{mid}?api_key={TMDB_KEY}", timeout=5).json()
        title = d.get('title') or d.get('name') or qq
        pp = best.get('poster_path')
        poster = f"https://image.tmdb.org/t/p/w500{pp}" if pp else None
        rating = round(d.get('vote_average',0),1)
        gl = [g['name'] for g in d.get('genres',[])][:2]
        genres = ", ".join(gl) if gl else "N/A"
        date = d.get('release_date') or d.get('first_air_date') or "N/A"
        year = date[:4] if len(date)>=4 else "N/A"
        rt = d.get('runtime',0)
        runtime = f"{rt//60}H {rt%60}M" if mtype=='movie' and rt else "N/A"
        story = d.get('overview','')[:500] or "N/A"
        res = {"title":title,"year":year,"rating":rating,"genres":genres,"runtime":runtime,"date":date,"poster":poster,"story":story,"type":mtype}
        TMDB_CACHE[ck] = res
        return res
    except:
        return None

def build_search_markup(cid, page=0):
    data = SEARCH_CACHE.get(cid)
    if not data:
        return None,0,0
    keys = data["keys"]
    db = RAM_DB if RAM_DB else load_db()
    total = len(keys)
    tpages = (total + PAGE_SIZE - 1) // PAGE_SIZE or 1
    s = page * PAGE_SIZE
    e = s + PAGE_SIZE
    pkeys = keys[s:e]
    mk = InlineKeyboardMarkup(row_width=1)
    for i, key in enumerate(pkeys):
        ri = s + i
        files = db.get(key, [])
        bname = key.title()[:30]
        mk.add(InlineKeyboardButton(f"📥 {bname} ({len(files)})", callback_data=f"g_{ri}"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"sp_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{tpages}", callback_data="noop"))
    if page < tpages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"sp_{page+1}"))
    if total > PAGE_SIZE:
        mk.row(*nav)
    if page == 0 and data.get("info") and total > 0:
        info = data["info"]
        mk.row(InlineKeyboardButton("▶️ Trailer", url=f"https://www.youtube.com/results?search_query={quote_plus(info['title'])}+trailer"), InlineKeyboardButton("📍 Watch", url=f"https://www.justwatch.com/in/search?q={quote_plus(info['title'])}"))
    return mk, total, tpages

def build_file_markup(cid, key, page=0):
    files = FILE_CACHE.get(cid, {}).get("files", [])
    total = len(files)
    tpages = (total + PAGE_SIZE - 1) // PAGE_SIZE or 1
    s = page * PAGE_SIZE
    e = s + PAGE_SIZE
    mk = InlineKeyboardMarkup(row_width=1)
    for idx in range(s, min(e, total)):
        mk.add(InlineKeyboardButton(f"📦 Part {idx+1} - Download", callback_data=f"s_{idx}"))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"fp_{page-1}"))
    nav.append(InlineKeyboardButton(f"📄 {page+1}/{tpages}", callback_data="noop"))
    if page < tpages - 1:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"fp_{page+1}"))
    mk.row(*nav)
    mk.add(InlineKeyboardButton(f"📥 Send All {total} Files", callback_data="sa"))
    return mk, total, tpages

def channel_worker():
    while True:
        try:
            fid, cap, is_vid, tpath = CHANNEL_Q.get()
            try:
                if is_vid:
                    if tpath and os.path.exists(tpath):
                        with open(tpath, 'rb') as tf:
                            bot.send_video(DB_CH_ID, fid, thumb=tf, caption=cap)
                    else:
                        bot.send_video(DB_CH_ID, fid, caption=cap)
                else:
                    bot.send_document(DB_CH_ID, fid, caption=cap)
            except Exception as ex:
                if "429" in str(ex):
                    time.sleep(35)
                    CHANNEL_Q.put((fid, cap, is_vid, tpath))
            time.sleep(3.5)
            CHANNEL_Q.task_done()
        except:
            time.sleep(3)

Thread(target=channel_worker, daemon=True).start()

@bot.message_handler(content_types=['new_chat_members'])
def welcome_handler(message):
    for new_user in message.new_chat_members:
        try:
            if new_user.is_bot:
                continue
            fn = new_user.first_name or "Friend"
            un = f"@{new_user.username}" if new_user.username else fn
            ct = message.chat.title or "Film4You"
            txt = f"🎬 Welcome {fn}! ✨\n\nHey {un} 👋 Welcome to **{ct}** ❤️\n\n🔍 Just send any movie name\n🤖 AI will find it even if spelling is wrong\n\nEnjoy! 🍿"
            bot.send_message(message.chat.id, txt, parse_mode="Markdown")
        except Exception as e:
            print(f"Welcome Err {e}", flush=True)

@bot.message_handler(content_types=['video', 'document'])
def save_handler(message):
    if is_dup(message.message_id):
        return
    raw = message.caption or ""
    mg = getattr(message, 'media_group_id', None)
    if mg:
        if raw:
            ALBUM_CACHE[mg] = raw
        elif mg in ALBUM_CACHE:
            raw = ALBUM_CACHE[mg]
    if not raw:
        bot.reply_to(message, "❌ Caption me movie name likho! 🎬")
        return
    fid = message.video.file_id if message.video else message.document.file_id
    cn = clean_name(raw)
    if not cn or len(cn) < 3:
        bot.reply_to(message, f"❌ Invalid name: {raw[:30]}")
        return
    save_file_id(cn, fid)
    save_cap(fid, raw)
    db = RAM_DB if RAM_DB else load_db()
    bot.reply_to(message, f"✅ Saved! {cn} | Files: {len(db.get(cn, []))}")

@bot.message_handler(commands=['start'])
def start_handler(message):
    name = message.from_user.first_name or "Friend"
    txt = f"🎬✨ Film4you Live! ✨🎬\n\n👋 Hello {name}! Welcome! ❤️\n\n🔍 Send Movie Name 👇\n🤖 AI Enabled!"
    bot.send_message(message.chat.id, txt, parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def stats_handler(message):
    try:
        tm = len(RAM_DB)
        tf = sum(len(v) for v in RAM_DB.values())
        bot.send_message(message.chat.id, f"📊 Stats\nMovies: {tm}\nFiles: {tf}\nAI: {len(AI_KEYS)}", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ {e}")

@bot.message_handler(func=lambda m: True, content_types=['text'])
def search_handler(message):
    if message.text.startswith('/'):
        return
    if is_dup(message.message_id):
        return
    q = message.text.strip()
    if len(q) < 2:
        return
    if not RAM_DB:
        bot.send_message(message.chat.id, "⏳ Loading DB... try again in 10 sec")
        return
    cq = clean_name(q)
    if not cq or len(cq) < 2:
        cq = q.lower().strip()
    matched = []
    for ok, ck in CLEAN_CACHE.items():
        if not ck or len(ck) < 3:
            continue
        if cq == ck:
            matched.append(ok)
        elif cq in ck:
            matched.append(ok)
        elif len(cq) >= 4 and ck in cq:
            matched.append(ok)
        if len(matched) >= 30:
            break
    ai_used = False
    if not matched:
        ar = ai_search(q, top_k=10)
        if ar:
            matched = ar
            ai_used = True
        else:
            for ok, ck in CLEAN_CACHE.items():
                if any(w in ck for w in cq.split() if len(w)>=4):
                    if ok not in matched:
                        matched.append(ok)
                if len(matched) >= 10:
                    break
            if matched:
                ai_used = True
    SEARCH_CACHE[message.chat.id] = {"keys": matched, "query": q, "info": None}
    mk, total, tpages = build_search_markup(message.chat.id, 0)
    if total == 0:
        sent = bot.send_message(message.chat.id, f"❌ No results for *{q}*", parse_mode="Markdown")
    else:
        label = "🤖 AI Search" if ai_used else "🎬 Search"
        sent = bot.send_message(message.chat.id, f"{label} - *{q}* 🔍\n\n{total} results - Page 1/{tpages} 👇", parse_mode="Markdown", reply_markup=mk)

    def fetch_tmdb():
        try:
            info = get_tmdb(q, q)
            if not info:
                return
            if SEARCH_CACHE[message.chat.id]["keys"]:
                SEARCH_CACHE[message.chat.id]["info"] = info
                mk2, total2, tpages2 = build_search_markup(message.chat.id, 0)
                if total2 == 0:
                    return
                cap = f"🎬 *{info['title']} ({info['year']})* - {info['type'].upper()} ✨\n⭐ {info['rating']}/10 | 🎭 {info['genres']}\n📅 {info['date']}\n\n📝 {info['story']}\n\n🔍 {total2} results"
                try:
                    if info['poster']:
                        bot.delete_message(message.chat.id, sent.message_id)
                        bot.send_photo(message.chat.id, info['poster'], caption=cap, parse_mode="Markdown", reply_markup=mk2)
                    else:
                        bot.edit_message_text(cap, message.chat.id, sent.message_id, parse_mode="Markdown", reply_markup=mk2)
                except:
                    pass
        except:
            pass
    Thread(target=fetch_tmdb, daemon=True).start()

@bot.callback_query_handler(func=lambda call: True)
def cb(call):
    cid = call.message.chat.id
    db = RAM_DB if RAM_DB else load_db()
    caps = load_caps()
    d = call.data

    if d == "noop":
        bot.answer_callback_query(call.id)
        return

    if d.startswith("sp_"):
        try:
            pg = int(d.split("_")[1])
            mk, tot, tpg = build_search_markup(cid, pg)
            if mk:
                try:
                    bot.edit_message_reply_markup(cid, call.message.message_id, reply_markup=mk)
                except:
                    pass
            bot.answer_callback_query(call.id)
        except:
            bot.answer_callback_query(call.id)
        return

    if d.startswith("fp_"):
        try:
            pg = int(d.split("_")[1])
            key = FILE_CACHE.get(cid, {}).get("key", "")
            mk, tot, tpg = build_file_markup(cid, key, pg)
            try:
                bot.edit_message_text(f"🎬 *{key.title()}* - {tot} Files\n\n📄 Page {pg+1}/{tpg}", cid, call.message.message_id, parse_mode="Markdown", reply_markup=mk)
            except:
                pass
            bot.answer_callback_query(call.id)
        except:
            bot.answer_callback_query(call.id)
        return

    if d.startswith("g_"):
        try:
            idx = int(d.split("_")[1])
            keys = SEARCH_CACHE.get(cid, {}).get("keys", [])
            if idx >= len(keys):
                bot.answer_callback_query(call.id, "❌ Not found", show_alert=True)
                return
            key = keys[idx]
            flist = db.get(key, [])
            if not flist:
                bot.answer_callback_query(call.id, "❌ File not found", show_alert=True)
                return
            FILE_CACHE[cid] = {"key": key, "files": flist}
            mk, tot, tpg = build_file_markup(cid, key, 0)
            bot.send_message(cid, f"🎬 *{key.title()}* - {tot} Files\n\n📄 Page 1/{tpg} 👇", parse_mode="Markdown", reply_markup=mk)
            bot.answer_callback_query(call.id)
        except Exception as e:
            print(f"get err {e}", flush=True)
            bot.answer_callback_query(call.id)
        return

    if d.startswith("s_"):
        try:
            idx = int(d.split("_")[1])
            cache = FILE_CACHE.get(cid, {})
            files = cache.get("files", [])
            key = cache.get("key", "")
            if idx < len(files):
                fid = files[idx]
                ctext = caps.get(fid, key.title())
                try:
                    bot.send_document(cid, fid, caption=ctext)
                except:
                    try:
                        bot.send_video(cid, fid, caption=ctext)
                    except Exception as e:
                        bot.send_message(cid, f"❌ Error: {e}")
            bot.answer_callback_query(call.id)
        except:
            bot.answer_callback_query(call.id)
        return

    if d == "sa":
        try:
            cache = FILE_CACHE.get(cid, {})
            files = cache.get("files", [])
            key = cache.get("key", "")
            cnt = len(files)
            bot.answer_callback_query(call.id)
            for fid in files:
                ctext = caps.get(fid, key.title())
                time.sleep(0.8)
                try:
                    bot.send_document(cid, fid, caption=ctext)
                except:
                    try:
                        bot.send_video(cid, fid, caption=ctext)
                    except:
                        pass
        except:
            bot.answer_callback_query(call.id)
        return

print("Loading cache...", flush=True)
Thread(target=init_ram, daemon=True).start()
print("Polling...", flush=True)

try:
    bot.remove_webhook()
    time.sleep(2)
except:
    pass

while True:
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)
    except Exception as e:
        print(f"Polling Err {e}", flush=True)
        time.sleep(5)
