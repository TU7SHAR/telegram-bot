import hashlib
import logging
import asyncio
import os
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import NetworkError, BadRequest
import scraper
from groq_engine import get_groq_response

logger = logging.getLogger(__name__)

async def deactivate_old_menu(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    last_id = context.user_data.get("last_menu_id")
    if last_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=last_id)
        except BadRequest:
            try:
                await context.bot.edit_message_reply_markup(chat_id=chat_id, message_id=last_id, reply_markup=None)
            except:
                pass
        context.user_data["last_menu_id"] = None

def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("Upload File", callback_data="menu_upload")],
        [InlineKeyboardButton("Manage Stored Files", callback_data="menu_manage")],
        [InlineKeyboardButton("Crawl New Website", callback_data="menu_crawl")],
        [InlineKeyboardButton("Clear Screen (Keep Memory)", callback_data="clear_chat")],
        [InlineKeyboardButton("Wipe All Memory & Screen", callback_data="clear_all")],
        [InlineKeyboardButton("Support / Help", url="https://t.me/tu7shar")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user.first_name
    logger.info(f"COMMAND triggered: /start by user {user}")
    await deactivate_old_menu(context, update.effective_chat.id)
    context.user_data["file_map"] = {}
    context.user_data["msg_ids"] = []
    sent_msg = await update.message.reply_html(
        "<b>RAG Bot</b>\n\n"
        "1. Select Upload File to see supported formats\n"
        "2. Use /crawl [url] for web content\n"
        "3. Use /manage to delete memory",
        reply_markup=get_main_menu_keyboard()
    )
    context.user_data["last_menu_id"] = sent_msg.message_id
    context.user_data["msg_ids"].extend([sent_msg.message_id, update.message.message_id])

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"COMMAND triggered: /menu or 'menu' text by user {update.effective_user.first_name}")
    await deactivate_old_menu(context, update.effective_chat.id)
    sent_msg = await update.message.reply_html("<b>Main Menu</b>", reply_markup=get_main_menu_keyboard())
    context.user_data["last_menu_id"] = sent_msg.message_id
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data["msg_ids"].extend([sent_msg.message_id, update.message.message_id])

async def clear_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("COMMAND triggered: /clearchat (Screen only)")
    chat_id = update.effective_chat.id
    if 'msg_ids' in context.user_data:
        for msg_id in context.user_data['msg_ids']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
    context.user_data['msg_ids'] = []
    bot_reply = await context.bot.send_message(
        chat_id=chat_id, 
        text="Screen cleared! (Files are still in memory)."
    )
    context.user_data['msg_ids'].append(bot_reply.message_id)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("COMMAND triggered: /clearhistory (Full memory wipe)")
    chat_id = update.effective_chat.id
    if 'msg_ids' in context.user_data:
        for msg_id in context.user_data['msg_ids']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
    context.user_data['msg_ids'] = []
    context.user_data["file_map"] = {}
    logger.info("STATE -> User memory file_map completely erased.")
    bot_reply = await context.bot.send_message(
        chat_id=chat_id, 
        text="Total wipe successful. Screen and memory erased."
    )
    context.user_data['msg_ids'].append(bot_reply.message_id)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.warning("COMMAND triggered: /restart. Rebooting system now.")
    await update.message.reply_text("Restarting bot... Please wait.")
    os.execl(sys.executable, sys.executable, *sys.argv)

