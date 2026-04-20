import io
import logging
from pypdf import PdfReader
from docx import Document
from telegram import Update
from telegram.ext import ContextTypes
from groq_engine import get_groq_response

user_contexts = {}

logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "I'm ready! Send me a .txt, .pdf, or .docx file and I'll analyze it for you."
    )

def extract_text_from_file(file_bytes, file_name):
    """Helper to convert various file formats into a single text string."""
    text = ""
    
    if file_name.lower().endswith('.pdf'):
        reader = PdfReader(io.BytesIO(file_bytes))
        for page in reader.pages:
            text += page.extract_text() + "\n"
    elif file_name.lower().endswith('.docx'):
        doc = Document(io.BytesIO(file_bytes))
        for para in doc.paragraphs:
            text += para.text + "\n"
    else:
        text = file_bytes.decode("utf-8", errors="ignore")
        
    return text.strip()

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    file = update.message.document
    supported_extensions = ('.txt', '.pdf', '.docx')
    
    if not file.file_name.lower().endswith(supported_extensions):
        await update.message.reply_text("Unsupported format! Please send a .txt, .pdf, or .docx.")
        return

    await update.message.reply_text(f"Processing {file.file_name}...")
    
    try:
        new_file = await context.bot.get_file(file.file_id)
        file_bytes = await new_file.download_as_bytearray()
        extracted_text = extract_text_from_file(file_bytes, file_name=file.file_name)
        if not extracted_text:
            await update.message.reply_text("The file seems to be empty or unreadable.")
            return

        user_contexts[update.effective_chat.id] = extracted_text
        await update.message.reply_text(f"Done! I've read {len(extracted_text)} characters from your document. Ask away!")
        
    except Exception as e:
        logger.error(f"File processing error: {e}")
        await update.message.reply_text("Failed to read that file. Is it password protected?")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_message = update.message.text
    
    current_context = user_contexts.get(chat_id)
    
    if not current_context:
        await update.message.reply_text("Upload a document first so I know what we're talking about!")
        return

    await context.bot.send_chat_action(chat_id=chat_id, action='typing')
    response_text = await get_groq_response(user_message, current_context)
    await update.message.reply_text(response_text)