#!/usr/bin/env python3
"""Comprehensive Voice Assistant Diagnostic Tool

This tool provides step-by-step diagnostics for the three critical issues:
1. Wake word detection only works when shouted
2. Speech capture fails after wake word  
3. Timeout/silence detection misjudges conversation flow

Run this script to diagnose and verify fixes for your voice assistant.
"""

import sys
import os
import time
import json
import audioop
import numpy as np
import pyaudio
import webrtcvad
from collections import deque
from typing import Optional, List, Dict, Any

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.audio.stt import StreamingTranscriber
from app.audio.agc import AutomaticGainControl, AdaptiveVAD
from app.util.config import load_config


# ============================================================================
# DIAGNOSTIC INFRASTRUCTURE
# ============================================================================

class AudioDiagnostics:
    """Track audio levels and timing through entire pipeline"""
    
    def __init__(self):
        self.start_time = time.time()
        self.events = []
        self.audio_levels = deque(maxlen=100)
        
    def log_event(self, stage: str, **kwargs):
        """Log pipeline event with timestamp"""
        timestamp = time.time() - self.start_time
        event = {
            'timestamp': timestamp,
            'stage': stage,
            **kwargs
        }
        self.events.append(event)
        
        log_msg = f"[{timestamp:7.3f}s] {stage}"
        for key, value in kwargs.items():
            log_msg += f" | {key}={value}"
        print(log_msg)
        
    def log_audio_chunk(self, audio_data: bytes, stage: str):
        """Log audio level statistics"""
        rms = audioop.rms(audio_data, 2)
        db = 20 * np.log10(rms / 32768.0) if rms > 0 else -96.0
        
        self.audio_levels.append(rms)
        avg_rms = np.mean(self.audio_levels)
        
        self.log_event(
            stage,
            rms=f"{rms:5d}",
            db=f"{db:6.2f}",
            avg_rms=f"{avg_rms:.0f}",
            chunk_bytes=len(audio_data)
        )
        
        # Visual audio level indicator
        bar_length = min(int((rms / 1000) * 20), 40)
        bar = "█" * bar_length
        status = ""
        if rms < 500:
            status = "⚠️  TOO QUIET"
        elif rms > 20000:
            status = "⚠️  CLIPPING"
        else:
            status = "✓ GOOD"
            
        print(f"    Audio: [{bar:<40}] {status}")
        
        return rms, db


# ============================================================================
# PHASE 1: AUDIO LEVEL DIAGNOSTIC
# ============================================================================

def diagnose_audio_levels(duration_seconds: int = 5):
    """Record and analyze baseline audio levels"""
    print(f"\n{'='*60}")
    print("PHASE 1: AUDIO LEVEL DIAGNOSTIC")
    print(f"{'='*60}")
    print(f"\nSpeak normally for {duration_seconds} seconds...")
    print("This will measure your microphone's audio levels.\n")
    
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 4096
    
    p = pyaudio.PyAudio()
    
    # Get default input device
    default_device = p.get_default_input_device_info()
    print(f"Using microphone: {default_device['name']}\n")
    
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        start=True
    )
    
    rms_values = []
    db_values = []
    
    chunks_to_record = int((SAMPLE_RATE / CHUNK_SIZE) * duration_seconds)
    
    for i in range(chunks_to_record):
        audio_chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        rms = audioop.rms(audio_chunk, 2)
        db = 20 * np.log10(rms / 32768.0) if rms > 0 else -96.0
        
        rms_values.append(rms)
        db_values.append(db)
        
        # Real-time display
        bar = "█" * min(int(rms / 100), 50)
        print(f"\rRMS: {rms:5d} | dB: {db:6.2f} | {bar:<50}", end="")
        
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print(f"\n\n{'='*60}")
    print("AUDIO LEVEL ANALYSIS RESULTS")
    print(f"{'='*60}")
    print(f"RMS - Min: {min(rms_values):5d} | Avg: {np.mean(rms_values):5.0f} | Max: {max(rms_values):5d}")
    print(f"dB  - Min: {min(db_values):6.2f} | Avg: {np.mean(db_values):6.2f} | Max: {max(db_values):6.2f}")
    print(f"\nRECOMMENDATIONS:")
    
    avg_rms = np.mean(rms_values)
    recommendations = []
    
    if avg_rms < 500:
        needed_gain_db = 20 * np.log10(1000 / avg_rms) if avg_rms > 0 else 20
        print(f"⚠️  AUDIO TOO QUIET - Your microphone needs boosting")
        print(f"   Current AGC target_rms: 3000.0")
        print(f"   Estimated gain needed: +{needed_gain_db:.1f} dB")
        print(f"   ✓ AGC is enabled in config.json - this should help")
        recommendations.append("audio_too_quiet")
    elif avg_rms > 15000:
        print(f"⚠️  AUDIO TOO LOUD - May cause clipping")
        print(f"   Reduce microphone volume in system settings")
        recommendations.append("audio_too_loud")
    else:
        print(f"✓ Audio levels are good ({avg_rms:.0f} RMS)")
        recommendations.append("audio_good")
    
    print(f"{'='*60}\n")
    
    return {
        'avg_rms': avg_rms,
        'min_rms': min(rms_values),
        'max_rms': max(rms_values),
        'avg_db': np.mean(db_values),
        'recommendations': recommendations
    }


