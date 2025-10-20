from __future__ import annotations

import platform
import subprocess
import threading
import time
from typing import Optional

import pyttsx3

from app.util.log import get_event_logger

# Module-level lock for audio output serialization
audio_out_lock = threading.Lock()


class SpeechSynthesizer:
    """Manage text-to-speech playback via pyttsx3 with macOS/Windows/Linux support."""

    def __init__(self, voice: Optional[str] = None, rate: Optional[int] = None) -> None:
        driver = "nsss" if platform.system() == "Darwin" else None
        self._engine = pyttsx3.init(driverName=driver) if driver else pyttsx3.init()
        if voice:
            self._engine.setProperty("voice", voice)
        if rate:
            self._engine.setProperty("rate", rate)
        self._lock = threading.Lock()
        self._current_thread: Optional[threading.Thread] = None

    def speak(self, text: str) -> None:
        """Speak text with guaranteed output (lock + retry mechanism)."""
        msg = text.strip() or "Sorry, I didn't catch that."
        logger = get_event_logger()

        try:
            logger.log_tts_started(msg)
            with audio_out_lock:
                with self._lock:
                    self._engine.stop()
                    self._engine.say(msg)
                    self._engine.runAndWait()
            logger.log_tts_done()
        except Exception as e:
            logger.log_tts_error(str(e), retry=True)
            time.sleep(0.25)  # Brief pause before retry
            try:
                with audio_out_lock:
                    with self._lock:
                        self._engine.stop()
                        self._engine.say(msg)
                        self._engine.runAndWait()
                logger.log_tts_done()
            except Exception as e2:
                logger.log_tts_error(str(e2), retry=False)
                # Final fallback to platform command
                self._fallback_say(msg)

    def speak_async(self, text: str) -> threading.Thread:
        if self._current_thread and self._current_thread.is_alive():
            self._engine.stop()

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
