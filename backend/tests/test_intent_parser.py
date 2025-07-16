import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, time, timedelta

from nlp.intent_parser import IntentParser
from shared.models import (
    IntentRequest, IntentResponse, IntentType, UserContext, 
    UserPreferences, IntentEntity
)

class TestIntentParser:
    """Test suite for the IntentParser class"""
    
    @pytest.fixture
    def intent_parser(self):
        """Create IntentParser instance for testing"""
        return IntentParser()
    
    @pytest.fixture
    def sample_user_context(self):
        """Create sample user context for testing"""
        return UserContext(
            user_id="test_user_123",
            email="test@example.com",
            name="Test User",
            preferences=UserPreferences(
                preferred_meeting_duration=60,
                work_start_time=time(9, 0),
                work_end_time=time(17, 0),
                timezone="UTC",
                buffer_time=15
            ),
            current_timezone="UTC",
            existing_events=[]
        )
    
    @pytest.fixture
    def mock_openai_response(self):
        """Mock OpenAI API response"""
        return {
            "intent_type": "schedule_event",
            "confidence": 0.95,
            "entities": {
                "title": "Team Meeting",
                "start_time": "2024-01-15T14:00:00Z",
                "duration": 60,
                "location": "Conference Room A"
            },
            "extracted_entities": [
                {
                    "entity_type": "title",
                    "value": "Team Meeting",
                    "confidence": 0.98,
                    "start_pos": 12,
                    "end_pos": 24
                }
            ],
            "requires_clarification": False,
            "clarification_question": None
        }
    
    @pytest.mark.asyncio
    async def test_parse_simple_scheduling_intent(self, intent_parser, sample_user_context, mock_openai_response):
        """Test parsing a simple scheduling request"""
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            # Mock the OpenAI response
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps(mock_openai_response)
            mock_create.return_value = mock_response
            
            # Test the parsing
            result = await intent_parser.parse_intent(
                "Schedule a team meeting tomorrow at 2pm",
                sample_user_context
            )
            
            assert isinstance(result, IntentResponse)
            assert result.intent_type == IntentType.SCHEDULE_EVENT
            assert result.confidence == 0.95
            assert result.entities["title"] == "Team Meeting"
            assert result.entities["duration"] == 60
            assert not result.requires_clarification
    
    @pytest.mark.asyncio
    async def test_parse_get_schedule_intent(self, intent_parser, sample_user_context):
        """Test parsing a get schedule request"""
        mock_response = {
            "intent_type": "get_schedule",
            "confidence": 0.92,
            "entities": {
                "start_date": "2024-01-16",
                "end_date": "2024-01-16"
            },
            "extracted_entities": [],
            "requires_clarification": False,
            "clarification_question": None
        }
        
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_api_response = Mock()
            mock_api_response.choices = [Mock()]
            mock_api_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_api_response
            
            result = await intent_parser.parse_intent(
                "What do I have scheduled for tomorrow?",
                sample_user_context
            )
            
            assert result.intent_type == IntentType.GET_SCHEDULE
            assert result.confidence == 0.92
            assert result.entities["start_date"] == "2024-01-16"
            assert result.entities["end_date"] == "2024-01-16"
    
    @pytest.mark.asyncio
    async def test_parse_ambiguous_request(self, intent_parser, sample_user_context):
        """Test parsing an ambiguous request that requires clarification"""
        mock_response = {
            "intent_type": "schedule_event",
            "confidence": 0.6,
            "entities": {
                "title": "meeting"
            },
            "extracted_entities": [],
            "requires_clarification": True,
            "clarification_question": "What day and time would work best for the meeting?"
        }
        
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_api_response = Mock()
            mock_api_response.choices = [Mock()]
            mock_api_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_api_response
            
            result = await intent_parser.parse_intent(
                "Can we meet sometime?",
                sample_user_context
            )
            
            assert result.intent_type == IntentType.SCHEDULE_EVENT
            assert result.confidence == 0.6
            assert result.requires_clarification
            assert result.clarification_question == "What day and time would work best for the meeting?"
    
    @pytest.mark.asyncio
    async def test_parse_reschedule_intent(self, intent_parser, sample_user_context):
        """Test parsing a reschedule request"""
        mock_response = {
            "intent_type": "reschedule_event",
            "confidence": 0.88,
            "entities": {
                "original_time": "15:00",
                "new_time": "16:00"
            },
            "extracted_entities": [],
            "requires_clarification": False,
            "clarification_question": None
        }
        
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_api_response = Mock()
            mock_api_response.choices = [Mock()]
            mock_api_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_api_response
            
            result = await intent_parser.parse_intent(
                "Move my 3pm meeting to 4pm",
                sample_user_context
            )
            
            assert result.intent_type == IntentType.RESCHEDULE_EVENT
            assert result.confidence == 0.88
            assert result.entities["original_time"] == "15:00"
            assert result.entities["new_time"] == "16:00"
    
    @pytest.mark.asyncio
    async def test_parse_cancel_intent(self, intent_parser, sample_user_context):
        """Test parsing a cancel request"""
        mock_response = {
            "intent_type": "cancel_event",
            "confidence": 0.95,
            "entities": {
                "event_identifier": "team meeting",
                "date": "2024-01-15"
            },
            "extracted_entities": [],
            "requires_clarification": False,
            "clarification_question": None
        }
        
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_api_response = Mock()
            mock_api_response.choices = [Mock()]
            mock_api_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_api_response
            
            result = await intent_parser.parse_intent(
                "Cancel my team meeting tomorrow",
                sample_user_context
            )
            
            assert result.intent_type == IntentType.CANCEL_EVENT
            assert result.confidence == 0.95
            assert result.entities["event_identifier"] == "team meeting"
    
    @pytest.mark.asyncio
    async def test_parse_complex_scheduling_request(self, intent_parser, sample_user_context):
        """Test parsing a complex scheduling request with multiple entities"""
        mock_response = {
            "intent_type": "schedule_event",
            "confidence": 0.98,
            "entities": {
                "title": "quarterly review meeting",
                "start_time": "2024-01-19T10:00:00Z",
                "end_time": "2024-01-19T12:00:00Z",
                "duration": 120,
                "location": "main conference room",
                "attendees": ["John", "Sarah"]
            },
            "extracted_entities": [
                {
                    "entity_type": "title",
                    "value": "quarterly review meeting",
                    "confidence": 0.99,
                    "start_pos": 10,
                    "end_pos": 35
                },
                {
                    "entity_type": "attendees",
                    "value": "John and Sarah",
                    "confidence": 0.95,
                    "start_pos": 41,
                    "end_pos": 55
                }
            ],
            "requires_clarification": False,
            "clarification_question": None
        }
        
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_api_response = Mock()
            mock_api_response.choices = [Mock()]
            mock_api_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_api_response
            
            result = await intent_parser.parse_intent(
                "Set up a quarterly review meeting with John and Sarah for next Friday from 10am to 12pm in the main conference room",
                sample_user_context
            )
            
            assert result.intent_type == IntentType.SCHEDULE_EVENT
            assert result.confidence == 0.98
            assert result.entities["title"] == "quarterly review meeting"
            assert result.entities["duration"] == 120
            assert result.entities["location"] == "main conference room"
            assert result.entities["attendees"] == ["John", "Sarah"]
            assert len(result.extracted_entities) == 2
    
    @pytest.mark.asyncio
    async def test_parse_unknown_intent(self, intent_parser, sample_user_context):
        """Test parsing an unrelated request"""
        mock_response = {
            "intent_type": "unknown",
            "confidence": 0.1,
            "entities": {},
            "extracted_entities": [],
            "requires_clarification": True,
            "clarification_question": "I didn't understand that. Could you please ask about scheduling?"
        }
        
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_api_response = Mock()
            mock_api_response.choices = [Mock()]
            mock_api_response.choices[0].message.content = json.dumps(mock_response)
            mock_create.return_value = mock_api_response
            
            result = await intent_parser.parse_intent(
                "What's the weather like today?",
                sample_user_context
            )
            
            assert result.intent_type == IntentType.UNKNOWN
            assert result.confidence == 0.1
            assert result.requires_clarification
    
    @pytest.mark.asyncio
    async def test_openai_api_failure(self, intent_parser, sample_user_context):
        """Test handling OpenAI API failures"""
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_create.side_effect = Exception("API Error")
            
            result = await intent_parser.parse_intent(
                "Schedule a meeting",
                sample_user_context
            )
            
            assert result.intent_type == IntentType.UNKNOWN
            assert result.confidence == 0.0
            assert result.requires_clarification
            assert "couldn't understand" in result.clarification_question
    
    @pytest.mark.asyncio
    async def test_invalid_json_response(self, intent_parser, sample_user_context):
        """Test handling invalid JSON responses from OpenAI"""
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "Invalid JSON response"
            mock_create.return_value = mock_response
            
            result = await intent_parser.parse_intent(
                "Schedule a meeting",
                sample_user_context
            )
            
            # Should fall back to keyword matching
            assert result.intent_type == IntentType.SCHEDULE_EVENT
            assert result.confidence == 0.5
            assert result.requires_clarification
    
    @pytest.mark.asyncio
    async def test_batch_intent_parsing(self, intent_parser, sample_user_context):
        """Test parsing multiple intents in batch"""
        mock_responses = [
            {
                "intent_type": "schedule_event",
                "confidence": 0.9,
                "entities": {"title": "Meeting 1"},
                "extracted_entities": [],
                "requires_clarification": False,
                "clarification_question": None
            },
            {
                "intent_type": "get_schedule",
                "confidence": 0.85,
                "entities": {"start_date": "2024-01-16"},
                "extracted_entities": [],
                "requires_clarification": False,
                "clarification_question": None
            }
        ]
        
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_create.side_effect = [
                Mock(choices=[Mock(message=Mock(content=json.dumps(mock_responses[0])))]),
                Mock(choices=[Mock(message=Mock(content=json.dumps(mock_responses[1])))])
            ]
            
            texts = ["Schedule a meeting", "What's my schedule?"]
            results = await intent_parser.parse_batch_intents(texts, sample_user_context)
            
            assert len(results) == 2
            assert results[0].intent_type == IntentType.SCHEDULE_EVENT
            assert results[1].intent_type == IntentType.GET_SCHEDULE
    
    def test_validate_time_entities(self, intent_parser):
        """Test time entity validation"""
        entities = {
            "start_time": "2024-01-15T14:00:00Z",
            "end_time": "invalid_time",
            "duration": "60"
        }
        
        validated = intent_parser._validate_time_entities(entities)
        
        assert "start_time" in validated
        assert "end_time" not in validated  # Should be removed due to invalid format
        assert validated["duration"] == 60  # Should be converted to int
    
    def test_add_default_values(self, intent_parser, sample_user_context):
        """Test adding default values based on user context"""
        entities = {"title": "Meeting"}
        
        enhanced = intent_parser._add_default_values(entities, sample_user_context)
        
        assert enhanced["duration"] == 60  # From user preferences
        assert enhanced["calendar_provider"] == "google"  # Default
    
    def test_get_supported_intents(self, intent_parser):
        """Test getting supported intent types"""
        intents = intent_parser.get_supported_intents()
        
        assert "schedule_event" in intents
        assert "get_schedule" in intents
        assert "reschedule_event" in intents
        assert "cancel_event" in intents
        assert "unknown" in intents
    
    def test_get_supported_entities(self, intent_parser):
        """Test getting supported entity types"""
        entities = intent_parser.get_supported_entities()
        
        assert "title" in entities
        assert "start_time" in entities
        assert "duration" in entities
        assert "location" in entities
        assert "attendees" in entities
    
    @pytest.mark.asyncio
    async def test_empty_text_validation(self, intent_parser, sample_user_context):
        """Test validation of empty text input"""
        result = await intent_parser.parse_intent("", sample_user_context)
        
        assert result.intent_type == IntentType.UNKNOWN
        assert result.confidence == 0.0
        assert result.requires_clarification
    
    @pytest.mark.asyncio
    async def test_very_long_text_handling(self, intent_parser, sample_user_context):
        """Test handling of very long text input"""
        long_text = "Schedule a meeting " * 1000  # Very long text
        
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps({
                "intent_type": "schedule_event",
                "confidence": 0.8,
                "entities": {"title": "meeting"},
                "extracted_entities": [],
                "requires_clarification": False,
                "clarification_question": None
            })
            mock_create.return_value = mock_response
            
            result = await intent_parser.parse_intent(long_text, sample_user_context)
            
            assert result.intent_type == IntentType.SCHEDULE_EVENT
            # Should handle long text gracefully
    
    @pytest.mark.asyncio
    async def test_context_preparation(self, intent_parser, sample_user_context):
        """Test preparation of context information"""
        context_info = intent_parser._prepare_context(sample_user_context)
        
        assert context_info["timezone"] == "UTC"
        assert context_info["preferences"]["preferred_meeting_duration"] == 60
        assert context_info["preferences"]["work_start_time"] == "09:00:00"
        assert context_info["preferences"]["work_end_time"] == "17:00:00"
    
    @pytest.mark.asyncio
    async def test_context_preparation_none(self, intent_parser):
        """Test preparation of context when user context is None"""
        context_info = intent_parser._prepare_context(None)
        
        assert context_info["timezone"] == "UTC"
        assert context_info["preferences"] == {}
        assert context_info["existing_events"] == []
    
    def test_create_entity_objects(self, intent_parser):
        """Test creation of IntentEntity objects"""
        entities_data = [
            {
                "entity_type": "title",
                "value": "Meeting",
                "confidence": 0.95,
                "start_pos": 0,
                "end_pos": 7
            },
            {
                "entity_type": "time",
                "value": "2pm",
                "confidence": 0.88
            }
        ]
        
        entities = intent_parser._create_entity_objects(entities_data)
        
        assert len(entities) == 2
        assert entities[0].entity_type == "title"
        assert entities[0].value == "Meeting"
        assert entities[0].confidence == 0.95
        assert entities[1].entity_type == "time"
        assert entities[1].start_pos is None  # Not provided in second entity
    
    @pytest.mark.asyncio
    async def test_processing_time_calculation(self, intent_parser, sample_user_context):
        """Test that processing time is calculated correctly"""
        with patch.object(intent_parser.client.chat.completions, 'create') as mock_create:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = json.dumps({
                "intent_type": "schedule_event",
                "confidence": 0.9,
                "entities": {},
                "extracted_entities": [],
                "requires_clarification": False,
                "clarification_question": None
            })
            mock_create.return_value = mock_response
            
            result = await intent_parser.parse_intent("Schedule a meeting", sample_user_context)
            
            assert result.processing_time > 0
            assert result.processing_time < 10  # Should be reasonable time 