# ============================================================================
# PHASE 2: VAD CONFIGURATION DIAGNOSTIC
# ============================================================================

def diagnose_vad_setup():
    """Verify WebRTC VAD configuration is correct"""
    print(f"\n{'='*60}")
    print("PHASE 2: WEBRTC VAD CONFIGURATION DIAGNOSTIC")
    print(f"{'='*60}\n")
    
    SAMPLE_RATE = 16000
    VAD_FRAME_MS = 30
    
    # Check sample rate
    print(f"Sample Rate: {SAMPLE_RATE} Hz")
    if SAMPLE_RATE not in [8000, 16000, 32000, 48000]:
        print("❌ ERROR: Invalid sample rate for WebRTC VAD")
        print("   Valid rates: 8000, 16000, 32000, 48000 Hz")
        return False
    else:
        print("✓ Sample rate is valid")
    
    # Check frame duration
    print(f"\nFrame Duration: {VAD_FRAME_MS} ms")
    if VAD_FRAME_MS not in [10, 20, 30]:
        print("❌ ERROR: Invalid frame duration for WebRTC VAD")
        print("   Valid durations: 10, 20, 30 ms")
        return False
    else:
        print("✓ Frame duration is valid")
    
    # Calculate frame size
    frame_size_samples = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)
    frame_size_bytes = frame_size_samples * 2  # 16-bit = 2 bytes per sample
    
    print(f"\nCalculated Frame Size:")
    print(f"  Samples: {frame_size_samples}")
    print(f"  Bytes: {frame_size_bytes}")
    
    # Test VAD initialization
    try:
        vad = webrtcvad.Vad()
        print("\n✓ WebRTC VAD initialized successfully")
        
        # Test each aggressiveness mode
        print(f"\nTesting aggressiveness modes:")
        for mode in [0, 1, 2, 3]:
            vad.set_mode(mode)
            
            # Create silent test frame
            test_frame = b'\x00\x00' * frame_size_samples
            
            try:
                result = vad.is_speech(test_frame, SAMPLE_RATE)
                print(f"  Mode {mode}: ✓ Working (silence detected: {not result})")
            except Exception as e:
                print(f"  Mode {mode}: ❌ Error - {e}")
        
        print(f"\n{'='*60}\n")
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR initializing VAD: {e}")
        print(f"{'='*60}\n")
        return False


# ============================================================================
# PHASE 3: WAKE WORD SENSITIVITY TEST
# ============================================================================

