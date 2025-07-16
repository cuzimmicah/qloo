from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, date, time
from enum import Enum

class IntentType(str, Enum):
    """Types of intents the system can recognize"""
    SCHEDULE_EVENT = "schedule_event"
    GET_SCHEDULE = "get_schedule"
    RESCHEDULE_EVENT = "reschedule_event"
    CANCEL_EVENT = "cancel_event"
    UPDATE_EVENT = "update_event"
    CHECK_AVAILABILITY = "check_availability"
    SET_REMINDER = "set_reminder"
    UNKNOWN = "unknown"

class CalendarProvider(str, Enum):
    """Supported calendar providers"""
    GOOGLE = "google"
    OUTLOOK = "outlook"
    APPLE = "apple"
    ICAL = "ical"

class EventStatus(str, Enum):
    """Event status options"""
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    RESCHEDULED = "rescheduled"

class TimeZone(str, Enum):
    """Common timezone options"""
    UTC = "UTC"
    EST = "America/New_York"
    PST = "America/Los_Angeles"
    CST = "America/Chicago"
    MST = "America/Denver"

# Base Models
class UserPreferences(BaseModel):
    """User scheduling preferences"""
    preferred_meeting_duration: int = Field(default=60, description="Default meeting duration in minutes")
    work_start_time: time = Field(default=time(9, 0), description="Work day start time")
    work_end_time: time = Field(default=time(17, 0), description="Work day end time")
    timezone: str = Field(default="UTC", description="User's timezone")
    buffer_time: int = Field(default=15, description="Buffer time between meetings in minutes")
    max_meetings_per_day: int = Field(default=8, description="Maximum meetings per day")
    preferred_calendar: CalendarProvider = Field(default=CalendarProvider.GOOGLE)

class UserContext(BaseModel):
    """User context for personalized scheduling"""
    user_id: str
    email: str
    name: Optional[str] = None
    preferences: UserPreferences = Field(default_factory=UserPreferences)
    current_timezone: str = Field(default="UTC")
    existing_events: List[Dict[str, Any]] = Field(default_factory=list)
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            time: lambda v: v.isoformat()
        }

# Intent Models
class IntentEntity(BaseModel):
    """Individual entity extracted from intent"""
    entity_type: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    start_pos: Optional[int] = None
    end_pos: Optional[int] = None

class IntentRequest(BaseModel):
    """Request for intent parsing"""
    text: str = Field(..., description="Natural language text to parse")
    user_context: Optional[UserContext] = None
    conversation_history: List[str] = Field(default_factory=list)
    
    @validator('text')
    def text_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Text cannot be empty')
        return v

class IntentResponse(BaseModel):
    """Response from intent parsing"""
    intent_type: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    entities: Dict[str, Any] = Field(default_factory=dict)
    extracted_entities: List[IntentEntity] = Field(default_factory=list)
    requires_clarification: bool = False
    clarification_question: Optional[str] = None
    processing_time: float = Field(description="Processing time in seconds")

