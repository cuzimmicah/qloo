import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json
import aiohttp

from shared.models import Event, EventStatus, CalendarProvider

logger = logging.getLogger(__name__)

class OutlookAPI:
    """Microsoft Graph API integration for Outlook Calendar"""
    
    def __init__(self):
        self.client_id = os.getenv('MICROSOFT_CLIENT_ID')
        self.client_secret = os.getenv('MICROSOFT_CLIENT_SECRET')
        self.tenant_id = os.getenv('MICROSOFT_TENANT_ID', 'common')
        self.redirect_uri = os.getenv('MICROSOFT_REDIRECT_URI', 'http://localhost:8000/auth/microsoft/callback')
        
        # API endpoints
        self.graph_url = "https://graph.microsoft.com/v1.0"
        self.auth_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0"
        
        # Scopes needed for calendar access
        self.scopes = ["https://graph.microsoft.com/calendars.readwrite"]
        
        # Authentication
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        
        # Rate limiting
        self.rate_limit_delay = 0.1  # 100ms between requests
        self.max_retries = 3
        
    async def initialize(self):
        """Initialize the Outlook API client"""
        try:
            await self._load_tokens()
            if not self.access_token:
                logger.error("No access token available. Need to authenticate.")
                return False
            
            logger.info("Outlook API initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Outlook API: {str(e)}")
            return False
    
    async def _load_tokens(self):
        """Load authentication tokens from storage"""
        try:
            token_file = os.getenv('MICROSOFT_TOKEN_FILE', 'microsoft_token.json')
            if os.path.exists(token_file):
                with open(token_file, 'r') as f:
                    token_data = json.load(f)
                    self.access_token = token_data.get('access_token')
                    self.refresh_token = token_data.get('refresh_token')
                    self.token_expires_at = token_data.get('expires_at')
                
                # Check if token needs refresh
                if self.token_expires_at and datetime.now().timestamp() >= self.token_expires_at:
                    await self._refresh_access_token()
                    
        except Exception as e:
            logger.error(f"Failed to load tokens: {str(e)}")
    
    async def _refresh_access_token(self):
        """Refresh the access token using refresh token"""
        try:
            if not self.refresh_token:
                logger.error("No refresh token available")
                return False
            
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'refresh_token': self.refresh_token,
                'grant_type': 'refresh_token'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.auth_url}/token", data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self.access_token = token_data.get('access_token')
                        if 'refresh_token' in token_data:
                            self.refresh_token = token_data['refresh_token']
                        
                        expires_in = token_data.get('expires_in', 3600)
                        self.token_expires_at = datetime.now().timestamp() + expires_in
                        
                        # Save tokens
                        await self._save_tokens()
                        
                        logger.info("Access token refreshed successfully")
                        return True
                    else:
                        logger.error(f"Failed to refresh token: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Failed to refresh access token: {str(e)}")
            return False
    
    async def _save_tokens(self):
        """Save authentication tokens to storage"""
        try:
            token_file = os.getenv('MICROSOFT_TOKEN_FILE', 'microsoft_token.json')
            token_data = {
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
                'expires_at': self.token_expires_at
            }
            
            with open(token_file, 'w') as f:
                json.dump(token_data, f)
                
        except Exception as e:
            logger.error(f"Failed to save tokens: {str(e)}")
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """Make an authenticated request to Microsoft Graph API"""
        if not self.access_token:
            await self.initialize()
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        url = f"{self.graph_url}{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                # Add rate limiting delay
                await asyncio.sleep(self.rate_limit_delay)
                
                async with aiohttp.ClientSession() as session:
                    if method.upper() == 'GET':
                        async with session.get(url, headers=headers) as response:
                            return await self._handle_response(response, attempt)
                    elif method.upper() == 'POST':
                        async with session.post(url, headers=headers, json=data) as response:
                            return await self._handle_response(response, attempt)
                    elif method.upper() == 'PATCH':
                        async with session.patch(url, headers=headers, json=data) as response:
                            return await self._handle_response(response, attempt)
                    elif method.upper() == 'DELETE':
                        async with session.delete(url, headers=headers) as response:
                            return await self._handle_response(response, attempt)
                            
            except Exception as e:
                logger.error(f"Request failed (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        
        raise Exception(f"Request failed after {self.max_retries} attempts")
    
    async def _handle_response(self, response: aiohttp.ClientResponse, attempt: int) -> Optional[Dict]:
        """Handle API response with error handling"""
        if response.status == 200 or response.status == 201:
            return await response.json()
        elif response.status == 204:  # No content (successful delete)
            return {}
        elif response.status == 401:  # Unauthorized
            logger.warning("Access token expired, refreshing...")
            if await self._refresh_access_token():
                if attempt < self.max_retries - 1:
                    return None  # Retry with new token
            raise Exception("Authentication failed")
        elif response.status == 429:  # Rate limit
            retry_after = int(response.headers.get('Retry-After', 60))
            logger.warning(f"Rate limit exceeded, waiting {retry_after}s")
            await asyncio.sleep(retry_after)
            return None  # Retry
        else:
            error_text = await response.text()
            logger.error(f"API request failed: {response.status} - {error_text}")
            raise Exception(f"API request failed: {response.status}")
    
    async def get_events(self, start_date: str, end_date: str) -> List[Event]:
        """Get events from Outlook Calendar"""
        try:
            # Format dates for Microsoft Graph API
            start_time = f"{start_date}T00:00:00Z"
            end_time = f"{end_date}T23:59:59Z"
            
            # Build query parameters
            params = f"?$filter=start/dateTime ge '{start_time}' and end/dateTime le '{end_time}'"
            params += "&$orderby=start/dateTime"
            params += "&$select=id,subject,body,start,end,location,attendees,isAllDay,isCancelled"
            
            endpoint = f"/me/events{params}"
            
            response = await self._make_request('GET', endpoint)
            
            if not response:
                return []
            
            events = response.get('value', [])
            
            # Convert to our Event model
            converted_events = []
            for event in events:
                converted_event = self._convert_outlook_event(event)
                if converted_event:
                    converted_events.append(converted_event)
            
            logger.info(f"Retrieved {len(converted_events)} events from Outlook Calendar")
            return converted_events
            
        except Exception as e:
            logger.error(f"Failed to get events: {str(e)}")
            return []
    
    def _convert_outlook_event(self, outlook_event: Dict[str, Any]) -> Optional[Event]:
        """Convert Outlook event to our Event model"""
        try:
            # Parse start time
            start_data = outlook_event.get('start', {})
            start_time = datetime.fromisoformat(
                start_data.get('dateTime', '').replace('Z', '+00:00')
            )
            
            # Parse end time
            end_data = outlook_event.get('end', {})
            end_time = datetime.fromisoformat(
                end_data.get('dateTime', '').replace('Z', '+00:00')
            )
            
            # Extract attendees
            attendees = []
            for attendee in outlook_event.get('attendees', []):
                email_address = attendee.get('emailAddress', {})
                if email_address.get('address'):
                    attendees.append(email_address['address'])
            
            # Determine status
            status = EventStatus.SCHEDULED
            if outlook_event.get('isCancelled'):
                status = EventStatus.CANCELLED
            
            # Get description
            body = outlook_event.get('body', {})
            description = body.get('content', '') if body else ''
            
            # Get location
            location_data = outlook_event.get('location', {})
            location = location_data.get('displayName', '') if location_data else ''
            
            return Event(
                event_id=outlook_event.get('id'),
                title=outlook_event.get('subject', 'Untitled Event'),
                description=description,
                start_time=start_time,
                end_time=end_time,
                location=location,
                attendees=attendees,
                calendar_provider=CalendarProvider.OUTLOOK,
                status=status
            )
            
        except Exception as e:
            logger.error(f"Failed to convert Outlook event: {str(e)}")
            return None
    
    async def create_event(self, event_data: Dict[str, Any]) -> Event:
        """Create a new event in Outlook Calendar"""
        try:
            # Convert our event data to Outlook format
            outlook_event = self._convert_to_outlook_event(event_data)
            
            # Create the event
            response = await self._make_request('POST', '/me/events', outlook_event)
            
            if not response:
                raise Exception("Failed to create event")
            
            # Convert back to our Event model
            result = self._convert_outlook_event(response)
            if result:
                logger.info(f"Created event: {result.title}")
                return result
            else:
                raise Exception("Failed to convert created event")
                
        except Exception as e:
            logger.error(f"Failed to create event: {str(e)}")
            raise
    
    def _convert_to_outlook_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert our event data to Outlook format"""
        outlook_event = {
            'subject': event_data.get('title', 'Untitled Event'),
            'body': {
                'contentType': 'text',
                'content': event_data.get('description', '')
            },
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
            outlook_event['location'] = {
                'displayName': event_data['location']
            }
        
        # Add attendees if provided
        if event_data.get('attendees'):
            outlook_event['attendees'] = [
                {
                    'emailAddress': {
                        'address': email,
                        'name': email
                    }
                }
                for email in event_data['attendees']
            ]
        
        return outlook_event
    
    async def update_event(self, event_id: str, updates: Dict[str, Any]) -> Event:
        """Update an existing event in Outlook Calendar"""
        try:
            # Convert updates to Outlook format
            outlook_updates = {}
            
            if 'title' in updates:
                outlook_updates['subject'] = updates['title']
            
            if 'description' in updates:
                outlook_updates['body'] = {
                    'contentType': 'text',
                    'content': updates['description']
                }
            
            if 'start_time' in updates:
                outlook_updates['start'] = {
                    'dateTime': updates['start_time'].isoformat(),
                    'timeZone': 'UTC'
                }
            
            if 'end_time' in updates:
                outlook_updates['end'] = {
                    'dateTime': updates['end_time'].isoformat(),
                    'timeZone': 'UTC'
                }
            
            if 'location' in updates:
                outlook_updates['location'] = {
                    'displayName': updates['location']
                }
            
            if 'attendees' in updates:
                outlook_updates['attendees'] = [
                    {
                        'emailAddress': {
                            'address': email,
                            'name': email
                        }
                    }
                    for email in updates['attendees']
                ]
            
            # Update the event
            response = await self._make_request('PATCH', f'/me/events/{event_id}', outlook_updates)
            
            if not response:
                raise Exception("Failed to update event")
            
            # Convert back to our Event model
            result = self._convert_outlook_event(response)
            if result:
                logger.info(f"Updated event: {result.title}")
                return result
            else:
                raise Exception("Failed to convert updated event")
                
        except Exception as e:
            logger.error(f"Failed to update event: {str(e)}")
            raise
    
    async def cancel_event(self, event_id: str) -> bool:
        """Cancel an event in Outlook Calendar"""
        try:
            # Delete the event
            response = await self._make_request('DELETE', f'/me/events/{event_id}')
            
            logger.info(f"Cancelled event: {event_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel event: {str(e)}")
            return False
    
    async def get_event(self, event_id: str) -> Optional[Event]:
        """Get a specific event by ID"""
        try:
            response = await self._make_request('GET', f'/me/events/{event_id}')
            
            if not response:
                return None
            
            return self._convert_outlook_event(response)
            
        except Exception as e:
            logger.error(f"Failed to get event {event_id}: {str(e)}")
            return None
    
    async def sync(self) -> int:
        """Sync calendar and return number of events processed"""
        try:
            # Get events for the next 30 days
            start_date = datetime.now().date().isoformat()
            end_date = (datetime.now().date() + timedelta(days=30)).isoformat()
            
            events = await self.get_events(start_date, end_date)
            
            # In a real implementation, you would:
            # 1. Store events in local database
            # 2. Handle incremental sync using delta queries
            # 3. Detect and handle conflicts
            
            logger.info(f"Synced {len(events)} events from Outlook Calendar")
            return len(events)
            
        except Exception as e:
            logger.error(f"Failed to sync Outlook Calendar: {str(e)}")
            return 0
    
    async def get_calendars(self) -> List[Dict[str, Any]]:
        """Get list of user's calendars"""
        try:
            response = await self._make_request('GET', '/me/calendars')
            
            if not response:
                return []
            
            calendars = response.get('value', [])
            
            # Return simplified calendar info
            return [
                {
                    'id': cal.get('id'),
                    'name': cal.get('name'),
                    'is_default': cal.get('isDefaultCalendar', False),
                    'can_edit': cal.get('canEdit', False)
                }
                for cal in calendars
            ]
            
        except Exception as e:
            logger.error(f"Failed to get calendars: {str(e)}")
            return []
    
    async def check_availability(self, start_time: datetime, end_time: datetime) -> bool:
        """Check if a time slot is available"""
        try:
            # Use the findMeetingTimes API for availability checking
            request_data = {
                'attendees': [
                    {
                        'emailAddress': {
                            'address': 'me'
                        }
                    }
                ],
                'timeConstraint': {
                    'timeslots': [
                        {
                            'start': {
                                'dateTime': start_time.isoformat(),
                                'timeZone': 'UTC'
                            },
                            'end': {
                                'dateTime': end_time.isoformat(),
                                'timeZone': 'UTC'
                            }
                        }
                    ]
                },
                'maxCandidates': 1
            }
            
            response = await self._make_request('POST', '/me/calendar/getSchedule', request_data)
            
            if not response:
                return False
            
            # Check if there are any conflicts
            schedules = response.get('value', [])
            if schedules:
                busy_times = schedules[0].get('busyTimes', [])
                return len(busy_times) == 0
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to check availability: {str(e)}")
            return False
    
    def get_auth_url(self) -> str:
        """Get the authorization URL for OAuth flow"""
        params = {
            'client_id': self.client_id,
            'response_type': 'code',
            'redirect_uri': self.redirect_uri,
            'scope': ' '.join(self.scopes),
            'response_mode': 'query'
        }
        
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return f"{self.auth_url}/authorize?{query_string}"
    
    async def exchange_code_for_tokens(self, code: str) -> bool:
        """Exchange authorization code for access tokens"""
        try:
            data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'code': code,
                'redirect_uri': self.redirect_uri,
                'grant_type': 'authorization_code'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.auth_url}/token", data=data) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self.access_token = token_data.get('access_token')
                        self.refresh_token = token_data.get('refresh_token')
                        
                        expires_in = token_data.get('expires_in', 3600)
                        self.token_expires_at = datetime.now().timestamp() + expires_in
                        
                        # Save tokens
                        await self._save_tokens()
                        
                        logger.info("Successfully exchanged code for tokens")
                        return True
                    else:
                        logger.error(f"Failed to exchange code: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Failed to exchange code for tokens: {str(e)}")
            return False 