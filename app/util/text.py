from __future__ import annotations

import re
from typing import Optional


# Scene-related prefixes that should be stripped when no images are sent.
# We keep patterns lightweight (no anchors) and add shared trailing punctuation
# handling in code so we can strip phrases like "I see", "From the image,"
# or even just "I see" with no trailing whitespace.
SCENE_PREFACE_PATTERNS = [
    r"I see",
    r"From the image(?:s)?",
    r"In the (?:photo|picture|image)(?:s)?",
    r"Looking at (?:the )?(?:image|photo|picture)(?:s)?",
    r"Based on the (?:image|photo|picture)(?:s)?",
    r"The image shows",
    r"The (?:photo|picture) shows",
    r"I can see",
    r"From what I can see",
    r"In this (?:image|photo|picture)",
]


def _strip_preface(text: str) -> tuple[str, bool]:
    """Return text without a recognised scene preface and whether one was removed."""
    stripped = text.lstrip()
    for pattern in SCENE_PREFACE_PATTERNS:
        # Allow trailing whitespace or punctuation such as comma, colon, dash, period.
        match = re.match(
            rf"(?is)^{pattern}(?:[\s,.:;-]+|$)",
            stripped,
        )
        if match:
            without = stripped[match.end():]
            return without.lstrip(), True
    return stripped, False


def strip_scene_preface(text: Optional[str]) -> Optional[str]:
    """
    Remove accidental scene-related prefixes from VLM responses.

    This function is used when no images were sent to the VLM, but the model
    still responds as if it's looking at images. It strips common prefixes like:
    - "I see..."
    - "From the image..."
    - "Looking at the photo..."
    - etc.

    Only strips from the beginning of the text. Preserves the rest of the response.

    Args:
        text: The VLM response text

    Returns:
        Text with scene prefixes removed, preserving the rest of the content
    """
    if text is None:
        return text

    stripped, removed = _strip_preface(text)

    # If nothing left (preface-only), just return empty string.
    if not stripped:
        return ""

    # Capitalize first letter if needed
    if stripped and stripped[0].islower():
        stripped = stripped[0].upper() + stripped[1:]

    return stripped.strip()
