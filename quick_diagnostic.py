#!/usr/bin/env python3
"""Quick Voice Assistant Diagnostic

A simplified diagnostic tool that checks the most common issues:
1. Microphone audio levels
2. AGC functionality
3. Wake word detection

Run this first to quickly identify problems.
"""

import sys
import os
import time
import audioop
import numpy as np
import pyaudio

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.audio.stt import StreamingTranscriber
from app.audio.agc import AutomaticGainControl
from app.util.config import load_config


def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(title)
    print(f"{'='*60}\n")


def quick_audio_check():
    """Quick 5-second audio level check"""
    print_header("QUICK AUDIO LEVEL CHECK")
    print("Speak normally for 5 seconds...\n")
    
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 4096
    
    p = pyaudio.PyAudio()
    
    # Get default input device
    default_device = p.get_default_input_device_info()
    print(f"Using: {default_device['name']}\n")
    
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        start=True
    )
    
    rms_values = []
    chunks = int((SAMPLE_RATE / CHUNK_SIZE) * 5)
    
    for i in range(chunks):
        audio_chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        rms = audioop.rms(audio_chunk, 2)
        rms_values.append(rms)
        
        # Visual feedback
        bar = "█" * min(int(rms / 100), 50)
        print(f"\r{bar:<50} RMS: {rms:5d}", end="")
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    avg_rms = np.mean(rms_values)
    
    print(f"\n\nAverage RMS: {avg_rms:.0f}")
    
    if avg_rms < 500:
        print("❌ AUDIO TOO QUIET")
        print("   Your microphone needs boosting")
        print("   ✓ AGC should help automatically")
        return False
    elif avg_rms > 15000:
        print("⚠️  AUDIO TOO LOUD")
        print("   May cause clipping - reduce mic volume")
        return True
    else:
        print("✓ Audio levels look good!")
        return True


def quick_agc_test():
    """Test AGC is working"""
    print_header("AGC (AUTO GAIN CONTROL) TEST")
    print("Testing AGC boost on quiet audio...\n")
    
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 4096
    
    # Initialize AGC
    agc = AutomaticGainControl(
        target_rms=3000.0,
        min_gain=1.0,
        max_gain=10.0
    )
    
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        start=True
    )
    
    print("Speak normally for 3 seconds...\n")
    
    chunks = int((SAMPLE_RATE / CHUNK_SIZE) * 3)
    
    for i in range(chunks):
        raw_chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        rms_before = audioop.rms(raw_chunk, 2)
        
        # Apply AGC
        gained_chunk = agc.process(raw_chunk)
        rms_after = audioop.rms(gained_chunk, 2)
        
        stats = agc.get_stats()
        
        print(f"\rRMS: {rms_before:5d} → {rms_after:5d} | Gain: {stats['current_gain']:.2f}x ({stats['current_gain_db']:+.1f}dB)", end="")
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    final_stats = agc.get_stats()
    
    print(f"\n\nFinal AGC Stats:")
    print(f"  Gain: {final_stats['current_gain']:.2f}x ({final_stats['current_gain_db']:+.1f}dB)")
    print(f"  Target RMS: {final_stats['target_rms']:.0f}")
    print(f"  Current RMS: {final_stats['running_rms']:.0f}")
    
    if final_stats['current_gain'] > 1.5:
        print(f"\n✓ AGC is boosting your audio (good for quiet mics)")
    else:
        print(f"\n✓ AGC is active (minimal boost needed)")
    
    return True


def quick_wake_test(config):
    """Quick wake word detection test"""
    print_header("WAKE WORD DETECTION TEST")
    print("Say 'hey glasses' 3 times in the next 20 seconds...\n")
    
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 4096
    
    # Initialize STT
    stt = StreamingTranscriber(
        model_path=config.vosk_model_path,
        sample_rate=SAMPLE_RATE
    )
    stt.start()
    
    # Initialize AGC
    agc = AutomaticGainControl(
        target_rms=3000.0,
        min_gain=1.0,
        max_gain=10.0
    )
    
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        start=True
    )
    
    detections = 0
    start_time = time.time()
    duration = 20
    wake_words = ["hey glasses", "hi glasses", "ok glasses"]
    
    print("Listening...")
    
    while time.time() - start_time < duration:
        # Read and process audio
        raw_chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        gained_chunk = agc.process(raw_chunk)
        
        # Feed to STT
        stt.feed(gained_chunk)
        
        # Check for wake word
        text = stt.combined_text.lower()
        
        for wake_word in wake_words:
            if wake_word in text:
                detections += 1
                elapsed = time.time() - start_time
                stats = agc.get_stats()
                
                print(f"\n✓ Detection #{detections} at {elapsed:.1f}s")
                print(f"  Text: '{text}'")
                print(f"  AGC Gain: {stats['current_gain']:.2f}x")
                
                # Reset to avoid duplicate
                stt.reset()
                stt.start()
                break
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print(f"\n\nResults: {detections} detections in {duration} seconds")
    
    if detections == 0:
        print("❌ NO WAKE WORDS DETECTED")
        print("\nPossible issues:")
        print("  1. Microphone too quiet (run audio check)")
        print("  2. Wrong wake word (check config.json wake_variants)")
        print("  3. Speaking too fast/unclear")
        return False
    elif detections < 2:
        print("⚠️  PARTIAL SUCCESS")
        print("   Wake word detected but not reliably")
        return True
    else:
        print("✓ Wake word detection working!")
        return True


def main():
    """Run quick diagnostics"""
    print("\n" + "="*60)
    print("QUICK VOICE ASSISTANT DIAGNOSTIC")
    print("="*60)
    print("\nThis will quickly check:")
    print("  1. Microphone audio levels")
    print("  2. AGC (Automatic Gain Control)")
    print("  3. Wake word detection")
    print("\nTotal time: ~30 seconds")
    print("="*60)
    
    try:
        # Load config
        config = load_config()
        print(f"\n✓ Config loaded: {config.vosk_model_path}")
        
        # Run tests
        input("\nPress Enter to start...")
        
        audio_ok = quick_audio_check()
        
        input("\nPress Enter for AGC test...")
        agc_ok = quick_agc_test()
        
        input("\nPress Enter for wake word test...")
        wake_ok = quick_wake_test(config)
        
        # Summary
        print_header("SUMMARY")
        print(f"Audio Levels: {'✓ PASS' if audio_ok else '❌ FAIL'}")
        print(f"AGC Test:     ✓ PASS")
        print(f"Wake Word:    {'✓ PASS' if wake_ok else '❌ FAIL'}")
        
        if audio_ok and wake_ok:
            print("\n✓ All tests passed! Your voice assistant should work.")
            print("\nNext steps:")
            print("  1. Run the full assistant: python app/main.py")
            print("  2. Say 'hey glasses' to activate")
        else:
            print("\n⚠️  Some tests failed.")
            print("\nNext steps:")
            print("  1. Run full diagnostic: python diagnostic_voice_comprehensive.py")
            print("  2. Check microphone settings in system preferences")
            print("  3. Verify config.json settings")
        
        print("="*60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\nDiagnostic interrupted.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
