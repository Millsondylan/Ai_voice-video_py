"""
Output sanitization for TTS to prevent debug artifacts from being spoken.

FIX Problem 9: Enhanced text cleaning based on diagnostic guide to remove:
- Role labels (User:, Assistant:, System:)
- Timestamps ([HH:MM:SS], etc.)
- Message IDs and metadata
- Debug info and logging
- Markdown code blocks
- URLs and emails
- Unsafe characters
- Unicode normalization
"""
import re
import logging
import unicodedata

logger = logging.getLogger(__name__)


class OutputSanitizer:
    """Sanitize text before TTS to remove debug artifacts and test phrases."""

    BLOCKED_PATTERNS = [
        r'DEBUG',
        r'test\s+(one|two|three|four|five)',
        r'TODO',
        r'FIXME',
        r'print\(',
        r'\[(debug|info|trace|log)[^]]*]',  # Remove bracketed debug info but keep regular brackets
        r'<.*?>',  # Remove HTML-like tags
    ]

    @staticmethod
    def sanitize_for_tts(text: str) -> str:
        """
        Remove any debug artifacts from text before TTS.

        FIX Problem 9: Comprehensive text cleaning matching diagnostic guide.
        Removes metadata, timestamps, and problematic characters.

        Args:
            text: Raw text that might contain debug artifacts

        Returns:
            Cleaned text safe for TTS output
        """
        if not text:
            return ""

        original = text

        # FIX Problem 9: Remove role labels (User:, Assistant:, System:, AI:, Human:)
        text = re.sub(r'^(User|Assistant|System|AI|Human):\s*', '',
                      text, flags=re.MULTILINE | re.IGNORECASE)

        # FIX Problem 9: Remove timestamps [HH:MM:SS], [HH:MM], (HH:MM:SS)
        text = re.sub(r'\[?\(?\d{1,2}:\d{2}(:\d{2})?\)?]?', '', text)

        # FIX Problem 9: Remove dates: DD/MM/YYYY, MM-DD-YYYY, YYYY-MM-DD
        text = re.sub(r'\d{1,4}[-/]\d{1,2}[-/]\d{1,4}', '', text)

        # FIX Problem 9: Remove message IDs and metadata
        text = re.sub(r'id=[\'"][\\w-]+[\'"]', '', text)
        text = re.sub(r'message_id:\s*\S+', '', text)

        # FIX Problem 9: Remove debug info
        text = re.sub(r'\[DEBUG\].*?(\n|$)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[INFO\].*?(\n|$)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[TRACE\].*?(\n|$)', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[LOG\].*?(\n|$)', '', text, flags=re.IGNORECASE)

        # FIX Problem 9: Remove markdown code blocks
        text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
        text = re.sub(r'`[^`]+`', '', text)

        # FIX Problem 9: Remove URLs and emails
        text = re.sub(r'http[s]?://\S+', '', text)
        text = re.sub(r'\S+@\S+\.\S+', '', text)

        # Apply all blocked pattern filters
        for pattern in OutputSanitizer.BLOCKED_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)

        # FIX Problem 9: Keep only safe characters
        # Allow word chars, whitespace, and common punctuation
        text = re.sub(r'[^\w\s.!?,;:\'"—\-]', '', text)

        # FIX Problem 9: Normalize Unicode to remove weird characters
        text = unicodedata.normalize('NFKD', text)

        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        # Log if sanitization changed the output
        if text != original and text:
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