# Event Models
class TimeSlot(BaseModel):
    """Available time slot"""
    start_time: datetime
    end_time: datetime
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence this slot is good")
    
    @validator('end_time')
    def end_after_start(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v

class Event(BaseModel):
    """Event model"""
    event_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    calendar_provider: CalendarProvider = CalendarProvider.GOOGLE
    status: EventStatus = EventStatus.SCHEDULED
    reminder_minutes: List[int] = Field(default_factory=lambda: [15])
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    @validator('end_time')
    def end_after_start(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('End time must be after start time')
        return v

class EventRequest(BaseModel):
    """Request to create/update an event"""
    title: str
    description: Optional[str] = None
    start_time: Optional[datetime] = None
    duration: int = Field(default=60, description="Duration in minutes")
    preferred_time: Optional[datetime] = None
    location: Optional[str] = None
    attendees: List[str] = Field(default_factory=list)
    calendar_provider: CalendarProvider = CalendarProvider.GOOGLE
    user_context: Optional[UserContext] = None
    
    @validator('duration')
    def duration_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Duration must be positive')
        return v

class EventResponse(BaseModel):
    """Response from event operations"""
    event_id: str
    title: str
    start_time: datetime
    end_time: datetime
    status: EventStatus
    calendar_provider: CalendarProvider
    suggested_alternatives: List[TimeSlot] = Field(default_factory=list)

# Voice Models
class VoiceRequest(BaseModel):
    """Request for voice processing"""
    audio_data: bytes
    format: str = Field(default="wav", description="Audio format")
    sample_rate: int = Field(default=16000, description="Audio sample rate")
    user_context: Optional[UserContext] = None

class VoiceResponse(BaseModel):
    """Response from voice transcription"""
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    processing_time: float = Field(description="Processing time in seconds")
    language: str = Field(default="en-US")
    alternatives: List[str] = Field(default_factory=list)

# Calendar Sync Models
class CalendarSyncRequest(BaseModel):
    """Request for calendar synchronization"""
    providers: List[CalendarProvider]
    sync_period_days: int = Field(default=30, description="Number of days to sync")
    last_sync: Optional[datetime] = None
    full_sync: bool = Field(default=False, description="Whether to perform full sync")

class SyncResult(BaseModel):
    """Result of calendar sync for a provider"""
    provider: CalendarProvider
    status: str
    events_synced: int
    errors: List[str] = Field(default_factory=list)
    last_sync_time: datetime = Field(default_factory=datetime.utcnow)

class CalendarSyncResponse(BaseModel):
    """Response from calendar synchronization"""
    sync_results: List[SyncResult]
    last_sync: datetime = Field(default_factory=datetime.utcnow)
    total_events_synced: int = 0
    
    @validator('total_events_synced', always=True)
    def calculate_total(cls, v, values):
        if 'sync_results' in values:
            return sum(result.events_synced for result in values['sync_results'])
        return v

# Health and System Models
class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(description="Service status")
    message: str = Field(description="Status message")
    version: str = Field(description="API version")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    dependencies: Dict[str, str] = Field(default_factory=dict, description="Status of dependencies")

# Search and Query Models
class AvailabilityQuery(BaseModel):
    """Query for checking availability"""
    start_date: date
    end_date: date
    duration: int = Field(description="Meeting duration in minutes")
    user_context: Optional[UserContext] = None
    exclude_events: List[str] = Field(default_factory=list, description="Event IDs to exclude")

class AvailabilityResponse(BaseModel):
    """Response with available time slots"""
    available_slots: List[TimeSlot]
    total_slots: int
    query_date_range: tuple[date, date]
    
    @validator('total_slots', always=True)
    def calculate_total_slots(cls, v, values):
        if 'available_slots' in values:
            return len(values['available_slots'])
        return v

# Text-to-Speech Models
class TTSRequest(BaseModel):
    """Request for text-to-speech"""
    text: str
    voice_id: Optional[str] = None
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    pitch: float = Field(default=1.0, ge=0.5, le=2.0)
    
    @validator('text')
    def text_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Text cannot be empty')
        return v

class TTSResponse(BaseModel):
    """Response from text-to-speech"""
    audio_url: str
    duration: float = Field(description="Audio duration in seconds")
    voice_id: str
    file_size: int = Field(description="File size in bytes")

# Error Models
class ErrorResponse(BaseModel):
    """Standard error response"""
    error_code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Batch Processing Models
class BatchEventRequest(BaseModel):
    """Request for batch event processing"""
    events: List[EventRequest]
    user_context: Optional[UserContext] = None
    
    @validator('events')
    def events_must_not_be_empty(cls, v):
        if not v:
            raise ValueError('Events list cannot be empty')
        return v

class BatchEventResponse(BaseModel):
    """Response from batch event processing"""
    results: List[EventResponse]
    failed_events: List[Dict[str, Any]] = Field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    
    @validator('success_count', always=True)
    def calculate_success_count(cls, v, values):
        if 'results' in values:
            return len(values['results'])
        return v
    
    @validator('failure_count', always=True)
    def calculate_failure_count(cls, v, values):
        if 'failed_events' in values:
            return len(values['failed_events'])
        return v 