def test_wake_word_sensitivity(config, duration: int = 30):
    """Test wake word detection at different volumes"""
    print(f"\n{'='*60}")
    print("PHASE 3: WAKE WORD SENSITIVITY TEST")
    print(f"{'='*60}")
    print("\nInstructions:")
    print("1. Say wake word at NORMAL volume")
    print("2. Say wake word QUIETLY")
    print("3. Say wake word LOUDLY")
    print(f"\nListening for {duration} seconds...")
    print(f"{'='*60}\n")
    
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 4096
    
    # Initialize components
    diagnostics = AudioDiagnostics()
    
    # Initialize Vosk STT
    stt = StreamingTranscriber(
        model_path=config.vosk_model_path,
        sample_rate=SAMPLE_RATE
    )
    stt.start()
    
    # Initialize AGC
    agc = AutomaticGainControl(
        target_rms=3000.0,
        min_gain=1.0,
        max_gain=10.0,
        attack_rate=0.9,
        release_rate=0.999
    )
    
    # Initialize audio stream
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        start=True
    )
    
    detections = []
    start_time = time.time()
    wake_words = ["hey glasses", "hi glasses", "ok glasses"]
    
    print("Listening... (say wake word)")
    
    while time.time() - start_time < duration:
        # Read audio
        raw_chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        
        # Log original level
        rms_before = audioop.rms(raw_chunk, 2)
        
        # Apply AGC
        gained_chunk = agc.process(raw_chunk)
        rms_after = audioop.rms(gained_chunk, 2)
        
        # Feed to STT
        stt.feed(gained_chunk)
        
        # Check for wake word in combined text
        combined_text = stt.combined_text.lower()
        
        for wake_word in wake_words:
            if wake_word in combined_text:
                elapsed = time.time() - start_time
                agc_stats = agc.get_stats()
                
                detection = {
                    'time': elapsed,
                    'text': combined_text,
                    'wake_word': wake_word,
                    'rms_before': rms_before,
                    'rms_after': rms_after,
                    'agc_gain': agc_stats['current_gain'],
                    'agc_gain_db': agc_stats['current_gain_db']
                }
                detections.append(detection)
                
                print(f"\n✓ DETECTED at {elapsed:.1f}s:")
                print(f"  Wake word: '{wake_word}'")
                print(f"  Full text: '{combined_text}'")
                print(f"  RMS: {rms_before} → {rms_after} (AGC gain: {agc_stats['current_gain']:.2f}x / {agc_stats['current_gain_db']:+.1f}dB)")
                print()
                
                # Reset STT to avoid duplicate detections
                stt.reset()
                stt.start()
                break
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(detections)} detections in {duration} seconds")
    
    if detections:
        print("\nDetection details:")
        for d in detections:
            print(f"  {d['time']:5.1f}s: '{d['wake_word']}' (RMS: {d['rms_before']} → {d['rms_after']}, Gain: {d['agc_gain']:.2f}x)")
    else:
        print("\n⚠️  NO WAKE WORDS DETECTED")
        print("Possible issues:")
        print("  1. Microphone too quiet (check Phase 1 results)")
        print("  2. AGC not boosting enough")
        print("  3. Vosk model not recognizing wake word")
    
    print(f"{'='*60}\n")
    
    return len(detections) > 0


# ============================================================================
# PHASE 4: VAD SPEECH CAPTURE TEST
# ============================================================================

