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
from database import get_bot_settings, log_chat_interaction, verify_and_authorize, is_authorized, get_user_role, log_ingested_file, remove_ingested_file, get_google_id, clear_user_auth, get_user_state, update_user_state, save_onboarding_lead, get_active_filenames, save_test_result, get_onboarding_lead

logger = logging.getLogger(__name__)

def require_auth(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        telegram_id = update.effective_user.id
        if not is_authorized(telegram_id):
            if update.callback_query:
                await update.callback_query.answer(" Access Denied.", show_alert=True)
            elif update.message:
                await update.message.reply_text("Access Denied. You must authenticate using a valid invite link first.")
            return
            
        if 'role' not in context.user_data:
            context.user_data['role'] = get_user_role(telegram_id)
        if 'mode' not in context.user_data:
            context.user_data['mode'] = 'feed' if context.user_data['role'] == 'admin' else 'use'
        if 'google_id' not in context.user_data:
            context.user_data['google_id'] = get_google_id(telegram_id)
            
        return await func(update, context, *args, **kwargs)
    return wrapper

def get_tenant_files(context: ContextTypes.DEFAULT_TYPE):
    google_id = context.user_data.get('google_id')
    if not google_id:
        return {}
    if google_id not in context.bot_data:
        context.bot_data[google_id] = {"file_map": {}}
    return context.bot_data[google_id]["file_map"]

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
            modes_row.append(InlineKeyboardButton("Add Custom Data", callback_data="mode_test"))
        if mode != "use":
            modes_row.append(InlineKeyboardButton("Use Mode", callback_data="mode_use"))
        if modes_row:
            keyboard.append(modes_row)

        if mode == "feed":
            keyboard.append([InlineKeyboardButton("Upload File", callback_data="menu_upload")])
            keyboard.append([InlineKeyboardButton("Manage Stored Files", callback_data="menu_manage")])
            keyboard.append([InlineKeyboardButton("Crawl New Website", callback_data="menu_crawl")])

    # --- NEW: Show Sales Assistant features in 'Use Mode' ---
    if mode == "use":
        keyboard.append([InlineKeyboardButton(" Start Onboarding", callback_data="start_onboarding")])
        keyboard.append([InlineKeyboardButton(" Training Mode", callback_data="start_training")])
        keyboard.append([InlineKeyboardButton(" Test Mode", callback_data="start_test")])

    keyboard.append([InlineKeyboardButton("Clear Screen (Keep Memory)", callback_data="clear_chat")])
    if role == "admin":
        keyboard.append([InlineKeyboardButton("Wipe All Memory & Screen", callback_data="clear_all")])
    keyboard.append([InlineKeyboardButton("Support / Help", url="https://t.me/tu7shar")])
    
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_name = update.effective_user.first_name

    if not context.args:
        await update.message.reply_text(" Access Denied. Please use a valid invite link from the dashboard.")
        return

    token_id = context.args[0]
    telegram_id = update.effective_user.id
    telegram_username = update.effective_user.username or update.effective_user.first_name
    
    is_valid = verify_and_authorize(token_id, telegram_id, telegram_username)
    
    if not is_valid:
        await update.message.reply_text(" This invite link is invalid or has already been used.")
        return

    role = get_user_role(telegram_id)
    google_id = get_google_id(telegram_id)
    
    context.user_data['role'] = role
    context.user_data['mode'] = 'feed' if role == 'admin' else 'use'
    context.user_data['google_id'] = google_id

    await deactivate_old_menu(context, chat_id)
    context.user_data["msg_ids"] = []
    
    sent_msg = await update.message.reply_html(
        f"<b>Welcome {user_name}!</b>\n\nYour access is active. Role: {role.upper()}",
        reply_markup=get_main_menu_keyboard(role, context.user_data['mode'])
    )
    context.user_data["last_menu_id"] = sent_msg.message_id

@require_auth
async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    google_id = context.user_data.get('google_id')
    if role != 'admin' or not google_id:
        return
        
    chat_id = update.effective_chat.id
    if 'msg_ids' in context.user_data:
        for msg_id in context.user_data['msg_ids']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except Exception:
                pass
                
    context.user_data['msg_ids'] = []
    if google_id in context.bot_data:
        context.bot_data[google_id]["file_map"] = {}
        
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
    await update.message.reply_text("Restarting bot... Please wait.")
    os.execl(sys.executable, sys.executable, *sys.argv)

@require_auth
async def handle_crawl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = context.user_data.get('role', 'normal')
    mode = context.user_data.get('mode', 'use')
    google_id = context.user_data.get('google_id')
    
    if role != 'admin' or mode != 'feed':
        msg = await update.message.reply_text(" Must be Admin in Feed Mode.")
        if 'msg_ids' not in context.user_data: context.user_data['msg_ids'] = []
        context.user_data['msg_ids'].extend([msg.message_id, update.message.message_id])
        return

    await deactivate_old_menu(context, update.effective_chat.id)
    if 'msg_ids' not in context.user_data: context.user_data['msg_ids'] = []
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
            result = await asyncio.to_thread(scraper.crawl_website_links, url)
            urls_to_scrape = result['urls']
        elif crawl_mode == "sitemap" or url.endswith('.xml'):
            result = await asyncio.to_thread(scraper.extract_sitemap_urls, url)
            urls_to_scrape = result['urls']
        else:
            urls_to_scrape = [url]
            
        files = get_tenant_files(context)
        
        for i, target_url in enumerate(urls_to_scrape):
            current_log = logs + f"[{i+1}/{len(urls_to_scrape)}] Reading: {target_url}\n"
            await status_msg.edit_text(current_log)
            res = await asyncio.to_thread(scraper.scrape_single_url, target_url)
            if res['success']:
                safe_name = "".join(x for x in res['title'] if x.isalnum() or x in " _-").strip() or "Scraped_Page"
                filename = f"{safe_name}_{hashlib.md5(target_url.encode()).hexdigest()[:6]}.md"
                files[filename] = {
                    "text": res['content'],
                    "file_id": None,
                    "is_crawl": True,
                    "url": target_url
                }
                logs += f"[{i+1}/{len(urls_to_scrape)}] SUCCESS: {filename}\n"
                log_ingested_file(filename, update.effective_user.id, update.effective_user.username or update.effective_user.first_name, google_id)
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
    google_id = context.user_data.get('google_id')
    
    if role != 'admin' or mode != 'feed':
        msg = await update.message.reply_text("❌ Must be Admin in Feed Mode.")
        if 'msg_ids' not in context.user_data: context.user_data['msg_ids'] = []
        context.user_data['msg_ids'].extend([msg.message_id, update.message.message_id])
        return

    await deactivate_old_menu(context, update.effective_chat.id)
    if 'msg_ids' not in context.user_data: context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(update.message.message_id)
    file = update.message.document
    
    files = get_tenant_files(context)
    
    msg = await update.message.reply_text(f"Reading {file.file_name}...")
    context.user_data['msg_ids'].append(msg.message_id)
    try:
        tg_file = await context.bot.get_file(file.file_id)
        file_bytes = await tg_file.download_as_bytearray()
        content, truncated, processed, unprocessed = await scraper.extract_content(file_bytes, file.file_name)
        
        # 1. HOLD DATA USING A DICTIONARY KEYED BY MESSAGE ID
        if 'pending_files' not in context.user_data:
            context.user_data['pending_files'] = {}
            
        context.user_data['pending_files'][msg.message_id] = {
            "filename": file.file_name,
            "text": content,
            "file_id": file.file_id,
            "is_crawl": False
        }
        
        # 2. PASS THE MESSAGE ID INTO THE BUTTON CALLBACK DATA
        m_id = msg.message_id
        keyboard = [
            [InlineKeyboardButton(" Technical", callback_data=f"cat_Technical_{m_id}"),
             InlineKeyboardButton(" Marketing", callback_data=f"cat_Marketing_{m_id}")],
            [InlineKeyboardButton(" HR", callback_data=f"cat_HR_{m_id}"),
             InlineKeyboardButton(" General", callback_data=f"cat_General_{m_id}")]
        ]
        
        await msg.edit_text(
            f"File read successfully! Please select a category for <b>{file.file_name}</b>:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
    except Exception as e:
        await msg.edit_text(f"Failed: {str(e)}")

@require_auth
async def manage_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    role = context.user_data.get('role', 'normal')
    if role != 'admin':
        return
        
    effective_message = update.callback_query.message if update.callback_query else update.message
    await deactivate_old_menu(context, update.effective_chat.id)
    
    files = get_tenant_files(context)
    if not files:
        msg = await effective_message.reply_text("Your Private Knowledge Base is empty.")
        if 'msg_ids' not in context.user_data: context.user_data['msg_ids'] = []
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
    sent_msg = await effective_message.reply_html(f"<b>Manage Tenant Files</b>", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["last_menu_id"] = sent_msg.message_id
    context.user_data['msg_ids'].append(sent_msg.message_id)

@require_auth
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    role = context.user_data.get("role", "normal")
    mode = context.user_data.get("mode", "use")
    google_id = context.user_data.get("google_id")
    files = get_tenant_files(context)
    id_map = context.user_data.get("id_map", {})
    if google_id:
        active_filenames = get_active_filenames(google_id)
        if active_filenames is not None:
            files_to_remove = [name for name in list(files.keys()) if name not in active_filenames]
            for name in files_to_remove:
                del files[name]
    
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
            "<b>File Upload Instructions</b>\n\n1. Click <b>Attachment</b> icon.\n2. Select Document.",
            parse_mode="HTML", reply_markup=get_main_menu_keyboard(role, mode)
        )
        
    elif query.data == "menu_crawl":
        await query.edit_message_text(
            "<b>Web Crawler Instructions</b>\n\nUse <code>/crawl [url]</code>",
            parse_mode="HTML", reply_markup=get_main_menu_keyboard(role, mode)
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
            context.user_data['msg_ids'].append(doc_msg.message_id)
            
    elif query.data == "menu_manage":
        await manage_files(update, context)
        
    elif query.data == "back_to_main":
        await query.edit_message_text("Main Menu", reply_markup=get_main_menu_keyboard(role, mode))
        
    elif query.data == "clear_chat":
        chat_id = update.effective_chat.id
        if 'msg_ids' in context.user_data:
            for msg_id in context.user_data['msg_ids']:
                try: await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except: pass
        context.user_data['msg_ids'] = []
        bot_reply = await context.bot.send_message(chat_id=chat_id, text="Screen cleared!")
        context.user_data['msg_ids'].append(bot_reply.message_id)
        
    elif query.data == "clear_all":
        chat_id = update.effective_chat.id
        if 'msg_ids' in context.user_data:
            for msg_id in context.user_data['msg_ids']:
                try: await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except: pass
        context.user_data['msg_ids'] = []
        if google_id in context.bot_data: context.bot_data[google_id]["file_map"] = {}
        bot_reply = await context.bot.send_message(chat_id=chat_id, text="Wipe successful.")
        context.user_data['msg_ids'].append(bot_reply.message_id)
        
    elif query.data.startswith("del_"):
        filename = id_map.get(query.data.replace("del_", ""))
        if filename in files:
            del files[filename]
            remove_ingested_file(filename, google_id)
            await query.edit_message_text(f"Removed: {filename}")
            
    # --- MULTI-FILE CATEGORIZATION LOGIC ---
    elif query.data.startswith("cat_"):
        parts = query.data.split("_")
        category = parts[1]
        msg_id = int(parts[2]) if len(parts) > 2 else query.message.message_id
        
        pending_files = context.user_data.get('pending_files', {})
        pending_file = pending_files.get(msg_id)
        
        if not pending_file:
            await query.edit_message_text("Session expired. Please upload the file again.")
            return
            
        filename = pending_file['filename']
        pending_file['category'] = category
        
        # Save to bot memory
        files = get_tenant_files(context)
        files[filename] = pending_file
        
        # Log to database
        log_ingested_file(
            filename, 
            update.effective_user.id, 
            update.effective_user.username or update.effective_user.first_name, 
            google_id, 
            category
        )
        
        # Clean up memory
        del pending_files[msg_id]
        await query.edit_message_text(f" <b>{filename}</b> successfully saved under <b>[{category}]</b>.", parse_mode="HTML")

    # --- ONBOARDING LOGIC ---
    elif query.data == "start_onboarding":
        telegram_id = update.effective_user.id
        update_user_state(telegram_id, mode="onboarding", step=1)
        await query.edit_message_text(
            " Welcome to Onboarding! Let's get you set up.\n\nFirst, what is your full name?"
        )

    # --- SALES TRAINING LOGIC ---
    elif query.data == "start_training":
        keyboard = [
            [InlineKeyboardButton(" Technical", callback_data="traincat_Technical"),
             InlineKeyboardButton(" Marketing", callback_data="traincat_Marketing")],
            [InlineKeyboardButton(" HR", callback_data="traincat_HR"),
             InlineKeyboardButton(" General", callback_data="traincat_General")]
        ]
        await query.edit_message_text(
            " <b>Sales Training Mode</b>\n\nWhich category would you like to study today?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    # --- TAKE A TEST LOGIC ---
    elif query.data == "start_test":
        keyboard = [
            [InlineKeyboardButton(" Technical", callback_data="testcat_Technical"),
             InlineKeyboardButton(" Marketing", callback_data="testcat_Marketing")],
            [InlineKeyboardButton(" HR", callback_data="testcat_HR"),
             InlineKeyboardButton(" General", callback_data="testcat_General")]
        ]
        await query.edit_message_text(
            " <b>Sales Knowledge Test</b>\n\nWhich category would you like to be tested on?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )

    elif query.data.startswith("testcat_"):
        category = query.data.split("_")[1]
        telegram_id = update.effective_user.id
        await query.edit_message_text(f" Generating your customized test from <b>{category}</b>... Please wait.", parse_mode="HTML")
        
        # 1. Fetch the user's passion from the database
        lead_data = get_onboarding_lead(telegram_id)
        passion = lead_data.get('passion', 'achieving career success') if lead_data else 'achieving career success'
        
        test_context = ""
        for name, data in files.items():
            if data.get('category') == category:
                test_context += f"\n\n--- SOURCE: {name} ---\n{data['text']}"
                
        if not test_context:
            await query.edit_message_text(f" No documents found in <b>{category}</b>.", parse_mode="HTML")
            return
            
        # 2. Randomize total questions between 3 and 7
        num_mcqs = random.randint(0, 4)
        total_questions = 3 + num_mcqs
            
        prompt = f"""Based ONLY on these {category} documents, generate a test with EXACTLY {total_questions} questions. Do NOT use line breaks inside a question.

        REQUIREMENTS:
        - Questions 1 to 3 MUST be theoretical free-text questions about the documents. Format each exactly like this on a single line:
        TEXT_Q::: [Question Text]
        """
        
        if num_mcqs > 0:
            prompt += f"""
        - The remaining {num_mcqs} questions MUST be Multiple Choice Questions (MCQs).
        - The MCQs MUST integrate the user's core passion/drive, which is: "{passion}". Frame the MCQs as situational sales scenarios combining the documents with their passion. Do NOT ask about their basic personal details.
        - Format each MCQ exactly like this on a single line:
        MCQ::: [Question Text] ||| [Option A] ||| [Option B] ||| [Option C] ||| [Option D]
        """

        try:
            response = await get_groq_response(prompt, test_context, temperature=0.3)
            
            # 3. Parse Groq's output securely
            questions = []
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith("TEXT_Q:::"):
                    questions.append({
                        "type": "text", 
                        "text": line.replace("TEXT_Q:::", "").strip()
                    })
                elif line.startswith("MCQ:::"):
                    parts = line.replace("MCQ:::", "").split("|||")
                    if len(parts) >= 5:
                        questions.append({
                            "type": "mcq", 
                            "text": parts[0].strip(), 
                            "options": [p.strip() for p in parts[1:5]]
                        })
            
            if len(questions) < 3:
                await query.edit_message_text(" Failed to generate the test format correctly. Please try again.")
                return
                
            # Lock the user into "Testing" mode
            update_user_state(telegram_id, "testing", step=0, metadata={
                "category": category,
                "questions": questions,
                "answers": [],
                "total_questions": len(questions)
            })
            
            first_q = questions[0]
            await query.edit_message_text(
                f" <b>Test Started: {category}</b>\n\n<b>Question 1 of {len(questions)}:</b>\n{first_q['text']}\n\n<i>Type your answer below:</i>",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Test generation error: {e}")
            await query.edit_message_text(" Error generating test.")
    elif query.data.startswith("traincat_"):
        category = query.data.split("_")[1]
        await query.edit_message_text(f" Pulling training materials for <b>{category}</b>... Please wait.", parse_mode="HTML")
        
        # Filter files by the selected category
        training_context = ""
        for name, data in files.items():
            if data.get('category') == category:
                training_context += f"\n\n--- SOURCE: {name} ---\n{data['text']}"
                
        if not training_context:
            await query.edit_message_text(
                f" No documents found in the <b>{category}</b> category. Admin needs to upload some in Feed Mode first.", 
                parse_mode="HTML"
            )
            return
            
        # Ask Groq for a specific training summary
        prompt = f"Create a bite-sized, highly actionable 3-bullet-point training summary based ONLY on these {category} documents. Keep it brief to help a sales rep learn the material quickly."
        
        try:
            # Use strict temperature (0.2) to prevent hallucination
            response = await get_groq_response(prompt, training_context, temperature=0.2)
            
            tutorial_msg = (
                f" <b>Training Module: {category}</b>\n\n"
                f"{response}\n\n"
                f"<i>When you are ready to test your knowledge, try the Quiz mode!</i>"
            )
            await query.edit_message_text(tutorial_msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Training error: {e}")
            await query.edit_message_text(" Error generating training module. Please try again.")

@require_auth
async def start_onboarding_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user types /onboard"""
    telegram_id = update.effective_user.id
    update_user_state(telegram_id, mode="onboarding", step=1)
    await update.message.reply_text("👋 Welcome to Onboarding! Let's get you set up.\n\nFirst, what is your full name?")

async def handle_onboarding_step(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
    """Expanded Onboarding Flow with Bot Tutorial"""
    step = state['current_step']
    text = update.message.text
    metadata = state.get('metadata', {})
    t_id = update.effective_user.id

    if step == 1:
        metadata['full_name'] = text
        update_user_state(t_id, "onboarding", step=2, metadata=metadata)
        await update.message.reply_text(f"Nice to meet you, {text}! What's the best phone number to reach you at?")
    
    elif step == 2:
        metadata['phone_number'] = text
        update_user_state(t_id, "onboarding", step=3, metadata=metadata)
        await update.message.reply_text("Got it. What is your current role or job title in the company?")
        
    elif step == 3:
        metadata['role'] = text
        update_user_state(t_id, "onboarding", step=4, metadata=metadata)
        await update.message.reply_text(
            "Awesome. Finally, tell me a bit about yourself—what is your passion, or what drives you to succeed in your career?"
        )

    elif step == 4:
        # Save the detailed lead to the database
        save_onboarding_lead({
            "telegram_id": t_id,
            "full_name": metadata.get('full_name', 'Unknown'),
            "phone_number": metadata.get('phone_number', 'Unknown'),
            "role": metadata.get('role', 'Unknown'),
            "passion": text
        })
        
        # Release the user back to normal AI chat mode
        update_user_state(t_id, mode="use", step=0, metadata={})
        
        # The Onboarding Tutorial Payload
        tutorial_text = (
            " <b>Profile Locked In!</b>\n\n"
            "Welcome aboard. I am your Sales Assistant. Here is how you can use me to crush your goals:\n\n"
            " <b>Ask Anything:</b> Just type a question (e.g., <i>'What are our pricing tiers?'</i>) and I will pull the exact answer from our company knowledge base.\n"
            " <b>Sales Training:</b> Need to brush up on a topic? We have bite-sized training modules based on real company documents.\n"
            " <b>Navigation:</b> If you ever get lost, just type <code>menu</code> to pull up your options.\n\n"
            "Let's get to work! What do you need help with today?"
        )
        await update.message.reply_html(tutorial_text) 
        await update.message.reply_text("✅ Onboarding Complete! Your profile has been saved. You can now chat with the AI normally.")

async def handle_test_step(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict):
    """Processes the Dynamic Randomized Test Mode"""
    text = update.message.text
    t_id = update.effective_user.id
    
    # Allow user to escape the test
    if text.lower() in ["/cancel", "cancel"]:
        update_user_state(t_id, mode="use", step=0, metadata={})
        await update.message.reply_text("🚫 Test cancelled. Returning to normal chat mode.")
        return

    step = state['current_step']
    metadata = state.get('metadata', {})
    questions = metadata.get("questions", [])
    answers = metadata.get("answers", [])
    total_questions = metadata.get("total_questions", 3)
    
    # Save user's answer
    answers.append(text)
    metadata["answers"] = answers
    
    if step + 1 < total_questions:
        next_step = step + 1
        update_user_state(t_id, "testing", step=next_step, metadata=metadata)
        
        q_data = questions[next_step]
        msg_text = f"<b>Question {next_step + 1} of {total_questions}:</b>\n{q_data['text']}\n\n"
        
        # Format MCQ options if it's a multiple-choice question
        if q_data['type'] == 'mcq':
            msg_text += "<b>Options:</b>\n"
            letters = ['A', 'B', 'C', 'D']
            for i, opt in enumerate(q_data['options']):
                msg_text += f"<b>{letters[i]})</b> {opt}\n"
            msg_text += "\n<i>Type the letter of your answer (A, B, C, or D):</i>"
        else:
            msg_text += "<i>Type your answer below:</i>"
            
        await update.message.reply_html(msg_text)
    else:
        # Evaluate All Answers
        msg = await update.message.reply_html("⏳ <b>Evaluating your answers...</b> Please wait.")
        
        category = metadata.get("category")
        files = get_tenant_files(context)
        test_context = "".join([f"\n--- SOURCE: {name} ---\n{data['text']}" for name, data in files.items() if data.get('category') == category])
        
        # Build QA Log for Groq
        qa_log = ""
        for i in range(total_questions):
            qa_log += f"Q{i+1}: {questions[i]['text']}\nUser Answer: {answers[i]}\n\n"
        
        eval_prompt = (
            f"You are an expert Sales Manager evaluating a trainee. Assess these {total_questions} answers based ONLY on the provided {category} documents.\n\n"
            f"{qa_log}"
            f"Provide brief, constructive remarks for each answer. For MCQs, state if they chose the correct letter. Then assign a total score out of {total_questions}. "
            "Format your response exactly like this:\n\nSCORE: [X]\n\nREMARKS:\n[Your specific remarks here]"
        )
        
        try:
            response = await get_groq_response(eval_prompt, test_context, temperature=0.2)
            
            score = 0
            if "SCORE:" in response:
                try:
                    score_line = [line for line in response.split("\n") if "SCORE:" in line][0]
                    score = int(''.join(filter(str.isdigit, score_line)))
                except: pass
            
            simplified_qs = [q['text'] for q in questions]
            
            save_test_result({
                "telegram_id": t_id,
                "category": category,
                "qa_data": {"questions": simplified_qs, "user_answers": answers},
                "score": score,
                "total_questions": total_questions,
                "remarks": response
            })
            
            update_user_state(t_id, mode="use", step=0, metadata={})
            await msg.edit_text(f" Test Complete!\n\n{response}")
            
        except Exception as e:
            logger.error(f"Test evaluation error: {e}")
            update_user_state(t_id, mode="use", step=0, metadata={})
            await msg.edit_text(" Error evaluating test. Returning to chat mode.")

@require_auth
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if 'msg_ids' not in context.user_data: context.user_data['msg_ids'] = []
    context.user_data['msg_ids'].append(update.message.message_id)
    user_text = update.message.text
    user = update.effective_user
    
    state = get_user_state(user.id)
    if state and state.get('current_mode') == 'onboarding':
        await handle_onboarding_step(update, context, state)
        return
    elif state.get('current_mode') == 'testing':
            await handle_test_step(update, context, state)
            return

    if user_text.lower() == "menu":
        await show_menu(update, context)
        return
        
    await deactivate_old_menu(context, update.effective_chat.id)
    
    role = context.user_data.get('role', 'normal')
    mode = context.user_data.get('mode', 'use')
    google_id = context.user_data.get('google_id')
    files = get_tenant_files(context)

    if google_id:
        active_filenames = get_active_filenames(google_id)
        if active_filenames is not None:
            # list() is required here to prevent dictionary size errors during iteration
            files_to_remove = [name for name in list(files.keys()) if name not in active_filenames]
            for name in files_to_remove:
                del files[name]

    # 1. Fetch Dynamic Settings from Supabase linked to the Admin (google_id)
    settings = get_bot_settings(google_id)
    
    # 2. Maintenance Mode Check
    # Blocks non-admins if Maintenance Mode is toggled ON in the dashboard
    if settings.get('maintenance_mode') and role != 'admin':
        msg = await update.message.reply_html(
            "🚧 <b>Maintenance Mode</b>\nThe bot is temporarily offline for updates. Please check back later."
        )
        context.user_data['msg_ids'].append(msg.message_id)
        return
    
    # --- Mode Logic ---
    if role == 'admin' and mode == 'test':
        safe_name = "CustomText"
        filename = f"{safe_name}_{hashlib.md5(user_text.encode()).hexdigest()[:6]}.txt"
        files[filename] = {
            "text": user_text,
            "file_id": None,
            "is_crawl": False,
            "is_custom": True
        }
        msg = await update.message.reply_text(f" Saved as {filename}", reply_markup=get_main_menu_keyboard(role, mode))
        context.user_data['msg_ids'].append(msg.message_id)
        return
        
    if role == 'admin' and mode == 'feed':
        msg = await update.message.reply_text(" Switch to Use Mode to ask questions.", reply_markup=get_main_menu_keyboard(role, mode))
        context.user_data['msg_ids'].append(msg.message_id)
        return
        
    if not files:
        if role == 'admin':
            msg = await update.message.reply_text("Your Knowledge Base is empty. Upload files.", reply_markup=get_main_menu_keyboard(role, mode))
        else:
            msg = await update.message.reply_text("The knowledge base is currently empty.", reply_markup=get_main_menu_keyboard(role, mode))
        context.user_data["last_menu_id"] = msg.message_id 
        context.user_data['msg_ids'].append(msg.message_id)
        return
        
    full_context = ""
    for name, data in files.items():
        full_context += f"\n\n--- SOURCE: {name} ---\n{data['text']}"
        
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
    
    try:
        # 3. Use Dynamic Temperature from Settings (Dashboard controlled)
        # Defaults to 0.2 if settings aren't found
        current_temp = settings.get('temperature', 0.2)
        
        response = await get_groq_response(user_text, full_context, temperature=current_temp)
        msg = await update.message.reply_text(response)
        context.user_data['msg_ids'].append(msg.message_id)

        # 4. Log Chat Analytics to Supabase
        # Captures the conversation for the Admin dashboard
        log_chat_interaction(
            telegram_id=user.id,
            username=user.username or user.first_name,
            query=user_text,
            response=response,
            admin_id=google_id
        )

    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        msg = await update.message.reply_text("Error processing request.")
        context.user_data['msg_ids'].append(msg.message_id)

async def clear_key_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Hidden command: Doesn't show in any menus
    telegram_id = update.effective_user.id
    
    success = clear_user_auth(telegram_id)
    
    if success:
        # Wipe local bot memory for this user
        context.user_data.clear()
        await update.message.reply_text("🔑 <b>Dev Mode:</b> Your auth is wiped. The token you used is now reusable. Send a new /start link.", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ Failed to clear keys.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    pass