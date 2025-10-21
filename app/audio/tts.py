from __future__ import annotations

import platform
import subprocess
import threading
import time
from typing import Optional

import pyttsx3

from app.audio.io import pause_input
from app.util.log import get_event_logger, logger as audio_logger

# Module-level lock for audio output serialization
audio_out_lock = threading.Lock()


class SpeechSynthesizer:
    """Manage text-to-speech playback via pyttsx3 with macOS/Windows/Linux support."""

    def __init__(self, voice: Optional[str] = None, rate: Optional[int] = None) -> None:
        self._driver_name = "nsss" if platform.system() == "Darwin" else None
        self._voice = voice
        self._rate = rate
        self._engine = self._create_engine()
        self._lock = threading.Lock()
        self._current_thread: Optional[threading.Thread] = None
        self._turn_index = 0

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
        """Speak text with guaranteed output (lock + retry mechanism) and mic muting.

        FIX: VOICE REPLY FLOW - Proper microphone muting ensures clean conversation flow:
        - FIX: Pause microphone input BEFORE speaking (pause_input(True) on line 65)
        - FIX: Resume microphone input AFTER speaking (pause_input(False) on line 114)
        - FIX: Grace period (150ms) after TTS to avoid tail echo (line 113)
        - Global audio lock to prevent overlapping TTS
        - Automatic retry with engine reinitialization
        - Fallback to platform-specific commands

        This prevents the system from picking up its own voice output as user input,
        and ensures the mic is ready to hear the user's next utterance after TTS completes.
        """
        msg = text.strip() or "Sorry, I didn't catch that."
        logger = get_event_logger()
        start_ts = time.monotonic()

        # FIX: MICROPHONE MUTING - Pause input during TTS to prevent echo/feedback
        # This stops the system from capturing its own voice as user input
        pause_input(True)

        try:
            logger.log_tts_started(msg)

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
            logger.log_tts_done()
            audio_logger.info(f"TTS completed successfully in {duration_ms}ms")

        except Exception as e:
            logger.log_tts_error(str(e), retry=True)
            audio_logger.warning(f"TTS failed, retrying: {e}")
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
                logger.log_tts_done()
                audio_logger.info(f"TTS retry succeeded in {duration_ms}ms")

            except Exception as e2:
                logger.log_tts_error(str(e2), retry=False)
                audio_logger.error(f"TTS retry failed, using fallback: {e2}")
                # Final fallback to platform command
                self._fallback_say(msg)

        finally:
            # FIX: GRACE PERIOD - Add 150ms delay before resuming mic to avoid tail echo
            # This ensures the TTS audio has fully finished playing before we start listening
            time.sleep(0.15)
            # FIX: MICROPHONE UNMUTING - Resume input so system can hear user's next utterance
            pause_input(False)

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
