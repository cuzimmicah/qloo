import asyncio
import logging
import os
import tempfile
import time
from typing import Optional, Dict, Any, List
import io

import speech_recognition as sr
from openai import AsyncOpenAI
import aiofiles

logger = logging.getLogger(__name__)

class VoiceTranscriber:
    """Voice transcription service supporting multiple providers"""
    
    def __init__(self):
        self.openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.recognizer = sr.Recognizer()
        
        # Supported audio formats
        self.supported_formats = [
            'wav', 'mp3', 'mp4', 'm4a', 'ogg', 'flac', 'webm'
        ]
        
        # Provider preference order
        self.providers = ['openai_whisper', 'google', 'azure', 'fallback']
        
        # Configuration
        self.max_file_size = 25 * 1024 * 1024  # 25MB limit for OpenAI
        self.chunk_duration = 30  # seconds for long audio files
        
    async def transcribe(
        self, 
        audio_data: bytes, 
        format: str = "wav",
        language: str = "en",
        provider: Optional[str] = None
    ) -> str:
        """Transcribe audio data to text"""
        try:
            # Validate input
            if len(audio_data) > self.max_file_size:
                return await self._transcribe_large_file(audio_data, format, language)
            
            # Use specified provider or try in order
            providers_to_try = [provider] if provider else self.providers
            
            for provider_name in providers_to_try:
                try:
                    if provider_name == 'openai_whisper':
                        result = await self._transcribe_openai_whisper(audio_data, format, language)
                    elif provider_name == 'google':
                        result = await self._transcribe_google(audio_data, format, language)
                    elif provider_name == 'azure':
                        result = await self._transcribe_azure(audio_data, format, language)
                    elif provider_name == 'fallback':
                        result = await self._transcribe_fallback(audio_data, format, language)
                    else:
                        continue
                    
                    if result:
                        logger.info(f"Successfully transcribed using {provider_name}")
                        return result
                        
                except Exception as e:
                    logger.warning(f"Transcription failed with {provider_name}: {str(e)}")
                    continue
            
            # If all providers fail
            logger.error("All transcription providers failed")
            return "Sorry, I couldn't understand the audio. Please try again."
            
        except Exception as e:
            logger.error(f"Transcription error: {str(e)}")
            return "Sorry, there was an error processing your audio."
    
    async def _transcribe_openai_whisper(
        self, 
        audio_data: bytes, 
        format: str, 
        language: str
    ) -> Optional[str]:
        """Transcribe using OpenAI Whisper API"""
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as temp_file:
                temp_file.write(audio_data)
                temp_file_path = temp_file.name
            
            try:
                # Open file for Whisper API
                with open(temp_file_path, "rb") as audio_file:
                    transcript = await self.openai_client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language=language if language != "auto" else None,
                        response_format="text"
                    )
                
                return transcript.strip() if transcript else None
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
                    
        except Exception as e:
            logger.error(f"OpenAI Whisper transcription failed: {str(e)}")
            return None
    
    async def _transcribe_google(
        self, 
        audio_data: bytes, 
        format: str, 
        language: str
    ) -> Optional[str]:
        """Transcribe using Google Speech-to-Text"""
        try:
            # Convert audio data to AudioData object
            audio_source = sr.AudioData(audio_data, 16000, 2)  # Assuming 16kHz, 16-bit
            
            # Use Google Speech Recognition
            result = self.recognizer.recognize_google(
                audio_source, 
                language=language if language != "auto" else "en-US"
            )
            
            return result.strip() if result else None
            
        except sr.UnknownValueError:
            logger.warning("Google Speech Recognition could not understand audio")
            return None
        except sr.RequestError as e:
            logger.error(f"Google Speech Recognition error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Google transcription failed: {str(e)}")
            return None
    
    async def _transcribe_azure(
        self, 
        audio_data: bytes, 
        format: str, 
        language: str
    ) -> Optional[str]:
        """Transcribe using Azure Speech Service"""
        try:
            # Azure Speech SDK implementation would go here
            # For now, return None to fall back to other providers
            logger.info("Azure Speech Service not implemented yet")
            return None
            
        except Exception as e:
            logger.error(f"Azure transcription failed: {str(e)}")
            return None
    
    async def _transcribe_fallback(
        self, 
        audio_data: bytes, 
        format: str, 
        language: str
    ) -> Optional[str]:
        """Fallback transcription using built-in speech recognition"""
        try:
            # Use the built-in speech recognition as last resort
            with tempfile.NamedTemporaryFile(suffix=f".{format}") as temp_file:
                temp_file.write(audio_data)
                temp_file.flush()
                
                # Load audio file
                with sr.AudioFile(temp_file.name) as source:
                    audio = self.recognizer.record(source)
                
                # Try to recognize
                result = self.recognizer.recognize_sphinx(audio)
                return result.strip() if result else None
                
        except Exception as e:
            logger.error(f"Fallback transcription failed: {str(e)}")
            return None
    
    async def _transcribe_large_file(
        self, 
        audio_data: bytes, 
        format: str, 
        language: str
    ) -> str:
        """Handle large audio files by chunking"""
        try:
            # For large files, we would need to:
            # 1. Split audio into chunks
            # 2. Transcribe each chunk
            # 3. Combine results
            
            # This is a simplified implementation
            logger.warning("Large file transcription not fully implemented")
            
            # Try to transcribe first part only
            chunk_size = self.max_file_size // 2
            first_chunk = audio_data[:chunk_size]
            
            result = await self.transcribe(first_chunk, format, language)
            
            if len(audio_data) > chunk_size:
                result += " [Audio truncated due to size limit]"
            
            return result
            
        except Exception as e:
            logger.error(f"Large file transcription failed: {str(e)}")
            return "Sorry, the audio file is too large to process."
    
    async def transcribe_with_confidence(
        self, 
        audio_data: bytes, 
        format: str = "wav",
        language: str = "en"
    ) -> Dict[str, Any]:
        """Transcribe audio and return result with confidence score"""
        start_time = time.time()
        
        try:
            # Get transcription
            text = await self.transcribe(audio_data, format, language)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Estimate confidence based on text length and processing time
            # This is a simplified confidence calculation
            confidence = 0.9 if len(text) > 10 else 0.7
            
            # Check for common transcription errors
            if "sorry" in text.lower() or "error" in text.lower():
                confidence = 0.3
            
            return {
                "text": text,
                "confidence": confidence,
                "processing_time": processing_time,
                "language": language,
                "alternatives": []  # Could be populated by provider-specific results
            }
            
        except Exception as e:
            logger.error(f"Transcription with confidence failed: {str(e)}")
            return {
                "text": "Sorry, transcription failed.",
                "confidence": 0.0,
                "processing_time": time.time() - start_time,
                "language": language,
                "alternatives": []
            }
    
    async def batch_transcribe(
        self, 
        audio_files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Transcribe multiple audio files in batch"""
        try:
            tasks = []
            for audio_file in audio_files:
                task = self.transcribe_with_confidence(
                    audio_file["data"],
                    audio_file.get("format", "wav"),
                    audio_file.get("language", "en")
                )
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    processed_results.append({
                        "text": "Transcription failed",
                        "confidence": 0.0,
                        "processing_time": 0.0,
                        "language": audio_files[i].get("language", "en"),
                        "alternatives": [],
                        "error": str(result)
                    })
                else:
                    processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"Batch transcription failed: {str(e)}")
            return []
    
    def get_supported_formats(self) -> List[str]:
        """Get list of supported audio formats"""
        return self.supported_formats.copy()
    
    def validate_audio_format(self, format: str) -> bool:
        """Validate if audio format is supported"""
        return format.lower() in self.supported_formats
    
    def estimate_transcription_time(self, file_size: int) -> float:
        """Estimate transcription time based on file size"""
        # Rough estimate: 1MB takes about 2 seconds to transcribe
        return (file_size / (1024 * 1024)) * 2
    
    async def get_transcription_quality(self, text: str) -> Dict[str, Any]:
        """Analyze transcription quality"""
        try:
            # Simple quality metrics
            word_count = len(text.split())
            char_count = len(text)
            
            # Check for common transcription issues
            issues = []
            if word_count < 3:
                issues.append("Very short transcription")
            
            if text.count("um") > word_count * 0.1:
                issues.append("Many filler words detected")
            
            if text.count("[") > 0 or text.count("(") > 0:
                issues.append("Unclear audio sections detected")
            
            # Calculate quality score
            quality_score = 1.0
            if issues:
                quality_score = max(0.3, 1.0 - (len(issues) * 0.2))
            
            return {
                "quality_score": quality_score,
                "word_count": word_count,
                "character_count": char_count,
                "issues": issues,
                "readability": "good" if quality_score > 0.7 else "fair" if quality_score > 0.4 else "poor"
            }
            
        except Exception as e:
            logger.error(f"Quality analysis failed: {str(e)}")
            return {
                "quality_score": 0.5,
                "word_count": 0,
                "character_count": 0,
                "issues": ["Analysis failed"],
                "readability": "unknown"
            } 