#!/usr/bin/env python3
"""
Comprehensive Vosk STT Debugging Script
Tests Vosk at multiple levels to identify the transcription issue.
"""

import json
import sys
import time
import struct
import math
from vosk import Model, KaldiRecognizer
import pyaudio

def test_audio_levels():
    """Test 1: Check if microphone is producing audio."""
    print("\n" + "="*60)
    print("TEST 1: AUDIO INPUT LEVELS")
    print("="*60)
    print("Speak into the microphone for 5 seconds...")
    print("You should see bars moving when you speak\n")

    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=1024
    )

    max_rms = 0
    avg_rms = 0
    samples = 0

    for i in range(80):  # 5 seconds
        try:
            data = stream.read(1024, exception_on_overflow=False)
            shorts = struct.unpack('h' * 1024, data)
            rms = math.sqrt(sum(s**2 for s in shorts) / len(shorts))
            max_rms = max(max_rms, rms)
            avg_rms += rms
            samples += 1

            bars = '#' * min(50, int(rms / 100))
            print(f'\r{int(rms):>5} |{bars:<50}|', end='', flush=True)
            time.sleep(0.05)
        except:
            pass

    stream.stop_stream()
    stream.close()
    p.terminate()

    avg_rms = avg_rms / samples if samples > 0 else 0

    print(f"\n\nResults:")
    print(f"  Max RMS:     {int(max_rms)}")
    print(f"  Average RMS: {int(avg_rms)}")

    if max_rms < 300:
        print("  ⚠️  WARNING: Very low audio! Increase microphone volume")
        return False
    elif max_rms < 1000:
        print("  ⚠️  Audio is weak. Consider speaking louder or increasing mic volume")
        return False
    else:
        print("  ✅ Audio levels look good!")
        return True

def test_vosk_simple():
    """Test 2: Simple Vosk recognition test."""
    print("\n" + "="*60)
    print("TEST 2: BASIC VOSK RECOGNITION")
    print("="*60)
    print("Loading Vosk model...")

    try:
        model = Model("models/vosk-model-en-us-0.22")
        print("✅ Model loaded")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        return False

    rec = KaldiRecognizer(model, 16000)
    rec.SetWords(True)

    print("\nSpeak CLEARLY and SLOWLY:")
    print("  Try: 'hello', 'testing', 'one two three'\n")
    print("Listening for 10 seconds...\n")

    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=8000
    )

    got_partial = False
    got_final = False
    last_partial = ""

    for i in range(20):  # 10 seconds
        data = stream.read(8000, exception_on_overflow=False)

        if rec.AcceptWaveform(data):
            result = json.loads(rec.Result())
            text = result.get('text', '')
            if text:
                print(f"\n✅ FINAL: '{text}'")
                got_final = True
        else:
            partial = json.loads(rec.PartialResult())
            partial_text = partial.get('partial', '')
            if partial_text and partial_text != last_partial:
                print(f"\r🔄 PARTIAL: '{partial_text}'", end='', flush=True)
                got_partial = True
                last_partial = partial_text

    # Get final result
    result = json.loads(rec.FinalResult())
    final_text = result.get('text', '')

    stream.stop_stream()
    stream.close()
    p.terminate()

    print(f"\n\nFINAL RESULT: '{final_text}'")
    print(f"\nResults:")
    print(f"  Got partial results: {got_partial}")
    print(f"  Got final result: {got_final}")
    print(f"  Final text: '{final_text}'")

    if not got_partial and not got_final and not final_text:
        print("\n❌ FAILED: Vosk heard nothing at all")
        print("   Possible causes:")
        print("   1. Audio too quiet (see Test 1)")
        print("   2. Speech not clear enough for small model")
        print("   3. Accent/pronunciation not recognized")
        print("   4. Background noise too high")
        return False
    elif not final_text:
        print("\n⚠️  WARNING: Got partial results but no final text")
        print("   Try speaking more slowly and clearly")
        return False
    else:
        print("\n✅ SUCCESS: Vosk is working!")
        return True

