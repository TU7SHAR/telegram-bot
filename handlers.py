import hashlib
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import NetworkError, BadRequest
import scraper
from groq_engine import get_groq_response

logger = logging.getLogger(__name__)

async def deactivate_old_menu(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Deletes the previous menu message entirely so it vanishes from history."""
    last_id = context.user_data.get("last_menu_id")
    if last_id:
        try:
            await context.bot.delete_message(
                chat_id=chat_id,
                message_id=last_id
            )
        except BadRequest:
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=chat_id,
                    message_id=last_id,
                    reply_markup=None
                )
            except:
                pass
        
        context.user_data["last_menu_id"] = None

def get_main_menu_keyboard():
    """Vertical menu as requested."""
    keyboard = [
        [InlineKeyboardButton("Upload File", callback_data="menu_upload")],
        [InlineKeyboardButton("Manage Stored Files", callback_data="menu_manage")],
        [InlineKeyboardButton("Crawl New Website", callback_data="menu_crawl")],
        [InlineKeyboardButton("Clear All Memory", callback_data="clear_all")],
        [InlineKeyboardButton("Support / Help", url="https://t.me/tu7shar")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await deactivate_old_menu(context, update.effective_chat.id)
    context.user_data["file_map"] = {}
    sent_msg = await update.message.reply_html(
        "<b>Universal RAG Bot Active</b>\n\n"
        "1. Select Upload File to see supported formats\n"
        "2. Use /crawl [url] for web content\n"
        "3. Use /manage to delete memory",
        reply_markup=get_main_menu_keyboard()
    )
    context.user_data["last_menu_id"] = sent_msg.message_id

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await deactivate_old_menu(context, update.effective_chat.id)
    sent_msg = await update.message.reply_html("<b>Main Menu</b>", reply_markup=get_main_menu_keyboard())
    context.user_data["last_menu_id"] = sent_msg.message_id

async def handle_crawl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await deactivate_old_menu(context, update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("Usage: /crawl [url] [optional: spider/sitemap]")
        return
    
    url = context.args[0]
    mode = context.args[1].lower() if len(context.args) > 1 else "single"
    status_msg = await update.message.reply_text(f"Starting crawl for: {url}")
    logs = f"Initializing Scraper for Target: {url}\n"
    urls_to_scrape = []

    try:
        # Discovery Phase
        if mode == "spider":
            logs += "Deep Crawl Mode: Searching for internal links...\n"
            await status_msg.edit_text(logs)
            result = await asyncio.to_thread(scraper.crawl_website_links, url)
            urls_to_scrape = result['urls']
            logs += f"Spider complete. Found {len(urls_to_scrape)} links.\n"
        elif mode == "sitemap" or url.endswith('.xml'):
            logs += "Sitemap Mode: Extracting URLs...\n"
            await status_msg.edit_text(logs)
            result = await asyncio.to_thread(scraper.extract_sitemap_urls, url)
            urls_to_scrape = result['urls']
            logs += f"Sitemap parsed. Found {len(urls_to_scrape)} links.\n"
        else:
            urls_to_scrape = [url]

        # Scraping Phase with 3000 word limit
        if "file_map" not in context.user_data:
            context.user_data["file_map"] = {}

        success_count = 0
        for i, target_url in enumerate(urls_to_scrape):
            current_log = logs + f"Starting batch scrape...\n[{i+1}/{len(urls_to_scrape)}] Reading: {target_url}\n"
            await status_msg.edit_text(current_log)
            res = await asyncio.to_thread(scraper.scrape_single_url, target_url)
            if res['success']:
                safe_name = "".join(x for x in res['title'] if x.isalnum() or x in " _-").strip() or "Scraped_Page"
                filename = f"{safe_name}_{hashlib.md5(target_url.encode()).hexdigest()[:6]}.md"
                context.user_data["file_map"][filename] = {
                    "text": res['content'],
                    "file_id": None,
                    "is_crawl": True,
                    "url": target_url
                }
                success_count += 1
                logs += f"[{i+1}/{len(urls_to_scrape)}] SUCCESS: {filename}\n"
            else:
                logs += f"[{i+1}/{len(urls_to_scrape)}] FAILED: {res.get('error')}\n"
            await asyncio.sleep(1)

        await status_msg.edit_text(logs + f"\n--- INGESTION COMPLETE ---")
    except Exception as e:
        await status_msg.edit_text(logs + f"\nCRITICAL ERROR: {str(e)}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await deactivate_old_menu(context, update.effective_chat.id)
    file = update.message.document
    if "file_map" not in context.user_data:
        context.user_data["file_map"] = {}
    msg = await update.message.reply_text(f"Reading {file.file_name}...")
    try:
        tg_file = await context.bot.get_file(file.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        content, truncated = await scraper.extract_content(file_bytes, file.file_name)
        context.user_data["file_map"][file.file_name] = {
            "text": content,
            "file_id": file.file_id,
            "is_crawl": False
        }
        status = "Truncated" if truncated else "Complete"
        await msg.edit_text(f"Added {file.file_name}\nStatus: {status}")
    except Exception as e:
        await msg.edit_text(f"Failed: {str(e)}")

async def manage_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    effective_message = update.callback_query.message if update.callback_query else update.message
    await deactivate_old_menu(context, update.effective_chat.id)
    
    files = context.user_data.get("file_map", {})
    if not files:
        await effective_message.reply_text("Memory is empty.")
        return

    context.user_data["id_map"] = {}
    keyboard = []
    for name in files.keys():
        short_id = hashlib.md5(name.encode()).hexdigest()[:10]
        context.user_data["id_map"][short_id] = name
        keyboard.append([
            InlineKeyboardButton(f"DL {name[:15]}", callback_data=f"dl_{short_id}"),
            InlineKeyboardButton(f"Del", callback_data=f"del_{short_id}")
        ])
    keyboard.append([InlineKeyboardButton("Back", callback_data="back_to_main")])
    sent_msg = await effective_message.reply_html(f"<b>Manage Files</b>", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["last_menu_id"] = sent_msg.message_id

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    files = context.user_data.get("file_map", {})
    id_map = context.user_data.get("id_map", {})

    if query.data == "menu_upload":
        await query.edit_message_text(
        "<b>File Upload Instructions</b>\n\n"
        "1. Click the 📎 <b>Attachment</b> icon below.\n"
        "2. Select <b>File</b> or <b>Document</b>.\n"
        "3. Send one of these formats: <code>PDF, Docx, PPTX, XLSX, CSV, HTML, TXT</code>\n\n"
        "The bot will automatically process it once received.",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard()
        )
    elif query.data.startswith("dl_"):
        filename = id_map.get(query.data.replace("dl_", ""))
        data = files.get(filename)
        if data:
            if data["is_crawl"]:
                buffer = scraper.create_downloadable_buffer(data["text"], filename)
                await query.message.reply_document(document=buffer, caption=f"Source: {data['url']}")
            else:
                await query.message.reply_document(document=data["file_id"], caption=f"{filename}")

    elif query.data == "menu_manage":
        await manage_files(update, context)
    elif query.data == "back_to_main":
        await query.edit_message_text("Main Menu", reply_markup=get_main_menu_keyboard())
    elif query.data == "clear_all":
        context.user_data["file_map"] = {}
        await query.edit_message_text("Memory cleared.")
    elif query.data.startswith("del_"):
        filename = id_map.get(query.data.replace("del_", ""))
        if filename in files:
            del files[filename]
            await query.edit_message_text(f"Removed: {filename}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_text = update.message.text
    # Check for manual menu request
    if user_text.lower() == "menu":
        await show_menu(update, context)
        return

    # Chat is continuing: Deactivate any previous menu
    await deactivate_old_menu(context, update.effective_chat.id)

    files = context.user_data.get("file_map", {})
    if not files:
        await update.message.reply_text("Upload a document first.")
        return

    full_context = ""
    for name, data in files.items():
        full_context += f"\n\n--- SOURCE: {name} ---\n{data['text']}"

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        response = await get_groq_response(user_text, full_context)
        await update.message.reply_text(response)
    except Exception:
        await update.message.reply_text("Error processing request.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, NetworkError):
        logger.warning(f"Network issue: {context.error}")
    else:
        logger.error(f"Exception: {context.error}")