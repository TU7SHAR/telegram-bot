import hashlib
import logging
import asyncio
import os
import sys
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import NetworkError, BadRequest
import scraper
from groq_engine import get_groq_response
from database import verify_and_authorize, is_authorized, get_user_role, log_ingested_file, remove_ingested_file

logger = logging.getLogger(__name__)

def require_auth(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        telegram_id = update.effective_user.id
        if not is_authorized(telegram_id):
            if update.callback_query:
                await update.callback_query.answer("❌ Access Denied.", show_alert=True)
            elif update.message:
                await update.message.reply_text("❌ Access Denied. You must authenticate using a valid invite link first.")
            return
        if 'role' not in context.user_data:
            context.user_data['role'] = get_user_role(telegram_id)
        if 'mode' not in context.user_data:
            context.user_data['mode'] = 'feed' if context.user_data['role'] == 'admin' else 'use'
        return await func(update, context, *args, **kwargs)
    return wrapper

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

def get_main_menu_keyboard(role: str, mode: str):
    keyboard = []
    if role == "admin":
        modes_row = []
        if mode != "feed":
            modes_row.append(InlineKeyboardButton("Feed Mode", callback_data="mode_feed"))
        if mode != "test":
            modes_row.append(InlineKeyboardButton("Test Mode", callback_data="mode_test"))
        if mode != "use":
            modes_row.append(InlineKeyboardButton("Use Mode", callback_data="mode_use"))
        if modes_row:
            keyboard.append(modes_row)

        if mode == "feed":
            keyboard.append([InlineKeyboardButton("Upload File", callback_data="menu_upload")])
            keyboard.append([InlineKeyboardButton("Manage Stored Files", callback_data="menu_manage")])
            keyboard.append([InlineKeyboardButton("Crawl New Website", callback_data="menu_crawl")])

    keyboard.append([InlineKeyboardButton("Clear Screen (Keep Memory)", callback_data="clear_chat")])
    
    if role == "admin":
        keyboard.append([InlineKeyboardButton("Wipe All Memory & Screen", callback_data="clear_all")])
        
    keyboard.append([InlineKeyboardButton("Support / Help", url="https://t.me/tu7shar")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name

    if not context.args:
        logger.warning(f"UNAUTHORIZED: {user_name} tried to start without a token.")
        await update.message.reply_text("❌ Access Denied. Please use a valid invite link from the dashboard.")
        return

    token_id = context.args[0]
    telegram_id = update.effective_user.id
    telegram_username = update.effective_user.username or update.effective_user.first_name
    
    is_valid = verify_and_authorize(token_id, telegram_id, telegram_username)
    
    if not is_valid:
        await update.message.reply_text("❌ This invite link is invalid or has already been used.")
        return

    role = get_user_role(telegram_id)
    context.user_data['role'] = role
    context.user_data['mode'] = 'feed' if role == 'admin' else 'use'

    logger.info(f"ACCESS GRANTED: {user_name} activated a token with role {role}.")
    await deactivate_old_menu(context, chat_id)
    
    context.user_data["msg_ids"] = []
    
    sent_msg = await update.message.reply_html(
        f"<b>Welcome {user_name}!</b>\n\nYour access is active. Role: {role.upper()}",
        reply_markup=get_main_menu_keyboard(role, context.user_data['mode'])
    )
    context.user_data["last_menu_id"] = sent_msg.message_id

@require_auth
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"COMMAND triggered: /menu")
    await deactivate_old_menu(context, update.effective_chat.id)
    role = context.user_data.get('role', 'normal')
    mode = context.user_data.get('mode', 'use')
    sent_msg = await update.message.reply_html("<b>Main Menu</b>", reply_markup=get_main_menu_keyboard(role, mode))
    context.user_data["last_menu_id"] = sent_msg.message_id
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data["msg_ids"].extend([sent_msg.message_id, update.message.message_id])

@require_auth
async def clear_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("COMMAND triggered: /clearchat")
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
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

@require_auth
async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get('role', 'normal')
    if role != 'admin':
        return
    logger.info("COMMAND triggered: /clearhistory")
    chat_id = update.effective_chat.id
    if 'msg_ids' in context.user_data:
        for msg_id in context.user_data['msg_ids']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
    context.user_data['msg_ids'] = []
    context.bot_data["file_map"] = {}
    bot_reply = await context.bot.send_message(chat_id=chat_id, text="Total wipe successful. Screen and memory erased.")
    context.user_data['msg_ids'].append(bot_reply.message_id)
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=update.message.message_id)
    except Exception:
        pass

@require_auth
async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get('role', 'normal')
    if role != 'admin':
        return
    logger.warning("COMMAND triggered: /restart. Rebooting system now.")
    await update.message.reply_text("Restarting bot... Please wait.")
    os.execl(sys.executable, sys.executable, *sys.argv)

@require_auth
async def handle_crawl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get('role', 'normal')
    mode = context.user_data.get('mode', 'use')
    if role != 'admin' or mode != 'feed':
        msg = await update.message.reply_text("❌ Must be Admin in Feed Mode.")
        if 'msg_ids' not in context.user_data:
            context.user_data['msg_ids'] = []
        context.user_data['msg_ids'].extend([msg.message_id, update.message.message_id])
        return

    await deactivate_old_menu(context, update.effective_chat.id)
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(update.message.message_id)
    if not context.args:
        msg = await update.message.reply_text("Usage: /crawl [url] [optional: spider/sitemap]")
        context.user_data['msg_ids'].append(msg.message_id)
        return
    url = context.args[0]
    crawl_mode = context.args[1].lower() if len(context.args) > 1 else "single"
    status_msg = await update.message.reply_text(f"Starting crawl for: {url}")
    context.user_data['msg_ids'].append(status_msg.message_id)
    logs = f"Initializing Scraper for Target: {url}\n"
    urls_to_scrape = []
    try:
        if crawl_mode == "spider":
            logs += "Deep Crawl Mode: Searching for internal links...\n"
            await status_msg.edit_text(logs)
            result = await asyncio.to_thread(scraper.crawl_website_links, url)
            urls_to_scrape = result['urls']
            logs += f"Spider complete. Found {len(urls_to_scrape)} links.\n"
        elif crawl_mode == "sitemap" or url.endswith('.xml'):
            logs += "Sitemap Mode: Extracting URLs...\n"
            await status_msg.edit_text(logs)
            result = await asyncio.to_thread(scraper.extract_sitemap_urls, url)
            urls_to_scrape = result['urls']
            logs += f"Sitemap parsed. Found {len(urls_to_scrape)} links.\n"
        else:
            urls_to_scrape = [url]
        if "file_map" not in context.bot_data:
            context.bot_data["file_map"] = {}
        success_count = 0
        for i, target_url in enumerate(urls_to_scrape):
            current_log = logs + f"Starting batch scrape...\n[{i+1}/{len(urls_to_scrape)}] Reading: {target_url}\n"
            await status_msg.edit_text(current_log)
            res = await asyncio.to_thread(scraper.scrape_single_url, target_url)
            if res['success']:
                safe_name = "".join(x for x in res['title'] if x.isalnum() or x in " _-").strip() or "Scraped_Page"
                filename = f"{safe_name}_{hashlib.md5(target_url.encode()).hexdigest()[:6]}.md"
                context.bot_data["file_map"][filename] = {
                    "text": res['content'],
                    "file_id": None,
                    "is_crawl": True,
                    "url": target_url
                }
                success_count += 1
                logs += f"[{i+1}/{len(urls_to_scrape)}] SUCCESS: {filename}\n"
                log_ingested_file(filename, update.effective_user.id, update.effective_user.username or update.effective_user.first_name)
            else:
                logs += f"[{i+1}/{len(urls_to_scrape)}] FAILED: {res.get('error')}\n"
            await asyncio.sleep(1)
        await status_msg.edit_text(logs + f"\n--- INGESTION COMPLETE ---")
    except Exception as e:
        await status_msg.edit_text(logs + f"\nCRITICAL ERROR: {str(e)}")

@require_auth
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = context.user_data.get('role', 'normal')
    mode = context.user_data.get('mode', 'use')
    if role != 'admin' or mode != 'feed':
        msg = await update.message.reply_text("❌ Must be Admin in Feed Mode.")
        if 'msg_ids' not in context.user_data:
            context.user_data['msg_ids'] = []
        context.user_data['msg_ids'].extend([msg.message_id, update.message.message_id])
        return

    await deactivate_old_menu(context, update.effective_chat.id)
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(update.message.message_id)
    file = update.message.document
    if "file_map" not in context.bot_data:
        context.bot_data["file_map"] = {}
    msg = await update.message.reply_text(f"Reading {file.file_name}...")
    context.user_data['msg_ids'].append(msg.message_id)
    try:
        tg_file = await context.bot.get_file(file.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        content, truncated, processed, unprocessed = await scraper.extract_content(file_bytes, file.file_name)
        context.bot_data["file_map"][file.file_name] = {
            "text": content,
            "file_id": file.file_id,
            "is_crawl": False
        }
        log_ingested_file(file.file_name, update.effective_user.id, update.effective_user.username or update.effective_user.first_name)
        if truncated:
            status = f"Truncated\nProcessed: {processed} chars\nLeft out: {unprocessed} chars"
        else:
            status = "Complete"
        await msg.edit_text(f"Added {file.file_name}\nStatus: {status}")
    except Exception as e:
        await msg.edit_text(f"Failed: {str(e)}")

@require_auth
async def manage_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = context.user_data.get('role', 'normal')
    if role != 'admin':
        return
        
    effective_message = update.callback_query.message if update.callback_query else update.message
    await deactivate_old_menu(context, update.effective_chat.id)
    files = context.bot_data.get("file_map", {})
    if not files:
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
    sent_msg = await effective_message.reply_html(f"<b>Manage Files (Global)</b>", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["last_menu_id"] = sent_msg.message_id
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(sent_msg.message_id)

@require_auth
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    role = context.user_data.get("role", "normal")
    mode = context.user_data.get("mode", "use")
    files = context.bot_data.get("file_map", {})
    id_map = context.user_data.get("id_map", {})
    
    if query.data.startswith("mode_"):
        new_mode = query.data.split("_")[1]
        context.user_data["mode"] = new_mode
        text_map = {
            "feed": "<b>Feed Mode</b>\nUpload files or use /crawl to build memory.",
            "test": "<b>Test Prompt Mode</b>\nSend any text. It will be saved as a document.",
            "use": "<b>Use Mode</b>\nAsk questions based on the stored context."
        }
        await query.edit_message_text(text_map[new_mode], parse_mode="HTML", reply_markup=get_main_menu_keyboard(role, new_mode))
    elif query.data == "menu_upload":
        await query.edit_message_text(
            "<b>File Upload Instructions</b>\n\n"
            "1. Click the <b>Attachment</b> icon below.\n"
            "2. Select <b>File</b> or <b>Document</b>.\n"
            "3. Send one of these formats: <code>PDF, Docx, PPTX, XLSX, CSV, HTML, TXT</code>\n\n"
            "The bot will automatically process it once received.",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(role, mode)
        )
    elif query.data == "menu_crawl":
        await query.edit_message_text(
            "<b>Web Crawler Instructions</b>\n\n"
            "To scrape a website, type the command directly in the chat:\n\n"
            "<b>Single Page:</b>\n<code>/crawl https://example.com</code>\n\n"
            "<b>Deep Crawl (Finds internal links):</b>\n<code>/crawl https://example.com spider</code>\n\n"
            "<b>Sitemap:</b>\n<code>/crawl https://example.com sitemap</code>",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(role, mode)
        )
    elif query.data.startswith("dl_"):
        filename = id_map.get(query.data.replace("dl_", ""))
        data = files.get(filename)
        if data:
            if data.get("is_crawl") or data.get("is_custom"):
                buffer = scraper.create_downloadable_buffer(data["text"], filename)
                doc_msg = await query.message.reply_document(document=buffer, caption=f"Source: {filename}")
            else:
                doc_msg = await query.message.reply_document(document=data["file_id"], caption=f"{filename}")
            if 'msg_ids' not in context.user_data:
                context.user_data['msg_ids'] = []
            context.user_data['msg_ids'].append(doc_msg.message_id)
    elif query.data == "menu_manage":
        await manage_files(update, context)
    elif query.data == "back_to_main":
        await query.edit_message_text("Main Menu", reply_markup=get_main_menu_keyboard(role, mode))
    elif query.data == "clear_chat":
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
        chat_id = update.effective_chat.id
        if 'msg_ids' in context.user_data:
            for msg_id in context.user_data['msg_ids']:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception:
                    pass
        context.user_data['msg_ids'] = []
        context.bot_data["file_map"] = {}
        bot_reply = await context.bot.send_message(chat_id=chat_id, text="Total wipe successful. Screen and memory erased.")
        context.user_data['msg_ids'].append(bot_reply.message_id)
    elif query.data.startswith("del_"):
        filename = id_map.get(query.data.replace("del_", ""))
        if filename in files:
            del files[filename]
            remove_ingested_file(filename)
            await query.edit_message_text(f"Removed: {filename}")

@require_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'msg_ids' not in context.user_data:
        context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(update.message.message_id)
    user_text = update.message.text
    
    if user_text.lower() == "menu":
        await show_menu(update, context)
        return
        
    await deactivate_old_menu(context, update.effective_chat.id)
    
    role = context.user_data.get('role', 'normal')
    mode = context.user_data.get('mode', 'use')
    
    if role == 'admin' and mode == 'test':
        if "file_map" not in context.bot_data:
            context.bot_data["file_map"] = {}
        safe_name = "CustomText"
        filename = f"{safe_name}_{hashlib.md5(user_text.encode()).hexdigest()[:6]}.txt"
        context.bot_data["file_map"][filename] = {
            "text": user_text,
            "file_id": None,
            "is_crawl": False,
            "is_custom": True
        }
        msg = await update.message.reply_text(f"✅ Text captured and saved as {filename}\nSwitch to Use Mode to ask questions about it.", reply_markup=get_main_menu_keyboard(role, mode))
        context.user_data['msg_ids'].append(msg.message_id)
        return
        
    if role == 'admin' and mode == 'feed':
        msg = await update.message.reply_text("❌ You are in Feed Mode. Please upload a file, use /crawl, or switch to Use Mode to ask questions.", reply_markup=get_main_menu_keyboard(role, mode))
        context.user_data['msg_ids'].append(msg.message_id)
        return
        
    files = context.bot_data.get("file_map", {})
    if not files:
        if role == 'admin':
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
                reply_markup=get_main_menu_keyboard(role, mode)
            )
        else:
            msg = await update.message.reply_text(
                "The knowledge base is currently empty. Please wait for an Admin to upload documents.",
                reply_markup=get_main_menu_keyboard(role, mode)
            )
            
        context.user_data["last_menu_id"] = msg.message_id 
        context.user_data['msg_ids'].append(msg.message_id)
        try:
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id, 
                message_id=msg.message_id,
                disable_notification=True
            )
        except Exception as e:
            pass
        return
        
    full_context = ""
    for name, data in files.items():
        full_context += f"\n\n--- SOURCE: {name} ---\n{data['text']}"
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    try:
        response = await get_groq_response(user_text, full_context)
        msg = await update.message.reply_text(response)
        context.user_data['msg_ids'].append(msg.message_id)
    except Exception as e:
        msg = await update.message.reply_text("Error processing request.")
        context.user_data['msg_ids'].append(msg.message_id)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    pass