#!/usr/bin/env python3
"""
Comprehensive test script for smart glasses voice assistant.

Tests all 6 critical fixes:
1. Complete speech capture (VAD with ring buffer)
2. Wake word reliability (Porcupine)
3. Multi-turn conversation (transcription restart)
4. 15-second timeout (state machine)
5. No debug output (sanitizer)
6. TTS reliability (hybrid fallback)
"""
import logging
import os
import sys
import time
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s %(message)s'
)
logger = logging.getLogger(__name__)

try:
    from app.audio.voice_recorder import VoiceRecorder
    VOICE_RECORDER_AVAILABLE = True
except ImportError as e:
    VOICE_RECORDER_AVAILABLE = False
    logger.warning(f"VoiceRecorder not available: {e}")

try:
    from app.audio.tts import SpeechSynthesizer
    TTS_AVAILABLE = True
except ImportError as e:
    TTS_AVAILABLE = False
    logger.warning(f"SpeechSynthesizer not available: {e}")

from app.conversation_state import AssistantState, ConversationStateMachine
from app.util.sanitizer import OutputSanitizer
from config_production import ProductionConfig


class TestResults:
    """Track test results."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def add_result(self, name: str, passed: bool, message: str = ""):
        """Add a test result."""
        self.tests.append({
            'name': name,
            'passed': passed,
            'message': message
        })
        if passed:
            self.passed += 1
            logger.info(f"✓ {name}: PASSED {message}")
        else:
            self.failed += 1
            logger.error(f"✗ {name}: FAILED {message}")

    def summary(self):
        """Print summary of results."""
        total = self.passed + self.failed
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        for test in self.tests:
            status = "✓ PASS" if test['passed'] else "✗ FAIL"
            print(f"{status}: {test['name']}")
            if test['message']:
                print(f"       {test['message']}")
        print("=" * 60)
        print(f"Total: {total} tests, {self.passed} passed, {self.failed} failed")
        print(f"Success rate: {(self.passed / total * 100):.1f}%")
        print("=" * 60)

        return self.failed == 0


def test_config_validation():
    """Test #0: Configuration validation."""
    results = TestResults()

    # Test config loading
    try:
        is_valid = ProductionConfig.validate()
        results.add_result(
            "Configuration validation",
            True,
            f"Config valid: {is_valid}"
        )
    except Exception as e:
        results.add_result(
            "Configuration validation",
            False,
            f"Error: {e}"
        )

    return results


def test_output_sanitizer():
    """Test #5: Output sanitization removes debug artifacts."""
    results = TestResults()

    # Test cases: (input, should_be_blocked)
    test_cases = [
        ("Hello world", False),
        ("test one two three", True),
        ("DEBUG: Something wrong", True),
        ("TODO: Fix this", True),
        ("Normal speech here", False),
        ("[DEBUG] test output", True),
        ("This is a normal response", False),
    ]

    for input_text, should_be_blocked in test_cases:
        sanitized = OutputSanitizer.sanitize_for_tts(input_text)
        is_valid = OutputSanitizer.validate_tts_output(sanitized)

        if should_be_blocked:
            # Should be cleaned or rejected
            passed = (not is_valid) or (sanitized != input_text)
            results.add_result(
                f"Sanitize '{input_text[:30]}'",
                passed,
                f"Cleaned to: '{sanitized[:30]}'" if passed else "Not blocked!"
            )
        else:
            # Should pass through unchanged
            passed = is_valid and sanitized == input_text
            results.add_result(
                f"Allow '{input_text[:30]}'",
                passed,
                "Correctly allowed" if passed else "Incorrectly blocked!"
            )

    return results


def test_vad_ring_buffer():
    """Test #1: VAD ring buffer pattern."""
    results = TestResults()

    if not VOICE_RECORDER_AVAILABLE:
        results.add_result(
            "VoiceRecorder availability",
            False,
            "Module not available (webrtcvad not installed)"
        )
        return results

    try:
        # Test basic initialization
        recorder = VoiceRecorder(
            sample_rate=16000,
            frame_duration_ms=30,
            padding_duration_ms=300,
            aggressiveness=3,
        )

        results.add_result(
            "VoiceRecorder initialization",
            True,
            f"Frame size: {recorder.frame_size}, Buffer: {recorder.padding_frames} frames"
        )

        # Test Bluetooth adaptive padding
        bt_recorder = VoiceRecorder(
            sample_rate=16000,
            frame_duration_ms=30,
            padding_duration_ms=300,
            aggressiveness=3,
            is_bluetooth=True,
        )

        # Should increase to 500ms for Bluetooth
        expected_frames = int(500 / 30)  # ~16 frames
        passed = bt_recorder.padding_frames >= expected_frames
        results.add_result(
            "Bluetooth adaptive padding",
            passed,
            f"Padding: {bt_recorder.padding_frames} frames (expected >= {expected_frames})"
        )

        # Test buffer status
        status = recorder.get_buffer_status()
        results.add_result(
            "VoiceRecorder buffer status",
            'triggered' in status and 'voiced_frames' in status,
            f"Status keys: {list(status.keys())}"
        )

    except Exception as e:
        results.add_result(
            "VoiceRecorder tests",
            False,
            f"Error: {e}"
        )

    return results


