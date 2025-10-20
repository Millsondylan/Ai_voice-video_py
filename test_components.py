#!/usr/bin/env python3
"""Simple component test without voice input required."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("COMPONENT TEST (No voice input needed)")
print("=" * 60)

# Test 1: Configuration
print("\n1. Testing configuration...")
try:
    from app.util.config import load_config
    config = load_config()
    print(f"   ✓ Config loaded")
    print(f"     sample_rate_hz: {config.sample_rate_hz}")
    print(f"     chunk_samples: {config.chunk_samples}")
    print(f"     silence_ms: {config.silence_ms}")
    print(f"     mic_device_name: {config.mic_device_name}")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test 2: List microphones
print("\n2. Listing microphone devices...")
try:
    from app.audio.mic import MicrophoneStream
    devices = MicrophoneStream.list_input_devices()
    if devices:
        print(f"   ✓ Found {len(devices)} devices:")
        for dev in devices:
            print(f"     [{dev['index']}] {dev['name']}")
    else:
        print(f"   ⚠ No input devices found")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 3: Open microphone (no read)
print("\n3. Testing microphone open...")
try:
    from app.audio.mic import MicrophoneStream
    mic = MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    )
    mic.start()
    print(f"   ✓ Microphone opened (chunk size: {mic.chunk})")
    mic.stop()
    mic.terminate()
    print(f"   ✓ Microphone closed")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    print(f"   HINT: Check microphone permissions")
    import traceback
    traceback.print_exc()

# Test 4: TTS initialization
print("\n4. Testing TTS initialization...")
try:
    from app.audio.tts import SpeechSynthesizer
    tts = SpeechSynthesizer(voice=config.tts_voice, rate=config.tts_rate)
    print(f"   ✓ TTS initialized")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 5: TTS speak (sync)
print("\n5. Testing TTS sync speak...")
try:
    tts.speak("Test one")
    print(f"   ✓ First TTS call completed")
    tts.speak("Test two")
    print(f"   ✓ Second TTS call completed")
    tts.speak("Test three")
    print(f"   ✓ Third TTS call completed")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 6: TTS speak (async)
print("\n6. Testing TTS async speak...")
try:
    import time
    thread1 = tts.speak_async("Async test one")
    thread1.join()
    print(f"   ✓ First async TTS completed")

    thread2 = tts.speak_async("Async test two")
    thread2.join()
    print(f"   ✓ Second async TTS completed")

    thread3 = tts.speak_async("Async test three")
    thread3.join()
    print(f"   ✓ Third async TTS completed")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 7: STT initialization
print("\n7. Testing STT initialization...")
try:
    from app.audio.stt import StreamingTranscriber
    from vosk import Model

    if not config.vosk_model_path or not Path(config.vosk_model_path).exists():
        print(f"   ✗ Vosk model not found at: {config.vosk_model_path}")
    else:
        model = Model(config.vosk_model_path)
        stt = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
        print(f"   ✓ STT initialized")

        # Test methods exist
        stt.start()
        print(f"   ✓ stt.start() works")
        stt.end()
        print(f"   ✓ stt.end() works")
        result = stt.result()
        print(f"   ✓ stt.result() works (empty: '{result}')")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()

# Test 8: Logger
print("\n8. Testing logger...")
try:
    from app.util.log import get_event_logger
    logger = get_event_logger()
    logger.reset()
    logger.log_wake_detected()
    logger.log_segment_start(
        vad_aggr=config.vad_aggressiveness,
        silence_ms=config.silence_ms,
        chunk_ms=max(1, int((config.chunk_samples / config.sample_rate_hz) * 1000)),
        pre_roll_ms=config.pre_roll_ms,
    )
    logger.log_segment_stop("test", "hello world", 1000, 900)
    logger.log_tts_started("test")
    logger.log_tts_done()
    print(f"   ✓ Logger works")
    summary = logger.get_summary()
    print(f"   ✓ Summary: {len(summary)} fields tracked")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("COMPONENT TEST COMPLETE")
print("=" * 60)
print("\nIf all tests passed, components are working.")
print("Issues are likely in:")
print("  - Microphone permissions (if mic test failed)")
print("  - Audio device conflicts (if TTS works once then fails)")
print("  - Vosk model (if STT failed)")
print("=" * 60)