async def handle_crawl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await deactivate_old_menu(context, update.effective_chat.id)
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(update.message.message_id)
    if not context.args:
        logger.info("CRAWL -> User triggered /crawl with no arguments.")
        msg = await update.message.reply_text("Usage: /crawl [url] [optional: spider/sitemap]")
        context.user_data['msg_ids'].append(msg.message_id)
        return
    url = context.args[0]
    mode = context.args[1].lower() if len(context.args) > 1 else "single"
    logger.info(f"COMMAND triggered: /crawl | URL: {url} | Mode: {mode}")
    status_msg = await update.message.reply_text(f"Starting crawl for: {url}")
    context.user_data['msg_ids'].append(status_msg.message_id)
    logs = f"Initializing Scraper for Target: {url}\n"
    urls_to_scrape = []
    try:
        if mode == "spider":
            logs += "Deep Crawl Mode: Searching for internal links...\n"
            await status_msg.edit_text(logs)
            result = await asyncio.to_thread(scraper.crawl_website_links, url)
            urls_to_scrape = result['urls']
            logger.info(f"CRAWL SPIDER -> Found {len(urls_to_scrape)} links.")
            logs += f"Spider complete. Found {len(urls_to_scrape)} links.\n"
        elif mode == "sitemap" or url.endswith('.xml'):
            logs += "Sitemap Mode: Extracting URLs...\n"
            await status_msg.edit_text(logs)
            result = await asyncio.to_thread(scraper.extract_sitemap_urls, url)
            urls_to_scrape = result['urls']
            logger.info(f"CRAWL SITEMAP -> Found {len(urls_to_scrape)} links.")
            logs += f"Sitemap parsed. Found {len(urls_to_scrape)} links.\n"
        else:
            urls_to_scrape = [url]
        if "file_map" not in context.user_data:
            context.user_data["file_map"] = {}
        success_count = 0
        for i, target_url in enumerate(urls_to_scrape):
            current_log = logs + f"Starting batch scrape...\n[{i+1}/{len(urls_to_scrape)}] Reading: {target_url}\n"
            await status_msg.edit_text(current_log)
            logger.info(f"CRAWL FIRECRAWL -> Extracting markdown from: {target_url}")
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
                logger.info(f"CRAWL SUCCESS -> Stored {filename} ({len(res['content'])} chars)")
                logs += f"[{i+1}/{len(urls_to_scrape)}] SUCCESS: {filename}\n"
            else:
                logger.error(f"CRAWL FAILED -> {target_url} | Error: {res.get('error')}")
                logs += f"[{i+1}/{len(urls_to_scrape)}] FAILED: {res.get('error')}\n"
            await asyncio.sleep(1)
        logger.info(f"CRAWL COMPLETE -> Total ingested: {success_count}/{len(urls_to_scrape)}")
        await status_msg.edit_text(logs + f"\n--- INGESTION COMPLETE ---")
    except Exception as e:
        logger.error(f"CRAWL CRITICAL ERROR -> {str(e)}")
        await status_msg.edit_text(logs + f"\nCRITICAL ERROR: {str(e)}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"DOCUMENT received: {update.message.document.file_name}")
    await deactivate_old_menu(context, update.effective_chat.id)
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(update.message.message_id)
    file = update.message.document
    if "file_map" not in context.user_data:
        context.user_data["file_map"] = {}
    msg = await update.message.reply_text(f"Reading {file.file_name}...")
    context.user_data['msg_ids'].append(msg.message_id)
    try:
        logger.info(f"FILE DOWNLOAD -> Fetching {file.file_name} from Telegram servers...")
        tg_file = await context.bot.get_file(file.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        logger.info(f"FILE PARSE -> Extracting text using MarkItDown...")
        content, truncated, processed, unprocessed = await scraper.extract_content(file_bytes, file.file_name)
        context.user_data["file_map"][file.file_name] = {
            "text": content,
            "file_id": file.file_id,
            "is_crawl": False
        }
        if truncated:
            status = f"Truncated\nProcessed: {processed} chars\nLeft out: {unprocessed} chars"
        else:
            status = "Complete"
        logger.info(f"FILE SUCCESS -> Stored {file.file_name} | Length: {len(content)} chars | Status: {status.replace(chr(10), ' - ')}")
        await msg.edit_text(f"Added {file.file_name}\nStatus: {status}")
    except Exception as e:
        logger.error(f"FILE ERROR -> Failed to process {file.file_name}: {str(e)}")
        await msg.edit_text(f"Failed: {str(e)}")

async def manage_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("COMMAND triggered: /manage (or Manage Files menu)")
    effective_message = update.callback_query.message if update.callback_query else update.message
    await deactivate_old_menu(context, update.effective_chat.id)
    files = context.user_data.get("file_map", {})
    if not files:
        logger.info("MANAGE FILES -> Memory is currently empty.")
        msg = await effective_message.reply_text("Memory is empty.")
        if 'msg_ids' not in context.user_data:
            context.user_data['msg_ids'] = []
        context.user_data['msg_ids'].append(msg.message_id)
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
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(sent_msg.message_id)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    logger.info(f"BUTTON CLICK -> User pressed: {query.data}")
    await query.answer()
    files = context.user_data.get("file_map", {})
    id_map = context.user_data.get("id_map", {})
    if query.data == "menu_upload":
        await query.edit_message_text(
            "<b>File Upload Instructions</b>\n\n"
            "1. Click the <b>Attachment</b> icon below.\n"
            "2. Select <b>File</b> or <b>Document</b>.\n"
            "3. Send one of these formats: <code>PDF, Docx, PPTX, XLSX, CSV, HTML, TXT</code>\n\n"
            "The bot will automatically process it once received.",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    elif query.data == "menu_crawl":
        await query.edit_message_text(
            "<b>Web Crawler Instructions</b>\n\n"
            "To scrape a website, type the command directly in the chat:\n\n"
            "<b>Single Page:</b>\n<code>/crawl https://example.com</code>\n\n"
            "<b>Deep Crawl (Finds internal links):</b>\n<code>/crawl https://example.com spider</code>\n\n"
            "<b>Sitemap:</b>\n<code>/crawl https://example.com sitemap</code>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
    elif query.data.startswith("dl_"):
        filename = id_map.get(query.data.replace("dl_", ""))
        data = files.get(filename)
        if data:
            logger.info(f"DOWNLOAD TRIGGERED -> Sending {filename} to user.")
            if data["is_crawl"]:
                buffer = scraper.create_downloadable_buffer(data["text"], filename)
                doc_msg = await query.message.reply_document(document=buffer, caption=f"Source: {data['url']}")
            else:
                doc_msg = await query.message.reply_document(document=data["file_id"], caption=f"{filename}")
            if 'msg_ids' not in context.user_data:
                context.user_data['msg_ids'] = []
            context.user_data['msg_ids'].append(doc_msg.message_id)
    elif query.data == "menu_manage":
        await manage_files(update, context)
    elif query.data == "back_to_main":
        await query.edit_message_text("Main Menu", reply_markup=get_main_menu_keyboard())
    elif query.data == "clear_chat":
        logger.info("BUTTON CLICK -> Clear Screen Executing")
        chat_id = update.effective_chat.id
        if 'msg_ids' in context.user_data:
            for msg_id in context.user_data['msg_ids']:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception:
                    pass
        context.user_data['msg_ids'] = []
        bot_reply = await context.bot.send_message(chat_id=chat_id, text="Screen cleared! (Files are still in memory).")
        context.user_data['msg_ids'].append(bot_reply.message_id)
    elif query.data == "clear_all":
        logger.info("BUTTON CLICK -> Clear All Executing")
        chat_id = update.effective_chat.id
        if 'msg_ids' in context.user_data:
            for msg_id in context.user_data['msg_ids']:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception:
                    pass
        context.user_data['msg_ids'] = []
        context.user_data["file_map"] = {}
        bot_reply = await context.bot.send_message(chat_id=chat_id, text="Total wipe successful. Screen and memory erased.")
        context.user_data['msg_ids'].append(bot_reply.message_id)
    elif query.data.startswith("del_"):
        filename = id_map.get(query.data.replace("del_", ""))
        if filename in files:
            del files[filename]
            logger.info(f"FILE DELETE -> Removed {filename} from user memory.")
            await query.edit_message_text(f"Removed: {filename}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(update.message.message_id)
    user_text = update.message.text
    logger.info(f"CHAT INPUT -> User asks: '{user_text}'")
    if user_text.lower() == "menu":
        await show_menu(update, context)
        return
    await deactivate_old_menu(context, update.effective_chat.id)
    files = context.user_data.get("file_map", {})
    if not files:
        logger.warning("CHAT INPUT REJECTED -> User asked a question but memory is empty.")
        manual_text = (
            "Please upload a document or crawl a website first to give me some context.\n\n"
            "<b>Command Manual:</b>\n"
            "• <code>/start</code> - Initialize session\n"
            "• <code>/menu</code> - Show control panel\n"
            "• <code>/crawl [url]</code> - Scrape a webpage\n"
            "• <code>/crawl [url] spider</code> - Deep crawl internal links\n"
            "• <code>/manage</code> - View, download, or delete files\n"
            "• <code>/clearchat</code> - Clear screen (keep memory)\n"
            "• <code>/clearhistory</code> - Wipe screen & memory\n"
            "• <code>/restart</code> - Reboot system"
        )
        msg = await update.message.reply_text(
            manual_text,
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard()
        )
        context.user_data["last_menu_id"] = msg.message_id 
        context.user_data['msg_ids'].append(msg.message_id)
        try:
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id, 
                message_id=msg.message_id,
                disable_notification=True
            )
            logger.info("UX AUTOMATION -> Pinned the command manual for the user.")
        except Exception as e:
            logger.error(f"UX ERROR -> Failed to pin message: {e}")
        return
    full_context = ""
    for name, data in files.items():
        full_context += f"\n\n--- SOURCE: {name} ---\n{data['text']}"
    logger.info(f"RAG BUILDER -> Appending {len(files)} files to prompt. Total context length: {len(full_context)} chars.")
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        response = await get_groq_response(user_text, full_context)
        msg = await update.message.reply_text(response)
        context.user_data['msg_ids'].append(msg.message_id)
    except Exception as e:
        logger.error(f"CHAT ROUTING ERROR -> Failed to get response: {str(e)}")
        msg = await update.message.reply_text("Error processing request.")
        context.user_data['msg_ids'].append(msg.message_id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, NetworkError):
        logger.warning(f"TELEGRAM NETWORK ISSUE: {context.error}")
    else:
        logger.error(f"TELEGRAM FATAL EXCEPTION: {context.error}", exc_info=True)