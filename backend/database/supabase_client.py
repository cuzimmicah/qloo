import os
import logging
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from datetime import datetime

logger = logging.getLogger(__name__)

class SupabaseClient:
    """Supabase database client for Qloo application"""
    
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not self.url or not self.key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
        
        self.client: Client = create_client(self.url, self.key)
        logger.info("Supabase client initialized successfully")
    
    async def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user preferences from database"""
        try:
            result = self.client.table("user_preferences").select("*").eq("user_id", user_id).execute()
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"Failed to get user preferences: {str(e)}")
            return None
    
    async def save_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> bool:
        """Save user preferences to database"""
        try:
            data = {
                "user_id": user_id,
                "preferences": preferences,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Upsert (insert or update)
            result = self.client.table("user_preferences").upsert(data).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Failed to save user preferences: {str(e)}")
            return False
    
    async def save_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        """Save event to database"""
        try:
            result = self.client.table("events").insert(event_data).execute()
            if result.data:
                return result.data[0]["id"]
            return None
        except Exception as e:
            logger.error(f"Failed to save event: {str(e)}")
            return None
    
    async def get_user_events(self, user_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get user events from database"""
        try:
            result = self.client.table("events").select("*").eq("user_id", user_id).gte("start_time", start_date).lte("end_time", end_date).execute()
            return result.data or []
        except Exception as e:
            logger.error(f"Failed to get user events: {str(e)}")
            return []
    
    async def save_calendar_sync_log(self, user_id: str, provider: str, status: str, events_synced: int) -> bool:
        """Save calendar sync log to database"""
        try:
            data = {
                "user_id": user_id,
                "provider": provider,
                "status": status,
                "events_synced": events_synced,
                "synced_at": datetime.utcnow().isoformat()
            }
            
            result = self.client.table("calendar_sync_logs").insert(data).execute()
            return len(result.data) > 0
        except Exception as e:
            logger.error(f"Failed to save calendar sync log: {str(e)}")
            return False

# Global instance
supabase_client = SupabaseClient() 