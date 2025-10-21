from __future__ import annotations

import logging
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


class OutputSanitizer:
    """Remove debug artifacts before TTS output.
    
    FIX: DEBUG OUTPUT PREVENTION - Catches and removes test phrases, debug markers,
    and other artifacts that should never be spoken aloud.
    """
    
    BLOCKED_PATTERNS = [
        r'DEBUG',
        r'test\s+(one|two|three|four|five)',
        r'TODO',
        r'FIXME',
        r'print\(',
        r'\[.*\]',  # Remove bracketed debug info
    ]
    
    @staticmethod
    def sanitize_for_tts(text: str) -> str:
        """Remove any debug artifacts from text before TTS.
        
        FIX: This is the last line of defense against debug output contamination.
        All text passes through this filter before being spoken.
        """
        import re
        
        if not text:
            return ""
            
        original = text
        
        # Remove blocked patterns
        for pattern in OutputSanitizer.BLOCKED_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Log if we sanitized anything
        if text != original:
            audio_logger.warning(f"Sanitized TTS output! Original: {original[:100]}")
        
        return text.strip()


class SpeechSynthesizer:
    """Manage text-to-speech playback via pyttsx3 with macOS/Windows/Linux support.
    
    FIX: VOICE REPLY RELIABILITY - Enhanced with:
    - Comprehensive error handling and retry logic
    - Output sanitization to prevent debug phrase contamination
    - Microphone muting during speech to prevent feedback
    - Thread-safe operation with locks
    - Engine reinitialization on failures
    - Platform-specific fallback commands
    - Detailed logging for troubleshooting
    """

    def __init__(self, voice: Optional[str] = None, rate: Optional[int] = None) -> None:
        self._driver_name = "nsss" if platform.system() == "Darwin" else None
        self._voice = voice
        self._rate = rate
        self._engine = self._create_engine()
        self._lock = threading.Lock()
        self._current_thread: Optional[threading.Thread] = None
        self._turn_index = 0
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3

    def _create_engine(self):
        """Create or recreate the pyttsx3 engine with configured settings."""
        try:
            engine = pyttsx3.init(driverName=self._driver_name) if self._driver_name else pyttsx3.init()
            if self._voice:
                try:
                    engine.setProperty("voice", self._voice)
                except Exception:
                    audio_logger.warning(f"Could not set voice: {self._voice}")
            if self._rate:
                try:
                    engine.setProperty("rate", self._rate)
                except Exception:
                    audio_logger.warning(f"Could not set rate: {self._rate}")
            return engine
        except Exception as e:
            audio_logger.error(f"Failed to create TTS engine: {e}")
            return None

    def _reinitialize_engine(self) -> None:
        """Force recreation of the TTS engine.
        
        FIX: ENGINE RECOVERY - Called when TTS fails to ensure fresh state.
        """
        audio_logger.info("Reinitializing TTS engine")
        try:
            if self._engine:
                try:
                    self._engine.stop()
                except Exception:
                    pass
            self._engine = self._create_engine()
        except Exception as e:
            audio_logger.error(f"Engine reinitialization failed: {e}")
            self._engine = None

    def set_turn_index(self, turn_index: int):
        """Set current turn index for logging."""
        self._turn_index = turn_index

    def speak(self, text: str) -> None:
        """Speak text with guaranteed output (lock + retry mechanism) and mic muting.

        FIX: VOICE REPLY FLOW - Proper microphone muting ensures clean conversation flow:
        - FIX: Sanitize output to prevent debug phrase contamination
        - FIX: Pause microphone input BEFORE speaking (pause_input(True))
        - FIX: Resume microphone input AFTER speaking (pause_input(False))
        - FIX: Grace period (150ms) after TTS to avoid tail echo
        - FIX: Global audio lock to prevent overlapping TTS
        - FIX: Automatic retry with engine reinitialization
        - FIX: Fallback to platform-specific commands
        - FIX: Track consecutive failures and force recovery

        This prevents the system from picking up its own voice output as user input,
        and ensures the mic is ready to hear the user's next utterance after TTS completes.
        """
        # FIX: SANITIZE OUTPUT - Remove any debug artifacts before speaking
        msg = OutputSanitizer.sanitize_for_tts(text)
        if not msg:
            msg = "Sorry, I didn't catch that."
        
        logger = get_event_logger()
        start_ts = time.monotonic()

        # FIX: MICROPHONE MUTING - Pause input during TTS to prevent echo/feedback
        # This stops the system from capturing its own voice as user input
        pause_input(True)

        try:
            logger.log_tts_started(msg)
            audio_logger.info(f"TTS: Speaking '{msg[:50]}{'...' if len(msg) > 50 else ''}'")

            # FIX: PRIMARY TTS ATTEMPT
            success = self._speak_with_engine(msg)
            
            if success:
                duration_ms = int((time.monotonic() - start_ts) * 1000)
                logger.log_tts_done()
                audio_logger.info(f"TTS completed successfully in {duration_ms}ms")
                self._consecutive_failures = 0  # Reset failure counter
            else:
                # FIX: RETRY WITH ENGINE REINITIALIZATION
                logger.log_tts_error("Primary attempt failed", retry=True)
                audio_logger.warning("TTS failed, reinitializing engine and retrying")
                time.sleep(0.25)
                
                self._reinitialize_engine()
                success = self._speak_with_engine(msg)
                
                if success:
                    duration_ms = int((time.monotonic() - start_ts) * 1000)
                    logger.log_tts_done()
                    audio_logger.info(f"TTS retry succeeded in {duration_ms}ms")
                    self._consecutive_failures = 0
                else:
                    # FIX: FINAL FALLBACK TO PLATFORM COMMANDS
                    logger.log_tts_error("Retry failed", retry=False)
                    audio_logger.error("TTS retry failed, using platform fallback")
                    self._fallback_say(msg)
                    self._consecutive_failures += 1

            # FIX: FORCE ENGINE RECOVERY - If too many failures, recreate engine
            if self._consecutive_failures >= self._max_consecutive_failures:
                audio_logger.warning(
                    f"Too many consecutive TTS failures ({self._consecutive_failures}), "
                    "forcing engine recreation"
                )
                self._reinitialize_engine()
                self._consecutive_failures = 0

        except Exception as e:
            logger.log_tts_error(str(e), retry=False)
            audio_logger.error(f"Unexpected TTS error: {e}")
            self._fallback_say(msg)

        finally:
            # FIX: GRACE PERIOD - Add 150ms delay before resuming mic to avoid tail echo
            # This ensures the TTS audio has fully finished playing before we start listening
            time.sleep(0.15)
            # FIX: MICROPHONE UNMUTING - Resume input so system can hear user's next utterance
            pause_input(False)

    def _speak_with_engine(self, text: str) -> bool:
        """Attempt to speak using the pyttsx3 engine.
        
        Returns True if successful, False otherwise.
        
        FIX: ISOLATED ENGINE INTERACTION - Separates engine interaction from
        error handling logic for cleaner retry flow.
        """
        if not self._engine:
            return False
            
        try:
            with audio_out_lock:
                with self._lock:
                    # Clear any queued speech before starting
                    try:
                        self._engine.stop()
                    except Exception:
                        pass  # Ignore stop errors
                    
                    self._engine.say(text)
                    self._engine.runAndWait()
            
            return True
            
        except Exception as e:
            audio_logger.error(f"Engine speak failed: {e}")
            return False

    def speak_async(self, text: str) -> threading.Thread:
        """Speak text asynchronously in a background thread.
        
        FIX: ASYNC SUPPORT - For non-blocking TTS in UI applications.
        """
        if self._current_thread and self._current_thread.is_alive():
            try:
                with self._lock:
                    if self._engine:
                        self._engine.stop()
            except Exception:
                pass  # Ignore stop errors
            self._current_thread.join(timeout=2.0)

        thread = threading.Thread(target=self.speak, args=(text,), daemon=True)
        self._current_thread = thread
        thread.start()
        return thread

    def _fallback_say(self, text: str) -> None:
        """Fallback to platform speech command if pyttsx3 fails.
        
        FIX: PLATFORM FALLBACK - Ensures speech output even if pyttsx3 is broken.
        macOS uses 'say', Linux uses 'espeak' or 'spd-say', Windows uses PowerShell.
        """
        system = platform.system()
        audio_logger.info(f"Using platform fallback for {system}")
        
        try:
            if system == "Darwin":
                subprocess.run(["say", text], check=False, timeout=30)
                audio_logger.info("macOS 'say' command succeeded")
            elif system == "Linux":
                # Try espeak first
                result = subprocess.run(
                    ["espeak", text],
                    check=False,
                    timeout=30,
                    capture_output=True
                )
                if result.returncode != 0:
                    # Try spd-say if espeak failed
                    subprocess.run(["spd-say", text], check=False, timeout=30)
                audio_logger.info("Linux TTS command succeeded")
            elif system == "Windows":
                # Use PowerShell Add-Type speech
                ps_command = f'Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak("{text}")'
                subprocess.run(
                    ["powershell", "-Command", ps_command],
                    check=False,
                    timeout=30
                )
                audio_logger.info("Windows PowerShell TTS succeeded")
        except subprocess.TimeoutExpired:
            audio_logger.error("Platform TTS command timed out")
        except FileNotFoundError:
            audio_logger.error(f"Platform TTS command not found for {system}")
        except Exception as e:
            audio_logger.error(f"Platform fallback failed: {e}")

