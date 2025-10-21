#!/usr/bin/env python3
"""System Analysis - Check all voice assistant components without audio input"""

import sys
import os
import json

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def print_header(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def print_status(label, status, details=""):
    status_symbol = "✓" if status else "✗"
    status_text = "PASS" if status else "FAIL"
    color = "\033[92m" if status else "\033[91m"
    reset = "\033[0m"
    print(f"{color}{status_symbol} {label}: {status_text}{reset}")
    if details:
        print(f"  {details}")

def check_dependencies():
    """Check all required dependencies"""
    print_header("DEPENDENCY CHECK")
    
    all_ok = True
    
    # Check Python version
    import sys
    version = sys.version_info
    python_ok = version.major == 3 and version.minor >= 8
    print_status("Python Version", python_ok, f"Python {version.major}.{version.minor}.{version.micro}")
    all_ok = all_ok and python_ok
    
    # Check numpy
    try:
        import numpy as np
        print_status("NumPy", True, f"Version {np.__version__}")
    except ImportError as e:
        print_status("NumPy", False, str(e))
        all_ok = False
    
    # Check PyAudio
    try:
        import pyaudio
        print_status("PyAudio", True, "Available")
    except ImportError as e:
        print_status("PyAudio", False, str(e))
        all_ok = False
    
    # Check webrtcvad
    try:
        import webrtcvad
        print_status("WebRTC VAD", True, "Available")
    except ImportError as e:
        print_status("WebRTC VAD", False, str(e))
        all_ok = False
    
    # Check Vosk
    try:
        from vosk import Model, KaldiRecognizer
        print_status("Vosk", True, "Available")
    except ImportError as e:
        print_status("Vosk", False, str(e))
        all_ok = False
    
    return all_ok

def check_configuration():
    """Check configuration file"""
    print_header("CONFIGURATION CHECK")
    
    all_ok = True
    
    try:
        from app.util.config import load_config
        config = load_config()
        print_status("Config Loading", True, "config.json loaded successfully")
        
        # Check critical parameters
        checks = [
            ("Sample Rate", config.sample_rate_hz == 16000, f"{config.sample_rate_hz} Hz (must be 16000)"),
            ("VAD Aggressiveness", 0 <= config.vad_aggressiveness <= 3, f"{config.vad_aggressiveness} (0-3)"),
            ("AGC Enabled", config.enable_agc, f"{config.enable_agc}"),
            ("Pre-roll Buffer", config.pre_roll_ms > 0, f"{config.pre_roll_ms} ms"),
            ("Silence Threshold", config.silence_ms > 0, f"{config.silence_ms} ms"),
            ("Min Speech Frames", config.min_speech_frames > 0, f"{config.min_speech_frames} frames"),
            ("Wake Sensitivity", 0.0 <= config.wake_sensitivity <= 1.0, f"{config.wake_sensitivity}"),
        ]
        
        for label, status, details in checks:
            print_status(label, status, details)
            all_ok = all_ok and status
        
        # Check wake variants
        if config.wake_variants and len(config.wake_variants) > 0:
            print_status("Wake Variants", True, f"{len(config.wake_variants)} variants configured")
            for variant in config.wake_variants[:3]:
                print(f"    - '{variant}'")
            if len(config.wake_variants) > 3:
                print(f"    ... and {len(config.wake_variants) - 3} more")
        else:
            print_status("Wake Variants", False, "No wake variants configured")
            all_ok = False
        
    except Exception as e:
        print_status("Config Loading", False, str(e))
        all_ok = False
    
    return all_ok

def check_vosk_model():
    """Check Vosk model availability"""
    print_header("VOSK MODEL CHECK")
    
    all_ok = True
    
    try:
        from app.util.config import load_config
        config = load_config()
        
        model_path = config.vosk_model_path
        
        if not model_path:
            print_status("Model Path", False, "Model path not configured")
            return False
        
        if os.path.exists(model_path):
            print_status("Model Path", True, str(model_path))
            
            # Check required files
            required_files = ['am/final.mdl', 'graph/HCLG.fst', 'graph/phones/word_boundary.int']
            for req_file in required_files:
                full_path = os.path.join(str(model_path), req_file)
                exists = os.path.exists(full_path)
                print_status(f"  {req_file}", exists, full_path if exists else "Missing")
                all_ok = all_ok and exists
            
            # Try to load model
            try:
                from vosk import Model
                model = Model(model_path)
                print_status("Model Loading", True, "Model loaded successfully")
            except Exception as e:
                print_status("Model Loading", False, str(e))
                all_ok = False
        else:
            print_status("Model Path", False, f"Not found: {model_path}")
            all_ok = False
    
    except Exception as e:
        print_status("Model Check", False, str(e))
        all_ok = False
    
    return all_ok

def check_agc_implementation():
    """Check AGC implementation"""
    print_header("AGC IMPLEMENTATION CHECK")
    
    all_ok = True
    
    try:
        from app.audio.agc import AutomaticGainControl, AdaptiveVAD
        
        # Test AGC initialization
        try:
            agc = AutomaticGainControl(
                target_rms=3000.0,
                min_gain=1.0,
                max_gain=10.0
            )
            print_status("AGC Initialization", True, "AutomaticGainControl created")
            
            # Check AGC stats
            stats = agc.get_stats()
            print(f"  Initial gain: {stats['current_gain']:.2f}x")
            print(f"  Target RMS: {stats['target_rms']:.0f}")
            print(f"  Max gain: 10.0x (can boost quiet mics up to 10x)")
        except Exception as e:
            print_status("AGC Initialization", False, str(e))
            all_ok = False
        
        # Test Adaptive VAD initialization
        try:
            vad = AdaptiveVAD(sample_rate=16000)
            print_status("Adaptive VAD Initialization", True, "AdaptiveVAD created")
            print(f"  Initial VAD level: {vad.get_vad_level()}")
            print(f"  Auto-calibrates to environment")
        except Exception as e:
            print_status("Adaptive VAD Initialization", False, str(e))
            all_ok = False
    
    except ImportError as e:
        print_status("AGC Import", False, str(e))
        all_ok = False
    
    return all_ok

def check_vad_configuration():
    """Check VAD configuration"""
    print_header("VAD CONFIGURATION CHECK")
    
    all_ok = True
    
    try:
        import webrtcvad
        from app.util.config import load_config
        
        config = load_config()
        
        SAMPLE_RATE = 16000
        VAD_FRAME_MS = 30
        
        # Check sample rate
        valid_rates = [8000, 16000, 32000, 48000]
        rate_ok = SAMPLE_RATE in valid_rates
        print_status("Sample Rate", rate_ok, f"{SAMPLE_RATE} Hz (valid: {valid_rates})")
        all_ok = all_ok and rate_ok
        
        # Check frame duration
        valid_durations = [10, 20, 30]
        duration_ok = VAD_FRAME_MS in valid_durations
        print_status("Frame Duration", duration_ok, f"{VAD_FRAME_MS} ms (valid: {valid_durations})")
        all_ok = all_ok and duration_ok
        
        # Calculate frame size
        frame_size_samples = int(SAMPLE_RATE * VAD_FRAME_MS / 1000)
        frame_size_bytes = frame_size_samples * 2
        print_status("Frame Size", True, f"{frame_size_samples} samples = {frame_size_bytes} bytes")
        
        # Test VAD initialization
        try:
            vad = webrtcvad.Vad()
            print_status("VAD Initialization", True, "WebRTC VAD created")
            
            # Test all aggressiveness modes
            for mode in [0, 1, 2, 3]:
                try:
                    vad.set_mode(mode)
                    test_frame = b'\x00\x00' * frame_size_samples
                    result = vad.is_speech(test_frame, SAMPLE_RATE)
                    print(f"  Mode {mode}: ✓ Working")
                except Exception as e:
                    print(f"  Mode {mode}: ✗ Error - {e}")
                    all_ok = False
        except Exception as e:
            print_status("VAD Initialization", False, str(e))
            all_ok = False
    
    except Exception as e:
        print_status("VAD Check", False, str(e))
        all_ok = False
    
    return all_ok

def check_audio_pipeline():
    """Check audio pipeline components"""
    print_header("AUDIO PIPELINE CHECK")
    
    all_ok = True
    
    # Check wake word detection
    try:
        from app.audio.wake import WakeWordListener
        print_status("Wake Word Listener", True, "WakeWordListener available")
    except ImportError as e:
        print_status("Wake Word Listener", False, str(e))
        all_ok = False
    
    # Check STT
    try:
        from app.audio.stt import StreamingTranscriber
        print_status("Streaming Transcriber", True, "StreamingTranscriber available")
    except ImportError as e:
        print_status("Streaming Transcriber", False, str(e))
        all_ok = False
    
    # Check capture
    try:
        from app.audio.capture import run_segment
        print_status("Segment Capture", True, "run_segment available")
    except ImportError as e:
        print_status("Segment Capture", False, str(e))
        all_ok = False
    
    # Check session manager
    try:
        from app.session import SessionManager
        print_status("Session Manager", True, "SessionManager available")
    except ImportError as e:
        print_status("Session Manager", False, str(e))
        all_ok = False
    
    return all_ok

def analyze_configuration_optimizations():
    """Analyze configuration and suggest optimizations"""
    print_header("CONFIGURATION ANALYSIS")
    
    try:
        from app.util.config import load_config
        config = load_config()
        
        recommendations = []
        
        # Check AGC
        if not config.enable_agc:
            recommendations.append(("Enable AGC", "Set 'enable_agc': true for automatic microphone boost"))
        else:
            print("✓ AGC is enabled (good for quiet microphones)")
        
        # Check VAD aggressiveness
        if config.vad_aggressiveness > 2:
            recommendations.append(("Lower VAD aggressiveness", f"Current: {config.vad_aggressiveness}, try 1 or 2 for better speech detection"))
        else:
            print(f"✓ VAD aggressiveness is {config.vad_aggressiveness} (good for most environments)")
        
        # Check silence threshold
        if config.silence_ms < 1000:
            recommendations.append(("Increase silence threshold", f"Current: {config.silence_ms}ms, try 1200-1500ms to avoid cutting off speech"))
        else:
            print(f"✓ Silence threshold is {config.silence_ms}ms (good for natural speech)")
        
        # Check pre-roll buffer
        if config.pre_roll_ms < 500:
            recommendations.append(("Increase pre-roll buffer", f"Current: {config.pre_roll_ms}ms, try 600-800ms to capture beginning of speech"))
        else:
            print(f"✓ Pre-roll buffer is {config.pre_roll_ms}ms (good for capturing wake word)")
        
        # Check wake sensitivity
        if config.wake_sensitivity < 0.6:
            recommendations.append(("Increase wake sensitivity", f"Current: {config.wake_sensitivity}, try 0.7-0.8 for easier detection"))
        else:
            print(f"✓ Wake sensitivity is {config.wake_sensitivity} (balanced)")
        
        if recommendations:
            print("\nRecommendations:")
            for i, (title, desc) in enumerate(recommendations, 1):
                print(f"  {i}. {title}")
                print(f"     {desc}")
        else:
            print("\n✓ Configuration looks optimal!")
    
    except Exception as e:
        print(f"✗ Error analyzing configuration: {e}")

def main():
    """Run all system checks"""
    print("\n" + "="*70)
    print(" "*15 + "VOICE ASSISTANT SYSTEM ANALYSIS")
    print("="*70)
    print("\nThis analysis checks all components without requiring audio input.")
    print("="*70)
    
    results = {}
    
    # Run all checks
    results['dependencies'] = check_dependencies()
    results['configuration'] = check_configuration()
    results['vosk_model'] = check_vosk_model()
    results['agc'] = check_agc_implementation()
    results['vad'] = check_vad_configuration()
    results['pipeline'] = check_audio_pipeline()
    
    # Analyze configuration
    analyze_configuration_optimizations()
    
    # Summary
    print_header("SUMMARY")
    
    all_passed = all(results.values())
    
    for check, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        color = "\033[92m" if passed else "\033[91m"
        reset = "\033[0m"
        print(f"{color}{status}{reset} - {check.replace('_', ' ').title()}")
    
    print()
    if all_passed:
        print("="*70)
        print("✓ ALL CHECKS PASSED!")
        print("="*70)
        print("\nYour voice assistant is properly configured and ready to use.")
        print("\nNext steps:")
        print("  1. Run the voice assistant: python3 app/main.py")
        print("  2. Say 'hey glasses' to activate")
        print("  3. Speak your command")
        print("  4. Continue conversation without re-waking")
        print("="*70)
    else:
        print("="*70)
        print("⚠️  SOME CHECKS FAILED")
        print("="*70)
        print("\nPlease fix the issues above before running the voice assistant.")
        print("\nFor help:")
        print("  - Read: START_HERE_VOICE_DIAGNOSTICS.md")
        print("  - Read: VOICE_ASSISTANT_COMPLETE_SOLUTION.md")
        print("="*70)

if __name__ == "__main__":
    main()
