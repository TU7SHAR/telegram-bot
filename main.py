import logging
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, PicklePersistence
from config import TELEGRAM_TOKEN
import handlers

logging.basicConfig(
    format='[%(asctime)s] %(name)s | %(levelname)s | %(message)s',
    level=logging.INFO, 
    handlers=[
        logging.StreamHandler(sys.stdout) 
    ]
)
logger = logging.getLogger(__name__)

def main() -> None:
    logger.info("Initializing Document Assistant Bot...")
    
    persistence = PicklePersistence(filepath="bot_memory.pickle")
    application = Application.builder().token(TELEGRAM_TOKEN).persistence(persistence).build()
    
    application.add_error_handler(handlers.error_handler)
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("menu", handlers.show_menu))
    application.add_handler(CommandHandler("manage", handlers.manage_files))
    application.add_handler(CommandHandler("crawl", handlers.handle_crawl))
    application.add_handler(CommandHandler("clearchat", handlers.clear_chat_command))
    application.add_handler(CommandHandler("clearhistory", handlers.clear_history_command))
    application.add_handler(CommandHandler("restart", handlers.restart_command))
    application.add_handler(CallbackQueryHandler(handlers.button_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, handlers.handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))        
    
    logger.info("Bot is polling and ready for messages!")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()