from __future__ import annotations

import re


# Scene-related prefixes that should be stripped when no images are sent
SCENE_PREFACE_PATTERNS = [
    r"^I see\s+",
    r"^From the image[s]?,?\s+",
    r"^In the (photo|picture|image)[s]?,?\s+",
    r"^Looking at (the )?(image|photo|picture)[s]?,?\s+",
    r"^Based on the (image|photo|picture)[s]?,?\s+",
    r"^The image shows\s+",
    r"^The (photo|picture) shows\s+",
    r"^I can see\s+",
    r"^From what I can see,?\s+",
    r"^In this (image|photo|picture),?\s+",
]


def strip_scene_preface(text: str) -> str:
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
    if not text:
        return text

    stripped = text
    for pattern in SCENE_PREFACE_PATTERNS:
        stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE)
        # Only apply the first matching pattern
        if stripped != text:
            break

    # Capitalize first letter if needed
    if stripped and stripped[0].islower():
        stripped = stripped[0].upper() + stripped[1:]

    return stripped.strip()
