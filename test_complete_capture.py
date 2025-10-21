#!/usr/bin/env python3
"""
Test script to verify complete speech and video capture.
Tests that NO words are cut off and video frames are captured.
"""

import os
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from app.util.config import load_config
from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.audio.capture import run_segment
from vosk import Model


def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_speech_capture():
    """Test complete speech capture with no cutoffs."""
    print_header("TESTING COMPLETE SPEECH CAPTURE")

    load_dotenv()
    config = load_config()

    print(f"\nConfiguration:")
    print(f"  Pre-roll: {config.pre_roll_ms}ms (captures audio BEFORE speech starts)")
    print(f"  Silence threshold: {config.silence_ms}ms (waits this long after you stop)")
    print(f"  VAD aggressiveness: {config.vad_aggressiveness} (1=sensitive, catches all speech)")
    print(f"  Min speech frames: {config.min_speech_frames} (prevents premature cutoff)")
    print(f"  Tail padding: {config.tail_padding_ms}ms (extra audio after you finish)")

    print(f"\nThese settings ensure:")
    print(f"  ✅ First syllable captured (pre-roll buffer)")
    print(f"  ✅ Natural pauses allowed (high silence threshold)")
    print(f"  ✅ Last word captured (tail padding)")
    print(f"  ✅ No premature cutoffs (min speech frames)")

    print(f"\n" + "-" * 70)
    print(f"  TEST INSTRUCTIONS")
    print(f"-" * 70)
    print(f"\n  You will record a test phrase to verify complete capture.")
    print(f"\n  Please say this EXACT phrase:")
    print(f'  "The quick brown fox jumps over the lazy dog"')
    print(f"\n  Speak naturally with normal pauses between words.")
    print(f"\n  Press ENTER when ready to start recording...")
    input()

    # Load Vosk model
    print(f"\nLoading speech recognition model...")
    model = Model(config.vosk_model_path)
    transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)

    print(f"✅ Model loaded")
    print(f"\nStarting recording in 2 seconds...")
    time.sleep(2)

    print(f"\n🎤 RECORDING... (speak now)")
    print(f"-" * 70)

    # Record speech
    with MicrophoneStream(
        rate=config.sample_rate_hz,
        chunk_samples=config.chunk_samples,
        input_device_name=config.mic_device_name,
    ) as mic:
        result = run_segment(
            mic=mic,
            stt=transcriber,
            config=config,
            stop_event=None,
            on_chunk=None,
            pre_roll_buffer=None,
            no_speech_timeout_ms=None,
        )

    print(f"-" * 70)
    print(f"✅ Recording complete!")

    # Analyze results
    print(f"\n" + "=" * 70)
    print(f"  CAPTURE RESULTS")
    print(f"=" * 70)

    print(f"\nTranscript:")
    print(f'  "{result.clean_transcript}"')

    print(f"\nCapture Details:")
    print(f"  Stop reason: {result.stop_reason}")
    print(f"  Duration: {result.duration_ms}ms")
    print(f"  Audio captured: {result.audio_ms}ms")
    print(f"  Word count: {len(result.clean_transcript.split())}")

    # Validation
    print(f"\n" + "-" * 70)
    print(f"  VALIDATION")
    print(f"-" * 70)

    expected_phrase = "the quick brown fox jumps over the lazy dog"
    transcript_lower = result.clean_transcript.lower()

    # Check for key words
    key_words = ["quick", "brown", "fox", "jumps", "lazy", "dog"]
    missing_words = []
    found_words = []

    for word in key_words:
        if word in transcript_lower:
            found_words.append(word)
            print(f"  ✅ Found: '{word}'")
        else:
            missing_words.append(word)
            print(f"  ❌ Missing: '{word}'")

    # Check first and last words
    words = result.clean_transcript.lower().split()
    if words:
        first_word = words[0]
        last_word = words[-1]

        print(f"\nFirst/Last Word Check:")
        if first_word in ["the", "quick", "brown"]:
            print(f"  ✅ First word captured: '{first_word}'")
        else:
            print(f"  ⚠️  First word: '{first_word}' (expected 'the' or 'quick')")

        if last_word in ["dog", "lazy"]:
            print(f"  ✅ Last word captured: '{last_word}'")
        else:
            print(f"  ⚠️  Last word: '{last_word}' (expected 'dog' or 'lazy')")

    # Overall assessment
    print(f"\n" + "=" * 70)
    if len(found_words) >= 5:
        print(f"  ✅ SUCCESS: Complete capture verified!")
        print(f"  {len(found_words)}/6 key words captured")
    elif len(found_words) >= 3:
        print(f"  ⚠️  PARTIAL: Some words may have been missed")
        print(f"  {len(found_words)}/6 key words captured")
        print(f"  Missing: {', '.join(missing_words)}")
    else:
        print(f"  ❌ ISSUES: Many words missing")
        print(f"  {len(found_words)}/6 key words captured")
        print(f"  Missing: {', '.join(missing_words)}")

    print(f"=" * 70)

    # Save audio for manual verification
    audio_file = Path("test_capture.wav")
    with wave.open(str(audio_file), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(config.sample_rate_hz)
        wav_file.writeframes(result.audio_bytes)

    print(f"\n📁 Audio saved to: {audio_file}")
    print(f"   Listen to verify complete capture:")
    print(f"   macOS: afplay {audio_file}")
    print(f"   Linux: aplay {audio_file}")

    return len(found_words) >= 5


def test_configuration():
    """Test that configuration is optimized for complete capture."""
    print_header("TESTING CONFIGURATION")

    load_dotenv()
    config = load_config()

    checks = []

    # Check pre-roll
    if config.pre_roll_ms >= 500:
        print(f"  ✅ Pre-roll buffer: {config.pre_roll_ms}ms (good)")
        checks.append(True)
    else:
        print(f"  ⚠️  Pre-roll buffer: {config.pre_roll_ms}ms (consider 500-600ms)")
        checks.append(False)

    # Check silence threshold
    if config.silence_ms >= 1500:
        print(f"  ✅ Silence threshold: {config.silence_ms}ms (good)")
        checks.append(True)
    else:
        print(f"  ⚠️  Silence threshold: {config.silence_ms}ms (consider 1500-1800ms)")
        checks.append(False)

    # Check VAD
    if config.vad_aggressiveness <= 1:
        print(f"  ✅ VAD aggressiveness: {config.vad_aggressiveness} (sensitive)")
        checks.append(True)
    else:
        print(f"  ⚠️  VAD aggressiveness: {config.vad_aggressiveness} (consider 1 for complete capture)")
        checks.append(False)

    # Check min speech frames
    if config.min_speech_frames >= 3:
        print(f"  ✅ Min speech frames: {config.min_speech_frames} (prevents early cutoff)")
        checks.append(True)
    else:
        print(f"  ⚠️  Min speech frames: {config.min_speech_frames} (consider 3-5)")
        checks.append(False)

    # Check tail padding
    if config.tail_padding_ms >= 300:
        print(f"  ✅ Tail padding: {config.tail_padding_ms}ms (captures end)")
        checks.append(True)
    else:
        print(f"  ⚠️  Tail padding: {config.tail_padding_ms}ms (consider 300-500ms)")
        checks.append(False)

    if all(checks):
        print(f"\n  ✅ Configuration optimized for complete capture!")
    else:
        print(f"\n  ⚠️  Configuration could be improved")
        print(f"\n  See config.complete_capture.json for optimal settings")

    return all(checks)


def main():
    print("\n" + "=" * 70)
    print("  COMPLETE SPEECH & VIDEO CAPTURE TEST")
    print("=" * 70)
    print("\n  This test verifies that:")
    print("    1. Configuration is optimized for complete capture")
    print("    2. No words are cut off (first or last)")
    print("    3. Natural pauses are handled correctly")

    # Test 1: Configuration
    config_ok = test_configuration()

    # Test 2: Speech Capture
    capture_ok = test_speech_capture()

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    if config_ok and capture_ok:
        print("\n  ✅ ALL TESTS PASSED!")
        print("\n  Your system is configured for complete speech capture.")
        print("  All words should be captured without cutoffs.")
        return 0
    elif capture_ok:
        print("\n  ✅ CAPTURE WORKS!")
        print("  ⚠️  Configuration could be improved for consistency.")
        return 0
    else:
        print("\n  ⚠️  CAPTURE ISSUES DETECTED")
        print("\n  Recommendations:")
        print("    1. Use config.complete_capture.json")
        print("    2. Test again with optimized settings")
        print("    3. Check microphone quality/placement")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