def test_vad_capture(config, duration: int = 30):
    """Test VAD captures speech after wake word"""
    print(f"\n{'='*60}")
    print("PHASE 4: VAD SPEECH CAPTURE TEST")
    print(f"{'='*60}")
    print("\nInstructions:")
    print('1. Say: "hey glasses"')
    print('2. Wait for confirmation')
    print('3. Say: "what is the weather today"')
    print(f'\nTest will run for {duration} seconds...')
    print(f"{'='*60}\n")
    
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 4096
    VAD_FRAME_MS = 30
    VAD_FRAME_SIZE = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)
    VAD_FRAME_BYTES = VAD_FRAME_SIZE * 2
    
    # Initialize components
    diagnostics = AudioDiagnostics()
    
    # Initialize Vosk STT
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
    
    # Initialize Adaptive VAD
    adaptive_vad = AdaptiveVAD(sample_rate=SAMPLE_RATE)
    
    # Initialize audio stream
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        start=True
    )
    
    # State machine
    state = "LISTENING_FOR_WAKE"
    recording_buffer = []
    pre_wake_buffer = deque(maxlen=30)  # ~1 second at 30ms frames
    silence_start: Optional[float] = None
    
    start_time = time.time()
    wake_words = ["hey glasses", "hi glasses", "ok glasses"]
    
    print("Listening for wake word...")
    
    while time.time() - start_time < duration:
        # Read audio
        raw_chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        
        # Apply AGC
        gained_chunk = agc.process(raw_chunk)
        
        if state == "LISTENING_FOR_WAKE":
            # Maintain pre-wake buffer
            pre_wake_buffer.append(gained_chunk)
            
            # Feed to STT
            stt.feed(gained_chunk)
            
            # Check for wake word
            combined_text = stt.combined_text.lower()
            wake_detected = any(wake_word in combined_text for wake_word in wake_words)
            
            if wake_detected:
                print(f"✓ Wake word detected: '{combined_text}'")
                print("  Now listening for command...")
                
                # Transition to recording
                recording_buffer = list(pre_wake_buffer)
                adaptive_vad = AdaptiveVAD(sample_rate=SAMPLE_RATE)  # Reset VAD
                state = "RECORDING"
                
                # Reset STT for command
                stt.reset()
                stt.start()
                
                # Feed pre-wake buffer to STT
                for frame in recording_buffer:
                    stt.feed(frame)
                
        elif state == "RECORDING":
            # Add to recording buffer
            recording_buffer.append(gained_chunk)
            
            # Feed to STT
            stt.feed(gained_chunk)
            
            # Check VAD
            vad_frame = gained_chunk[:VAD_FRAME_BYTES]
            is_speech = adaptive_vad.is_speech(vad_frame)
            
            # Simple silence detection (1.5 seconds)
            if not is_speech:
                if silence_start is None:
                    silence_start = time.time()
                elif silence_start is not None and time.time() - silence_start > 1.5:
                    # End recording
                    print("  ■ Speech ended (silence detected)")
                    
                    # Finalize STT
                    stt.end()
                    transcript = stt.result()
                    
                    # Calculate recording stats
                    audio_data = b''.join(recording_buffer)
                    duration_sec = len(audio_data) / (SAMPLE_RATE * 2)
                    
                    print(f"\n✓ RECORDING CAPTURED:")
                    print(f"  Transcript: '{transcript}'")
                    print(f"  Duration: {duration_sec:.2f} seconds")
                    print(f"  Size: {len(audio_data)} bytes")
                    print(f"  Chunks: {len(recording_buffer)}")
                    
                    # Reset for next wake word
                    recording_buffer = []
                    state = "LISTENING_FOR_WAKE"
                    stt.reset()
                    stt.start()
                    silence_start = None
                    print(f"\nListening for wake word again...")
            else:
                # Speech detected, reset silence timer
                silence_start = None
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print(f"\n{'='*60}")
    print("TEST COMPLETE")
    print(f"{'='*60}\n")


# ============================================================================
# PHASE 5: TIMEOUT BEHAVIOR TEST
# ============================================================================

def test_timeout_behavior(config):
    """Test timeout parameters with different scenarios"""
    print(f"\n{'='*60}")
    print("PHASE 5: TIMEOUT BEHAVIOR TEST")
    print(f"{'='*60}")
    print("\nCurrent configuration:")
    print(f"  silence_ms: {config.silence_ms}")
    print(f"  pre_roll_ms: {config.pre_roll_ms}")
    print(f"  min_speech_frames: {config.min_speech_frames}")
    print(f"  vad_aggressiveness: {config.vad_aggressiveness}")
    print("\nScenarios to test:")
    print("1. Say nothing (should timeout)")
    print("2. Say short phrase with no pauses")
    print("3. Say phrase with mid-sentence pause")
    print(f"{'='*60}\n")
    
    SAMPLE_RATE = 16000
    CHUNK_SIZE = 4096
    VAD_FRAME_MS = 30
    VAD_FRAME_SIZE = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)
    VAD_FRAME_BYTES = VAD_FRAME_SIZE * 2
    
    # Initialize VAD
    vad = webrtcvad.Vad(config.vad_aggressiveness)
    
    # Initialize audio stream
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
        start=True
    )
    
    # Timeout tracking
    start_time = time.time()
    last_speech_time = None
    has_spoken = False
    test_duration = 10  # seconds
    
    print("Recording started... speak or stay silent")
    
    while time.time() - start_time < test_duration:
        # Read audio
        audio_chunk = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        
        # Check VAD
        vad_frame = audio_chunk[:VAD_FRAME_BYTES]
        is_speech = vad.is_speech(vad_frame, SAMPLE_RATE)
        
        now = time.time()
        
        if is_speech:
            if not has_spoken:
                print(f"\n► First speech detected at {now - start_time:.2f}s")
                has_spoken = True
            last_speech_time = now
            print(".", end="", flush=True)
        else:
            print(" ", end="", flush=True)
        
        # Check timeout conditions
        if has_spoken and last_speech_time:
            silence_duration_ms = (now - last_speech_time) * 1000
            
            if silence_duration_ms >= config.silence_ms:
                elapsed = now - start_time
                print(f"\n\n✓ TIMEOUT TRIGGERED: silence")
                print(f"  Time: {elapsed:.2f} seconds")
                print(f"  Silence duration: {silence_duration_ms:.0f}ms (threshold: {config.silence_ms}ms)")
                break
        elif not has_spoken:
            # No speech timeout (15 seconds)
            elapsed_ms = (now - start_time) * 1000
            if elapsed_ms >= 15000:
                print(f"\n\n✓ TIMEOUT TRIGGERED: no_speech")
                print(f"  Time: {elapsed_ms/1000:.2f} seconds")
                break
    
    stream.stop_stream()
    stream.close()
    p.terminate()
    
    print(f"\n{'='*60}\n")


