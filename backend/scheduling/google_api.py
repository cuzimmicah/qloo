import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import google.auth.exceptions

from shared.models import Event, EventStatus, CalendarProvider

logger = logging.getLogger(__name__)

class GoogleCalendarAPI:
    """Google Calendar API integration with OAuth2 authentication"""
    
    def __init__(self):
        self.scopes = ['https://www.googleapis.com/auth/calendar']
        self.credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
        self.token_file = os.getenv('GOOGLE_TOKEN_FILE', 'token.json')
        self.service = None
        self.credentials = None
        
        # Rate limiting
        self.rate_limit_delay = 0.1  # 100ms between requests
        self.max_retries = 3
        
    async def initialize(self):
        """Initialize the Google Calendar service"""
        try:
            await self._authenticate()
            if self.credentials:
                self.service = build('calendar', 'v3', credentials=self.credentials)
                logger.info("Google Calendar API initialized successfully")
            else:
                logger.error("Failed to initialize Google Calendar API - no credentials")
        except Exception as e:
            logger.error(f"Failed to initialize Google Calendar API: {str(e)}")
            raise
    
    async def _authenticate(self):
        """Handle OAuth2 authentication"""
        try:
            # Load existing credentials
            if os.path.exists(self.token_file):
                self.credentials = Credentials.from_authorized_user_file(
                    self.token_file, self.scopes
                )
            
            # If credentials are invalid or don't exist, get new ones
            if not self.credentials or not self.credentials.valid:
                if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                    try:
                        self.credentials.refresh(Request())
                    except google.auth.exceptions.RefreshError:
                        logger.warning("Failed to refresh credentials, need to re-authenticate")
                        self.credentials = None
                
                if not self.credentials:
                    # This would typically be handled by a web flow in production
                    logger.error("No valid credentials available. Need to implement OAuth flow.")
                    return
                
                # Save credentials for future use
                with open(self.token_file, 'w') as token:
                    token.write(self.credentials.to_json())
                    
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            raise
    
    async def _make_request(self, request_func, *args, **kwargs):
        """Make an API request with rate limiting and retry logic"""
        for attempt in range(self.max_retries):
            try:
                # Add rate limiting delay
                await asyncio.sleep(self.rate_limit_delay)
                
                # Make the request
                result = request_func(*args, **kwargs)
                return result
                
            except HttpError as e:
                if e.resp.status == 429:  # Rate limit exceeded
                    wait_time = min(2 ** attempt, 60)  # Exponential backoff, max 60s
                    logger.warning(f"Rate limit exceeded, waiting {wait_time}s before retry")
                    await asyncio.sleep(wait_time)
                    continue
                elif e.resp.status == 401:  # Authentication error
                    logger.error("Authentication error, need to re-authenticate")
                    await self._authenticate()
                    if attempt < self.max_retries - 1:
                        continue
                else:
                    logger.error(f"HTTP error {e.resp.status}: {e.content}")
                    raise
            except Exception as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        
        raise Exception(f"Request failed after {self.max_retries} attempts")
    
    async def get_events(self, start_date: str, end_date: str, calendar_id: str = 'primary') -> List[Event]:
        """Get events from Google Calendar"""
        try:
            if not self.service:
                await self.initialize()
            
            # Format dates for Google Calendar API
            start_time = f"{start_date}T00:00:00Z"
            end_time = f"{end_date}T23:59:59Z"
            
            # Make the API request
            events_result = await self._make_request(
                self.service.events().list,
                calendarId=calendar_id,
                timeMin=start_time,
                timeMax=end_time,
                singleEvents=True,
                orderBy='startTime'
            )
            
            events = events_result.get('items', [])
            
            # Convert to our Event model
            converted_events = []
            for event in events:
                converted_event = self._convert_google_event(event)
                if converted_event:
                    converted_events.append(converted_event)
            
            logger.info(f"Retrieved {len(converted_events)} events from Google Calendar")
            return converted_events
            
        except Exception as e:
            logger.error(f"Failed to get events: {str(e)}")
            return []
    
    def _convert_google_event(self, google_event: Dict[str, Any]) -> Optional[Event]:
        """Convert Google Calendar event to our Event model"""
        try:
            # Handle different time formats
            start = google_event.get('start', {})
            end = google_event.get('end', {})
            
            # Parse start time
            if 'dateTime' in start:
                start_time = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
            elif 'date' in start:
                start_time = datetime.fromisoformat(f"{start['date']}T00:00:00+00:00")
            else:
                logger.warning(f"Event {google_event.get('id')} has no start time")
                return None
            
            # Parse end time
            if 'dateTime' in end:
                end_time = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
            elif 'date' in end:
                end_time = datetime.fromisoformat(f"{end['date']}T23:59:59+00:00")
            else:
                end_time = start_time + timedelta(hours=1)  # Default 1 hour duration
            
            # Extract attendees
            attendees = []
            for attendee in google_event.get('attendees', []):
                if 'email' in attendee:
                    attendees.append(attendee['email'])
            
            # Determine status
            status = EventStatus.SCHEDULED
            if google_event.get('status') == 'cancelled':
                status = EventStatus.CANCELLED
            
            return Event(
                event_id=google_event.get('id'),
                title=google_event.get('summary', 'Untitled Event'),
                description=google_event.get('description'),
                start_time=start_time,
                end_time=end_time,
                location=google_event.get('location'),
                attendees=attendees,
                calendar_provider=CalendarProvider.GOOGLE,
                status=status
            )
            
        except Exception as e:
            logger.error(f"Failed to convert Google event: {str(e)}")
            return None
    
    async def create_event(self, event_data: Dict[str, Any], calendar_id: str = 'primary') -> Event:
        """Create a new event in Google Calendar"""
        try:
            if not self.service:
                await self.initialize()
            
            # Convert our event data to Google Calendar format
            google_event = self._convert_to_google_event(event_data)
            
            # Create the event
            created_event = await self._make_request(
                self.service.events().insert,
                calendarId=calendar_id,
                body=google_event
            )
            
            # Convert back to our Event model
            result = self._convert_google_event(created_event)
            if result:
                logger.info(f"Created event: {result.title}")
                return result
            else:
                raise Exception("Failed to convert created event")
                
        except Exception as e:
            logger.error(f"Failed to create event: {str(e)}")
            raise
    
    def _convert_to_google_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert our event data to Google Calendar format"""
        google_event = {
            'summary': event_data.get('title', 'Untitled Event'),
            'description': event_data.get('description', ''),
            'start': {
                'dateTime': event_data['start_time'].isoformat(),
                'timeZone': 'UTC'
            },
            'end': {
                'dateTime': event_data['end_time'].isoformat(),
                'timeZone': 'UTC'
            }
        }
        
        # Add location if provided
        if event_data.get('location'):
            google_event['location'] = event_data['location']
        
        # Add attendees if provided
        if event_data.get('attendees'):
            google_event['attendees'] = [
                {'email': email} for email in event_data['attendees']
            ]
        
        # Add reminders
        google_event['reminders'] = {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},  # 24 hours
                {'method': 'popup', 'minutes': 15}  # 15 minutes
            ]
        }
        
        return google_event
    
    async def update_event(self, event_id: str, updates: Dict[str, Any], calendar_id: str = 'primary') -> Event:
        """Update an existing event in Google Calendar"""
        try:
            if not self.service:
                await self.initialize()
            
            # Get the existing event
            existing_event = await self._make_request(
                self.service.events().get,
                calendarId=calendar_id,
                eventId=event_id
            )
            
            # Apply updates
            for key, value in updates.items():
                if key == 'title':
                    existing_event['summary'] = value
                elif key == 'description':
                    existing_event['description'] = value
                elif key == 'start_time':
                    existing_event['start'] = {
                        'dateTime': value.isoformat(),
                        'timeZone': 'UTC'
                    }
                elif key == 'end_time':
                    existing_event['end'] = {
                        'dateTime': value.isoformat(),
                        'timeZone': 'UTC'
                    }
                elif key == 'location':
                    existing_event['location'] = value
                elif key == 'attendees':
                    existing_event['attendees'] = [
                        {'email': email} for email in value
                    ]
            
            # Update the event
            updated_event = await self._make_request(
                self.service.events().update,
                calendarId=calendar_id,
                eventId=event_id,
                body=existing_event
            )
            
            # Convert back to our Event model
            result = self._convert_google_event(updated_event)
            if result:
                logger.info(f"Updated event: {result.title}")
                return result
            else:
                raise Exception("Failed to convert updated event")
                
        except Exception as e:
            logger.error(f"Failed to update event: {str(e)}")
            raise
    
    async def cancel_event(self, event_id: str, calendar_id: str = 'primary') -> bool:
        """Cancel an event in Google Calendar"""
        try:
            if not self.service:
                await self.initialize()
            
            # Delete the event
            await self._make_request(
                self.service.events().delete,
                calendarId=calendar_id,
                eventId=event_id
            )
            
            logger.info(f"Cancelled event: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel event: {str(e)}")
            return False
    
    async def get_event(self, event_id: str, calendar_id: str = 'primary') -> Optional[Event]:
        """Get a specific event by ID"""
        try:
            if not self.service:
                await self.initialize()
            
            google_event = await self._make_request(
                self.service.events().get,
                calendarId=calendar_id,
                eventId=event_id
            )
            
            return self._convert_google_event(google_event)
            
        except Exception as e:
            logger.error(f"Failed to get event {event_id}: {str(e)}")
            return None
    
    async def sync(self, calendar_id: str = 'primary') -> int:
        """Sync calendar and return number of events processed"""
        try:
            # Get events for the next 30 days
            start_date = datetime.now().date().isoformat()
            end_date = (datetime.now().date() + timedelta(days=30)).isoformat()
            
            events = await self.get_events(start_date, end_date, calendar_id)
            
            # In a real implementation, you would:
            # 1. Store events in local database
            # 2. Handle incremental sync
            # 3. Detect and handle conflicts
            
            logger.info(f"Synced {len(events)} events from Google Calendar")
            return len(events)
            
        except Exception as e:
            logger.error(f"Failed to sync Google Calendar: {str(e)}")
            return 0
    
    async def get_calendars(self) -> List[Dict[str, Any]]:
        """Get list of user's calendars"""
        try:
            if not self.service:
                await self.initialize()
            
            calendars_result = await self._make_request(
                self.service.calendarList().list
            )
            
            calendars = calendars_result.get('items', [])
            
            # Return simplified calendar info
            return [
                {
                    'id': cal.get('id'),
                    'name': cal.get('summary'),
                    'primary': cal.get('primary', False),
                    'access_role': cal.get('accessRole')
                }
                for cal in calendars
            ]
            
        except Exception as e:
            logger.error(f"Failed to get calendars: {str(e)}")
            return []
    
    async def check_availability(self, start_time: datetime, end_time: datetime, calendar_id: str = 'primary') -> bool:
        """Check if a time slot is available"""
        try:
            if not self.service:
                await self.initialize()
            
            # Query for events in the time range
            events_result = await self._make_request(
                self.service.events().list,
                calendarId=calendar_id,
                timeMin=start_time.isoformat(),
                timeMax=end_time.isoformat(),
                singleEvents=True
            )
            
            events = events_result.get('items', [])
            
            # Check for conflicts
            for event in events:
                if event.get('status') == 'cancelled':
                    continue
                
                event_start = event.get('start', {})
                event_end = event.get('end', {})
                
                # Parse event times
                if 'dateTime' in event_start:
                    event_start_time = datetime.fromisoformat(event_start['dateTime'].replace('Z', '+00:00'))
                elif 'date' in event_start:
                    event_start_time = datetime.fromisoformat(f"{event_start['date']}T00:00:00+00:00")
                else:
                    continue
                
                if 'dateTime' in event_end:
                    event_end_time = datetime.fromisoformat(event_end['dateTime'].replace('Z', '+00:00'))
                elif 'date' in event_end:
                    event_end_time = datetime.fromisoformat(f"{event_end['date']}T23:59:59+00:00")
                else:
                    continue
                
                # Check for overlap
                if start_time < event_end_time and end_time > event_start_time:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to check availability: {str(e)}")
            return False 