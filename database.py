import logging
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def is_authorized(telegram_id: int) -> bool:
    try:
        res = supabase.table("authorized_users").select("*").eq("telegram_id", telegram_id).execute()
        return len(res.data) > 0
    except Exception as e:
        logger.error(f"Auth check error: {e}")
        return False

def get_user_role(telegram_id: int) -> str:
    try:
        res = supabase.table("invite_tokens").select("token_type").eq("used_by_telegram_id", telegram_id).execute()
        if res.data and res.data[0].get("token_type"):
            return res.data[0]["token_type"].lower()
        return "normal"
    except Exception as e:
        logger.error(f"Role fetch error: {e}")
        return "normal"

def get_google_id(telegram_id: int) -> str:
    try:
        res = supabase.table("invite_tokens").select("created_by").eq("used_by_telegram_id", telegram_id).execute()
        if res.data and res.data[0].get("created_by"):
            return res.data[0]["created_by"]
        return None
    except Exception as e:
        logger.error(f"Error fetching Google ID: {e}")
        return None

def verify_and_authorize(token_suffix: str, telegram_id: int, telegram_username: str):
    try:
        search_str = f"%{token_suffix}%"
        
        res = supabase.table("invite_tokens").select("*").ilike("token_string", search_str).execute()

        if not res.data:
            logger.warning("Token not found in database.")
            return False

        token_record = res.data[0]

        if token_record.get('is_used') is True:
            logger.warning("Token is already marked as used.")
            return False

        supabase.table("invite_tokens").update({
            "is_used": True, 
            "used_by_telegram_id": telegram_id,
            "used_by_username": telegram_username
        }).eq("id", token_record['id']).execute()

        supabase.table("authorized_users").upsert({
            "telegram_id": telegram_id,
            "token_used": token_record['token_string']
        }).execute()
            
        return True
        
    except Exception as e:
        logger.error(f"Authorization Error: {e}")
        return False

def log_ingested_file(filename: str, telegram_id: int, username: str, google_id: str, category: str = "General"):
    try:
        supabase.table("ingested_files").insert({
            "filename": filename,
            "uploaded_by_telegram_id": telegram_id,
            "uploaded_by_username": username,
            "created_by": google_id,
            "category": category
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log file to db: {e}")

def clear_user_auth(telegram_id: int) -> bool:
    try:
        supabase.table("invite_tokens").update({
            "is_used": False, 
            "used_by_telegram_id": None,
            "used_by_username": None
        }).eq("used_by_telegram_id", telegram_id).execute()

        supabase.table("authorized_users").delete().eq("telegram_id", telegram_id).execute()
        return True
    except Exception as e:
        logger.error(f"Error clearing auth: {e}")
        return False

def remove_ingested_file(filename: str, google_id: str):
    try:
        supabase.table("ingested_files").delete().eq("filename", filename).eq("created_by", google_id).execute()
    except Exception as e:
        logger.error(f"Failed to delete file from db: {e}")

# Add these functions to database.py

def get_bot_settings(google_id: str):
    """Fetches the specific admin's bot preferences."""
    try:
        # Link to 'created_by' column
        res = supabase.table("bot_settings").select("*").eq("created_by", google_id).execute()
        if res.data:
            return res.data[0]
        return {"strict_knowledge_mode": True, "temperature": 0.2, "maintenance_mode": False}
    except Exception:
        return {"strict_knowledge_mode": True, "temperature": 0.2, "maintenance_mode": False}

def log_chat_interaction(telegram_id, username, query, response, admin_id):
    """Log user questions and AI answers for analytics."""
    try:
        supabase.table("chat_analytics").insert({
            "telegram_id": telegram_id,
            "username": username,
            "user_query": query,
            "bot_response": response,
            "admin_id": admin_id
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log chat: {e}")


# --- NEW SALES ASSISTANT STATE FUNCTIONS ---

def get_user_state(telegram_id: int):
    try:
        res = supabase.table("user_states").select("*").eq("telegram_id", telegram_id).execute()
        return res.data[0] if res.data else None
    except Exception as e: 
        logger.error(f"Error fetching state: {e}")
        return None

def update_user_state(telegram_id: int, mode: str, step: int = 0, metadata: dict = {}):
    try:
        supabase.table("user_states").upsert({
            "telegram_id": telegram_id,
            "current_mode": mode,
            "current_step": step,
            "metadata": metadata
        }, on_conflict="telegram_id").execute() # <-- ADD THIS PART
    except Exception as e:
        logger.error(f"State update error: {e}")

def save_onboarding_lead(data: dict):
    try:
        supabase.table("onboarding_leads").insert(data).execute()
    except Exception as e:
        logger.error(f"Lead save error: {e}")

# --- NEW: SYNC FUNCTION ---
def get_active_filenames(google_id: str):
    """Fetches the list of filenames currently stored in Supabase for this user."""
    try:
        res = supabase.table("ingested_files").select("filename").eq("created_by", google_id).execute()
        return [row['filename'] for row in res.data] if res.data else []
    except Exception as e:
        logger.error(f"Error fetching active files: {e}")
        return None
    
def save_test_result(data: dict):
    try:
        supabase.table("test_results").insert(data).execute()
    except Exception as e:
        logger.error(f"Test result save error: {e}")

def get_onboarding_lead(telegram_id: int):
    """Fetches the user's onboarding data to personalize the AI tests."""
    try:
        res = supabase.table("onboarding_leads").select("*").eq("telegram_id", telegram_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Error fetching lead: {e}")
        return None