from __future__ import annotations

import re


# Vision-related intent patterns
DEICTIC_PATTERNS = [
    r"\bwhat\s+is\s+(this|that)\b",
    r"\bwhat\s+am\s+i\s+(holding|looking\s+at)\b",
    r"\bcan\s+you\s+see\s+what\s+i'?m\s+(holding|doing)\b",
    r"\blook\s+at\b",
    r"\bsee\s+(this|that)\b",
    r"\bidentify\b",
    r"\bis\s+this\b",
    r"\bshow\s+me\b",
    r"\bshow\s+what\s+i'?m\s+(holding|doing)\b",
    r"\bdescribe\s+(this|that|what\s+i'?m\s+holding)\b",
    r"\bwhat\s+(color|shape|size)\b",
    r"\bwhere\s+is\b",
    r"\bhow\s+many\b",
    r"\bdo\s+you\s+see\b",
    r"\bcan\s+you\s+see\b",
]

OCR_PATTERNS = [
    r"\bread\b",
    r"\btext\s+on\b",
    r"\blabel\b",
    r"\bsign\b",
    r"\bprice\b",
    r"\bserial\b",
    r"\bnumber\b.*\b(on|visible|shown)\b",
    r"\bwhat\s+does\s+(it|this|that)\s+say\b",
    r"\bwriting\b",
    r"\bwritten\b",
]

# Chat/greeting patterns (explicitly non-vision)
CHAT_PATTERNS = [
    r"^\s*(hi|hello|hey|howdy|greetings)\b",
    r"\bhow\s+are\s+you\b",
    r"\bwhat'?s\s+up\b",
    r"\bgood\s+(morning|afternoon|evening|night)\b",
    r"\bnice\s+to\s+(meet|see)\s+you\b",
    r"\bhow\s+do\s+you\s+do\b",
    r"^\s*(thanks|thank\s+you|thx)\b",
    r"^\s*(bye|goodbye|see\s+ya)\b",
]

# Leading greeting prefixes that should be ignored when evaluating intent.
CHAT_PREFIX_PATTERNS = [
    r"^\s*(hi|hello|hey|howdy|greetings)\b",
    r"^\s*good\s+(morning|afternoon|evening|night)\b",
    r"^\s*(thanks|thank\s+you|thx)\b",
    r"^\s*(bye|goodbye|see\s+ya)\b",
]


def _matches_patterns(text: str, patterns: list[str]) -> bool:
    """Return True if any regex in patterns matches text (case-insensitive)."""
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return True
    return False


def _strip_leading_greeting(text: str) -> tuple[str, bool]:
    """Strip leading greeting phrases and punctuation from text."""
    for pattern in CHAT_PREFIX_PATTERNS:
        match = re.match(pattern, text, flags=re.IGNORECASE)
        if match:
            remainder = text[match.end():]
            remainder = remainder.lstrip(" ,.!?-")
            return remainder, True
    return text, False


def _is_chat_only(text: str) -> bool:
    """Return True if text is purely chat/greeting with no extra content."""
    normalized = text.strip()
    if not normalized:
        return True

    for pattern in CHAT_PATTERNS:
        extended_pattern = f"{pattern}(?:[\\s,.!?]*)$"
        if re.fullmatch(extended_pattern, normalized, flags=re.IGNORECASE):
            return True
    return False


def wants_vision(transcript: str) -> bool:
    """
    Determine if user's intent requires vision/image analysis.

    Returns True only if transcript matches vision-related intents:
    - Deictic/identify: "what is that/this", "look at", "see this", "identify"
    - OCR: "read", "text on", "label", "sign", "price", "serial"

    Returns False for greetings/small-talk: "hi", "hello", "hey", "how are you", etc.

    Defaults conservatively to False unless clearly vision-related.

    Args:
        transcript: The user's spoken/transcribed query

    Returns:
        True if vision is needed, False otherwise
    """
    if not transcript or not transcript.strip():
        return False

    text_lower = transcript.lower().strip()
    no_greeting_text, _ = _strip_leading_greeting(text_lower)

    def needs_vision(candidate: str) -> bool:
        return _matches_patterns(candidate, DEICTIC_PATTERNS) or _matches_patterns(candidate, OCR_PATTERNS)

    # Evaluate both the original text and the greeting-stripped text.
    if needs_vision(text_lower) or needs_vision(no_greeting_text):
        return True

    # If the user only greeted or made small talk, treat as non-vision.
    if _is_chat_only(text_lower):
        return False

    # Default conservatively: no vision unless clearly requested
    return False
