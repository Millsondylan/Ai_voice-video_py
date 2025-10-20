"""Audio I/O control for managing microphone state during TTS playback."""

import threading
import time
from typing import Optional


class AudioIOController:
    """Controls audio input/output to prevent echo during TTS.

    This class manages the microphone state to prevent acoustic echo
    when TTS is playing through speakers.
    """

    def __init__(self):
        self._input_paused = False
        self._lock = threading.Lock()
        self._pause_event = threading.Event()
        self._active_mic = None

    def pause_input(self, paused: bool = True) -> None:
        """Pause or resume microphone input.

        Args:
            paused: True to pause input, False to resume
        """
        with self._lock:
            self._input_paused = paused
            if paused:
                self._pause_event.clear()
            else:
                self._pause_event.set()

    def is_input_paused(self) -> bool:
        """Check if input is currently paused."""
        with self._lock:
            return self._input_paused

    def wait_if_paused(self, timeout: Optional[float] = None) -> bool:
        """Block until input is unpaused.

        Returns:
            True if resumed, False if timeout
        """
        if not self.is_input_paused():
            return True
        return self._pause_event.wait(timeout)

    def register_mic(self, mic) -> None:
        """Register active microphone for control."""
        with self._lock:
            self._active_mic = mic

    def unregister_mic(self) -> None:
        """Unregister microphone."""
        with self._lock:
            self._active_mic = None


# Global instance for cross-module coordination
_audio_io_controller = AudioIOController()


def get_audio_io_controller() -> AudioIOController:
    """Get the global audio I/O controller instance."""
    return _audio_io_controller


def pause_input(paused: bool = True) -> None:
    """Global convenience function to pause/resume input.

    Args:
        paused: True to pause, False to resume
    """
    _audio_io_controller.pause_input(paused)


def is_input_paused() -> bool:
    """Check if input is currently paused."""
    return _audio_io_controller.is_input_paused()