import logging
from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

from schema_map import (
    TblTokens, TblUsers, TblBotSettings, TblChat, 
    TblFiles, TblUserStates, TblOnboarding, TblTests
)

logger = logging.getLogger(__name__)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def check_auth_status(telegram_id: int) -> str:
    """Returns 'authorized', 'banned', or 'unauthorized'"""
    try:
        res = supabase.table(TblUsers.TABLE).select("*").eq(TblUsers.ID, telegram_id).execute()
        if len(res.data) > 0:
            if res.data[0].get(TblUsers.IS_BANNED):
                return "banned"
            return "authorized"
        return "unauthorized"
    except Exception as e:
        logger.error(f"Auth check error: {e}")
        return "unauthorized"

def is_authorized(telegram_id: int) -> bool:
    """Legacy check for other functions"""
    return check_auth_status(telegram_id) == "authorized"

def verify_and_authorize(token_suffix: str, telegram_id: int, telegram_username: str):
    try:
        # Stop previously banned users
        if check_auth_status(telegram_id) == "banned":
            logger.warning(f"Banned user {telegram_id} attempted to use a new token.")
            return False
            
        search_str = f"%{token_suffix}%"
        
        res = supabase.table(TblTokens.TABLE).select("*").ilike(TblTokens.TOKEN_STRING, search_str).execute()

        if not res.data:
            logger.warning("Token not found in database.")
            return False

        token_record = res.data[0]

        if token_record.get(TblTokens.IS_USED) is True:
            logger.warning("Token is already marked as used.")
            return False

        # Mark token as used
        supabase.table(TblTokens.TABLE).update({
            TblTokens.IS_USED: True, 
            TblTokens.USED_BY_ID: telegram_id,
            TblTokens.USED_BY_USER: telegram_username
        }).eq(TblTokens.ID, token_record[TblTokens.ID]).execute()

        # UPSERT Authorized User and prevent ghost bans
        supabase.table(TblUsers.TABLE).upsert({
            TblUsers.ID: telegram_id,
            TblUsers.TOKEN_USED: token_record[TblTokens.TOKEN_STRING],
            TblUsers.IS_BANNED: False
        }).execute()
            
        return True
        
    except Exception as e:
        logger.error(f"Authorization Error: {e}")
        return False

def get_user_role(telegram_id: int) -> str:
    try:
        res = supabase.table(TblTokens.TABLE).select(TblTokens.TOKEN_TYPE).eq(TblTokens.USED_BY_ID, telegram_id).execute()
        if res.data and res.data[0].get(TblTokens.TOKEN_TYPE):
            return res.data[0][TblTokens.TOKEN_TYPE].lower()
        return "normal"
    except Exception as e:
        logger.error(f"Role fetch error: {e}")
        return "normal"

def get_google_id(telegram_id: int) -> str:
    try:
        res = supabase.table(TblTokens.TABLE).select(TblTokens.CREATED_BY).eq(TblTokens.USED_BY_ID, telegram_id).execute()
        if res.data and res.data[0].get(TblTokens.CREATED_BY):
            return res.data[0][TblTokens.CREATED_BY]
        return None
    except Exception as e:
        logger.error(f"Error fetching Google ID: {e}")
        return None

