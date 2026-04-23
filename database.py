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
    
def log_ingested_file(filename: str, telegram_id: int, username: str, google_id: str):
    try:
        supabase.table("ingested_files").insert({
            "filename": filename,
            "uploaded_by_telegram_id": telegram_id,
            "uploaded_by_username": username,
            "created_by": google_id
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log file to db: {e}")

def remove_ingested_file(filename: str, google_id: str):
    try:
        supabase.table("ingested_files").delete().eq("filename", filename).eq("created_by", google_id).execute()
    except Exception as e:
        logger.error(f"Failed to delete file from db: {e}")