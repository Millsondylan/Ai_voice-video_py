from __future__ import annotations

import re
import threading
import unicodedata
from typing import Any, Dict, List, Optional

from app.util.sanitizer import OutputSanitizer


def get_latest_assistant_response(conversation_history: List[Dict[str, str]]) -> Optional[str]:
    """Return the most recent assistant message content from conversation history."""
    for message in reversed(conversation_history):
        if message.get("role") == "assistant":
            return message.get("text") or message.get("content") or message.get("message")
    return None


def extract_from_api_response(response: Any) -> str:
    """
    Extract assistant text from API response object.

    Supports OpenAI- and Anthropic-style responses. Falls back to empty string
    if no assistant content found.
    """
    try:
        if response is None:
            return ""

        if hasattr(response, "choices"):
            choice = response.choices[0] if response.choices else None
            if choice and hasattr(choice, "message"):
                msg = choice.message
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, str):
                        return content.strip()
                if hasattr(msg, "content"):
                    return (msg.content or "").strip()
            if choice and hasattr(choice, "text"):
                return (choice.text or "").strip()

        if hasattr(response, "content"):
            content_blocks = getattr(response, "content")
            if isinstance(content_blocks, list):
                for block in content_blocks:
                    text = getattr(block, "text", None)
                    if text:
                        return text.strip()

        if isinstance(response, dict):
            for key in ("text", "result", "message"):
                val = response.get(key)
                if isinstance(val, str):
                    return val.strip()

            choices = response.get("choices")
            if isinstance(choices, list) and choices:
                choice = choices[0]
                if isinstance(choice, dict):
                    message = choice.get("message", {})
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, str):
                            return content.strip()
                        if isinstance(content, list) and content:
                            first = content[0]
                            if isinstance(first, dict) and "text" in first:
                                return str(first["text"]).strip()
                    if "text" in choice and isinstance(choice["text"], str):
                        return choice["text"].strip()

        return ""
    except Exception:
        return ""


_ROLE_PREFIX_RE = re.compile(r"^(User|Assistant|System|AI|Human):\s*", re.IGNORECASE | re.MULTILINE)
_TIMESTAMP_RE = re.compile(r"\[?\(?\d{1,2}:\d{2}(:\d{2})?\)?]?", re.MULTILINE)
_DATE_RE = re.compile(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}")
_ID_RE = re.compile(r"(id=[\'\"][\w-]+[\'\"]|message_id:\s*\S+)", re.IGNORECASE)
_URL_RE = re.compile(r"(http[s]?://\S+|\S+@\S+\.\S+)")
_UNSAFE_RE = re.compile(r"[^\w\s.!?,;:'\"—\-]")


def clean_text_for_tts(text: str) -> str:
    """
    Remove metadata, timestamps, and problematic characters before TTS.

    Builds on OutputSanitizer to ensure the spoken text contains only the
    latest assistant response without debug artifacts.
    """
    if not text:
        return ""

    cleaned = OutputSanitizer.sanitize_for_tts(text)
    cleaned = _ROLE_PREFIX_RE.sub("", cleaned)
    cleaned = _TIMESTAMP_RE.sub(" ", cleaned)
    cleaned = _DATE_RE.sub(" ", cleaned)
    cleaned = _ID_RE.sub(" ", cleaned)
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = _UNSAFE_RE.sub(" ", cleaned)
    cleaned = unicodedata.normalize("NFKD", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class ConversationStateTracker:
    """Track which messages have been spoken to prevent duplicates."""

    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []
        self.last_spoken_index: int = -1
        self._lock = threading.Lock()

    def add_message(self, role: str, content: str) -> int:
        with self._lock:
            message = {
                "role": role,
                "content": content,
                "index": len(self.messages),
            }
            self.messages.append(message)
            return message["index"]

    def get_latest_unspoken_assistant(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            for message in reversed(self.messages):
                if message["index"] <= self.last_spoken_index:
                    break
                if message["role"] == "assistant":
                    return message
        return None

    def should_speak(self, index: int) -> bool:
        with self._lock:
            if index <= self.last_spoken_index:
                return False
            if index >= len(self.messages):
                return False
            return self.messages[index]["role"] == "assistant"

    def mark_as_spoken(self, index: int) -> None:
        with self._lock:
            if index > self.last_spoken_index:
                self.last_spoken_index = index


class TTSManager:
    """Manage access to the underlying speech synthesizer."""

    def __init__(self, synthesizer) -> None:
        self._synth = synthesizer
        self._lock = threading.Lock()

    def clear_queue_and_stop(self) -> None:
        with self._lock:
            stop = getattr(self._synth, "stop", None)
            if callable(stop):
                stop()

    def speak(self, text: str) -> None:
        with self._lock:
            self._synth.speak(text)

    def speak_async(self, text: str):
        with self._lock:
            speak_async = getattr(self._synth, "speak_async", None)
            if callable(speak_async):
                return speak_async(text)
            # Fall back to blocking speak if async not available
            self._synth.speak(text)
            return None


class TTSResponsePipeline:
    """
    Integrated pipeline for filtering, tracking, and speaking assistant responses.
    """

    def __init__(
        self,
        tts_manager: TTSManager,
        state_tracker: Optional[ConversationStateTracker] = None,
    ) -> None:
        self.tts_manager = tts_manager
        self.state_tracker = state_tracker or ConversationStateTracker()

    def record_user_text(self, text: str) -> int:
        """Record a user utterance (never spoken aloud)."""
        return self.state_tracker.add_message("user", text or "")

    def speak_text(self, text: str, *, async_mode: bool = False) -> Dict[str, Any]:
        """Process and optionally speak an assistant response."""
        cleaned = clean_text_for_tts(text)
        if not cleaned:
            return {"status": "no_content", "text": ""}

        idx = self.state_tracker.add_message("assistant", cleaned)
        if not self.state_tracker.should_speak(idx):
            return {"status": "already_spoken", "text": cleaned, "index": idx}

        self.tts_manager.clear_queue_and_stop()
        if async_mode:
            self.tts_manager.speak_async(cleaned)
        else:
            self.tts_manager.speak(cleaned)
        self.state_tracker.mark_as_spoken(idx)
        return {"status": "spoken", "text": cleaned, "index": idx}

    def speak_from_history(self, conversation_history: List[Dict[str, str]], *, async_mode: bool = False) -> Dict[str, Any]:
        """Extract latest assistant message from history and speak it."""
        latest = get_latest_assistant_response(conversation_history)
        if latest is None:
            return {"status": "no_content", "text": ""}
        return self.speak_text(latest, async_mode=async_mode)

    def speak_from_api_response(self, api_response: Any, *, async_mode: bool = False) -> Dict[str, Any]:
        """Extract assistant message from API response and speak it."""
        extracted = extract_from_api_response(api_response)
        return self.speak_text(extracted, async_mode=async_mode)
