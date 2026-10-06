# 1. TUMHARI DOWNLOAD LIST - Jisme file hai wahi dikhegi
DOWNLOAD_MOVIES = {
    "kgf chapter 2": "BAACAgQAAxkB...",
    "animal 2023": "BAACAgQAAxkB...2",
    "jawan": "BAACAgQAAxkB...3",
    "pathaan": "BAACAgQAAxkB...4",
}

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle(m):
    text = m.text.lower().strip()
    if len(text) < 2: return
    if text.startswith('/'): return

    # Pehle TMDB se movie ka poster + details lao
    item = search_best(text)
    if not item:
        return

    title = (item.get('title') or item.get('name')).lower()
    real_title = item.get('title') or item.get('name')
    
    # CHECK KARO - Kya ye movie tumhare paas hai?
    file_id = None
    for name, fid in DOWNLOAD_MOVIES.items():
        if name in title or title in name or text in name:
            file_id = fid
            break

    markup = InlineKeyboardMarkup()

    if file_id:
        # AGAR HAI TO HI DOWNLOAD BUTTON DIKHEGA
        bot_name = bot.get_me().username
        # Deep link jisme file bhejega
        download_link = f"https://t.me/{bot_name}?start={name.replace(' ', '_')}"
        markup.row(InlineKeyboardButton("💾 DOWNLOAD AVAILABLE", url=download_link))
        markup.row(InlineKeyboardButton("📦 MovieBox", url=f"https://moviebox.ph/web/searchResult?keyword={urllib.parse.quote(real_title)}"))
        
        caption = f"🎬 *{real_title}*\n\n✅ Download Available hai!\n👇 Button pe click karo"
        has_download = True
    else:
        # AGAR NAHI HAI TO REQUEST BUTTON
        markup.row(InlineKeyboardButton("❌ Not Available - Request Karo", url="https://t.me/FSearch4ubot"))
        caption = f"🎬 *{real_title}*\n\n❌ Iska Download abhi mere paas nahi hai.\nRequest kar do, jaldi add kar dunga."
        has_download = False

    # Poster bhejo
    poster = item.get('poster_path')
    if poster:
        bot.send_photo(m.chat.id, f"https://image.tmdb.org/t/p/w500{poster}", caption=caption, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(m.chat.id, caption, parse_mode="Markdown", reply_markup=markup)

    # Agar download hai to file bhi bhej do
    if has_download and file_id:
        bot.send_document(m.chat.id, file_id)
        
