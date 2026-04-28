import logging
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, PicklePersistence
from config import TELEGRAM_TOKEN, WEBHOOK_URL, PORT, WEBHOOK_SECRET_TOKEN
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
    application.add_handler(CommandHandler("onboard", handlers.start_onboarding_command))
    application.add_handler(CommandHandler("manage", handlers.manage_files))
    application.add_handler(CommandHandler("crawl", handlers.handle_crawl))
    application.add_handler(CommandHandler("clearchat", handlers.clear_chat_command))
    application.add_handler(CommandHandler("clearhistory", handlers.clear_history_command))
    application.add_handler(CommandHandler("restart", handlers.restart_command))
    application.add_handler(CommandHandler("clearkey", handlers.clear_key_command))
    application.add_handler(CallbackQueryHandler(handlers.button_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, handlers.handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))        
    
    logger.info(f"Starting Webhook on port {PORT}. Listening for Telegram...")
    
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
        url_path="webhook",
        secret_token=WEBHOOK_SECRET_TOKEN, 
     )

if __name__ == "__main__":
    main()