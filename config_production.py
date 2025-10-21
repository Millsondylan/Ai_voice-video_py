"""
Production configuration module for smart glasses voice assistant.

Loads all configuration from environment variables with sensible defaults.
"""
import logging
import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'

logging.basicConfig(
    level=LOG_LEVEL if not DEBUG else 'DEBUG',
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.FileHandler('voice_assistant.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class ProductionConfig:
    """Production configuration for voice assistant."""

    # =================================================================
    # PORCUPINE WAKE WORD DETECTION
    # =================================================================
    PORCUPINE_ACCESS_KEY: Optional[str] = os.getenv('PORCUPINE_ACCESS_KEY')
    PORCUPINE_KEYWORD_PATH: str = os.getenv(
        'PORCUPINE_KEYWORD_PATH',
        'models/hey_glasses.ppn'
    )
    WAKE_WORD_SENSITIVITY: float = float(os.getenv('WAKE_WORD_SENSITIVITY', '0.5'))

    # =================================================================
    # TTS CONFIGURATION
    # =================================================================
    ELEVENLABS_API_KEY: Optional[str] = os.getenv('ELEVENLABS_API_KEY')
    ELEVENLABS_VOICE_ID: str = os.getenv(
        'ELEVENLABS_VOICE_ID',
        'JBFqnCBsd6RMkjVDRZzb'
    )
    PREFER_CLOUD_TTS: bool = os.getenv('PREFER_CLOUD_TTS', 'false').lower() == 'true'
    TTS_RATE: int = int(os.getenv('TTS_RATE', '175'))

    # =================================================================
    # LLM/VLM CONFIGURATION
    # =================================================================
    OPENAI_API_KEY: Optional[str] = os.getenv('OPENAI_API_KEY')
    ANTHROPIC_API_KEY: Optional[str] = os.getenv('ANTHROPIC_API_KEY')
    VLM_PROVIDER: str = os.getenv('VLM_PROVIDER', 'openai')
    VLM_MODEL: str = os.getenv('VLM_MODEL', 'gpt-4-vision-preview')

    # =================================================================
    # AUDIO SETTINGS
    # =================================================================
    SAMPLE_RATE: int = int(os.getenv('SAMPLE_RATE', '16000'))
    FRAME_DURATION_MS: int = int(os.getenv('FRAME_DURATION_MS', '30'))
    VAD_AGGRESSIVENESS: int = int(os.getenv('VAD_AGGRESSIVENESS', '3'))
    VAD_PADDING_MS: int = int(os.getenv('VAD_PADDING_MS', '300'))

    # Detect Bluetooth (user should set this)
    IS_BLUETOOTH: bool = os.getenv('IS_BLUETOOTH', 'false').lower() == 'true'

    # Adaptive padding for Bluetooth
    if IS_BLUETOOTH and VAD_PADDING_MS < 500:
        VAD_PADDING_MS = 500
        logger.info("Bluetooth mode: increased VAD padding to 500ms")

    # =================================================================
    # CONVERSATION SETTINGS
    # =================================================================
    CONVERSATION_TIMEOUT: int = int(os.getenv('CONVERSATION_TIMEOUT', '15'))

    # Exit commands
    EXIT_COMMANDS = [
        "bye glasses",
        "goodbye glasses",
        "goodbye",
        "exit",
        "stop listening",
        "stop",
    ]

    # =================================================================
    # VOSK SETTINGS (STT)
    # =================================================================
    VOSK_MODEL_PATH: Optional[str] = os.getenv('VOSK_MODEL_PATH')

    # =================================================================
    # LOGGING
    # =================================================================
    ENVIRONMENT: str = os.getenv('ENVIRONMENT', 'development')

    @classmethod
    def validate(cls) -> bool:
        """
        Validate that required configuration is present.

        Returns:
            True if config is valid, False otherwise
        """
        errors = []

        # Check required keys
        if not cls.PORCUPINE_ACCESS_KEY:
            errors.append("PORCUPINE_ACCESS_KEY not set")

        if not cls.VOSK_MODEL_PATH:
            errors.append("VOSK_MODEL_PATH not set")

        if not any([cls.OPENAI_API_KEY, cls.ANTHROPIC_API_KEY]):
            errors.append("At least one LLM API key required (OPENAI_API_KEY or ANTHROPIC_API_KEY)")

        if errors:
            logger.error("Configuration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            return False

        logger.info("Configuration validated successfully")
        return True

    @classmethod
    def log_config(cls) -> None:
        """Log configuration (hiding sensitive values)."""
        logger.info("=== Production Configuration ===")
        logger.info(f"Environment: {cls.ENVIRONMENT}")
        logger.info(f"Debug mode: {DEBUG}")
        logger.info(f"Log level: {LOG_LEVEL}")
        logger.info("")
        logger.info("Wake Word:")
        logger.info(f"  Porcupine access key: {'*' * 20 if cls.PORCUPINE_ACCESS_KEY else 'NOT SET'}")
        logger.info(f"  Keyword path: {cls.PORCUPINE_KEYWORD_PATH}")
        logger.info(f"  Sensitivity: {cls.WAKE_WORD_SENSITIVITY}")
        logger.info("")
        logger.info("TTS:")
        logger.info(f"  ElevenLabs API key: {'*' * 20 if cls.ELEVENLABS_API_KEY else 'NOT SET'}")
        logger.info(f"  Prefer cloud: {cls.PREFER_CLOUD_TTS}")
        logger.info(f"  TTS rate: {cls.TTS_RATE}")
        logger.info("")
        logger.info("Audio:")
        logger.info(f"  Sample rate: {cls.SAMPLE_RATE}Hz")
        logger.info(f"  Frame duration: {cls.FRAME_DURATION_MS}ms")
        logger.info(f"  VAD aggressiveness: {cls.VAD_AGGRESSIVENESS}")
        logger.info(f"  VAD padding: {cls.VAD_PADDING_MS}ms")
        logger.info(f"  Bluetooth mode: {cls.IS_BLUETOOTH}")
        logger.info("")
        logger.info("Conversation:")
        logger.info(f"  Timeout: {cls.CONVERSATION_TIMEOUT}s")
        logger.info(f"  Exit commands: {len(cls.EXIT_COMMANDS)}")
        logger.info("=" * 40)


# Validate on import (in production mode)
if ENVIRONMENT := os.getenv('ENVIRONMENT', 'development') == 'production':
    ProductionConfig.validate()