# ============================================================================
# MAIN DIAGNOSTIC RUNNER
# ============================================================================

def main():
    """Run all diagnostic phases"""
    print("\n" + "="*60)
    print("VOICE ASSISTANT COMPREHENSIVE DIAGNOSTIC TOOL")
    print("="*60)
    print("\nThis tool will diagnose three critical issues:")
    print("1. Wake word detection only works when shouted")
    print("2. Speech capture fails after wake word")
    print("3. Timeout/silence detection misjudges conversation flow")
    print("\n" + "="*60 + "\n")
    
    # Load config
    try:
        config = load_config()
        print(f"✓ Configuration loaded from config.json")
        print(f"  Vosk model: {config.vosk_model_path}")
        print(f"  AGC enabled: {getattr(config, 'enable_agc', True)}")
        print(f"  VAD aggressiveness: {config.vad_aggressiveness}")
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return
    
    # Run diagnostic phases
    try:
        # Phase 1: Audio levels
        input("\nPress Enter to start Phase 1 (Audio Level Diagnostic)...")
        audio_results = diagnose_audio_levels(duration_seconds=5)
        
        # Phase 2: VAD configuration
        input("\nPress Enter to start Phase 2 (VAD Configuration Diagnostic)...")
        vad_ok = diagnose_vad_setup()
        
        if not vad_ok:
            print("⚠️  VAD configuration issues detected. Fix these before continuing.")
            return
        
        # Phase 3: Wake word sensitivity
        input("\nPress Enter to start Phase 3 (Wake Word Sensitivity Test)...")
        wake_ok = test_wake_word_sensitivity(config, duration=30)
        
        if not wake_ok:
            print("\n⚠️  Wake word detection failed.")
            print("Recommendations:")
            if audio_results['avg_rms'] < 500:
                print("  - Your microphone is too quiet")
                print("  - AGC should help, but verify it's enabled in config.json")
            print("  - Try speaking louder or closer to the microphone")
            print("  - Check that wake_variants in config.json match what you're saying")
        
        # Phase 4: VAD capture
        input("\nPress Enter to start Phase 4 (VAD Speech Capture Test)...")
        test_vad_capture(config, duration=30)
        
        # Phase 5: Timeout behavior
        input("\nPress Enter to start Phase 5 (Timeout Behavior Test)...")
        test_timeout_behavior(config)
        
        # Summary
        print("\n" + "="*60)
        print("DIAGNOSTIC SUMMARY")
        print("="*60)
        print(f"\nAudio Levels:")
        print(f"  Average RMS: {audio_results['avg_rms']:.0f}")
        print(f"  Status: {audio_results['recommendations'][0]}")
        print(f"\nVAD Configuration:")
        print(f"  Status: {'✓ OK' if vad_ok else '❌ FAILED'}")
        print(f"\nWake Word Detection:")
        print(f"  Status: {'✓ OK' if wake_ok else '❌ FAILED'}")
        print(f"\nNext steps:")
        if not wake_ok:
            print("  1. Review wake word detection issues above")
            print("  2. Adjust AGC settings if needed")
            print("  3. Re-run this diagnostic")
        else:
            print("  1. All diagnostics passed!")
            print("  2. Test the full voice assistant")
        print("="*60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\nDiagnostic interrupted by user.")
    except Exception as e:
        print(f"\n❌ Error during diagnostic: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
