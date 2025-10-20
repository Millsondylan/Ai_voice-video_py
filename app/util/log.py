from __future__ import annotations

import logging
import time
from typing import Optional

# Configure module logger
logger = logging.getLogger("glasses.audio")
logger.setLevel(logging.INFO)

# Create console handler if not already configured
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


def now_ms() -> int:
    """Return current timestamp in milliseconds."""
    return int(time.time() * 1000)


class AudioEventLogger:
    """Structured logger for audio system events."""

    def __init__(self) -> None:
        self._wake_detected_at: Optional[int] = None
        self._segment_start_at: Optional[int] = None
        self._segment_stop_at: Optional[int] = None
        self._stop_reason: Optional[str] = None
        self._stt_final_text: Optional[str] = None
        self._stt_ms_total: Optional[int] = None
        self._audio_ms_total: Optional[int] = None
        self._tts_started_at: Optional[int] = None
        self._tts_done_at: Optional[int] = None
        self._tts_error: Optional[str] = None

    def log_wake_detected(self) -> None:
        """Log wake word detection timestamp."""
        self._wake_detected_at = now_ms()
        logger.info(f"Wake word detected at {self._wake_detected_at}")

    def log_segment_start(self) -> None:
        """Log segment recording start timestamp."""
        self._segment_start_at = now_ms()
        logger.info(f"Segment recording started at {self._segment_start_at}")

    def log_segment_stop(
        self, stop_reason: str, stt_final_text: str, audio_ms: int, stt_ms: int
    ) -> None:
        """Log segment recording stop with all relevant metrics."""
        self._segment_stop_at = now_ms()
        self._stop_reason = stop_reason
        self._stt_final_text = stt_final_text
        self._audio_ms_total = audio_ms
        self._stt_ms_total = stt_ms

        duration_s = (
            (self._segment_stop_at - self._segment_start_at) / 1000.0
            if self._segment_start_at
            else 0
        )

        logger.info(
            f"Segment stopped: reason={stop_reason}, duration={duration_s:.2f}s, "
            f"audio_ms={audio_ms}, stt_ms={stt_ms}, text_len={len(stt_final_text)}"
        )

    def log_tts_started(self, text: str) -> None:
        """Log TTS playback start."""
        self._tts_started_at = now_ms()
        logger.info(f"TTS started at {self._tts_started_at}, text_len={len(text)}")

    def log_tts_done(self) -> None:
        """Log successful TTS completion."""
        self._tts_done_at = now_ms()
        duration_ms = (
            self._tts_done_at - self._tts_started_at if self._tts_started_at else 0
        )
        logger.info(f"TTS completed in {duration_ms}ms")

    def log_tts_error(self, error: str, retry: bool = False) -> None:
        """Log TTS error (with optional retry flag)."""
        self._tts_error = error
        retry_str = " (retrying)" if retry else ""
        logger.error(f"TTS error{retry_str}: {error}")

    def get_summary(self) -> dict:
        """Return a summary dict of all logged events."""
        return {
            "wake_detected_at": self._wake_detected_at,
            "segment_start_at": self._segment_start_at,
            "segment_stop_at": self._segment_stop_at,
            "stop_reason": self._stop_reason,
            "stt_final_text": self._stt_final_text,
            "stt_ms_total": self._stt_ms_total,
            "audio_ms_total": self._audio_ms_total,
            "tts_started_at": self._tts_started_at,
            "tts_done_at": self._tts_done_at,
            "tts_error": self._tts_error,
        }

    def reset(self) -> None:
        """Reset all logged event data."""
        self._wake_detected_at = None
        self._segment_start_at = None
        self._segment_stop_at = None
        self._stop_reason = None
        self._stt_final_text = None
        self._stt_ms_total = None
        self._audio_ms_total = None
        self._tts_started_at = None
        self._tts_done_at = None
        self._tts_error = None


# Global instance for easy access
_event_logger = AudioEventLogger()


def get_event_logger() -> AudioEventLogger:
    """Get the global audio event logger instance."""
    return _event_logger
