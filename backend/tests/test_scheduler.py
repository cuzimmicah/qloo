import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta, time, date
import pytz

from ..scheduling.scheduler import Scheduler
from shared.models import (
    TimeSlot, Event, EventRequest, UserContext, UserPreferences,
    CalendarProvider, EventStatus
)

class TestScheduler:
    """Test suite for the Scheduler class"""
    
    @pytest.fixture
    def scheduler(self):
        """Create Scheduler instance for testing"""
        return Scheduler()
    
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
    def sample_events(self):
        """Create sample events for testing"""
        return [
            Event(
                event_id="event_1",
                title="Morning Meeting",
                start_time=datetime(2024, 1, 15, 10, 0, 0),
                end_time=datetime(2024, 1, 15, 11, 0, 0),
                calendar_provider=CalendarProvider.GOOGLE,
                status=EventStatus.SCHEDULED
            ),
            Event(
                event_id="event_2",
                title="Lunch Break",
                start_time=datetime(2024, 1, 15, 12, 0, 0),
                end_time=datetime(2024, 1, 15, 13, 0, 0),
                calendar_provider=CalendarProvider.GOOGLE,
                status=EventStatus.SCHEDULED
            ),
            Event(
                event_id="event_3",
                title="Cancelled Meeting",
                start_time=datetime(2024, 1, 15, 14, 0, 0),
                end_time=datetime(2024, 1, 15, 15, 0, 0),
                calendar_provider=CalendarProvider.GOOGLE,
                status=EventStatus.CANCELLED
            )
        ]
    
    @pytest.mark.asyncio
    async def test_find_available_slots_basic(self, scheduler, sample_user_context):
        """Test basic available slot finding"""
        with patch.object(scheduler, '_get_existing_events', return_value=[]):
            slots = await scheduler.find_available_slots(
                duration=60,
                user_context=sample_user_context,
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15)
            )
            
            assert len(slots) > 0
            assert all(isinstance(slot, TimeSlot) for slot in slots)
            assert all(slot.confidence > 0 for slot in slots)
            
            # Check that slots are within working hours
            for slot in slots:
                assert slot.start_time.time() >= time(9, 0)
                assert slot.end_time.time() <= time(17, 0)
    
    @pytest.mark.asyncio
    async def test_find_available_slots_with_conflicts(self, scheduler, sample_user_context, sample_events):
        """Test finding available slots with existing events"""
        with patch.object(scheduler, '_get_existing_events', return_value=sample_events):
            slots = await scheduler.find_available_slots(
                duration=60,
                user_context=sample_user_context,
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15)
            )
            
            # Should find slots that don't conflict with existing events
            for slot in slots:
                for event in sample_events:
                    if event.status != EventStatus.CANCELLED:
                        # Check no overlap
                        assert not (slot.start_time < event.end_time and 
                                  slot.end_time > event.start_time)
    
    @pytest.mark.asyncio
    async def test_find_available_slots_preferred_time(self, scheduler, sample_user_context):
        """Test finding slots with preferred time"""
        preferred_time = datetime(2024, 1, 15, 14, 0, 0)
        
        with patch.object(scheduler, '_get_existing_events', return_value=[]):
            slots = await scheduler.find_available_slots(
                duration=60,
                preferred_time=preferred_time,
                user_context=sample_user_context,
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15)
            )
            
            # First slot should be closest to preferred time
            assert len(slots) > 0
            
            # Check that slots are sorted by confidence (which includes preferred time bonus)
            for i in range(len(slots) - 1):
                assert slots[i].confidence >= slots[i + 1].confidence
    
    @pytest.mark.asyncio
    async def test_find_available_slots_timezone_handling(self, scheduler):
        """Test timezone handling in slot finding"""
        # Create user context with different timezone
        user_context = UserContext(
            user_id="test_user",
            email="test@example.com",
            preferences=UserPreferences(
                work_start_time=time(9, 0),
                work_end_time=time(17, 0)
            ),
            current_timezone="America/New_York"
        )
        
        with patch.object(scheduler, '_get_existing_events', return_value=[]):
            slots = await scheduler.find_available_slots(
                duration=60,
                user_context=user_context,
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15)
            )
            
            # Should handle timezone correctly
            assert len(slots) > 0
            
            # Check that slots are in the correct timezone
            for slot in slots:
                assert slot.start_time.tzinfo is not None
    
    @pytest.mark.asyncio
    async def test_find_available_slots_weekend_exclusion(self, scheduler, sample_user_context):
        """Test weekend exclusion in slot finding"""
        # Saturday and Sunday
        start_date = date(2024, 1, 13)  # Saturday
        end_date = date(2024, 1, 14)    # Sunday
        
        with patch.object(scheduler, '_get_existing_events', return_value=[]):
            slots = await scheduler.find_available_slots(
                duration=60,
                user_context=sample_user_context,
                start_date=start_date,
                end_date=end_date,
                exclude_weekends=True
            )
            
            # Should return no slots for weekends
            assert len(slots) == 0
    
    @pytest.mark.asyncio
    async def test_find_available_slots_include_weekends(self, scheduler, sample_user_context):
        """Test including weekends in slot finding"""
        # Saturday and Sunday
        start_date = date(2024, 1, 13)  # Saturday
        end_date = date(2024, 1, 14)    # Sunday
        
        with patch.object(scheduler, '_get_existing_events', return_value=[]):
            slots = await scheduler.find_available_slots(
                duration=60,
                user_context=sample_user_context,
                start_date=start_date,
                end_date=end_date,
                exclude_weekends=False
            )
            
            # Should return slots for weekends
            assert len(slots) > 0
    
    def test_generate_potential_slots(self, scheduler):
        """Test generation of potential time slots"""
        preferences = UserPreferences(
            work_start_time=time(9, 0),
            work_end_time=time(17, 0),
            buffer_time=15
        )
        timezone = pytz.UTC
        
        slots = scheduler._generate_potential_slots(
            start_date=date(2024, 1, 15),
            end_date=date(2024, 1, 15),
            duration=60,
            preferences=preferences,
            timezone=timezone,
            exclude_weekends=True
        )
        
        assert len(slots) > 0
        
        # Check slot properties
        for slot in slots:
            assert isinstance(slot, TimeSlot)
            assert slot.end_time > slot.start_time
            assert (slot.end_time - slot.start_time).total_seconds() == 3600  # 60 minutes
    
    def test_generate_day_slots(self, scheduler):
        """Test generation of slots for a specific day"""
        preferences = UserPreferences(
            work_start_time=time(9, 0),
            work_end_time=time(17, 0),
            buffer_time=15
        )
        timezone = pytz.UTC
        target_date = date(2024, 1, 15)
        
        slots = scheduler._generate_day_slots(
            target_date=target_date,
            duration=60,
            preferences=preferences,
            timezone=timezone
        )
        
        assert len(slots) > 0
        
        # Check that all slots are on the target date
        for slot in slots:
            assert slot.start_time.date() == target_date
            assert slot.end_time.date() == target_date
        
        # Check that slots have proper buffer time between them
        for i in range(len(slots) - 1):
            time_between = slots[i + 1].start_time - slots[i].end_time
            assert time_between.total_seconds() >= 900  # 15 minutes buffer
    
    def test_filter_conflicting_slots(self, scheduler, sample_events):
        """Test filtering out conflicting slots"""
        preferences = UserPreferences(buffer_time=15)
        
        # Create some test slots
        potential_slots = [
            TimeSlot(
                start_time=datetime(2024, 1, 15, 9, 0, 0),
                end_time=datetime(2024, 1, 15, 10, 0, 0),
                confidence=0.8
            ),
            TimeSlot(
                start_time=datetime(2024, 1, 15, 10, 0, 0),  # Conflicts with event_1
                end_time=datetime(2024, 1, 15, 11, 0, 0),
                confidence=0.8
            ),
            TimeSlot(
                start_time=datetime(2024, 1, 15, 15, 0, 0),  # After work hours
                end_time=datetime(2024, 1, 15, 16, 0, 0),
                confidence=0.8
            )
        ]
        
        available_slots = scheduler._filter_conflicting_slots(
            potential_slots, sample_events, preferences
        )
        
        # Should filter out conflicting slots
        assert len(available_slots) < len(potential_slots)
        
        # Check that remaining slots don't conflict
        for slot in available_slots:
            for event in sample_events:
                if event.status != EventStatus.CANCELLED:
                    assert not scheduler._slots_overlap(slot, event)
    
    def test_slots_overlap(self, scheduler):
        """Test slot overlap detection"""
        slot = TimeSlot(
            start_time=datetime(2024, 1, 15, 10, 0, 0),
            end_time=datetime(2024, 1, 15, 11, 0, 0),
            confidence=0.8
        )
        
        # Overlapping event
        overlapping_event = Event(
            event_id="overlap_test",
            title="Overlapping Event",
            start_time=datetime(2024, 1, 15, 10, 30, 0),
            end_time=datetime(2024, 1, 15, 11, 30, 0),
            calendar_provider=CalendarProvider.GOOGLE,
            status=EventStatus.SCHEDULED
        )
        
        # Non-overlapping event
        non_overlapping_event = Event(
            event_id="no_overlap_test",
            title="Non-overlapping Event",
            start_time=datetime(2024, 1, 15, 11, 30, 0),
            end_time=datetime(2024, 1, 15, 12, 30, 0),
            calendar_provider=CalendarProvider.GOOGLE,
            status=EventStatus.SCHEDULED
        )
        
        assert scheduler._slots_overlap(slot, overlapping_event)
        assert not scheduler._slots_overlap(slot, non_overlapping_event)
    
    def test_score_time_slots(self, scheduler):
        """Test time slot scoring"""
        preferences = UserPreferences(
            work_start_time=time(9, 0),
            work_end_time=time(17, 0)
        )
        timezone = pytz.UTC
        
        slots = [
            TimeSlot(
                start_time=datetime(2024, 1, 15, 9, 0, 0),  # Start of work day
                end_time=datetime(2024, 1, 15, 10, 0, 0),
                confidence=0.5
            ),
            TimeSlot(
                start_time=datetime(2024, 1, 15, 14, 0, 0),  # Afternoon
                end_time=datetime(2024, 1, 15, 15, 0, 0),
                confidence=0.5
            ),
            TimeSlot(
                start_time=datetime(2024, 1, 15, 19, 0, 0),  # After work hours
                end_time=datetime(2024, 1, 15, 20, 0, 0),
                confidence=0.5
            )
        ]
        
        preferred_time = datetime(2024, 1, 15, 14, 0, 0)
        
        scored_slots = scheduler._score_time_slots(
            slots, preferred_time, preferences, timezone
        )
        
        # Should be sorted by confidence (highest first)
        for i in range(len(scored_slots) - 1):
            assert scored_slots[i].confidence >= scored_slots[i + 1].confidence
        
        # Slot matching preferred time should have highest confidence
        assert scored_slots[0].start_time == preferred_time
    
    def test_calculate_slot_score(self, scheduler):
        """Test slot score calculation"""
        preferences = UserPreferences(
            work_start_time=time(9, 0),
            work_end_time=time(17, 0)
        )
        timezone = pytz.UTC
        
        # Morning slot (should get morning bonus)
        morning_slot = TimeSlot(
            start_time=datetime(2024, 1, 15, 10, 0, 0),
            end_time=datetime(2024, 1, 15, 11, 0, 0),
            confidence=0.5
        )
        
        # Afternoon slot
        afternoon_slot = TimeSlot(
            start_time=datetime(2024, 1, 15, 14, 0, 0),
            end_time=datetime(2024, 1, 15, 15, 0, 0),
            confidence=0.5
        )
        
        # Evening slot (should get penalty)
        evening_slot = TimeSlot(
            start_time=datetime(2024, 1, 15, 19, 0, 0),
            end_time=datetime(2024, 1, 15, 20, 0, 0),
            confidence=0.5
        )
        
        morning_score = scheduler._calculate_slot_score(
            morning_slot, None, preferences, timezone
        )
        afternoon_score = scheduler._calculate_slot_score(
            afternoon_slot, None, preferences, timezone
        )
        evening_score = scheduler._calculate_slot_score(
            evening_slot, None, preferences, timezone
        )
        
        # Morning should score higher than afternoon
        assert morning_score > afternoon_score
        
        # Evening should score lower due to being outside work hours
        assert evening_score < afternoon_score
    
    @pytest.mark.asyncio
    async def test_create_event(self, scheduler):
        """Test event creation"""
        mock_event = Event(
            event_id="created_event",
            title="Test Event",
            start_time=datetime(2024, 1, 15, 14, 0, 0),
            end_time=datetime(2024, 1, 15, 15, 0, 0),
            calendar_provider=CalendarProvider.GOOGLE,
            status=EventStatus.SCHEDULED
        )
        
        with patch.object(scheduler.google_calendar, 'create_event', return_value=mock_event):
            result = await scheduler.create_event(
                title="Test Event",
                start_time=datetime(2024, 1, 15, 14, 0, 0),
                end_time=datetime(2024, 1, 15, 15, 0, 0),
                calendar_provider="google"
            )
            
            assert result == mock_event
            assert result.title == "Test Event"
    
    @pytest.mark.asyncio
    async def test_update_event(self, scheduler):
        """Test event updating"""
        mock_event = Event(
            event_id="updated_event",
            title="Updated Event",
            start_time=datetime(2024, 1, 15, 14, 0, 0),
            end_time=datetime(2024, 1, 15, 15, 0, 0),
            calendar_provider=CalendarProvider.GOOGLE,
            status=EventStatus.SCHEDULED
        )
        
        with patch.object(scheduler.google_calendar, 'update_event', return_value=mock_event):
            result = await scheduler.update_event(
                event_id="test_event",
                updates={"title": "Updated Event"},
                calendar_provider="google"
            )
            
            assert result == mock_event
            assert result.title == "Updated Event"
    
    @pytest.mark.asyncio
    async def test_cancel_event(self, scheduler):
        """Test event cancellation"""
        with patch.object(scheduler.google_calendar, 'cancel_event', return_value=True):
            result = await scheduler.cancel_event(
                event_id="test_event",
                calendar_provider="google"
            )
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_availability_available(self, scheduler):
        """Test availability checking when time is available"""
        start_time = datetime(2024, 1, 15, 14, 0, 0)
        end_time = datetime(2024, 1, 15, 15, 0, 0)
        
        with patch.object(scheduler, '_get_existing_events', return_value=[]):
            result = await scheduler.check_availability(start_time, end_time)
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_availability_conflict(self, scheduler, sample_events):
        """Test availability checking when there's a conflict"""
        # Try to schedule at same time as existing event
        start_time = datetime(2024, 1, 15, 10, 0, 0)
        end_time = datetime(2024, 1, 15, 11, 0, 0)
        
        with patch.object(scheduler, '_get_existing_events', return_value=sample_events):
            result = await scheduler.check_availability(start_time, end_time)
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_find_meeting_time(self, scheduler, sample_user_context):
        """Test finding meeting time for multiple attendees"""
        attendees = ["john@example.com", "jane@example.com"]
        
        with patch.object(scheduler, 'find_available_slots') as mock_find_slots:
            mock_slots = [
                TimeSlot(
                    start_time=datetime(2024, 1, 15, 14, 0, 0),
                    end_time=datetime(2024, 1, 15, 15, 0, 0),
                    confidence=0.9
                )
            ]
            mock_find_slots.return_value = mock_slots
            
            result = await scheduler.find_meeting_time(
                attendees=attendees,
                duration=60,
                user_context=sample_user_context
            )
            
            assert result == mock_slots
            mock_find_slots.assert_called_once()
    
    def test_get_optimal_meeting_duration(self, scheduler):
        """Test optimal meeting duration calculation"""
        preferences = UserPreferences(preferred_meeting_duration=60)
        
        # Test different meeting types
        standup_duration = scheduler.get_optimal_meeting_duration(
            "standup", 5, preferences
        )
        assert standup_duration == 15
        
        team_meeting_duration = scheduler.get_optimal_meeting_duration(
            "team_meeting", 5, preferences
        )
        assert team_meeting_duration == 60
        
        # Test attendee count adjustment
        large_meeting_duration = scheduler.get_optimal_meeting_duration(
            "team_meeting", 12, preferences
        )
        assert large_meeting_duration == 75  # 60 + 15 for >10 attendees
    
    @pytest.mark.asyncio
    async def test_suggest_reschedule_options(self, scheduler):
        """Test suggesting reschedule options"""
        original_event = Event(
            event_id="reschedule_test",
            title="Original Event",
            start_time=datetime(2024, 1, 15, 14, 0, 0),
            end_time=datetime(2024, 1, 15, 15, 0, 0),
            calendar_provider=CalendarProvider.GOOGLE,
            status=EventStatus.SCHEDULED
        )
        
        mock_slots = [
            TimeSlot(
                start_time=datetime(2024, 1, 15, 16, 0, 0),
                end_time=datetime(2024, 1, 15, 17, 0, 0),
                confidence=0.9
            )
        ]
        
        with patch.object(scheduler.google_calendar, 'get_event', return_value=original_event):
            with patch.object(scheduler, 'find_available_slots', return_value=mock_slots):
                result = await scheduler.suggest_reschedule_options(
                    event_id="reschedule_test",
                    calendar_provider="google"
                )
                
                assert result == mock_slots
    
    def test_dict_to_event_conversion(self, scheduler):
        """Test converting dictionary to Event object"""
        event_dict = {
            "event_id": "test_event",
            "title": "Test Event",
            "start_time": "2024-01-15T14:00:00Z",
            "end_time": "2024-01-15T15:00:00Z",
            "location": "Conference Room",
            "attendees": ["john@example.com"],
            "status": "scheduled"
        }
        
        event = scheduler._dict_to_event(event_dict)
        
        assert isinstance(event, Event)
        assert event.event_id == "test_event"
        assert event.title == "Test Event"
        assert event.location == "Conference Room"
        assert event.attendees == ["john@example.com"]
        assert event.status == EventStatus.SCHEDULED
    
    @pytest.mark.asyncio
    async def test_get_existing_events(self, scheduler, sample_user_context):
        """Test getting existing events from all providers"""
        mock_google_events = [
            Event(
                event_id="google_event",
                title="Google Event",
                start_time=datetime(2024, 1, 15, 10, 0, 0),
                end_time=datetime(2024, 1, 15, 11, 0, 0),
                calendar_provider=CalendarProvider.GOOGLE,
                status=EventStatus.SCHEDULED
            )
        ]
        
        
        with patch.object(scheduler.google_calendar, 'get_events', return_value=mock_google_events):
            events = await scheduler._get_existing_events(
                start_date=date(2024, 1, 15),
                end_date=date(2024, 1, 15),
                user_context=sample_user_context
            )
            
            assert len(events) == 1
            assert events[0].calendar_provider == CalendarProvider.GOOGLE
    
    @pytest.mark.asyncio
    async def test_error_handling(self, scheduler):
        """Test error handling in scheduler methods"""
        # Test with invalid calendar provider
        with pytest.raises(ValueError):
            await scheduler.create_event(
                title="Test Event",
                start_time=datetime(2024, 1, 15, 14, 0, 0),
                end_time=datetime(2024, 1, 15, 15, 0, 0),
                calendar_provider="invalid_provider"
            )
        
        # Test with API failure
        with patch.object(scheduler.google_calendar, 'create_event', side_effect=Exception("API Error")):
            with pytest.raises(Exception):
                await scheduler.create_event(
                    title="Test Event",
                    start_time=datetime(2024, 1, 15, 14, 0, 0),
                    end_time=datetime(2024, 1, 15, 15, 0, 0),
                    calendar_provider="google"
                ) 