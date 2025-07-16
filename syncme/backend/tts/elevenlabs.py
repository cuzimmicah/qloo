import asyncio
import logging
import os
import tempfile
import time
import uuid
from typing import Optional, Dict, Any, List
import aiohttp
import aiofiles

logger = logging.getLogger(__name__)

class TextToSpeech:
    """ElevenLabs Text-to-Speech integration"""
    
    def __init__(self):
        self.api_key = os.getenv("ELEVENLABS_API_KEY")
        self.base_url = "https://api.elevenlabs.io/v1"
        
        # Default voice settings
        self.default_voice_id = os.getenv("ELEVENLABS_DEFAULT_VOICE", "21m00Tcm4TlvDq8ikWAM")  # Rachel
        self.default_model = "eleven_monolingual_v1"
        
        # Voice settings
        self.voice_settings = {
            "stability": 0.75,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True
        }
        
        # Rate limiting
        self.rate_limit_delay = 0.1
        self.max_retries = 3
        
        # Audio storage
        self.audio_storage_path = os.getenv("AUDIO_STORAGE_PATH", "temp_audio")
        os.makedirs(self.audio_storage_path, exist_ok=True)
        
        # Cache for voice list
        self._voice_cache = None
        self._voice_cache_time = 0
        self._voice_cache_ttl = 3600  # 1 hour
    
    async def generate_speech(
        self, 
        text: str, 
        voice_id: Optional[str] = None,
        model: Optional[str] = None,
        voice_settings: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Generate speech from text"""
        try:
            if not self.api_key:
                raise Exception("ElevenLabs API key not configured")
            
            # Use defaults if not specified
            voice_id = voice_id or self.default_voice_id
            model = model or self.default_model
            voice_settings = voice_settings or self.voice_settings
            
            # Validate text length
            if len(text) > 5000:
                raise Exception("Text too long (max 5000 characters)")
            
            # Generate unique file ID
            file_id = str(uuid.uuid4())
            
            # Make API request
            audio_data = await self._make_tts_request(text, voice_id, model, voice_settings)
            
            # Save audio file
            file_path = os.path.join(self.audio_storage_path, f"{file_id}.mp3")
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(audio_data)
            
            # Calculate duration (rough estimate)
            duration = self._estimate_audio_duration(text)
            
            # Get file size
            file_size = len(audio_data)
            
            logger.info(f"Generated speech for {len(text)} characters")
            
            return {
                "file_id": file_id,
                "file_path": file_path,
                "duration": duration,
                "file_size": file_size,
                "voice_id": voice_id,
                "text_length": len(text)
            }
            
        except Exception as e:
            logger.error(f"TTS generation failed: {str(e)}")
            raise
    
    async def _make_tts_request(
        self, 
        text: str, 
        voice_id: str, 
        model: str, 
        voice_settings: Dict[str, Any]
    ) -> bytes:
        """Make TTS API request"""
        url = f"{self.base_url}/text-to-speech/{voice_id}"
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        
        data = {
            "text": text,
            "model_id": model,
            "voice_settings": voice_settings
        }
        
        for attempt in range(self.max_retries):
            try:
                # Rate limiting
                await asyncio.sleep(self.rate_limit_delay)
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=data) as response:
                        if response.status == 200:
                            return await response.read()
                        elif response.status == 429:  # Rate limit
                            wait_time = min(2 ** attempt, 60)
                            logger.warning(f"Rate limit hit, waiting {wait_time}s")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            error_text = await response.text()
                            logger.error(f"TTS API error {response.status}: {error_text}")
                            raise Exception(f"TTS API error: {response.status}")
                            
            except Exception as e:
                logger.error(f"TTS request failed (attempt {attempt + 1}): {str(e)}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
        
        raise Exception(f"TTS request failed after {self.max_retries} attempts")
    
    def _estimate_audio_duration(self, text: str) -> float:
        """Estimate audio duration based on text length"""
        # Rough estimate: 150 words per minute, average 5 characters per word
        words = len(text) / 5
        minutes = words / 150
        return minutes * 60  # Convert to seconds
    
    async def get_voices(self) -> List[Dict[str, Any]]:
        """Get available voices from ElevenLabs"""
        try:
            # Check cache
            current_time = time.time()
            if (self._voice_cache and 
                current_time - self._voice_cache_time < self._voice_cache_ttl):
                return self._voice_cache
            
            if not self.api_key:
                return []
            
            url = f"{self.base_url}/voices"
            headers = {
                "Accept": "application/json",
                "xi-api-key": self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        voices = data.get("voices", [])
                        
                        # Process voice data
                        processed_voices = []
                        for voice in voices:
                            processed_voices.append({
                                "voice_id": voice.get("voice_id"),
                                "name": voice.get("name"),
                                "category": voice.get("category"),
                                "description": voice.get("description"),
                                "use_case": voice.get("use_case"),
                                "accent": voice.get("accent"),
                                "age": voice.get("age"),
                                "gender": voice.get("gender"),
                                "preview_url": voice.get("preview_url")
                            })
                        
                        # Update cache
                        self._voice_cache = processed_voices
                        self._voice_cache_time = current_time
                        
                        return processed_voices
                    else:
                        logger.error(f"Failed to get voices: {response.status}")
                        return []
                        
        except Exception as e:
            logger.error(f"Failed to get voices: {str(e)}")
            return []
    
    async def get_voice_settings(self, voice_id: str) -> Dict[str, Any]:
        """Get voice settings for a specific voice"""
        try:
            if not self.api_key:
                return {}
            
            url = f"{self.base_url}/voices/{voice_id}/settings"
            headers = {
                "Accept": "application/json",
                "xi-api-key": self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Failed to get voice settings: {response.status}")
                        return {}
                        
        except Exception as e:
            logger.error(f"Failed to get voice settings: {str(e)}")
            return {}
    
    async def clone_voice(
        self, 
        name: str, 
        audio_files: List[bytes], 
        description: Optional[str] = None
    ) -> Optional[str]:
        """Clone a voice from audio samples"""
        try:
            if not self.api_key:
                raise Exception("ElevenLabs API key not configured")
            
            url = f"{self.base_url}/voices/add"
            headers = {
                "Accept": "application/json",
                "xi-api-key": self.api_key
            }
            
            # Prepare multipart form data
            form_data = aiohttp.FormData()
            form_data.add_field("name", name)
            if description:
                form_data.add_field("description", description)
            
            # Add audio files
            for i, audio_data in enumerate(audio_files):
                form_data.add_field(
                    "files", 
                    audio_data, 
                    filename=f"sample_{i}.mp3",
                    content_type="audio/mpeg"
                )
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=form_data) as response:
                    if response.status == 200:
                        data = await response.json()
                        voice_id = data.get("voice_id")
                        logger.info(f"Voice cloned successfully: {voice_id}")
                        return voice_id
                    else:
                        error_text = await response.text()
                        logger.error(f"Voice cloning failed: {response.status} - {error_text}")
                        return None
                        
        except Exception as e:
            logger.error(f"Voice cloning failed: {str(e)}")
            return None
    
    async def delete_voice(self, voice_id: str) -> bool:
        """Delete a cloned voice"""
        try:
            if not self.api_key:
                return False
            
            url = f"{self.base_url}/voices/{voice_id}"
            headers = {
                "Accept": "application/json",
                "xi-api-key": self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.delete(url, headers=headers) as response:
                    if response.status == 200:
                        logger.info(f"Voice deleted: {voice_id}")
                        return True
                    else:
                        logger.error(f"Failed to delete voice: {response.status}")
                        return False
                        
        except Exception as e:
            logger.error(f"Failed to delete voice: {str(e)}")
            return False
    
    async def get_audio_file(self, file_id: str) -> Optional[bytes]:
        """Get audio file by ID"""
        try:
            file_path = os.path.join(self.audio_storage_path, f"{file_id}.mp3")
            
            if not os.path.exists(file_path):
                logger.warning(f"Audio file not found: {file_id}")
                return None
            
            async with aiofiles.open(file_path, "rb") as f:
                return await f.read()
                
        except Exception as e:
            logger.error(f"Failed to get audio file: {str(e)}")
            return None
    
    async def delete_audio_file(self, file_id: str) -> bool:
        """Delete audio file"""
        try:
            file_path = os.path.join(self.audio_storage_path, f"{file_id}.mp3")
            
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Audio file deleted: {file_id}")
                return True
            else:
                logger.warning(f"Audio file not found: {file_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete audio file: {str(e)}")
            return False
    
    async def batch_generate_speech(
        self, 
        texts: List[str], 
        voice_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Generate speech for multiple texts"""
        try:
            tasks = []
            for text in texts:
                task = self.generate_speech(text, voice_id)
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append({
                        "error": str(result),
                        "text": texts[i]
                    })
                else:
                    processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Batch TTS generation failed: {str(e)}")
            return []
    
    async def get_usage_stats(self) -> Dict[str, Any]:
        """Get API usage statistics"""
        try:
            if not self.api_key:
                return {}
            
            url = f"{self.base_url}/user"
            headers = {
                "Accept": "application/json",
                "xi-api-key": self.api_key
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "character_count": data.get("subscription", {}).get("character_count", 0),
                            "character_limit": data.get("subscription", {}).get("character_limit", 0),
                            "can_extend_character_limit": data.get("subscription", {}).get("can_extend_character_limit", False),
                            "allowed_to_extend_character_limit": data.get("subscription", {}).get("allowed_to_extend_character_limit", False),
                            "next_character_count_reset_unix": data.get("subscription", {}).get("next_character_count_reset_unix", 0)
                        }
                    else:
                        logger.error(f"Failed to get usage stats: {response.status}")
                        return {}
                        
        except Exception as e:
            logger.error(f"Failed to get usage stats: {str(e)}")
            return {}
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """Clean up old audio files"""
        try:
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            for filename in os.listdir(self.audio_storage_path):
                file_path = os.path.join(self.audio_storage_path, filename)
                
                if os.path.isfile(file_path):
                    file_age = current_time - os.path.getmtime(file_path)
                    
                    if file_age > max_age_seconds:
                        os.remove(file_path)
                        logger.info(f"Cleaned up old audio file: {filename}")
                        
        except Exception as e:
            logger.error(f"Failed to cleanup old files: {str(e)}")
    
    async def get_recommended_voice(self, text: str, use_case: str = "general") -> Optional[str]:
        """Get recommended voice based on text and use case"""
        try:
            voices = await self.get_voices()
            
            if not voices:
                return self.default_voice_id
            
            # Simple recommendation logic
            if use_case == "professional":
                # Prefer professional voices
                for voice in voices:
                    if voice.get("category") == "professional":
                        return voice["voice_id"]
            elif use_case == "casual":
                # Prefer conversational voices
                for voice in voices:
                    if voice.get("category") == "conversational":
                        return voice["voice_id"]
            elif use_case == "narrative":
                # Prefer narrative voices
                for voice in voices:
                    if voice.get("use_case") == "narration":
                        return voice["voice_id"]
            
            # Default to first available voice or default
            return voices[0]["voice_id"] if voices else self.default_voice_id
            
        except Exception as e:
            logger.error(f"Failed to get recommended voice: {str(e)}")
            return self.default_voice_id 