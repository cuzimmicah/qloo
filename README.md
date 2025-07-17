# Qloo Voice Scheduling Assistant

A voice-based scheduling assistant that helps you manage your calendar using natural language processing and voice commands.

## Features

- **Voice Input**: Speak your scheduling requests naturally
- **Intent Recognition**: AI-powered understanding of scheduling requests
- **Smart Scheduling**: Intelligent time slot suggestions based on your preferences
- **Calendar Integration**: Sync with Google Calendar
- **Simple Interface**: Clean web interface for easy interaction

## Project Structure

```
qloo-scheduler/
├── app.py              # Main FastAPI application
├── models.py           # Data models and schemas
├── services.py         # Business logic and services
├── mobile_app.py       # Streamlit web interface
├── test_app.py         # Test suite
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variables template
└── README.md          # This file
```

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Up Environment Variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. **Run the Backend**
   ```bash
   python app.py
   ```

4. **Run the Web Interface**
   ```bash
   streamlit run mobile_app.py
   ```

5. **Run Tests**
   ```bash
   python test_app.py
   ```

## Configuration

Create a `.env` file with the following variables:

```env
# OpenAI API for intent parsing
OPENAI_API_KEY=your_openai_api_key

# Google Calendar API
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Database (optional)
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# Voice services (optional)
ELEVENLABS_API_KEY=your_elevenlabs_api_key
```

## API Endpoints

- `GET /health` - Health check
- `POST /api/intent` - Parse natural language intent
- `POST /api/schedule` - Schedule an event
- `GET /api/schedule` - Get schedule for date range
- `POST /api/voice/transcribe` - Transcribe voice to text
- `POST /api/voice/speak` - Text to speech
- `POST /api/calendar/sync` - Sync with calendar
- `GET /api/availability` - Check availability

## Usage Examples

### Text Input
```
"Schedule a meeting with John tomorrow at 2 PM for 1 hour"
"What's my schedule for today?"
"Cancel my 3 PM meeting"
"Find me a free slot for 30 minutes this week"
```

### Voice Input
Upload a `.wav` file with your voice request through the web interface.

## Development

The project follows a simple, readable structure:

- **models.py**: Contains all data models using Pydantic
- **services.py**: Contains all business logic organized by service
- **app.py**: FastAPI application with clean endpoint definitions
- **mobile_app.py**: Streamlit web interface for easy testing

## Testing

Run the test suite to verify functionality:

```bash
python test_app.py
```

## Deployment

### Backend
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

### Web Interface
```bash
streamlit run mobile_app.py --server.port 8501
```

## Code Quality

The code is written with junior developer standards in mind:
- Clear, readable structure
- Minimal but effective comments
- Simple error handling
- Consistent naming conventions
- Proper separation of concerns

## Contributing

1. Keep the simple structure
2. Add tests for new features
3. Update README for new functionality
4. Follow the existing code style

## License

MIT License - see LICENSE file for details 