#!/usr/bin/env python3
"""
CRITICAL BUG DIAGNOSTIC TOOL
Tests the complete voice assistant flow with detailed timing and logging.

This script diagnoses:
1. Wake word detection and timing
2. Speech capture reliability
3. TTS delay issues (especially on 2nd turn)
4. Multi-turn conversation flow
"""

import time
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from app.util.config import load_config
from app.audio.stt import StreamingTranscriber
from app.audio.tts import SpeechSynthesizer
from app.audio.wake import WakeWordListener
from app.audio.mic import MicrophoneStream
from app.audio.capture import run_segment
from vosk import Model
import threading


class DiagnosticLogger:
    """Detailed timestamp logger for debugging"""
    
    def __init__(self):
        self.start_time = time.monotonic()
        self.events = []
    
    def log(self, event: str, details: str = ""):
        elapsed_ms = int((time.monotonic() - self.start_time) * 1000)
        timestamp = time.strftime("%H:%M:%S")
        msg = f"[{timestamp}] +{elapsed_ms:6d}ms | {event}"
        if details:
            msg += f" | {details}"
        print(msg)
        self.events.append((elapsed_ms, event, details))
        return elapsed_ms


def test_wake_word_detection(config, transcriber, logger):
    """Test 1: Wake word detection timing"""
    print("\n" + "="*80)
    print("TEST 1: WAKE WORD DETECTION")
    print("="*80)
    print("Say 'Hey Glasses' to test wake word detection...")
    print("This will test if wake word is detected and triggers state change.\n")
    
    wake_detected = threading.Event()
    pre_roll_buffer = []
    
    def on_wake_detect(buffer):
        logger.log("WAKE_DETECTED", f"Pre-roll buffer size: {len(buffer)} frames")
        nonlocal pre_roll_buffer
        pre_roll_buffer = list(buffer)
        wake_detected.set()
    
    logger.log("WAKE_LISTENER_START", "Starting wake word listener...")
    
    wake_listener = WakeWordListener(
        wake_variants=config.wake_variants,
        on_detect=on_wake_detect,
        transcriber=transcriber,
        sample_rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        mic_device_name=config.mic_device_name,
        pre_roll_ms=config.pre_roll_ms,
        sensitivity=config.wake_sensitivity,
    )
    
    wake_listener.start()
    
    # Wait for wake word (max 30 seconds)
    if wake_detected.wait(timeout=30):
        logger.log("WAKE_SUCCESS", "Wake word detected successfully!")
        wake_listener.stop()
        return True, pre_roll_buffer
    else:
        logger.log("WAKE_TIMEOUT", "No wake word detected in 30 seconds")
        wake_listener.stop()
        return False, []


def test_speech_capture(config, transcriber, logger, pre_roll_buffer=None):
    """Test 2: Speech capture timing and reliability"""
    print("\n" + "="*80)
    print("TEST 2: SPEECH CAPTURE")
    print("="*80)
    print("Speak a test phrase after the beep...")
    print("This will test if speech is captured immediately and completely.\n")
    
    logger.log("CAPTURE_START", "Opening microphone stream...")
    
    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        logger.log("MIC_OPENED", f"Mic device: {config.mic_device_name or 'default'}")
        logger.log("CAPTURE_LISTENING", "Listening for speech...")
        
        # Log when first audio frame is received
        first_frame_time = logger.log("FIRST_FRAME", "Reading first audio frame...")
        
        result = run_segment(
            mic=mic,
            stt=transcriber,
            config=config,
            pre_roll_buffer=pre_roll_buffer,
            no_speech_timeout_ms=15000,
        )
        
        capture_end_time = logger.log("CAPTURE_END", f"Stop reason: {result.stop_reason}")
        logger.log("TRANSCRIPT", f"Text: '{result.clean_transcript}'")
        logger.log("AUDIO_STATS", f"Duration: {result.duration_ms}ms, Audio: {result.audio_ms}ms")
        
        if result.average_confidence:
            logger.log("CONFIDENCE", f"Average: {result.average_confidence:.2%}")
        
        return result


def test_tts_timing(tts, logger, text, turn_number):
    """Test 3: TTS timing (especially important for 2nd turn)"""
    print("\n" + "="*80)
    print(f"TEST 3: TTS TIMING (Turn {turn_number})")
    print("="*80)
    print(f"Speaking: '{text}'\n")
    
    logger.log(f"TTS_START_TURN_{turn_number}", f"Text length: {len(text)} chars")
    
    # Timestamp before TTS
    pre_tts = time.monotonic()
    
    # Speak
    tts.speak(text)
    
    # Timestamp after TTS
    post_tts = time.monotonic()
    tts_duration_ms = int((post_tts - pre_tts) * 1000)
    
    logger.log(f"TTS_END_TURN_{turn_number}", f"Duration: {tts_duration_ms}ms")
    
    if turn_number == 2 and tts_duration_ms > 10000:
        logger.log("TTS_DELAY_BUG", f"⚠️  CRITICAL: 2nd turn TTS took {tts_duration_ms}ms (>10s)!")
    
    return tts_duration_ms


