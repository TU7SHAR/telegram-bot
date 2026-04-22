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

def verify_and_authorize(token_suffix: str, telegram_id: int):
    try:
        search_str = f"%{token_suffix}%"
        
        # 1. Fetch the token without the strict False check to bypass the NULL trap
        res = supabase.table("invite_tokens").select("*").ilike("token_string", search_str).execute()

        if not res.data:
            logger.warning("Token not found in database.")
            return False

        token_record = res.data[0]

        # 2. Safely check if it's used in Python (handles both True and NULL)
        if token_record.get('is_used') is True:
            logger.warning("Token is already marked as used.")
            return False

        # 3. Mark token as used
        supabase.table("invite_tokens").update({
            "is_used": True, 
            "used_by_telegram_id": telegram_id 
        }).eq("id", token_record['id']).execute()

        # 4. UPSERT the user to prevent Primary Key crashes if you test multiple times
        supabase.table("authorized_users").upsert({
            "telegram_id": telegram_id,
            "token_used": token_record['token_string']
        }).execute()
            
        return True
        
    except Exception as e:
        logger.error(f"Authorization Error: {e}")
        return False