import json
import os
import time
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import asyncio
import logging

from openai import AsyncOpenAI
from shared.models import (
    IntentResponse, IntentType, IntentEntity, UserContext, 
    IntentRequest, UserPreferences
)

logger = logging.getLogger(__name__)

class IntentParser:
    """GPT-4 based intent parser for scheduling requests"""
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.model = "gpt-4"
        self.max_tokens = 1000
        self.temperature = 0.1  # Low temperature for consistent parsing
        
        # Load the prompt template
        self.prompt_template = self._load_prompt_template()
        
    def _load_prompt_template(self) -> str:
        """Load the intent parsing prompt template"""
        try:
            with open("nlp/prompts/intent_prompt.txt", "r") as f:
                return f.read()
        except FileNotFoundError:
            logger.error("Intent prompt template not found")
            return self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """Default prompt if template file is not found"""
        return """
        You are a scheduling assistant. Parse the following request and return a JSON response with:
        - intent_type: one of schedule_event, get_schedule, reschedule_event, cancel_event, update_event, check_availability, set_reminder, unknown
        - confidence: float between 0.0 and 1.0
        - entities: dict with extracted information
        - requires_clarification: boolean
        - clarification_question: string if clarification needed
        
        Request: "{user_request}"
        """
    
    async def parse_intent(
        self, 
        text: str, 
        user_context: Optional[UserContext] = None
    ) -> IntentResponse:
        """Parse natural language intent for scheduling"""
        start_time = time.time()
        
        try:
            # Prepare context information
            context_info = self._prepare_context(user_context)
            
            # Format the prompt with context and user request
            formatted_prompt = self.prompt_template.format(
                user_timezone=context_info.get("timezone", "UTC"),
                current_datetime=datetime.now(timezone.utc).isoformat(),
                user_preferences=json.dumps(context_info.get("preferences", {})),
                existing_events=json.dumps(context_info.get("existing_events", [])),
                user_request=text
            )
            
            # Call GPT-4
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert scheduling assistant. Always respond with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": formatted_prompt
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            
            # Parse GPT-4 response
            gpt_response = response.choices[0].message.content
            parsed_response = self._parse_gpt_response(gpt_response)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Create IntentResponse object
            intent_response = IntentResponse(
                intent_type=IntentType(parsed_response.get("intent_type", "unknown")),
                confidence=parsed_response.get("confidence", 0.0),
                entities=parsed_response.get("entities", {}),
                extracted_entities=self._create_entity_objects(
                    parsed_response.get("extracted_entities", [])
                ),
                requires_clarification=parsed_response.get("requires_clarification", False),
                clarification_question=parsed_response.get("clarification_question"),
                processing_time=processing_time
            )
            
            # Post-process and validate
            intent_response = self._post_process_response(intent_response, user_context)
            
            return intent_response
            
        except Exception as e:
            logger.error(f"Intent parsing failed: {str(e)}")
            processing_time = time.time() - start_time
            
            # Return fallback response
            return IntentResponse(
                intent_type=IntentType.UNKNOWN,
                confidence=0.0,
                entities={},
                extracted_entities=[],
                requires_clarification=True,
                clarification_question="I'm sorry, I couldn't understand your request. Could you please rephrase it?",
                processing_time=processing_time
            )
    
    def _prepare_context(self, user_context: Optional[UserContext]) -> Dict[str, Any]:
        """Prepare context information for the prompt"""
        if not user_context:
            return {
                "timezone": "UTC",
                "preferences": {},
                "existing_events": []
            }
        
        return {
            "timezone": user_context.current_timezone,
            "preferences": {
                "preferred_meeting_duration": user_context.preferences.preferred_meeting_duration,
                "work_start_time": user_context.preferences.work_start_time.isoformat(),
                "work_end_time": user_context.preferences.work_end_time.isoformat(),
                "buffer_time": user_context.preferences.buffer_time,
                "preferred_calendar": user_context.preferences.preferred_calendar.value
            },
            "existing_events": user_context.existing_events
        }
    
    def _parse_gpt_response(self, gpt_response: str) -> Dict[str, Any]:
        """Parse GPT-4 JSON response"""
        try:
            # Clean the response (remove code blocks if present)
            cleaned_response = gpt_response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:-3]
            elif cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:-3]
            
            return json.loads(cleaned_response)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse GPT response as JSON: {e}")
            logger.error(f"Response was: {gpt_response}")
            
            # Try to extract intent type from text if JSON parsing fails
            return self._extract_fallback_intent(gpt_response)
    
    def _extract_fallback_intent(self, response: str) -> Dict[str, Any]:
        """Extract basic intent if JSON parsing fails"""
        response_lower = response.lower()
        
        # Simple keyword matching as fallback
        if any(word in response_lower for word in ["schedule", "create", "book", "set up"]):
            intent_type = "schedule_event"
        elif any(word in response_lower for word in ["what", "show", "list", "get"]):
            intent_type = "get_schedule"
        elif any(word in response_lower for word in ["reschedule", "move", "change time"]):
            intent_type = "reschedule_event"
        elif any(word in response_lower for word in ["cancel", "delete", "remove"]):
            intent_type = "cancel_event"
        elif any(word in response_lower for word in ["update", "modify", "edit"]):
            intent_type = "update_event"
        elif any(word in response_lower for word in ["available", "free", "open"]):
            intent_type = "check_availability"
        elif any(word in response_lower for word in ["remind", "reminder", "alert"]):
            intent_type = "set_reminder"
        else:
            intent_type = "unknown"
        
        return {
            "intent_type": intent_type,
            "confidence": 0.5,
            "entities": {},
            "extracted_entities": [],
            "requires_clarification": True,
            "clarification_question": "I had trouble understanding your request. Could you please be more specific?"
        }
    
    def _create_entity_objects(self, entities_data: List[Dict[str, Any]]) -> List[IntentEntity]:
        """Create IntentEntity objects from parsed data"""
        entities = []
        
        for entity_data in entities_data:
            try:
                entity = IntentEntity(
                    entity_type=entity_data.get("entity_type", ""),
                    value=entity_data.get("value", ""),
                    confidence=entity_data.get("confidence", 0.0),
                    start_pos=entity_data.get("start_pos"),
                    end_pos=entity_data.get("end_pos")
                )
                entities.append(entity)
            except Exception as e:
                logger.warning(f"Failed to create entity object: {e}")
                continue
        
        return entities
    
    def _post_process_response(
        self, 
        response: IntentResponse, 
        user_context: Optional[UserContext]
    ) -> IntentResponse:
        """Post-process the intent response for validation and enhancement"""
        
        # Validate time entities
        response.entities = self._validate_time_entities(response.entities)
        
        # Add missing default values based on user context
        if user_context:
            response.entities = self._add_default_values(response.entities, user_context)
        
        # Validate confidence score
        if response.confidence < 0.0:
            response.confidence = 0.0
        elif response.confidence > 1.0:
            response.confidence = 1.0
        
        return response
    
    def _validate_time_entities(self, entities: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and format time-related entities"""
        validated_entities = entities.copy()
        
        # Validate start_time
        if "start_time" in entities:
            try:
                # Ensure it's a valid datetime string
                if isinstance(entities["start_time"], str):
                    datetime.fromisoformat(entities["start_time"].replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"Invalid start_time format: {entities['start_time']}")
                del validated_entities["start_time"]
        
        # Validate end_time
        if "end_time" in entities:
            try:
                if isinstance(entities["end_time"], str):
                    datetime.fromisoformat(entities["end_time"].replace("Z", "+00:00"))
            except ValueError:
                logger.warning(f"Invalid end_time format: {entities['end_time']}")
                del validated_entities["end_time"]
        
        # Validate duration
        if "duration" in entities:
            try:
                duration = int(entities["duration"])
                if duration <= 0:
                    validated_entities["duration"] = 60  # Default to 60 minutes
                else:
                    validated_entities["duration"] = duration
            except (ValueError, TypeError):
                validated_entities["duration"] = 60
        
        return validated_entities
    
    def _add_default_values(
        self, 
        entities: Dict[str, Any], 
        user_context: UserContext
    ) -> Dict[str, Any]:
        """Add default values based on user context"""
        enhanced_entities = entities.copy()
        
        # Add default duration if not specified
        if "duration" not in enhanced_entities and "end_time" not in enhanced_entities:
            enhanced_entities["duration"] = user_context.preferences.preferred_meeting_duration
        
        # Add default calendar provider
        if "calendar_provider" not in enhanced_entities:
            enhanced_entities["calendar_provider"] = user_context.preferences.preferred_calendar.value
        
        return enhanced_entities
    
    async def parse_batch_intents(
        self, 
        texts: List[str], 
        user_context: Optional[UserContext] = None
    ) -> List[IntentResponse]:
        """Parse multiple intents in batch"""
        tasks = [self.parse_intent(text, user_context) for text in texts]
        return await asyncio.gather(*tasks)
    
    def get_supported_intents(self) -> List[str]:
        """Get list of supported intent types"""
        return [intent.value for intent in IntentType]
    
    def get_supported_entities(self) -> List[str]:
        """Get list of supported entity types"""
        return [
            "title", "start_time", "end_time", "duration", "date", "location",
            "attendees", "description", "reminder_minutes", "recurrence", "priority"
        ] 