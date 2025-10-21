#!/usr/bin/env python3
"""
CRITICAL BUG DIAGNOSTIC - Simplified Test
Tests wake word, speech capture, and TTS timing with detailed logs.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.util.config import load_config
from app.audio.stt import StreamingTranscriber
from app.audio.tts import SpeechSynthesizer
from app.audio.mic import MicrophoneStream
from app.audio.capture import run_segment
from vosk import Model


def main():
    print("="*80)
    print("CRITICAL BUG DIAGNOSTIC TOOL")
    print("="*80)
    print("\nThis will test:")
    print("1. Speech capture (say something after the prompt)")
    print("2. TTS timing (1st turn)")
    print("3. Speech capture again (2nd turn)")
    print("4. TTS timing (2nd turn) - THIS IS WHERE THE BUG USUALLY APPEARS")
    print("\nMake sure your microphone is working!\n")
    
    input("Press Enter to start...")
    
    # Load config
    print("\n[1/6] Loading configuration...")
    config = load_config()
    print(f"      Config loaded: VAD={config.vad_aggressiveness}, silence={config.silence_ms}ms")
    
    # Load model
    print("\n[2/6] Loading Vosk model...")
    model = Model(config.vosk_model_path)
    print(f"      Model loaded from: {config.vosk_model_path}")
    
    # Create transcriber
    print("\n[3/6] Creating transcriber...")
    transcriber = StreamingTranscriber(
        sample_rate=config.sample_rate_hz,
        model=model,
        enable_words=True,
    )
    print("      Transcriber ready")
    
    # Create TTS
    print("\n[4/6] Creating TTS engine...")
    tts = SpeechSynthesizer(voice=config.tts_voice, rate=config.tts_rate)
    print("      TTS engine ready")
    
    # Test Turn 1
    print("\n" + "="*80)
    print("TURN 1: SPEECH CAPTURE")
    print("="*80)
    print("Speak a test phrase (e.g., 'Hello, this is a test')...")
    print("Listening...")
    
    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        start_time = time.monotonic()
        result1 = run_segment(
            mic=mic,
            stt=transcriber,
            config=config,
            no_speech_timeout_ms=15000,
        )
        capture1_ms = int((time.monotonic() - start_time) * 1000)
    
    print(f"\n✓ Captured: '{result1.clean_transcript}'")
    print(f"  Duration: {capture1_ms}ms")
    print(f"  Stop reason: {result1.stop_reason}")
    
    if not result1.clean_transcript:
        print("\n⚠️  ERROR: No speech captured! Check microphone.")
        return 1
    
    # Test TTS Turn 1
    print("\n" + "="*80)
    print("TURN 1: TTS OUTPUT")
    print("="*80)
    print("Speaking response...")
    
    tts.set_turn_index(0)
    start_time = time.monotonic()
    tts.speak("This is the first response. Testing TTS timing.")
    tts1_ms = int((time.monotonic() - start_time) * 1000)
    
    print(f"\n✓ TTS Turn 1 completed in {tts1_ms}ms")
    
    # Small delay
    time.sleep(1.0)
    
    # Test Turn 2
    print("\n" + "="*80)
    print("TURN 2: SPEECH CAPTURE")
    print("="*80)
    print("Speak another test phrase...")
    print("Listening...")
    
    transcriber.reset()
    
    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        start_time = time.monotonic()
        result2 = run_segment(
            mic=mic,
            stt=transcriber,
            config=config,
            no_speech_timeout_ms=15000,
        )
        capture2_ms = int((time.monotonic() - start_time) * 1000)
    
    print(f"\n✓ Captured: '{result2.clean_transcript}'")
    print(f"  Duration: {capture2_ms}ms")
    print(f"  Stop reason: {result2.stop_reason}")
    
    if not result2.clean_transcript:
        print("\n⚠️  ERROR: No speech captured on turn 2! This is the bug.")
        return 1
    
    # Test TTS Turn 2 - THIS IS WHERE THE BUG APPEARS
    print("\n" + "="*80)
    print("TURN 2: TTS OUTPUT (CRITICAL TEST)")
    print("="*80)
    print("Speaking response...")
    print("⚠️  Watch for delay here - this is where 45-60s delays occur!")
    
    tts.set_turn_index(1)
    start_time = time.monotonic()
    tts.speak("This is the second response. Testing for TTS delay bug.")
    tts2_ms = int((time.monotonic() - start_time) * 1000)
    
    print(f"\n✓ TTS Turn 2 completed in {tts2_ms}ms")
    
    # Analysis
    print("\n" + "="*80)
    print("DIAGNOSTIC RESULTS")
    print("="*80)
    print(f"\nTurn 1:")
    print(f"  Speech capture: {capture1_ms}ms")
    print(f"  TTS output: {tts1_ms}ms")
    print(f"\nTurn 2:")
    print(f"  Speech capture: {capture2_ms}ms")
    print(f"  TTS output: {tts2_ms}ms")
    
    print(f"\nTTS Comparison:")
    print(f"  Turn 1: {tts1_ms}ms")
    print(f"  Turn 2: {tts2_ms}ms")
    
    if tts2_ms > tts1_ms * 3:
        ratio = tts2_ms / tts1_ms
        print(f"\n⚠️  CRITICAL BUG DETECTED!")
        print(f"  Turn 2 TTS is {ratio:.1f}x slower than Turn 1")
        print(f"  This indicates a TTS engine reinitialization issue.")
        return 1
    elif tts2_ms > 10000:
        print(f"\n⚠️  WARNING: Turn 2 TTS took {tts2_ms}ms (>10s)")
        print(f"  This is abnormally slow.")
        return 1
    else:
        print(f"\n✓ TTS timing is normal (ratio: {tts2_ms/tts1_ms:.2f}x)")
    
    if not result1.clean_transcript or not result2.clean_transcript:
        print("\n⚠️  Speech capture failed on one or more turns")
        return 1
    
    print("\n✓ All tests passed!")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n⚠️  ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
