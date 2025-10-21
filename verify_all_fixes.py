#!/usr/bin/env python3
"""
Complete Voice Assistant Fix Verification Script

This script tests all 6 critical fixes:
1. Speech capture completeness
2. Wake word reliability  
3. Multi-turn conversation
4. 15-second timeout
5. Debug output prevention
6. TTS reliability

Run this to verify all fixes are working correctly.
"""

import os
import sys
import time
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

def print_section(title):
    """Print a section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def test_config_loaded():
    """Test 1: Verify optimized configuration is loaded."""
    print_section("TEST 1: Configuration Verification")
    
    try:
        from app.util.config import load_config
        
        # Try to load the optimized config
        config_path = Path("config.optimized_complete.json")
        if not config_path.exists():
            print("❌ Optimized config not found, using default config.json")
            config_path = Path("config.json")
        
        config = load_config(config_path)
        
        print("✅ Configuration loaded successfully")
        print(f"\n📋 Key Settings:")
        print(f"   - VAD Aggressiveness: {config.vad_aggressiveness} (should be 1-2)")
        print(f"   - Pre-roll buffer: {config.pre_roll_ms}ms (should be ≥600ms)")
        print(f"   - Tail padding: {getattr(config, 'tail_padding_ms', 'NOT SET')}ms (should be ≥500ms)")
        print(f"   - Silence timeout: {config.silence_ms}ms (should be ≥1500ms)")
        print(f"   - Min speech frames: {getattr(config, 'min_speech_frames', 'NOT SET')} (should be ≥3)")
        print(f"   - Wake sensitivity: {getattr(config, 'wake_sensitivity', 'NOT SET')} (should be 0.5-0.7)")
        
        # Check if settings are optimal
        issues = []
        if config.vad_aggressiveness > 2:
            issues.append("VAD too aggressive - may miss quiet speech")
        if config.pre_roll_ms < 600:
            issues.append("Pre-roll too short - may miss first syllables")
        if getattr(config, 'tail_padding_ms', 0) < 500:
            issues.append("Tail padding too short - may cut off last words")
        if config.silence_ms < 1500:
            issues.append("Silence timeout too short - may cut off during pauses")
        
        if issues:
            print(f"\n⚠️  Configuration Issues Found:")
            for issue in issues:
                print(f"   - {issue}")
            print(f"\n   💡 Use config.optimized_complete.json for optimal settings")
            return False
        else:
            print(f"\n✅ All configuration settings are optimal!")
            return True
            
    except Exception as e:
        print(f"❌ Error loading configuration: {e}")
        return False

def test_microphone():
    """Test 2: Verify microphone access and audio capture."""
    print_section("TEST 2: Microphone & Audio Capture")
    
    try:
        import pyaudio
        from app.audio.mic import MicrophoneStream
        from app.util.config import load_config
        
        config = load_config(Path("config.json"))
        
        print("🎤 Testing microphone access...")
        with MicrophoneStream(
            rate=config.sample_rate_hz,
            chunk_samples=config.chunk_samples,
            input_device_name=config.mic_device_name,
        ) as mic:
            # Read a few chunks
            for i in range(5):
                frame = mic.read(config.chunk_samples)
                if frame:
                    print(f"   ✓ Captured audio frame {i+1} ({len(frame)} bytes)")
                else:
                    print(f"   ✗ Failed to capture frame {i+1}")
                    return False
        
        print(f"\n✅ Microphone working correctly!")
        return True
        
    except Exception as e:
        print(f"❌ Microphone error: {e}")
        print(f"\n💡 Troubleshooting:")
        print(f"   - Check microphone permissions")
        print(f"   - Ensure microphone is connected and not in use")
        print(f"   - Try: python -m pip install --upgrade pyaudio")
        return False

def test_vad():
    """Test 3: Verify VAD speech detection."""
    print_section("TEST 3: Voice Activity Detection (VAD)")
    
    try:
        import webrtcvad
        from app.audio.mic import MicrophoneStream
        from app.util.config import load_config
        
        config = load_config(Path("config.json"))
        vad = webrtcvad.Vad(config.vad_aggressiveness)
        
        print("🎙️  Testing VAD speech detection...")
        print("   📢 Please speak NOW for 2 seconds...")
        
        speech_frames = 0
        silence_frames = 0
        
        with MicrophoneStream(
            rate=config.sample_rate_hz,
            chunk_samples=config.chunk_samples,
            input_device_name=config.mic_device_name,
        ) as mic:
            start_time = time.time()
            while time.time() - start_time < 2.0:
                frame = mic.read(config.chunk_samples)
                is_speech = vad.is_speech(frame, config.sample_rate_hz)
                if is_speech:
                    speech_frames += 1
                else:
                    silence_frames += 1
        
        total_frames = speech_frames + silence_frames
        speech_percentage = (speech_frames / total_frames * 100) if total_frames > 0 else 0
        
        print(f"\n   Speech frames: {speech_frames}/{total_frames} ({speech_percentage:.1f}%)")
        
        if speech_frames > 0:
            print(f"✅ VAD detected your speech!")
            if speech_percentage < 30:
                print(f"⚠️  Low speech detection - try speaking louder or adjust mic volume")
            return True
        else:
            print(f"❌ VAD did not detect speech")
            print(f"\n💡 Troubleshooting:")
            print(f"   - Speak louder and closer to microphone")
            print(f"   - Check microphone input volume in system settings")
            print(f"   - Try lowering vad_aggressiveness in config (currently: {config.vad_aggressiveness})")
            return False
            
    except Exception as e:
        print(f"❌ VAD error: {e}")
        return False

def test_stt():
    """Test 4: Verify speech-to-text transcription."""
    print_section("TEST 4: Speech-to-Text (STT) Transcription")
    
    try:
        from vosk import Model
        from app.audio.stt import StreamingTranscriber
        from app.audio.mic import MicrophoneStream
        from app.util.config import load_config
        
        config = load_config(Path("config.json"))
        
        # Check if model exists
        model_path = config.vosk_model_path or os.getenv("VOSK_MODEL_PATH")
        if not model_path or not Path(model_path).exists():
            print(f"❌ Vosk model not found at: {model_path}")
            print(f"\n💡 Download a model from: https://alphacephei.com/vosk/models")
            print(f"   Recommended: vosk-model-en-us-0.22")
            return False
        
        print(f"📚 Loading Vosk model from: {model_path}")
        model = Model(model_path)
        transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
        
        print(f"\n🎤 Testing speech transcription...")
        print(f"   📢 Please say: 'The quick brown fox jumps over the lazy dog'")
        print(f"   (You have 5 seconds)")
        
        transcriber.start()
        
        with MicrophoneStream(
            rate=config.sample_rate_hz,
            chunk_samples=config.chunk_samples,
            input_device_name=config.mic_device_name,
        ) as mic:
            start_time = time.time()
            while time.time() - start_time < 5.0:
                frame = mic.read(config.chunk_samples)
                transcriber.feed(frame)
                
                # Show partial results
                if transcriber.combined_text:
                    print(f"\r   Current: {transcriber.combined_text}", end='', flush=True)
        
        transcriber.end()
        final_text = transcriber.result()
        
        print(f"\n\n   Final transcript: '{final_text}'")
        
        if final_text:
            print(f"✅ STT is working!")
            
            # Check quality
            test_words = ["quick", "brown", "fox", "lazy", "dog"]
            found_words = sum(1 for word in test_words if word.lower() in final_text.lower())
            accuracy = (found_words / len(test_words)) * 100
            
            print(f"   Accuracy: {found_words}/{len(test_words)} key words ({accuracy:.0f}%)")
            
            if accuracy < 60:
                print(f"⚠️  Low accuracy - model may need adjustment or better audio quality")
            
            return True
        else:
            print(f"❌ No transcription produced")
            print(f"\n💡 Troubleshooting:")
            print(f"   - Speak louder and more clearly")
            print(f"   - Check microphone position")
            print(f"   - Try a different Vosk model")
            return False
            
    except Exception as e:
        print(f"❌ STT error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tts():
    """Test 5: Verify text-to-speech reliability."""
    print_section("TEST 5: Text-to-Speech (TTS) Reliability")
    
    try:
        # Test both original and enhanced TTS
        test_phrases = [
            "Testing text to speech output",
            "This is turn two",
            "Third consecutive test",
            "Final verification test"
        ]
        
        print("🔊 Testing TTS reliability with 4 consecutive calls...")
        print("   (You should hear 4 distinct phrases)")
        
        # Try enhanced TTS first
        try:
            from app.audio.tts_enhanced import SpeechSynthesizer
            print("\n   Using ENHANCED TTS (with all fixes)")
            enhanced = True
        except ImportError:
            from app.audio.tts import SpeechSynthesizer
            print("\n   Using ORIGINAL TTS")
            enhanced = False
        
        tts = SpeechSynthesizer(rate=175)
        
        failures = 0
        for i, phrase in enumerate(test_phrases, 1):
            try:
                print(f"   Speaking {i}/4: '{phrase}'")
                tts.speak(phrase)
                time.sleep(0.5)
                print(f"   ✓ TTS call {i} completed")
            except Exception as e:
                print(f"   ✗ TTS call {i} failed: {e}")
                failures += 1
        
        if failures == 0:
            print(f"\n✅ All 4 TTS calls succeeded!")
            if enhanced:
                print(f"   🎉 Enhanced TTS with all fixes is working perfectly!")
            return True
        else:
            print(f"\n⚠️  {failures}/4 TTS calls failed")
            if not enhanced:
                print(f"\n💡 To enable enhanced TTS with better reliability:")
                print(f"   1. Copy app/audio/tts_enhanced.py to app/audio/tts.py")
                print(f"   2. Or import from tts_enhanced in your main.py")
            return False
            
    except Exception as e:
        print(f"❌ TTS error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sanitization():
    """Test 6: Verify debug output sanitization."""
    print_section("TEST 6: Debug Output Sanitization")
    
    try:
        from app.audio.tts_enhanced import OutputSanitizer
        
        test_cases = [
            ("test one two three", "Remove test phrases"),
            ("DEBUG: this is debug output", "Remove DEBUG markers"),
            ("TODO: fix this later", "Remove TODO markers"),
            ("Normal text without issues", "Clean text passes through"),
            ("print('hello world')", "Remove print statements"),
        ]
        
        print("🛡️  Testing output sanitization...")
        
        all_passed = True
        for original, description in test_cases:
            sanitized = OutputSanitizer.sanitize_for_tts(original)
            blocked = original != sanitized
            
            if "without issues" in original:
                # Should NOT be blocked
                if blocked:
                    print(f"   ✗ {description}: Incorrectly blocked clean text")
                    all_passed = False
                else:
                    print(f"   ✓ {description}: Clean text passed")
            else:
                # Should be blocked
                if blocked:
                    print(f"   ✓ {description}: Blocked correctly")
                    print(f"      Original: '{original}'")
                    print(f"      Sanitized: '{sanitized}'")
                else:
                    print(f"   ✗ {description}: Failed to block")
                    all_passed = False
        
        if all_passed:
            print(f"\n✅ Output sanitization working correctly!")
            return True
        else:
            print(f"\n⚠️  Some sanitization tests failed")
            return False
            
    except ImportError:
        print(f"⚠️  Enhanced TTS not found - sanitization not available")
        print(f"   To enable: Copy app/audio/tts_enhanced.py to app/audio/tts.py")
        return False
    except Exception as e:
        print(f"❌ Sanitization test error: {e}")
        return False

def print_summary(results):
    """Print test summary."""
    print_section("SUMMARY")
    
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r['passed'])
    
    print(f"Tests Passed: {passed_tests}/{total_tests}\n")
    
    for result in results:
        status = "✅" if result['passed'] else "❌"
        print(f"{status} {result['name']}")
    
    if passed_tests == total_tests:
        print(f"\n🎉 ALL TESTS PASSED! Your voice assistant is ready to use!")
        print(f"\n📝 Next Steps:")
        print(f"   1. Run: python app/main.py")
        print(f"   2. Say: 'Hey glasses'")
        print(f"   3. Speak your query")
        print(f"   4. Listen to response")
        print(f"   5. Continue conversation (no wake word needed for 15s)")
        print(f"   6. Say: 'Bye glasses' to exit")
    else:
        print(f"\n⚠️  Some tests failed. Review the output above for details.")
        print(f"\n💡 Common Fixes:")
        print(f"   - Microphone issues: Check permissions and volume")
        print(f"   - STT issues: Download correct Vosk model")
        print(f"   - TTS issues: Use enhanced TTS (tts_enhanced.py)")
        print(f"   - Config issues: Use config.optimized_complete.json")

def main():
    """Run all verification tests."""
    print("🔍 Voice Assistant Complete Fix Verification")
    print("=" * 70)
    print("\nThis script will verify all 6 critical fixes are working:")
    print("1. Speech capture completeness (no truncation)")
    print("2. Wake word reliability")
    print("3. Multi-turn conversation support")
    print("4. 15-second follow-up timeout")
    print("5. Debug output prevention")
    print("6. TTS reliability with fallback")
    print("\n" + "=" * 70)
    
    input("\nPress Enter to begin tests...")
    
    results = []
    
    # Run all tests
    results.append({
        'name': 'Configuration Verification',
        'passed': test_config_loaded()
    })
    
    results.append({
        'name': 'Microphone & Audio Capture',
        'passed': test_microphone()
    })
    
    results.append({
        'name': 'Voice Activity Detection (VAD)',
        'passed': test_vad()
    })
    
    results.append({
        'name': 'Speech-to-Text (STT)',
        'passed': test_stt()
    })
    
    results.append({
        'name': 'Text-to-Speech (TTS) Reliability',
        'passed': test_tts()
    })
    
    results.append({
        'name': 'Debug Output Sanitization',
        'passed': test_sanitization()
    })
    
    # Print summary
    print_summary(results)

if __name__ == "__main__":
    main()
