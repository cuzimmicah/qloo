import asyncio
import logging
from datetime import datetime, timedelta, time, date
from typing import List, Optional, Dict, Any, Tuple
import pytz
from dateutil import parser

from shared.models import (
    TimeSlot, Event, EventRequest, UserContext, CalendarProvider,
    EventStatus, UserPreferences
)
from calendar.google_api import GoogleCalendarAPI
from calendar.outlook_api import OutlookAPI

logger = logging.getLogger(__name__)

class Scheduler:
    """Core scheduling engine for finding available time slots and managing events"""
    
    def __init__(self):
        self.google_calendar = GoogleCalendarAPI()
        self.outlook_calendar = OutlookAPI()
        self.min_slot_duration = 15  # Minimum slot duration in minutes
        self.max_suggestions = 10  # Maximum number of suggestions to return
        
    async def find_available_slots(
        self,
        duration: int,
        preferred_time: Optional[datetime] = None,
        user_context: Optional[UserContext] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        exclude_weekends: bool = True
    ) -> List[TimeSlot]:
        """Find available time slots for scheduling"""
        try:
            # Set default date range if not provided
            if not start_date:
                start_date = date.today()
            if not end_date:
                end_date = start_date + timedelta(days=14)  # Look ahead 2 weeks
            
            # Get user preferences
            preferences = user_context.preferences if user_context else UserPreferences()
            timezone = pytz.timezone(user_context.current_timezone if user_context else "UTC")
            
            # Get existing events from all calendar providers
            existing_events = await self._get_existing_events(
                start_date, end_date, user_context
            )
            
            # Generate potential time slots
            potential_slots = self._generate_potential_slots(
                start_date, end_date, duration, preferences, timezone, exclude_weekends
            )
            
            # Filter out conflicting slots
            available_slots = self._filter_conflicting_slots(
                potential_slots, existing_events, preferences
            )
            
            # Score and rank slots
            scored_slots = self._score_time_slots(
                available_slots, preferred_time, preferences, timezone
            )
            
            # Return top suggestions
            return scored_slots[:self.max_suggestions]
            
        except Exception as e:
            logger.error(f"Failed to find available slots: {str(e)}")
            return []
    
    async def _get_existing_events(
        self,
        start_date: date,
        end_date: date,
        user_context: Optional[UserContext]
    ) -> List[Event]:
        """Get existing events from all calendar providers"""
        all_events = []
        
        try:
            # Get events from Google Calendar
            google_events = await self.google_calendar.get_events(
                start_date.isoformat(), end_date.isoformat()
            )
            all_events.extend(google_events)
            
            # Get events from Outlook Calendar
            outlook_events = await self.outlook_calendar.get_events(
                start_date.isoformat(), end_date.isoformat()
            )
            all_events.extend(outlook_events)
            
            # Add events from user context if available
            if user_context and user_context.existing_events:
                context_events = [
                    self._dict_to_event(event_dict) 
                    for event_dict in user_context.existing_events
                ]
                all_events.extend(context_events)
            
        except Exception as e:
            logger.error(f"Failed to fetch existing events: {str(e)}")
        
        return all_events
    
    def _dict_to_event(self, event_dict: Dict[str, Any]) -> Event:
        """Convert dictionary to Event object"""
        return Event(
            event_id=event_dict.get("event_id"),
            title=event_dict.get("title", ""),
            description=event_dict.get("description"),
            start_time=parser.parse(event_dict["start_time"]),
            end_time=parser.parse(event_dict["end_time"]),
            location=event_dict.get("location"),
            attendees=event_dict.get("attendees", []),
            status=EventStatus(event_dict.get("status", "scheduled"))
        )
    
    def _generate_potential_slots(
        self,
        start_date: date,
        end_date: date,
        duration: int,
        preferences: UserPreferences,
        timezone: pytz.BaseTzInfo,
        exclude_weekends: bool
    ) -> List[TimeSlot]:
        """Generate potential time slots within working hours"""
        slots = []
        current_date = start_date
        
        while current_date <= end_date:
            # Skip weekends if requested
            if exclude_weekends and current_date.weekday() >= 5:
                current_date += timedelta(days=1)
                continue
            
            # Generate slots for this day
            day_slots = self._generate_day_slots(
                current_date, duration, preferences, timezone
            )
            slots.extend(day_slots)
            
            current_date += timedelta(days=1)
        
        return slots
    
    def _generate_day_slots(
        self,
        target_date: date,
        duration: int,
        preferences: UserPreferences,
        timezone: pytz.BaseTzInfo
    ) -> List[TimeSlot]:
        """Generate time slots for a specific day"""
        slots = []
        
        # Create datetime objects for work hours
        work_start = datetime.combine(target_date, preferences.work_start_time)
        work_end = datetime.combine(target_date, preferences.work_end_time)
        
        # Localize to user's timezone
        work_start = timezone.localize(work_start)
        work_end = timezone.localize(work_end)
        
        # Generate slots with buffer time
        current_time = work_start
        slot_duration = timedelta(minutes=duration)
        buffer_duration = timedelta(minutes=preferences.buffer_time)
        
        while current_time + slot_duration <= work_end:
            slot_end = current_time + slot_duration
            
            slot = TimeSlot(
                start_time=current_time,
                end_time=slot_end,
                confidence=0.8  # Base confidence, will be adjusted later
            )
            slots.append(slot)
            
            # Move to next slot with buffer
            current_time = slot_end + buffer_duration
        
        return slots
    
    def _filter_conflicting_slots(
        self,
        potential_slots: List[TimeSlot],
        existing_events: List[Event],
        preferences: UserPreferences
    ) -> List[TimeSlot]:
        """Filter out time slots that conflict with existing events"""
        available_slots = []
        
        for slot in potential_slots:
            is_available = True
            
            for event in existing_events:
                # Skip cancelled events
                if event.status == EventStatus.CANCELLED:
                    continue
                
                # Check for overlap
                if self._slots_overlap(slot, event):
                    is_available = False
                    break
                
                # Check buffer time
                buffer_time = timedelta(minutes=preferences.buffer_time)
                if (slot.start_time - event.end_time < buffer_time and 
                    slot.start_time > event.end_time):
                    is_available = False
                    break
                
                if (event.start_time - slot.end_time < buffer_time and 
                    event.start_time > slot.end_time):
                    is_available = False
                    break
            
            if is_available:
                available_slots.append(slot)
        
        return available_slots
    
    def _slots_overlap(self, slot: TimeSlot, event: Event) -> bool:
        """Check if a time slot overlaps with an existing event"""
        return (slot.start_time < event.end_time and 
                slot.end_time > event.start_time)
    
    def _score_time_slots(
        self,
        slots: List[TimeSlot],
        preferred_time: Optional[datetime],
        preferences: UserPreferences,
        timezone: pytz.BaseTzInfo
    ) -> List[TimeSlot]:
        """Score and rank time slots based on preferences"""
        scored_slots = []
        
        for slot in slots:
            score = self._calculate_slot_score(
                slot, preferred_time, preferences, timezone
            )
            
            # Update slot confidence with calculated score
            slot.confidence = min(score, 1.0)
            scored_slots.append(slot)
        
        # Sort by confidence (highest first)
        scored_slots.sort(key=lambda x: x.confidence, reverse=True)
        
        return scored_slots
    
    def _calculate_slot_score(
        self,
        slot: TimeSlot,
        preferred_time: Optional[datetime],
        preferences: UserPreferences,
        timezone: pytz.BaseTzInfo
    ) -> float:
        """Calculate a score for a time slot based on various factors"""
        score = 0.5  # Base score
        
        # Preferred time bonus
        if preferred_time:
            time_diff = abs((slot.start_time - preferred_time).total_seconds())
            # Closer to preferred time = higher score
            time_bonus = max(0, 0.5 - (time_diff / (24 * 3600)))  # Max 0.5 bonus
            score += time_bonus
        
        # Working hours preference
        slot_time = slot.start_time.time()
        if preferences.work_start_time <= slot_time <= preferences.work_end_time:
            score += 0.2
        
        # Morning vs afternoon preference (assume morning is slightly preferred)
        if slot_time.hour < 12:
            score += 0.1
        
        # Avoid very early or very late slots
        if slot_time.hour < 8 or slot_time.hour > 17:
            score -= 0.2
        
        # Prefer slots not too close to lunch time
        if 11 <= slot_time.hour <= 13:
            score -= 0.1
        
        # Weekday preference
        if slot.start_time.weekday() < 5:  # Monday to Friday
            score += 0.1
        
        return max(0.0, min(1.0, score))
    
    async def create_event(
        self,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: List[str] = None,
        calendar_provider: str = "google"
    ) -> Event:
        """Create a new event in the specified calendar"""
        try:
            event_data = {
                "title": title,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "location": location,
                "attendees": attendees or []
            }
            
            if calendar_provider == "google":
                created_event = await self.google_calendar.create_event(event_data)
            elif calendar_provider == "outlook":
                created_event = await self.outlook_calendar.create_event(event_data)
            else:
                raise ValueError(f"Unsupported calendar provider: {calendar_provider}")
            
            return created_event
            
        except Exception as e:
            logger.error(f"Failed to create event: {str(e)}")
            raise
    
    async def update_event(
        self,
        event_id: str,
        updates: Dict[str, Any],
        calendar_provider: str = "google"
    ) -> Event:
        """Update an existing event"""
        try:
            if calendar_provider == "google":
                updated_event = await self.google_calendar.update_event(event_id, updates)
            elif calendar_provider == "outlook":
                updated_event = await self.outlook_calendar.update_event(event_id, updates)
            else:
                raise ValueError(f"Unsupported calendar provider: {calendar_provider}")
            
            return updated_event
            
        except Exception as e:
            logger.error(f"Failed to update event: {str(e)}")
            raise
    
    async def cancel_event(
        self,
        event_id: str,
        calendar_provider: str = "google"
    ) -> bool:
        """Cancel an existing event"""
        try:
            if calendar_provider == "google":
                success = await self.google_calendar.cancel_event(event_id)
            elif calendar_provider == "outlook":
                success = await self.outlook_calendar.cancel_event(event_id)
            else:
                raise ValueError(f"Unsupported calendar provider: {calendar_provider}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to cancel event: {str(e)}")
            return False
    
    async def find_meeting_time(
        self,
        attendees: List[str],
        duration: int,
        preferred_times: List[datetime] = None,
        user_context: Optional[UserContext] = None
    ) -> List[TimeSlot]:
        """Find optimal meeting times considering all attendees' availability"""
        # This is a simplified version - in a real implementation,
        # you would need to check availability for all attendees
        
        try:
            # For now, just find slots for the organizer
            available_slots = await self.find_available_slots(
                duration=duration,
                preferred_time=preferred_times[0] if preferred_times else None,
                user_context=user_context
            )
            
            # TODO: Implement actual multi-attendee availability checking
            # This would require:
            # 1. Get calendar access for all attendees
            # 2. Check their availability
            # 3. Find common free time slots
            # 4. Rank by optimal times for all participants
            
            return available_slots
            
        except Exception as e:
            logger.error(f"Failed to find meeting time: {str(e)}")
            return []
    
    async def suggest_reschedule_options(
        self,
        event_id: str,
        new_duration: Optional[int] = None,
        calendar_provider: str = "google"
    ) -> List[TimeSlot]:
        """Suggest alternative times for rescheduling an event"""
        try:
            # Get the original event
            if calendar_provider == "google":
                original_event = await self.google_calendar.get_event(event_id)
            elif calendar_provider == "outlook":
                original_event = await self.outlook_calendar.get_event(event_id)
            else:
                raise ValueError(f"Unsupported calendar provider: {calendar_provider}")
            
            # Calculate duration
            if new_duration:
                duration = new_duration
            else:
                duration = int((original_event.end_time - original_event.start_time).total_seconds() / 60)
            
            # Find new available slots
            available_slots = await self.find_available_slots(
                duration=duration,
                preferred_time=original_event.start_time,
                start_date=date.today(),
                end_date=date.today() + timedelta(days=30)
            )
            
            return available_slots
            
        except Exception as e:
            logger.error(f"Failed to suggest reschedule options: {str(e)}")
            return []
    
    def get_optimal_meeting_duration(
        self,
        meeting_type: str,
        attendee_count: int,
        user_preferences: Optional[UserPreferences] = None
    ) -> int:
        """Suggest optimal meeting duration based on type and attendee count"""
        base_duration = user_preferences.preferred_meeting_duration if user_preferences else 60
        
        # Adjust based on meeting type
        type_adjustments = {
            "standup": 15,
            "one_on_one": 30,
            "team_meeting": 60,
            "review": 90,
            "presentation": 60,
            "workshop": 120,
            "all_hands": 60
        }
        
        if meeting_type.lower() in type_adjustments:
            base_duration = type_adjustments[meeting_type.lower()]
        
        # Adjust based on attendee count
        if attendee_count > 10:
            base_duration += 15
        elif attendee_count > 5:
            base_duration += 10
        
        return base_duration
    
    async def check_availability(
        self,
        start_time: datetime,
        end_time: datetime,
        user_context: Optional[UserContext] = None
    ) -> bool:
        """Check if a specific time slot is available"""
        try:
            # Get existing events for the time range
            existing_events = await self._get_existing_events(
                start_time.date(),
                end_time.date(),
                user_context
            )
            
            # Check for conflicts
            for event in existing_events:
                if event.status == EventStatus.CANCELLED:
                    continue
                
                if (start_time < event.end_time and end_time > event.start_time):
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to check availability: {str(e)}")
            return False 