def test_multi_turn_flow(config, transcriber, tts, logger):
    """Test 4: Multi-turn conversation flow"""
    print("\n" + "="*80)
    print("TEST 4: MULTI-TURN CONVERSATION")
    print("="*80)
    print("This will test 2 conversation turns to check for delays.\n")
    
    # Turn 1
    print("\n--- TURN 1 ---")
    logger.log("TURN_1_START", "Starting first turn...")
    
    result1 = test_speech_capture(config, transcriber, logger)
    if not result1.clean_transcript:
        logger.log("TURN_1_EMPTY", "⚠️  No speech captured in turn 1")
        return False
    
    tts_time_1 = test_tts_timing(tts, logger, "This is the first response.", 1)
    logger.log("TURN_1_COMPLETE", f"Total TTS time: {tts_time_1}ms")
    
    # Small delay between turns
    time.sleep(1.0)
    
    # Turn 2 - THIS IS WHERE THE BUG USUALLY APPEARS
    print("\n--- TURN 2 ---")
    logger.log("TURN_2_START", "Starting second turn...")
    
    result2 = test_speech_capture(config, transcriber, logger)
    if not result2.clean_transcript:
        logger.log("TURN_2_EMPTY", "⚠️  No speech captured in turn 2")
        return False
    
    tts_time_2 = test_tts_timing(tts, logger, "This is the second response.", 2)
    logger.log("TURN_2_COMPLETE", f"Total TTS time: {tts_time_2}ms")
    
    # Compare timings
    print("\n" + "="*80)
    print("TIMING COMPARISON")
    print("="*80)
    print(f"Turn 1 TTS: {tts_time_1}ms")
    print(f"Turn 2 TTS: {tts_time_2}ms")
    
    if tts_time_2 > tts_time_1 * 3:
        print(f"\n⚠️  CRITICAL BUG DETECTED: Turn 2 is {tts_time_2 / tts_time_1:.1f}x slower!")
        logger.log("BUG_CONFIRMED", f"Turn 2 delay: {tts_time_2}ms vs {tts_time_1}ms")
        return False
    else:
        print("\n✓ TTS timing is consistent across turns")
        logger.log("TTS_OK", "No significant delay detected")
        return True


def main():
    print("="*80)
    print("CRITICAL BUG DIAGNOSTIC TOOL")
    print("="*80)
    print("\nThis tool will test:")
    print("1. Wake word detection and timing")
    print("2. Speech capture reliability")
    print("3. TTS delay issues (especially 2nd turn)")
    print("4. Multi-turn conversation flow")
    print("\nMake sure your microphone is working and not muted.\n")
    
    logger = DiagnosticLogger()
    
    # Load configuration
    logger.log("CONFIG_LOAD", "Loading configuration...")
    config = load_config()
    
    logger.log("CONFIG_LOADED", f"Vosk model: {config.vosk_model_path}")
    logger.log("CONFIG_PARAMS", f"VAD: {config.vad_aggressiveness}, Silence: {config.silence_ms}ms")
    
    # Initialize components
    logger.log("VOSK_INIT", "Loading Vosk model...")
    model = Model(config.vosk_model_path)
    
    logger.log("TRANSCRIBER_INIT", "Creating transcriber...")
    transcriber = StreamingTranscriber(
        sample_rate=config.sample_rate_hz,
        model=model,
        enable_words=True,
        max_alternatives=config.vosk_max_alternatives,
    )
    
    logger.log("TTS_INIT", "Creating TTS engine...")
    tts = SpeechSynthesizer(
        voice=config.tts_voice,
        rate=config.tts_rate,
    )
    
    logger.log("INIT_COMPLETE", "All components initialized")
    
    # Run tests
    try:
        # Test 1: Wake word
        wake_success, pre_roll = test_wake_word_detection(config, transcriber, logger)
        if not wake_success:
            print("\n⚠️  Wake word test failed. Skipping remaining tests.")
            return 1
        
        # Test 2: Speech capture
        transcriber.reset()
        result = test_speech_capture(config, transcriber, logger, pre_roll)
        if not result.clean_transcript:
            print("\n⚠️  Speech capture test failed. Check microphone and VAD settings.")
            return 1
        
        # Test 3 & 4: Multi-turn with TTS timing
        transcriber.reset()
        multi_turn_success = test_multi_turn_flow(config, transcriber, tts, logger)
        
        # Final summary
        print("\n" + "="*80)
        print("DIAGNOSTIC SUMMARY")
        print("="*80)
        
        print("\n✓ Wake word detection: PASSED" if wake_success else "\n✗ Wake word detection: FAILED")
        print("✓ Speech capture: PASSED" if result.clean_transcript else "✗ Speech capture: FAILED")
        print("✓ Multi-turn flow: PASSED" if multi_turn_success else "✗ Multi-turn flow: FAILED")
        
        if not multi_turn_success:
            print("\n⚠️  CRITICAL BUGS DETECTED - See detailed logs above")
            return 1
        else:
            print("\n✓ All tests passed!")
            return 0
            
    except KeyboardInterrupt:
        logger.log("INTERRUPTED", "Test interrupted by user")
        return 1
    except Exception as e:
        logger.log("ERROR", f"Exception: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
