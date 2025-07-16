from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging
import os
from typing import List, Optional
import asyncio

# Import our modules
from shared.models import (
    IntentRequest, IntentResponse, EventRequest, EventResponse,
    VoiceRequest, VoiceResponse, CalendarSyncRequest, CalendarSyncResponse,
    HealthResponse, UserContext
)
from nlp.intent_parser import IntentParser
from scheduling.scheduler import Scheduler
from scheduling.google_api import GoogleCalendarAPI
from voice.transcribe import VoiceTranscriber
from tts.elevenlabs import TextToSpeech
from database import supabase_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Qloo Voice Scheduling Assistant",
    description="Voice-based scheduling assistant with calendar integration",
    version="1.0.0"
)

# CORS configuration for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
intent_parser = IntentParser()
scheduler = Scheduler()
google_calendar = GoogleCalendarAPI()
voice_transcriber = VoiceTranscriber()
text_to_speech = TextToSpeech()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    try:
        return HealthResponse(
            status="healthy",
            message="Qloo backend is running",
            version="1.0.0"
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Service unhealthy")

@app.post("/voice/transcribe", response_model=VoiceResponse)
async def transcribe_voice(
    audio_file: UploadFile = File(...),
    user_context: Optional[str] = None
):
    """Transcribe voice input to text"""
    try:
        # Validate audio file
        if not audio_file.content_type.startswith("audio/"):
            raise HTTPException(status_code=400, detail="Invalid audio file format")
        
        # Read audio file
        audio_data = await audio_file.read()
        
        # Transcribe audio
        transcription = await voice_transcriber.transcribe(audio_data)
        
        return VoiceResponse(
            text=transcription,
            confidence=0.95,  # Will be updated by actual transcription service
            processing_time=0.5
        )
    except Exception as e:
        logger.error(f"Voice transcription failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Transcription failed")

@app.post("/nlp/parse-intent", response_model=IntentResponse)
async def parse_intent(request: IntentRequest):
    """Parse natural language intent for scheduling"""
    try:
        # Parse intent using GPT-4
        intent_result = await intent_parser.parse_intent(
            text=request.text,
            user_context=request.user_context
        )
        
        return intent_result
    except Exception as e:
        logger.error(f"Intent parsing failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Intent parsing failed")

@app.post("/calendar/schedule", response_model=EventResponse)
async def schedule_event(request: EventRequest):
    """Schedule a new event"""
    try:
        # Find available time slots
        available_slots = await scheduler.find_available_slots(
            duration=request.duration,
            preferred_time=request.preferred_time,
            user_context=request.user_context
        )
        
        if not available_slots:
            raise HTTPException(status_code=409, detail="No available time slots found")
        
        # Create event in calendar
        event = await scheduler.create_event(
            title=request.title,
            start_time=available_slots[0].start_time,
            end_time=available_slots[0].end_time,
            description=request.description,
            location=request.location,
            calendar_provider=request.calendar_provider
        )
        
        return EventResponse(
            event_id=event.event_id,
            title=event.title,
            start_time=event.start_time,
            end_time=event.end_time,
            status="scheduled",
            calendar_provider=request.calendar_provider
        )
    except Exception as e:
        logger.error(f"Event scheduling failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Event scheduling failed")

@app.get("/calendar/events")
async def get_events(
    start_date: str,
    end_date: str,
    calendar_provider: str = "google"
):
    """Get events from calendar"""
    try:
        if calendar_provider == "google":
            events = await google_calendar.get_events(start_date, end_date)
        else:
            raise HTTPException(status_code=400, detail="Unsupported calendar provider")
        
        return {"events": events}
    except Exception as e:
        logger.error(f"Failed to fetch events: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to fetch events")

@app.post("/calendar/sync", response_model=CalendarSyncResponse)
async def sync_calendar(request: CalendarSyncRequest):
    """Sync calendar with external providers"""
    try:
        sync_results = []
        
        if "google" in request.providers:
            google_result = await google_calendar.sync()
            sync_results.append({"provider": "google", "status": "success", "events_synced": google_result})
        

        
        return CalendarSyncResponse(
            sync_results=sync_results,
            last_sync=request.last_sync
        )
    except Exception as e:
        logger.error(f"Calendar sync failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Calendar sync failed")

@app.post("/tts/generate")
async def generate_speech(
    text: str,
    voice_id: Optional[str] = None,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Generate speech from text"""
    try:
        audio_data = await text_to_speech.generate_speech(text, voice_id)
        
        return {
            "audio_url": f"/audio/{audio_data['file_id']}",
            "duration": audio_data["duration"],
            "voice_id": voice_id or "default"
        }
    except Exception as e:
        logger.error(f"TTS generation failed: {str(e)}")
        raise HTTPException(status_code=500, detail="TTS generation failed")

@app.post("/voice/process")
async def process_voice_command(
    audio_file: UploadFile = File(...),
    user_context: Optional[str] = None
):
    """Complete voice processing pipeline: transcribe -> parse -> schedule"""
    try:
        # Step 1: Transcribe audio
        audio_data = await audio_file.read()
        transcription = await voice_transcriber.transcribe(audio_data)
        
        # Step 2: Parse intent
        intent_result = await intent_parser.parse_intent(
            text=transcription,
            user_context=UserContext.parse_raw(user_context) if user_context else None
        )
        
        # Step 3: Execute action based on intent
        if intent_result.intent_type == "schedule_event":
            # Schedule the event
            event_request = EventRequest(
                title=intent_result.entities.get("title", "New Event"),
                start_time=intent_result.entities.get("start_time"),
                duration=intent_result.entities.get("duration", 60),
                description=intent_result.entities.get("description"),
                location=intent_result.entities.get("location"),
                calendar_provider="google"  # Default
            )
            
            event_response = await schedule_event(event_request)
            
            # Generate voice response
            response_text = f"I've scheduled '{event_response.title}' for {event_response.start_time}"
            audio_response = await text_to_speech.generate_speech(response_text)
            
            return {
                "transcription": transcription,
                "intent": intent_result,
                "event": event_response,
                "audio_response": audio_response
            }
        
        elif intent_result.intent_type == "get_schedule":
            # Get schedule for requested time period
            events = await get_events(
                start_date=intent_result.entities.get("start_date"),
                end_date=intent_result.entities.get("end_date")
            )
            
            response_text = f"You have {len(events['events'])} events scheduled"
            audio_response = await text_to_speech.generate_speech(response_text)
            
            return {
                "transcription": transcription,
                "intent": intent_result,
                "events": events,
                "audio_response": audio_response
            }
        
        else:
            response_text = "I didn't understand that request. Please try again."
            audio_response = await text_to_speech.generate_speech(response_text)
            
            return {
                "transcription": transcription,
                "intent": intent_result,
                "audio_response": audio_response
            }
            
    except Exception as e:
        logger.error(f"Voice processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Voice processing failed")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True) 