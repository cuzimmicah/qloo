import json
import os
import time
import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, date
import pytz
from dateutil import parser
import speech_recognition as sr
from io import BytesIO
import tempfile

from openai import AsyncOpenAI
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from supabase import create_client, Client
from elevenlabs import generate, set_api_key
from fastapi import UploadFile

from models import *

logger = logging.getLogger(__name__)

class IntentService:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4"
        self.max_tokens = 1000
        self.temperature = 0.1
        
    async def parse_intent(self, request: IntentRequest) -> IntentResponse:
        start_time = time.time()
        
        try:
            prompt = self._build_prompt(request.text, request.user_context)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a scheduling assistant that parses natural language requests into structured data."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            result = json.loads(response.choices[0].message.content)
            processing_time = time.time() - start_time
            
            return IntentResponse(
                intent_type=IntentType(result.get("intent_type", "unknown")),
                confidence=result.get("confidence", 0.0),
                entities=result.get("entities", {}),
                requires_clarification=result.get("requires_clarification", False),
                clarification_question=result.get("clarification_question"),
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Intent parsing failed: {str(e)}")
            processing_time = time.time() - start_time
            return IntentResponse(
                intent_type=IntentType.UNKNOWN,
                confidence=0.0,
                entities={},
                requires_clarification=True,
                clarification_question="I didn't understand that. Could you please rephrase?",
                processing_time=processing_time
            )
    
    def _build_prompt(self, text: str, user_context: Optional[UserContext]) -> str:
        context_info = ""
        if user_context:
            context_info = f"""
            User timezone: {user_context.current_timezone}
            Work hours: {user_context.preferences.work_start_time} - {user_context.preferences.work_end_time}
            """
        
        return f"""
        Parse this scheduling request and return a JSON response:
        
        Request: "{text}"
        {context_info}
        
        Return JSON with:
        - intent_type: one of schedule_event, get_schedule, reschedule_event, cancel_event, update_event, check_availability, set_reminder, unknown
        - confidence: float between 0.0 and 1.0
        - entities: dict with extracted information (title, duration, time, date, location, attendees)
        - requires_clarification: boolean
        - clarification_question: string if clarification needed
        """

class SchedulingService:
    def __init__(self):
        self.google_calendar = GoogleCalendarService()
        self.database = DatabaseService()
        self.min_slot_duration = 15
        self.max_suggestions = 10
        
    async def schedule_event(self, request: EventRequest) -> EventResponse:
        start_time = time.time()
        
        try:
            if request.auto_schedule and request.preferred_time:
                event = await self._create_event_directly(request)
                processing_time = time.time() - start_time
                return EventResponse(
                    success=True,
                    event=event,
                    message="Event scheduled successfully",
                    processing_time=processing_time
                )
            else:
                slots = await self.find_available_slots(
                    request.duration,
                    request.preferred_time,
                    request.user_context
                )
                processing_time = time.time() - start_time
                return EventResponse(
                    success=True,
                    suggested_slots=slots,
                    message=f"Found {len(slots)} available time slots",
                    processing_time=processing_time
                )
                
        except Exception as e:
            logger.error(f"Event scheduling failed: {str(e)}")
            processing_time = time.time() - start_time
            return EventResponse(
                success=False,
                message=f"Scheduling failed: {str(e)}",
                processing_time=processing_time
            )
    
    async def find_available_slots(self, duration: int, preferred_time: Optional[datetime] = None, 
                                 user_context: Optional[UserContext] = None) -> List[TimeSlot]:
        try:
            start_date = date.today()
            end_date = start_date + timedelta(days=14)
            
            preferences = user_context.preferences if user_context else UserPreferences()
            timezone = pytz.timezone(user_context.current_timezone if user_context else "UTC")
            
            existing_events = await self.google_calendar.get_events(
                start_date, end_date, user_context.user_id if user_context else None
            )
            
            slots = []
            current_date = start_date
            
            while current_date <= end_date and len(slots) < self.max_suggestions:
                if current_date.weekday() < 5:  # Monday to Friday
                    day_slots = self._find_slots_for_day(
                        current_date, duration, preferences, existing_events, timezone
                    )
                    slots.extend(day_slots)
                
                current_date += timedelta(days=1)
            
            return sorted(slots, key=lambda x: x.availability_score, reverse=True)[:self.max_suggestions]
            
        except Exception as e:
            logger.error(f"Finding available slots failed: {str(e)}")
            return []
    
    def _find_slots_for_day(self, date_obj: date, duration: int, preferences: UserPreferences, 
                           existing_events: List[Dict], timezone) -> List[TimeSlot]:
        slots = []
        
        work_start = datetime.combine(date_obj, preferences.work_start_time)
        work_end = datetime.combine(date_obj, preferences.work_end_time)
        
        work_start = timezone.localize(work_start)
        work_end = timezone.localize(work_end)
        
        current_time = work_start
        
        while current_time + timedelta(minutes=duration) <= work_end:
            slot_end = current_time + timedelta(minutes=duration)
            
            if not self._has_conflict(current_time, slot_end, existing_events):
                slots.append(TimeSlot(
                    start_time=current_time,
                    end_time=slot_end,
                    duration_minutes=duration,
                    availability_score=self._calculate_availability_score(current_time, preferences)
                ))
            
            current_time += timedelta(minutes=15)
        
        return slots
    
    def _has_conflict(self, start_time: datetime, end_time: datetime, events: List[Dict]) -> bool:
        for event in events:
            event_start = parser.parse(event.get('start', ''))
            event_end = parser.parse(event.get('end', ''))
            
            if (start_time < event_end and end_time > event_start):
                return True
        return False
    
    def _calculate_availability_score(self, slot_time: datetime, preferences: UserPreferences) -> float:
        hour = slot_time.hour
        
        if 9 <= hour <= 11:
            return 0.9
        elif 14 <= hour <= 16:
            return 0.8
        elif 11 <= hour <= 14:
            return 0.7
        else:
            return 0.5
    
    async def _create_event_directly(self, request: EventRequest) -> Event:
        event_data = {
            'title': request.title,
            'description': request.description,
            'start_time': request.preferred_time,
            'end_time': request.preferred_time + timedelta(minutes=request.duration),
            'location': request.location,
            'attendees': request.attendees,
            'user_id': request.user_context.user_id if request.user_context else 'default'
        }
        
        calendar_event = await self.google_calendar.create_event(event_data)
        
        return Event(
            id=calendar_event.get('id'),
            title=request.title,
            description=request.description,
            start_time=request.preferred_time,
            end_time=request.preferred_time + timedelta(minutes=request.duration),
            location=request.location,
            attendees=request.attendees,
            user_id=request.user_context.user_id if request.user_context else 'default'
        )
    
    async def get_schedule(self, start_date: Optional[str], end_date: Optional[str], 
                          user_id: Optional[str]) -> List[Event]:
        try:
            start = parser.parse(start_date) if start_date else date.today()
            end = parser.parse(end_date) if end_date else date.today() + timedelta(days=7)
            
            events = await self.google_calendar.get_events(start, end, user_id)
            
            return [Event(
                id=event.get('id'),
                title=event.get('summary', 'No title'),
                description=event.get('description', ''),
                start_time=parser.parse(event.get('start', '')),
                end_time=parser.parse(event.get('end', '')),
                location=event.get('location', ''),
                user_id=user_id or 'default'
            ) for event in events]
            
        except Exception as e:
            logger.error(f"Getting schedule failed: {str(e)}")
            return []
    
    async def sync_calendar(self, request: CalendarSyncRequest) -> CalendarSyncResponse:
        try:
            events = await self.google_calendar.sync_events(request.user_id, request.sync_period_days)
            
            return CalendarSyncResponse(
                success=True,
                events_synced=len(events),
                last_sync_time=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Calendar sync failed: {str(e)}")
            return CalendarSyncResponse(
                success=False,
                events_synced=0,
                last_sync_time=datetime.now(),
                error_message=str(e)
            )

class GoogleCalendarService:
    def __init__(self):
        self.service = None
        
    async def get_events(self, start_date: date, end_date: date, user_id: Optional[str]) -> List[Dict]:
        try:
            if not self.service:
                return []
            
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_date.isoformat() + 'T00:00:00Z',
                timeMax=end_date.isoformat() + 'T23:59:59Z',
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            return events_result.get('items', [])
            
        except Exception as e:
            logger.error(f"Getting Google Calendar events failed: {str(e)}")
            return []
    
    async def create_event(self, event_data: Dict) -> Dict:
        try:
            if not self.service:
                return {}
            
            event = {
                'summary': event_data['title'],
                'description': event_data.get('description', ''),
                'start': {
                    'dateTime': event_data['start_time'].isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': event_data['end_time'].isoformat(),
                    'timeZone': 'UTC',
                },
                'location': event_data.get('location', ''),
                'attendees': [{'email': email} for email in event_data.get('attendees', [])]
            }
            
            created_event = self.service.events().insert(calendarId='primary', body=event).execute()
            return created_event
            
        except Exception as e:
            logger.error(f"Creating Google Calendar event failed: {str(e)}")
            return {}
    
    async def sync_events(self, user_id: str, sync_period_days: int) -> List[Dict]:
        try:
            start_date = date.today()
            end_date = start_date + timedelta(days=sync_period_days)
            
            return await self.get_events(start_date, end_date, user_id)
            
        except Exception as e:
            logger.error(f"Syncing Google Calendar events failed: {str(e)}")
            return []

class VoiceService:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        if os.getenv("ELEVENLABS_API_KEY"):
            set_api_key(os.getenv("ELEVENLABS_API_KEY"))
        
    async def transcribe_audio(self, audio_file: UploadFile) -> VoiceResponse:
        start_time = time.time()
        
        try:
            audio_data = await audio_file.read()
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            with sr.AudioFile(temp_file_path) as source:
                audio = self.recognizer.record(source)
            
            text = self.recognizer.recognize_google(audio)
            processing_time = time.time() - start_time
            
            os.unlink(temp_file_path)
            
            return VoiceResponse(
                success=True,
                transcribed_text=text,
                confidence=0.9,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Voice transcription failed: {str(e)}")
            processing_time = time.time() - start_time
            return VoiceResponse(
                success=False,
                confidence=0.0,
                processing_time=processing_time,
                error_message=str(e)
            )
    
    async def text_to_speech(self, text: str):
        try:
            if not os.getenv("ELEVENLABS_API_KEY"):
                return {"error": "ElevenLabs API key not configured"}
            
            audio = generate(
                text=text,
                voice="Bella",
                model="eleven_monolingual_v1"
            )
            
            return {"audio_data": audio}
            
        except Exception as e:
            logger.error(f"Text to speech failed: {str(e)}")
            return {"error": str(e)}

class DatabaseService:
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        
        if self.url and self.key:
            self.client: Client = create_client(self.url, self.key)
            logger.info("Database client initialized successfully")
        else:
            logger.warning("Database not configured - SUPABASE_URL and SUPABASE_KEY required")
            self.client = None
    
    async def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            if not self.client:
                return None
                
            result = self.client.table("user_preferences").select("*").eq("user_id", user_id).execute()
            return result.data[0] if result.data else None
            
        except Exception as e:
            logger.error(f"Failed to get user preferences: {str(e)}")
            return None
    
    async def save_user_preferences(self, user_id: str, preferences: Dict[str, Any]) -> bool:
        try:
            if not self.client:
                return False
                
            data = {
                "user_id": user_id,
                "preferences": preferences,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            result = self.client.table("user_preferences").upsert(data).execute()
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Failed to save user preferences: {str(e)}")
            return False
    
    async def save_event(self, event_data: Dict[str, Any]) -> Optional[str]:
        try:
            if not self.client:
                return None
                
            result = self.client.table("events").insert(event_data).execute()
            return result.data[0]['id'] if result.data else None
            
        except Exception as e:
            logger.error(f"Failed to save event: {str(e)}")
            return None