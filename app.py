from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import logging
import os
from typing import List, Optional
import asyncio
from datetime import datetime

from models import *
from services import IntentService, SchedulingService, VoiceService, DatabaseService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Qloo Voice Scheduling Assistant",
    description="Voice-based scheduling assistant with calendar integration",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

intent_service = IntentService()
scheduling_service = SchedulingService()
voice_service = VoiceService()
database_service = DatabaseService()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy", timestamp=datetime.now())

@app.post("/api/intent", response_model=IntentResponse)
async def parse_intent(request: IntentRequest):
    try:
        return await intent_service.parse_intent(request)
    except Exception as e:
        logger.error(f"Intent parsing failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Intent parsing failed")

@app.post("/api/schedule", response_model=EventResponse)
async def schedule_event(request: EventRequest):
    try:
        return await scheduling_service.schedule_event(request)
    except Exception as e:
        logger.error(f"Event scheduling failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Event scheduling failed")

@app.get("/api/schedule", response_model=List[Event])
async def get_schedule(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None
):
    try:
        return await scheduling_service.get_schedule(start_date, end_date, user_id)
    except Exception as e:
        logger.error(f"Failed to get schedule: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get schedule")

@app.post("/api/voice/transcribe", response_model=VoiceResponse)
async def transcribe_voice(audio: UploadFile = File(...)):
    try:
        return await voice_service.transcribe_audio(audio)
    except Exception as e:
        logger.error(f"Voice transcription failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Voice transcription failed")

@app.post("/api/voice/speak")
async def text_to_speech(text: str):
    try:
        return await voice_service.text_to_speech(text)
    except Exception as e:
        logger.error(f"Text to speech failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Text to speech failed")

@app.post("/api/calendar/sync", response_model=CalendarSyncResponse)
async def sync_calendar(request: CalendarSyncRequest):
    try:
        return await scheduling_service.sync_calendar(request)
    except Exception as e:
        logger.error(f"Calendar sync failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Calendar sync failed")

@app.get("/api/availability")
async def check_availability(
    duration: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None
):
    try:
        return await scheduling_service.find_available_slots(duration, start_date, end_date, user_id)
    except Exception as e:
        logger.error(f"Availability check failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Availability check failed")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)