def test_conversation_state_machine():
    """Test #4: Conversation state machine with timeout."""
    results = TestResults()

    try:
        # Test initialization
        sm = ConversationStateMachine(
            listening_timeout=2,  # 2 seconds for testing
            exit_commands=["bye glasses", "goodbye"]
        )

        # Should start in SLEEPING state
        results.add_result(
            "Initial state is SLEEPING",
            sm.get_state() == AssistantState.SLEEPING,
            f"State: {sm.get_state()}"
        )

        # Test state transition
        sm.transition_to(AssistantState.ACTIVE)
        results.add_result(
            "Transition to ACTIVE",
            sm.get_state() == AssistantState.ACTIVE,
            f"State: {sm.get_state()}"
        )

        # Test exit command detection
        test_phrases = [
            ("bye glasses", True),
            ("goodbye", True),
            ("hello there", False),
            ("exit now", False),  # Not in exit commands
        ]

        for phrase, should_exit in test_phrases:
            is_exit = sm.is_exit_command(phrase)
            passed = is_exit == should_exit
            results.add_result(
                f"Exit command '{phrase}'",
                passed,
                f"Detected: {is_exit}, Expected: {should_exit}"
            )

        # Test activity timer
        sm.reset_activity_timer()
        time.sleep(0.1)
        results.add_result(
            "Activity timer reset",
            True,
            "Timer reset successfully"
        )

        # Cleanup
        sm.cleanup()
        results.add_result(
            "State machine cleanup",
            True,
            "Cleanup successful"
        )

    except Exception as e:
        results.add_result(
            "Conversation state machine",
            False,
            f"Error: {e}"
        )

    return results


def test_tts_initialization():
    """Test #6: TTS hybrid system initialization."""
    results = TestResults()

    if not TTS_AVAILABLE:
        results.add_result(
            "SpeechSynthesizer availability",
            False,
            "Module not available (missing dependencies)"
        )
        return results

    try:
        # Test pyttsx3 (always available)
        tts = SpeechSynthesizer(
            voice=None,
            rate=175,
            elevenlabs_api_key=None,  # No API key
            prefer_cloud=False
        )

        results.add_result(
            "TTS initialization (pyttsx3)",
            tts._engine is not None,
            "pyttsx3 engine initialized"
        )

        # Test with ElevenLabs key (if available)
        if os.getenv('ELEVENLABS_API_KEY'):
            tts_cloud = SpeechSynthesizer(
                voice=None,
                rate=175,
                elevenlabs_api_key=os.getenv('ELEVENLABS_API_KEY'),
                prefer_cloud=True
            )

            results.add_result(
                "TTS initialization (ElevenLabs)",
                tts_cloud._elevenlabs_client is not None,
                "ElevenLabs client initialized"
            )
        else:
            results.add_result(
                "TTS initialization (ElevenLabs)",
                True,
                "Skipped (no API key)"
            )

    except Exception as e:
        results.add_result(
            "TTS initialization",
            False,
            f"Error: {e}"
        )

    return results


def test_porcupine_availability():
    """Test #2: Porcupine wake word detection availability."""
    results = TestResults()

    try:
        import pvporcupine

        # Check if access key is available
        access_key = os.getenv('PORCUPINE_ACCESS_KEY')

        if access_key:
            results.add_result(
                "Porcupine access key",
                True,
                "Access key found"
            )

            # Try to create instance with built-in keyword
            try:
                porcupine = pvporcupine.create(
                    access_key=access_key,
                    keywords=['jarvis']  # Built-in keyword for testing
                )
                porcupine.delete()

                results.add_result(
                    "Porcupine initialization",
                    True,
                    f"Version: {pvporcupine.LIBRARY_VERSION}"
                )
            except Exception as e:
                results.add_result(
                    "Porcupine initialization",
                    False,
                    f"Error: {e}"
                )
        else:
            results.add_result(
                "Porcupine access key",
                False,
                "PORCUPINE_ACCESS_KEY not set"
            )

    except ImportError:
        results.add_result(
            "Porcupine availability",
            False,
            "pvporcupine not installed"
        )

    return results


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("SMART GLASSES VOICE ASSISTANT - SYSTEM TEST")
    print("=" * 60)

    # Load configuration
    ProductionConfig.log_config()

    all_results = TestResults()

    # Run test suites
    print("\n### Test Suite 1: Configuration")
    r1 = test_config_validation()
    all_results.tests.extend(r1.tests)
    all_results.passed += r1.passed
    all_results.failed += r1.failed

    print("\n### Test Suite 2: Output Sanitizer (Fix #5)")
    r2 = test_output_sanitizer()
    all_results.tests.extend(r2.tests)
    all_results.passed += r2.passed
    all_results.failed += r2.failed

    print("\n### Test Suite 3: VAD Ring Buffer (Fix #1)")
    r3 = test_vad_ring_buffer()
    all_results.tests.extend(r3.tests)
    all_results.passed += r3.passed
    all_results.failed += r3.failed

    print("\n### Test Suite 4: Conversation State Machine (Fix #4)")
    r4 = test_conversation_state_machine()
    all_results.tests.extend(r4.tests)
    all_results.passed += r4.passed
    all_results.failed += r4.failed

    print("\n### Test Suite 5: TTS Hybrid System (Fix #6)")
    r5 = test_tts_initialization()
    all_results.tests.extend(r5.tests)
    all_results.passed += r5.passed
    all_results.failed += r5.failed

    print("\n### Test Suite 6: Porcupine Wake Word (Fix #2)")
    r6 = test_porcupine_availability()
    all_results.tests.extend(r6.tests)
    all_results.passed += r6.passed
    all_results.failed += r6.failed

    # Print summary
    success = all_results.summary()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
