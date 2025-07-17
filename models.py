from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import datetime, date, time
from enum import Enum

class IntentType(str, Enum):
    SCHEDULE_EVENT = "schedule_event"
    GET_SCHEDULE = "get_schedule"
    RESCHEDULE_EVENT = "reschedule_event"
    CANCEL_EVENT = "cancel_event"
    UPDATE_EVENT = "update_event"
    CHECK_AVAILABILITY = "check_availability"
    SET_REMINDER = "set_reminder"
    UNKNOWN = "unknown"

class CalendarProvider(str, Enum):
    GOOGLE = "google"
    APPLE = "apple"
    ICAL = "ical"

class EventStatus(str, Enum):
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    RESCHEDULED = "rescheduled"

class UserPreferences(BaseModel):
    preferred_meeting_duration: int = Field(default=60, description="Default meeting duration in minutes")
    work_start_time: time = Field(default=time(9, 0), description="Work day start time")
    work_end_time: time = Field(default=time(17, 0), description="Work day end time")
    timezone: str = Field(default="UTC", description="User's timezone")
    buffer_time: int = Field(default=15, description="Buffer time between meetings in minutes")
    max_meetings_per_day: int = Field(default=8, description="Maximum meetings per day")
    preferred_calendar: CalendarProvider = Field(default=CalendarProvider.GOOGLE)

class UserContext(BaseModel):
    user_id: str
    email: str
    name: Optional[str] = None
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    current_timezone: str = Field(default="UTC")
    existing_events: List[Dict[str, Any]] = Field(default_factory=list)

class IntentEntity(BaseModel):
    entity_type: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    start_pos: Optional[int] = None
    end_pos: Optional[int] = None

class IntentRequest(BaseModel):
    text: str = Field(..., description="Natural language text to parse")
    user_context: Optional[UserContext] = None
    conversation_history: List[str] = Field(default_factory=list)
    
    @validator('text')
    def text_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Text cannot be empty')
        return v

class IntentResponse(BaseModel):
    intent_type: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    entities: Dict[str, Any] = Field(default_factory=dict)
    extracted_entities: List[IntentEntity] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification_question: Optional[str] = None
    processing_time: float = Field(description="Processing time in seconds")

class TimeSlot(BaseModel):
    start_time: datetime
    end_time: datetime
    duration_minutes: int
    availability_score: float = Field(ge=0.0, le=1.0, description="How good this slot is (1.0 = perfect)")
    conflicts: List[str] = Field(default_factory=list, description="List of conflicting events")

class Event(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    status: EventStatus = EventStatus.SCHEDULED
    calendar_provider: CalendarProvider = CalendarProvider.GOOGLE
    user_id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class EventRequest(BaseModel):
    title: str
    description: Optional[str] = None
    duration: int = Field(..., description="Duration in minutes")
    preferred_time: Optional[datetime] = None
    location: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    user_context: Optional[UserContext] = None
    auto_schedule: bool = Field(default=True, description="Whether to auto-schedule or just find slots")

class EventResponse(BaseModel):
    success: bool
    event: Optional[Event] = None
    suggested_slots: List[TimeSlot] = Field(default_factory=list)
    message: str
    processing_time: float

class VoiceRequest(BaseModel):
    audio_data: bytes
    format: str = Field(default="wav", description="Audio format")
    sample_rate: int = Field(default=16000, description="Audio sample rate")
    user_context: Optional[UserContext] = None

class VoiceResponse(BaseModel):
    success: bool
    transcribed_text: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    processing_time: float
    error_message: Optional[str] = None

class CalendarSyncRequest(BaseModel):
    user_id: str
    calendar_provider: CalendarProvider
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    sync_period_days: int = Field(default=30, description="How many days to sync")

class CalendarSyncResponse(BaseModel):
    success: bool
    events_synced: int
    last_sync_time: datetime
    next_sync_time: Optional[datetime] = None
    error_message: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str = "1.0.0"
    services: Dict[str, str] = Field(default_factory=dict)