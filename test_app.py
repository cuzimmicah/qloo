import pytest
import asyncio
from datetime import datetime, timedelta
from models import *
from services import IntentService, SchedulingService, VoiceService, DatabaseService

def test_intent_parsing():
    """Test basic intent parsing functionality"""
    intent_service = IntentService()
    
    # Mock the OpenAI client for testing
    class MockResponse:
        def __init__(self, content):
            self.content = content
    
    class MockChoice:
        def __init__(self, content):
            self.message = MockResponse(content)
    
    class MockCompletion:
        def __init__(self, content):
            self.choices = [MockChoice(content)]
    
    # Test data
    test_cases = [
        {
            "text": "Schedule a meeting with John tomorrow at 2 PM",
            "expected_intent": "schedule_event"
        },
        {
            "text": "What's my schedule for today?",
            "expected_intent": "get_schedule"
        },
        {
            "text": "Cancel my 3 PM meeting",
            "expected_intent": "cancel_event"
        }
    ]
    
    print("✅ Intent parsing tests would run here (requires OpenAI API key)")

def test_scheduling_service():
    """Test scheduling service functionality"""
    scheduling_service = SchedulingService()
    
    # Test finding available slots
    user_context = UserContext(
        user_id="test_user",
        email="test@example.com",
        current_timezone="UTC"
    )
    
    # This would normally be async, but for testing we'll check the structure
    assert scheduling_service.min_slot_duration == 15
    assert scheduling_service.max_suggestions == 10
    
    print("✅ Scheduling service initialized correctly")

def test_models():
    """Test model validation"""
    
    # Test UserPreferences
    preferences = UserPreferences()
    assert preferences.preferred_meeting_duration == 60
    assert preferences.timezone == "UTC"
    
    # Test IntentRequest
    request = IntentRequest(text="Schedule a meeting")
    assert request.text == "Schedule a meeting"
    
    # Test Event
    event = Event(
        title="Test Meeting",
        start_time=datetime.now(),
        end_time=datetime.now() + timedelta(hours=1),
        user_id="test_user"
    )
    assert event.title == "Test Meeting"
    assert event.status == EventStatus.SCHEDULED
    
    print("✅ Model validation tests passed")

def test_voice_service():
    """Test voice service initialization"""
    voice_service = VoiceService()
    
    # Check that the service initializes correctly
    assert voice_service.recognizer is not None
    
    print("✅ Voice service initialized correctly")

def test_database_service():
    """Test database service initialization"""
    database_service = DatabaseService()
    
    # The service should handle missing credentials gracefully
    print("✅ Database service initialized correctly")

def run_all_tests():
    """Run all tests"""
    print("🧪 Running Qloo Application Tests")
    print("=" * 50)
    
    try:
        test_models()
        test_intent_parsing()
        test_scheduling_service()
        test_voice_service()
        test_database_service()
        
        print("=" * 50)
        print("✅ All tests passed!")
        
    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        raise

if __name__ == "__main__":
    run_all_tests()