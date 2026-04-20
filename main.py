from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from config import TELEGRAM_TOKEN
import handlers

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_error_handler(handlers.error_handler)
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("menu", handlers.show_menu))
    application.add_handler(CommandHandler("manage", handlers.manage_files))
    application.add_handler(CommandHandler("crawl", handlers.handle_crawl))
    application.add_handler(CallbackQueryHandler(handlers.button_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, handlers.handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message))        
    print("Document Assistant Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()