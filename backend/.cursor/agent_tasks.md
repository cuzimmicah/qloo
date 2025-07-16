# Cursor Background Agent Tasks for Qloo Backend

## Project Overview
Voice-based scheduling assistant with FastAPI backend that:
- Processes voice input for scheduling requests
- Integrates with Google Calendar, Outlook, and other calendar systems
- Uses GPT-4 for intent parsing
- Provides intelligent scheduling suggestions
- Handles voice transcription and text-to-speech

## Priority Tasks for Background Agents

### 1. Core FastAPI Setup (High Priority)
- **File**: `main.py`
- **Task**: Create FastAPI app with routes for voice processing, scheduling, and calendar integration
- **Requirements**:
  - Health check endpoint
  - Voice processing endpoint
  - Calendar integration endpoints
  - Error handling and logging
  - CORS configuration for mobile app

### 2. Data Models (High Priority)
- **File**: `shared/models.py`
- **Task**: Create Pydantic models for the entire system
- **Requirements**:
  - Intent model (text, intent_type, confidence, entities)
  - Event model (title, start_time, end_time, description, location)
  - User context model (preferences, existing schedule)
  - Calendar sync models
  - Voice processing models

### 3. Intent Parser (High Priority)
- **File**: `nlp/intent_parser.py`
- **Task**: Implement GPT-4 based intent parsing
- **Requirements**:
  - Parse natural language scheduling requests
  - Extract time, date, duration, event details
  - Handle ambiguous requests
  - Return structured intent objects
  - Use prompt from `nlp/prompts/intent_prompt.txt`

### 4. Calendar Integration (Medium Priority)
- **File**: `calendar/google_api.py`
- **Task**: Google Calendar API integration
- **Requirements**:
  - OAuth2 authentication
  - Fetch existing events
  - Create new events
  - Update/delete events
  - Handle rate limits

- **File**: `calendar/outlook_api.py`
- **Task**: Outlook API integration
- **Requirements**:
  - Microsoft Graph API integration
  - Similar functionality to Google Calendar

### 5. Scheduling Engine (High Priority)
- **File**: `calendar/scheduler.py`
- **Task**: Core scheduling logic
- **Requirements**:
  - Find available time slots
  - Consider user preferences
  - Handle conflicts
  - Suggest optimal meeting times
  - Support different time zones

### 6. Voice Processing (Medium Priority)
- **File**: `voice/transcribe.py`
- **Task**: Voice transcription
- **Requirements**:
  - Accept audio files
  - Convert speech to text
  - Handle different audio formats
  - Error handling for poor audio quality

- **File**: `tts/elevenlabs.py`
- **Task**: Text-to-speech
- **Requirements**:
  - Convert responses to speech
  - Handle different voices
  - Audio file generation

### 7. Testing Suite (High Priority)
- **File**: `tests/test_intent_parser.py`
- **Task**: Comprehensive intent parser tests
- **Requirements**:
  - Test various scheduling scenarios
  - Test edge cases
  - Mock GPT-4 responses
  
- **File**: `tests/test_scheduler.py`
- **Task**: Scheduler tests
- **Requirements**:
  - Test time slot finding
  - Test conflict resolution
  - Test timezone handling

## Success Criteria
- All endpoints return proper responses
- Voice input is correctly processed
- Calendar integration works
- Tests pass with >90% coverage
- Mobile app can communicate with backend
- Voice responses are natural and helpful

## Technical Requirements
- Use FastAPI with async/await
- Implement proper error handling
- Add logging throughout
- Use environment variables for API keys
- Follow REST API best practices
- Implement rate limiting
- Add request validation 