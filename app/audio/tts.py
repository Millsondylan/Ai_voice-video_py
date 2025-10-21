from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading
import time
from typing import Optional

import pyttsx3

from app.audio.io import pause_input
from app.util.log import get_event_logger, logger as audio_logger
from app.util.sanitizer import OutputSanitizer

# Module-level lock for audio output serialization
audio_out_lock = threading.Lock()

# Try to import ElevenLabs (optional dependency)
try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import play
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    ElevenLabs = None
    play = None

logger = logging.getLogger(__name__)


class SpeechSynthesizer:
    """
    Hybrid TTS system with ElevenLabs (cloud) and pyttsx3 (local) fallback.

    Provides reliable text-to-speech with automatic fallback:
    1. Try ElevenLabs (high quality, requires API key and internet)
    2. Fallback to pyttsx3 (offline, lower quality but always available)
    3. Final fallback to platform commands (say/espeak)
    """

    def __init__(
        self,
        voice: Optional[str] = None,
        rate: Optional[int] = None,
        elevenlabs_api_key: Optional[str] = None,
        prefer_cloud: bool = False,
    ) -> None:
        self._driver_name = "nsss" if platform.system() == "Darwin" else None
        self._voice = voice
        self._rate = rate
        self._engine = self._create_engine()
        self._lock = threading.Lock()
        self._current_thread: Optional[threading.Thread] = None
        self._turn_index = 0

        # ElevenLabs setup
        self._elevenlabs_client = None
        self._prefer_cloud = prefer_cloud
        if ELEVENLABS_AVAILABLE:
            api_key = elevenlabs_api_key or os.getenv('ELEVENLABS_API_KEY')
            if api_key:
                try:
                    self._elevenlabs_client = ElevenLabs(api_key=api_key)
                    logger.info("ElevenLabs TTS initialized successfully")
                except Exception as e:
                    logger.warning(f"ElevenLabs initialization failed: {e}")
            else:
                logger.info("ElevenLabs API key not provided, using pyttsx3 only")
        else:
            logger.info("ElevenLabs not available, using pyttsx3 only")

    def _create_engine(self):
        engine = pyttsx3.init(driverName=self._driver_name) if self._driver_name else pyttsx3.init()
        if self._voice:
            try:
                engine.setProperty("voice", self._voice)
            except Exception:
                pass
        if self._rate:
            try:
                engine.setProperty("rate", self._rate)
            except Exception:
                pass
        return engine

    def _reinitialize_engine(self) -> None:
        self._engine = self._create_engine()

    def set_turn_index(self, turn_index: int):
        """Set current turn index for logging."""
        self._turn_index = turn_index

    def speak(self, text: str) -> None:
        """
        Speak text with hybrid cloud/local TTS and guaranteed output.

        FIX: VOICE REPLY FLOW with multiple layers of reliability:
        1. Sanitize output to remove debug artifacts (prevents speaking test phrases)
        2. Try ElevenLabs if available and preferred
        3. Fallback to pyttsx3 with retry mechanism
        4. Final fallback to platform commands
        5. Proper microphone muting to prevent echo/feedback

        Microphone muting flow:
        - Pause microphone input BEFORE speaking
        - Resume microphone input AFTER speaking
        - Grace period (150ms) after TTS to avoid tail echo
        """
        # FIX: SANITIZE OUTPUT - Remove any debug artifacts before TTS
        clean_text = OutputSanitizer.sanitize_for_tts(text)
        if not clean_text:
            logger.warning("Text sanitization resulted in empty output, using fallback")
            clean_text = "Sorry, I didn't catch that."

        # Validate output is clean
        if not OutputSanitizer.validate_tts_output(clean_text):
            logger.error(f"TTS output validation failed for: {clean_text[:100]}")
            clean_text = "Sorry, there was an error."

        msg = clean_text.strip()
        event_logger = get_event_logger()
        start_ts = time.monotonic()

        # FIX: MICROPHONE MUTING - Pause input during TTS to prevent echo/feedback
        pause_input(True)

        try:
            event_logger.log_tts_started(msg)

            # Try ElevenLabs first if preferred and available
            if self._prefer_cloud and self._elevenlabs_client:
                if self._speak_elevenlabs(msg):
                    duration_ms = int((time.monotonic() - start_ts) * 1000)
                    event_logger.log_tts_done()
                    audio_logger.info(f"ElevenLabs TTS completed in {duration_ms}ms")
                    return

            # Fallback to pyttsx3 (or if cloud not preferred)
            self._speak_pyttsx3(msg, event_logger)

        finally:
            # FIX: GRACE PERIOD - Add 150ms delay before resuming mic to avoid tail echo
            time.sleep(0.15)
            # FIX: MICROPHONE UNMUTING - Resume input for next user utterance
            pause_input(False)

    def _speak_elevenlabs(self, text: str, retries: int = 2) -> bool:
        """
        Speak using ElevenLabs TTS with retry logic.

        Returns:
            True if successful, False if failed
        """
        if not self._elevenlabs_client:
            return False

        for attempt in range(retries):
            try:
                audio = self._elevenlabs_client.text_to_speech.convert(
                    text=text,
                    voice_id=os.getenv('ELEVENLABS_VOICE_ID', 'JBFqnCBsd6RMkjVDRZzb'),
                    model_id="eleven_multilingual_v2"
                )
                play(audio)
                logger.info(f"ElevenLabs spoke: '{text[:50]}'")
                return True

            except Exception as e:
                logger.warning(f"ElevenLabs attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(1.0 * (attempt + 1))  # Exponential backoff

        return False

    def _speak_pyttsx3(self, msg: str, event_logger) -> None:
        """Speak using pyttsx3 with retry mechanism."""
        start_ts = time.monotonic()

        try:
            with audio_out_lock:
                with self._lock:
                    if self._engine is None:
                        self._reinitialize_engine()
                    # Clear any queued speech before starting
                    try:
                        self._engine.stop()
                    except Exception:
                        pass  # Ignore stop errors

                    self._engine.say(msg)
                    self._engine.runAndWait()

            duration_ms = int((time.monotonic() - start_ts) * 1000)
            event_logger.log_tts_done()
            audio_logger.info(f"pyttsx3 TTS completed in {duration_ms}ms")

        except Exception as e:
            event_logger.log_tts_error(str(e), retry=True)
            audio_logger.warning(f"pyttsx3 failed, retrying: {e}")
            time.sleep(0.25)  # Brief pause before retry

            try:
                with audio_out_lock:
                    with self._lock:
                        # Force reinitialization on error
                        self._reinitialize_engine()
                        self._engine.stop()
                        self._engine.say(msg)
                        self._engine.runAndWait()

                duration_ms = int((time.monotonic() - start_ts) * 1000)
                event_logger.log_tts_done()
                audio_logger.info(f"pyttsx3 retry succeeded in {duration_ms}ms")

            except Exception as e2:
                event_logger.log_tts_error(str(e2), retry=False)
                audio_logger.error(f"pyttsx3 retry failed, using platform fallback: {e2}")
                # Final fallback to platform command
                self._fallback_say(msg)

    def speak_async(self, text: str) -> threading.Thread:
        """Speak text asynchronously in a background thread."""
        if self._current_thread and self._current_thread.is_alive():
            try:
                with self._lock:
                    self._engine.stop()
            except Exception:
                pass  # Ignore stop errors
            self._current_thread.join(timeout=2.0)

        thread = threading.Thread(target=self.speak, args=(text,), daemon=True)
        self._current_thread = thread
        thread.start()
        return thread

    def _fallback_say(self, text: str) -> None:
        """Fallback to platform speech command if pyttsx3 fails."""
        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.run(["say", text], check=False)
            elif system == "Linux":
                subprocess.run(["espeak", text], check=False)
        except Exception:
            pass
