#!/usr/bin/env python3
"""Manual recording test - simulates the full flow without GUI."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.util.config import load_config
from app.audio.stt import StreamingTranscriber
from app.audio.tts import SpeechSynthesizer
from app.segment import SegmentRecorder
from vosk import Model

print("=" * 60)
print("MANUAL RECORDING TEST")
print("=" * 60)

# Load config
print("\n1. Loading configuration...")
config = load_config()
print(f"   ✓ Silence threshold: {config.silence_ms}ms")
print(f"   ✓ Max segment: {config.max_segment_s}s")
print(f"   ✓ Chunk samples: {config.chunk_samples}")

# Initialize STT
print("\n2. Initializing STT...")
model = Model(config.vosk_model_path)
transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
print(f"   ✓ STT ready")

# Initialize recorder
print("\n3. Initializing segment recorder...")
recorder = SegmentRecorder(config, transcriber)
print(f"   ✓ Recorder ready")

# Initialize TTS
print("\n4. Initializing TTS...")
tts = SpeechSynthesizer(voice=config.tts_voice, rate=config.tts_rate)
print(f"   ✓ TTS ready")

# Do a manual recording
print("\n5. Starting manual recording...")
print(f"   📢 SPEAK NOW! Say something and wait for silence ({config.silence_ms}ms)")
print(f"   Or say 'done' to stop early")
print(f"   Press Ctrl+C to cancel")
print()

try:
    result = recorder.record_segment()

    print(f"\n6. Recording complete!")
    print(f"   Stop reason: {result.stop_reason}")
    print(f"   Duration: {result.duration_ms}ms")
    print(f"   Audio: {result.audio_ms}ms")
    print(f"   Transcript: '{result.transcript}'")
    print(f"   Clean transcript: '{result.clean_transcript}'")

    if not result.clean_transcript:
        print(f"\n   ⚠ WARNING: No speech detected!")
        print(f"   Possible causes:")
        print(f"   - Microphone volume too low")
        print(f"   - Wrong microphone selected")
        print(f"   - Not speaking loud enough")
        print(f"   - VAD too aggressive (try vad_aggressiveness: 1)")
    else:
        print(f"\n   ✓ Speech captured successfully!")

        # Test TTS
        print(f"\n7. Testing TTS response...")
        test_response = f"I heard you say: {result.clean_transcript}"
        print(f"   Speaking: \"{test_response}\"")
        tts.speak(test_response)
        print(f"   ✓ TTS completed")

        # Try again to test if TTS still works
        print(f"\n8. Testing TTS again (should still work)...")
        tts.speak("Testing TTS a second time")
        print(f"   ✓ Second TTS completed")

        print(f"\n   ✅ SUCCESS: Both recording and TTS work!")

except KeyboardInterrupt:
    print(f"\n   Cancelled by user")
except Exception as e:
    print(f"\n   ✗ ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
print("MANUAL TEST COMPLETE")
print("=" * 60)