def log_ingested_file(filename: str, telegram_id: int, username: str, google_id: str, category: str = "General"):
    try:
        supabase.table(TblFiles.TABLE).insert({
            TblFiles.FILENAME: filename,
            TblFiles.UPLOADED_BY_ID: telegram_id,
            TblFiles.UPLOADED_BY_USER: username,
            TblFiles.CREATED_BY: google_id,
            TblFiles.CATEGORY: category
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log file to db: {e}")

def clear_user_auth(telegram_id: int) -> bool:
    try:
        # Revoke Token
        supabase.table(TblTokens.TABLE).update({
            TblTokens.IS_REVOKED: True 
        }).eq(TblTokens.USED_BY_ID, telegram_id).execute()

        # Ban User
        supabase.table(TblUsers.TABLE).update({
            TblUsers.IS_BANNED: True
        }).eq(TblUsers.ID, telegram_id).execute()
        
        return True
    except Exception as e:
        logger.error(f"Error clearing auth: {e}")
        return False

def remove_ingested_file(filename: str, google_id: str):
    try:
        supabase.table(TblFiles.TABLE).delete().eq(TblFiles.FILENAME, filename).eq(TblFiles.CREATED_BY, google_id).execute()
    except Exception as e:
        logger.error(f"Failed to delete file from db: {e}")

def get_bot_settings(google_id: str):
    try:
        res = supabase.table(TblBotSettings.TABLE).select("*").eq(TblBotSettings.CREATED_BY, google_id).execute()
        if res.data:
            return res.data[0]
        return {TblBotSettings.STRICT_MODE: True, TblBotSettings.TEMPERATURE: 0.2, TblBotSettings.MAINTENANCE_MODE: False}
    except Exception:
        return {TblBotSettings.STRICT_MODE: True, TblBotSettings.TEMPERATURE: 0.2, TblBotSettings.MAINTENANCE_MODE: False}

def log_chat_interaction(telegram_id, username, query, response, admin_id):
    try:
        supabase.table(TblChat.TABLE).insert({
            TblChat.TELEGRAM_ID: telegram_id,
            TblChat.USERNAME: username,
            TblChat.USER_QUERY: query,
            TblChat.BOT_RESPONSE: response,
            TblChat.ADMIN_ID: admin_id
        }).execute()
    except Exception as e:
        logger.error(f"Failed to log chat: {e}")

def get_user_state(telegram_id: int):
    try:
        res = supabase.table(TblUserStates.TABLE).select("*").eq(TblUserStates.TELEGRAM_ID, telegram_id).execute()
        return res.data[0] if res.data else None
    except Exception as e: 
        logger.error(f"Error fetching state: {e}")
        return None

def update_user_state(telegram_id: int, mode: str, step: int = 0, metadata: dict = {}):
    try:
        supabase.table(TblUserStates.TABLE).upsert({
            TblUserStates.TELEGRAM_ID: telegram_id,
            TblUserStates.CURRENT_MODE: mode,
            TblUserStates.CURRENT_STEP: step,
            TblUserStates.METADATA: metadata
        }, on_conflict=TblUserStates.TELEGRAM_ID).execute()
    except Exception as e:
        logger.error(f"State update error: {e}")

def save_onboarding_lead(data: dict):
    try:
        # Note: 'data' dict keys should ideally be constructed using the map inside handlers.py
        supabase.table(TblOnboarding.TABLE).insert(data).execute()
    except Exception as e:
        logger.error(f"Lead save error: {e}")

def get_active_filenames(google_id: str):
    try:
        res = supabase.table(TblFiles.TABLE).select(TblFiles.FILENAME).eq(TblFiles.CREATED_BY, google_id).execute()
        return [row[TblFiles.FILENAME] for row in res.data] if res.data else []
    except Exception as e:
        logger.error(f"Error fetching active files: {e}")
        return None
    
def save_test_result(data: dict):
    try:
        supabase.table(TblTests.TABLE).insert(data).execute()
    except Exception as e:
        logger.error(f"Test result save error: {e}")

def validate_user_access(telegram_id):
    """
    Checks if a user is banned or using a revoked key.
    Uses Supabase client syntax: .table().select().execute()
    """
    try:
        # 1. Fetch user from authorized_users
        user_res = supabase.table(TblUsers.TABLE).select("*").eq(TblUsers.ID, telegram_id).execute()
        user = user_res.data[0] if user_res.data else None

        if not user:
            return False, "Unauthorized: Please use a valid invite link to start."

        # 2. Check for account-level ban
        if user.get(TblUsers.IS_BANNED):
            return False, "Access Denied: Your account has been banned."

        # 3. Get the token currently linked to this user
        active_token = user.get(TblUsers.TOKEN_USED)
        if not active_token:
            return False, "No valid invite link found. Please use /start with your token."

        # 4. Check the status of that specific token in invite_tokens
        token_res = supabase.table(TblTokens.TABLE).select("*").eq(TblTokens.TOKEN_STRING, active_token).execute()
        token_data = token_res.data[0] if token_res.data else None

        # 5. Revoke Check: If key is revoked, clear it from the user table[cite: 3]
        if token_data and token_data.get(TblTokens.IS_REVOKED):
            supabase.table(TblUsers.TABLE).update({TblUsers.TOKEN_USED: None}).eq(TblUsers.ID, telegram_id).execute()
            return False, "Access Denied: Your invite link has been revoked. Provide a new one."

        # 6. Safety check: If the token no longer exists in the system[cite: 3]
        if not token_data:
            supabase.table(TblUsers.TABLE).update({TblUsers.TOKEN_USED: None}).eq(TblUsers.ID, telegram_id).execute()
            return False, "Invalid Key: Your current session key is no longer valid."

        return True, "Authorized"

    except Exception as e:
        print(f"Database Error: {e}")
        return False, "An error occurred while verifying your access."

def get_onboarding_lead(telegram_id: int):
    try:
        res = supabase.table(TblOnboarding.TABLE).select("*").eq(TblOnboarding.TELEGRAM_ID, telegram_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error(f"Error fetching lead: {e}")
        return None