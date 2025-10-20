from __future__ import annotations

import re


# Vision-related intent patterns
DEICTIC_PATTERNS = [
    r"\bwhat\s+is\s+(this|that)\b",
    r"\blook\s+at\b",
    r"\bsee\s+(this|that)\b",
    r"\bidentify\b",
    r"\bis\s+this\b",
    r"\bshow\s+me\b",
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

    # Explicitly reject chat/greeting patterns
    for pattern in CHAT_PATTERNS:
        if re.search(pattern, text_lower):
            return False

    # Check for deictic (pointing/identifying) patterns
    for pattern in DEICTIC_PATTERNS:
        if re.search(pattern, text_lower):
            return True

    # Check for OCR/reading patterns
    for pattern in OCR_PATTERNS:
        if re.search(pattern, text_lower):
            return True

    # Default conservatively: no vision unless clearly requested
    return False
