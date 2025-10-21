"""
Simplified diagnostic logging module for human-readable console output.

This module provides simple, real-time event logging to help developers and users
understand the voice assistant's internal state transitions. Events are printed
to the console with timestamps for easy debugging.

Key Events Logged:
- wake_detected: Wake word recognized
- speech_start: User began speaking
- speech_end: User finished speaking
- tts_start: Assistant began speaking
- tts_end: Assistant finished speaking
- session_loop_start: Multi-turn conversation started
- session_exit_reason: Session ended (with reason: timeout, bye, manual, etc.)
"""

import time
from typing import Optional

# Global flag to enable/disable debug output
DEBUG_ENABLED = True


def enable_debug(enabled: bool = True) -> None:
    """Enable or disable debug logging output."""
    global DEBUG_ENABLED
    DEBUG_ENABLED = enabled


def log_event(event_name: str, details: str = "") -> None:
    """
    Log a diagnostic event with timestamp and optional details.

    Args:
        event_name: The event type (e.g., 'wake_detected', 'speech_start')
        details: Optional additional information about the event

    Example:
        log_event("wake_detected", "hey glasses")
        log_event("session_exit_reason", "timeout")
    """
    if not DEBUG_ENABLED:
        return

    timestamp = time.strftime("%H:%M:%S")
    message = f"[{timestamp}] {event_name}"

    if details:
        message += f": {details}"

    print(message)


def log_wake_detected(phrase: str = "") -> None:
    """Log wake word detection event."""
    log_event("wake_detected", phrase or "wake phrase recognized")


def log_speech_start() -> None:
    """Log start of user speech capture."""
    log_event("speech_start")


def log_speech_end() -> None:
    """Log end of user speech capture."""
    log_event("speech_end")


def log_tts_start(text_preview: str = "") -> None:
    """Log start of text-to-speech output."""
    preview = text_preview[:50] + "..." if len(text_preview) > 50 else text_preview
    log_event("tts_start", preview)


def log_tts_end() -> None:
    """Log end of text-to-speech output."""
    log_event("tts_end")


def log_session_start() -> None:
    """Log start of multi-turn conversation session."""
    log_event("session_loop_start")


def log_session_exit(reason: str) -> None:
    """
    Log session termination with reason.

    Args:
        reason: Why the session ended (timeout, bye, manual, error, etc.)
    """
    log_event("session_exit_reason", reason)


def log_turn(turn_index: int, user_text: str = "", assistant_text: str = "") -> None:
    """
    Log a conversation turn.

    Args:
        turn_index: Turn number (0-indexed)
        user_text: What the user said
        assistant_text: What the assistant responded
    """
    if not DEBUG_ENABLED:
        return

    timestamp = time.strftime("%H:%M:%S")
    print(f"\n[{timestamp}] === Turn {turn_index} ===")
    if user_text:
        print(f"  User: {user_text}")
    if assistant_text:
        print(f"  Assistant: {assistant_text}")


# Convenience function for structured event logging
def log_diagnostic(category: str, message: str, **kwargs) -> None:
    """
    Log a diagnostic message with category and optional key-value pairs.

    Args:
        category: Event category (e.g., 'VAD', 'STT', 'Session')
        message: Diagnostic message
        **kwargs: Additional key-value pairs to log

    Example:
        log_diagnostic("VAD", "Speech detected", aggressiveness=1, frame_ms=20)
    """
    if not DEBUG_ENABLED:
        return

    timestamp = time.strftime("%H:%M:%S")
    output = f"[{timestamp}] [{category}] {message}"

    if kwargs:
        details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        output += f" ({details})"

    print(output)


def print_section_header(title: str) -> None:
    """Print a visual section header for console output."""
    if not DEBUG_ENABLED:
        return

    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")
