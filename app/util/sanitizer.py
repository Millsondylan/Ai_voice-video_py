"""
Output sanitization for TTS to prevent debug artifacts from being spoken.
"""
import re
import logging

logger = logging.getLogger(__name__)


class OutputSanitizer:
    """Sanitize text before TTS to remove debug artifacts and test phrases."""

    BLOCKED_PATTERNS = [
        r'DEBUG',
        r'test\s+(one|two|three|four|five)',
        r'TODO',
        r'FIXME',
        r'print\(',
        r'\[.*?\]',  # Remove bracketed debug info
        r'<.*?>',  # Remove HTML-like tags
    ]

    @staticmethod
    def sanitize_for_tts(text: str) -> str:
        """
        Remove any debug artifacts from text before TTS.

        Args:
            text: Raw text that might contain debug artifacts

        Returns:
            Cleaned text safe for TTS output
        """
        if not text:
            return ""

        original = text

        # Apply all blocked pattern filters
        for pattern in OutputSanitizer.BLOCKED_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        # Log if sanitization changed the output
        if text != original:
            logger.warning(f"Sanitized output! Was: {original[:100]}")
            logger.info(f"Cleaned to: {text[:100]}")

        return text

    @staticmethod
    def validate_tts_output(text: str) -> bool:
        """
        Validate that text is safe for TTS (doesn't contain debug artifacts).

        Returns:
            True if text is clean, False if it contains blocked patterns
        """
        if not text:
            return False

        text_lower = text.lower()

        # Check for common debug patterns
        debug_indicators = [
            'debug', 'test one', 'test two', 'todo', 'fixme',
            'print(', '[debug]', '<debug>'
        ]

        for indicator in debug_indicators:
            if indicator in text_lower:
                logger.error(f"TTS validation failed: found '{indicator}' in output")
                return False

        return True
