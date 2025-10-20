from __future__ import annotations

import platform
import subprocess
import threading
from typing import Optional

import pyttsx3


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
        if not text.strip():
            return
        try:
            with self._lock:
                self._engine.stop()
                self._engine.say(text)
                self._engine.runAndWait()
        except Exception:
            self._fallback_say(text)

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