def test_vosk_with_stt_class():
    """Test 3: Test using the StreamingTranscriber class."""
    print("\n" + "="*60)
    print("TEST 3: STREAMING TRANSCRIBER CLASS")
    print("="*60)

    try:
        from vosk import Model
        from app.audio.stt import StreamingTranscriber
        from app.audio.mic import MicrophoneStream
        from app.util.config import load_config

        config = load_config()
        print(f"Config loaded: {config.vosk_model_path}")

        model = Model(config.vosk_model_path)
        transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)

        print("Speak for 8 seconds...")
        print()

        transcriber.start()

        with MicrophoneStream(
            rate=config.sample_rate_hz,
            chunk_samples=config.chunk_samples,
            input_device_name=config.mic_device_name,
        ) as mic:
            for i in range(400):  # ~8 seconds
                frame = mic.read(config.chunk_samples)
                result = transcriber.feed(frame)
                if result.text and not result.is_final:
                    print(f"\r[PARTIAL] {result.text}", end='', flush=True)
                elif result.text and result.is_final:
                    print(f"\n[FINAL] {result.text}")

        transcriber.end()
        final = transcriber.result()

        print(f"\n\nFinal transcript: '{final}'")
        print(f"Word count: {len(final.split())}")

        if not final:
            print("\n❌ FAILED: StreamingTranscriber got no text")
            return False
        else:
            print("\n✅ SUCCESS: StreamingTranscriber working!")
            return True

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "="*60)
    print("VOSK STT COMPREHENSIVE DEBUGGING")
    print("="*60)
    print("\nThis script will test 3 things:")
    print("1. Audio input levels (is mic working?)")
    print("2. Basic Vosk recognition (can Vosk hear you?)")
    print("3. StreamingTranscriber class (is the wrapper working?)")
    print("\n" + "="*60)

    input("\nPress Enter to start Test 1 (Audio Levels)...")
    test1_pass = test_audio_levels()

    if not test1_pass:
        print("\n⚠️  Audio levels are too low!")
        print("   Fix: Increase microphone volume in System Preferences")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            return

    input("\nPress Enter to start Test 2 (Basic Vosk)...")
    test2_pass = test_vosk_simple()

    if not test2_pass:
        print("\n❌ Vosk is not recognizing speech!")
        print("\nPossible fixes:")
        print("1. Download larger model:")
        print("   cd models/")
        print("   wget https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip")
        print("   unzip vosk-model-en-us-0.22.zip")
        print("2. Speak MORE SLOWLY and CLEARLY")
        print("3. Speak LOUDER")
        print("4. Reduce background noise")
        response = input("\nContinue to Test 3 anyway? (y/n): ")
        if response.lower() != 'y':
            return

    input("\nPress Enter to start Test 3 (StreamingTranscriber)...")
    test3_pass = test_vosk_with_stt_class()

    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    print(f"Test 1 (Audio Levels):         {'✅ PASS' if test1_pass else '❌ FAIL'}")
    print(f"Test 2 (Basic Vosk):           {'✅ PASS' if test2_pass else '❌ FAIL'}")
    print(f"Test 3 (StreamingTranscriber): {'✅ PASS' if test3_pass else '❌ FAIL'}")
    print("="*60)

    if test1_pass and test2_pass and test3_pass:
        print("\n✅ ALL TESTS PASSED!")
        print("The diagnostic tool should work correctly now.")
    elif not test1_pass:
        print("\n❌ PRIMARY ISSUE: Audio input is too quiet")
        print("FIX: Increase microphone volume to 70-80%")
    elif not test2_pass:
        print("\n❌ PRIMARY ISSUE: Vosk model cannot recognize your speech")
        print("FIX: Download the larger, more accurate Vosk model")
    else:
        print("\n⚠️  PARTIAL SUCCESS")
        print("Some tests passed, but StreamingTranscriber has issues")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
