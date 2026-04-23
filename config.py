import os
from dotenv import load_dotenv

load_dotenv()

ENV = os.getenv("ENVIRONMENT", "development")

if ENV == "production":
    TELEGRAM_TOKEN = os.getenv("PROD_TELEGRAM_TOKEN")
    WEBHOOK_URL = os.getenv("PROD_WEBHOOK_URL")
    PORT = int(os.getenv("PORT", "8443"))
else:
    TELEGRAM_TOKEN = os.getenv("DEV_TELEGRAM_TOKEN")
    WEBHOOK_URL = os.getenv("DEV_WEBHOOK_URL")
    PORT = int(os.getenv("PORT", "8443")) 

WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")

SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")