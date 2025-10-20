#!/usr/bin/env python3
"""
Diagnostic test script for the audio system.
Run this to debug voice capture and TTS issues.
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.audio.mic import MicrophoneStream
from app.audio.tts import SpeechSynthesizer
from app.audio.stt import StreamingTranscriber
from app.audio.wake import WakeWordListener
from app.util.config import load_config
from vosk import Model

print("=" * 60)
print("AUDIO SYSTEM DIAGNOSTIC TEST")
print("=" * 60)

# Load configuration
print("\n1. Loading configuration...")
try:
    config = load_config()
    print(f"   ✓ Config loaded")
    print(f"   - Sample rate: {config.sample_rate_hz} Hz")
    print(f"   - Chunk samples: {config.chunk_samples}")
    print(f"   - Silence threshold: {config.silence_ms} ms")
    print(f"   - Max segment: {config.max_segment_s} s")
    print(f"   - Wake word: {config.wake_word}")
    print(f"   - Mic device: {config.mic_device_name or 'default'}")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test microphone listing
print("\n2. Listing audio input devices...")
try:
    devices = MicrophoneStream.list_input_devices()
    print(f"   ✓ Found {len(devices)} input devices:")
    for dev in devices:
        marker = " ← SELECTED" if config.mic_device_name and config.mic_device_name in dev['name'] else ""
        print(f"   - [{dev['index']}] {dev['name']} ({dev['channels']} channels){marker}")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    sys.exit(1)

# Test microphone open
print("\n3. Testing microphone access...")
try:
    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        print(f"   ✓ Microphone opened successfully")
        print(f"   - Reading test chunk...")
        chunk = mic.read()
        print(f"   ✓ Read {len(chunk)} bytes")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    print(f"   HINT: Check microphone permissions in System Settings > Privacy & Security > Microphone")
    sys.exit(1)

# Test TTS
print("\n4. Testing text-to-speech...")
try:
    tts = SpeechSynthesizer(voice=config.tts_voice, rate=config.tts_rate)
    print(f"   ✓ TTS initialized")
    print(f"   - Speaking test message...")
    tts.speak("Audio system test. Can you hear me?")
    print(f"   ✓ TTS completed successfully")
except Exception as e:
    print(f"   ✗ FAILED: {e}")
    print(f"   WARNING: TTS may not work, but continuing...")

# Test STT
print("\n5. Testing speech-to-text...")
try:
    model_path = config.vosk_model_path
    if not model_path or not Path(model_path).exists():
        print(f"   ✗ FAILED: Vosk model not found at {model_path}")
        print(f"   HINT: Download from https://alphacephei.com/vosk/models")
        sys.exit(1)

    print(f"   - Loading Vosk model from {model_path}...")
    model = Model(model_path)
    print(f"   ✓ Model loaded")

    stt = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
    print(f"   ✓ STT initialized")

    print(f"\n   📢 SPEAK NOW: Say something for 2 seconds...")
    stt.start()

    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        for i in range(100):  # ~2 seconds at 20ms chunks
            chunk = mic.read()
            stt.feed(chunk)
            if i % 25 == 0:
                print(f"   - Partial: \"{stt.combined_text}\"")

    stt.end()
    final = stt.result()
    print(f"\n   ✓ Final transcript: \"{final}\"")

    if not final:
        print(f"   ⚠ WARNING: No speech detected. Check:")
        print(f"      - Microphone volume is up")
        print(f"      - You're speaking clearly")
        print(f"      - Correct microphone is selected")

except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test wake word detection
print("\n6. Testing wake word detection...")
try:
    wake_detected = False

    def on_detect():
        global wake_detected
        wake_detected = True
        print(f"\n   ✓ WAKE WORD DETECTED!")

    listener = WakeWordListener(
        wake_variants=[config.wake_word],
        on_detect=on_detect,
        transcriber=stt,
        sample_rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        mic_device_name=config.mic_device_name,
    )

    print(f"   ✓ Wake listener created")
    print(f"\n   📢 SPEAK NOW: Say '{config.wake_word}' within 5 seconds...")

    listener.start()

    for i in range(5):
        if wake_detected:
            break
        print(f"   - Waiting... ({5-i}s remaining)")
        time.sleep(1)

    listener.stop()
    listener.join(timeout=2)

    if wake_detected:
        print(f"   ✓ Wake word detection WORKING!")
    else:
        print(f"   ⚠ WARNING: Wake word not detected")
        print(f"   HINT: Try speaking louder or closer to microphone")

except Exception as e:
    print(f"   ✗ FAILED: {e}")
    import traceback
    traceback.print_exc()

# Summary
print("\n" + "=" * 60)
print("DIAGNOSTIC SUMMARY")
print("=" * 60)
print("If all tests passed, the audio system should work.")
print("If any test failed, check the hints provided above.")
print("\nCommon issues:")
print("- Microphone permissions not granted")
print("- Wrong microphone selected")
print("- Vosk model not downloaded")
print("- Microphone volume too low")
print("=" * 60)
