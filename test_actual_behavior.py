#!/usr/bin/env python3
"""
Test script to verify actual runtime behavior of the voice assistant.
This will show you exactly what's happening in your app.
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app.util.config import load_config

def test_config():
    """Test 1: Verify configuration is loaded correctly"""
    print("\n" + "="*70)
    print("TEST 1: Configuration Check")
    print("="*70)
    
    try:
        config = load_config()
        print(f"✓ Config loaded successfully")
        print(f"\nKey parameters:")
        print(f"  pre_roll_ms: {config.pre_roll_ms}")
        print(f"  tail_padding_ms: {config.tail_padding_ms}")
        print(f"  min_speech_frames: {config.min_speech_frames}")
        print(f"  silence_ms: {config.silence_ms}")
        print(f"  vad_aggressiveness: {config.vad_aggressiveness}")
        print(f"  wake_word: {config.wake_word}")
        print(f"  wake_variants: {config.wake_variants}")
        print(f"  wake_sensitivity: {config.wake_sensitivity}")
        
        # Check for issues
        issues = []
        if config.pre_roll_ms < 300:
            issues.append(f"⚠️  pre_roll_ms ({config.pre_roll_ms}) is low - should be 400+")
        if config.tail_padding_ms < 300:
            issues.append(f"⚠️  tail_padding_ms ({config.tail_padding_ms}) is low - should be 400+")
        if config.silence_ms < 1000:
            issues.append(f"⚠️  silence_ms ({config.silence_ms}) is low - should be 1500+")
        if config.vad_aggressiveness > 2:
            issues.append(f"⚠️  vad_aggressiveness ({config.vad_aggressiveness}) is high - may clip speech")
        
        if issues:
            print(f"\n⚠️  Configuration Issues Found:")
            for issue in issues:
                print(f"  {issue}")
        else:
            print(f"\n✓ Configuration looks good!")
        
        return config
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return None

def test_vosk_model(config):
    """Test 2: Verify Vosk model is accessible"""
    print("\n" + "="*70)
    print("TEST 2: Vosk Model Check")
    print("="*70)
    
    import os
    from vosk import Model
    
    model_path = config.vosk_model_path or os.getenv("VOSK_MODEL_PATH")
    if not model_path:
        print("❌ VOSK_MODEL_PATH not set")
        return False
    
    print(f"Model path: {model_path}")
    
    if not os.path.exists(model_path):
        print(f"❌ Model directory not found: {model_path}")
        return False
    
    try:
        model = Model(model_path)
        print(f"✓ Vosk model loaded successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to load Vosk model: {e}")
        return False

def test_audio_capture(config):
    """Test 3: Test audio capture with VAD"""
    print("\n" + "="*70)
    print("TEST 3: Audio Capture Test")
    print("="*70)
    
    try:
        import webrtcvad
        from app.audio.mic import MicrophoneStream
        
        print(f"Testing VAD with aggressiveness={config.vad_aggressiveness}")
        vad = webrtcvad.Vad(config.vad_aggressiveness)
        
        print(f"\nOpening microphone...")
        print(f"  Sample rate: {config.sample_rate_hz}")
        print(f"  Chunk samples: {config.chunk_samples}")
        
        with MicrophoneStream(
            rate=config.sample_rate_hz,
            chunk_samples=config.chunk_samples,
            input_device_name=config.mic_device_name,
        ) as mic:
            print(f"✓ Microphone opened successfully")
            print(f"\nSay something now (testing for 3 seconds)...")
            
            speech_frames = 0
            silence_frames = 0
            total_frames = 0
            
            start_time = time.time()
            while time.time() - start_time < 3.0:
                frame = mic.read(config.chunk_samples)
                is_speech = vad.is_speech(frame, config.sample_rate_hz)
                
                total_frames += 1
                if is_speech:
                    speech_frames += 1
                else:
                    silence_frames += 1
            
            print(f"\nResults:")
            print(f"  Total frames: {total_frames}")
            print(f"  Speech frames: {speech_frames}")
            print(f"  Silence frames: {silence_frames}")
            
            if speech_frames > 0:
                print(f"✓ VAD detected speech!")
            else:
                print(f"⚠️  No speech detected - try speaking louder or adjusting vad_aggressiveness")
            
            return True
            
    except Exception as e:
        print(f"❌ Audio capture test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tts(config):
    """Test 4: Test TTS functionality"""
    print("\n" + "="*70)
    print("TEST 4: TTS Test")
    print("="*70)
    
    try:
        from app.audio.tts import SpeechSynthesizer
        
        print(f"Initializing TTS...")
        print(f"  Voice: {config.tts_voice}")
        print(f"  Rate: {config.tts_rate}")
        
        tts = SpeechSynthesizer(voice=config.tts_voice, rate=config.tts_rate)
        
        print(f"✓ TTS initialized")
        print(f"\nTesting TTS (you should hear this)...")
        
        tts.speak("Testing text to speech")
        
        print(f"✓ TTS test complete")
        return True
        
    except Exception as e:
        print(f"❌ TTS test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_session_flow(config):
    """Test 5: Test session manager flow"""
    print("\n" + "="*70)
    print("TEST 5: Session Manager Flow Test")
    print("="*70)
    
    try:
        from vosk import Model
        from app.audio.stt import StreamingTranscriber
        from app.audio.tts import SpeechSynthesizer
        from app.segment import SegmentRecorder
        from app.session import SessionManager, SessionCallbacks
        from app.ai.vlm_client import VLMClient
        
        print(f"Loading Vosk model...")
        import os
        model_path = config.vosk_model_path or os.getenv("VOSK_MODEL_PATH")
        model = Model(model_path)
        
        print(f"Creating components...")
        transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
        tts = SpeechSynthesizer(voice=config.tts_voice, rate=config.tts_rate)
        segment_recorder = SegmentRecorder(config, transcriber)
        vlm_client = VLMClient(config)
        
        print(f"Creating session manager...")
        session_manager = SessionManager(
            config=config,
            segment_recorder=segment_recorder,
            vlm_client=vlm_client,
            tts=tts,
            followup_timeout_ms=15000,  # 15 seconds
        )
        
        print(f"✓ Session manager created")
        print(f"\nSession manager settings:")
        print(f"  followup_timeout_ms: {session_manager.followup_timeout_ms}")
        print(f"  config.pre_roll_ms: {config.pre_roll_ms}")
        print(f"  config.tail_padding_ms: {config.tail_padding_ms}")
        print(f"  config.silence_ms: {config.silence_ms}")
        
        return True
        
    except Exception as e:
        print(f"❌ Session manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "╔" + "="*68 + "╗")
    print("║" + " "*68 + "║")
    print("║" + "  VOICE ASSISTANT RUNTIME BEHAVIOR TEST".center(68) + "║")
    print("║" + " "*68 + "║")
    print("╚" + "="*68 + "╝")
    
    # Test 1: Configuration
    config = test_config()
    if not config:
        print("\n❌ Cannot continue without valid configuration")
        return 1
    
    # Test 2: Vosk Model
    if not test_vosk_model(config):
        print("\n❌ Cannot continue without Vosk model")
        return 1
    
    # Test 3: Audio Capture
    print("\n⚠️  Next test will use your microphone")
    input("Press Enter to continue...")
    test_audio_capture(config)
    
    # Test 4: TTS
    print("\n⚠️  Next test will play audio through speakers")
    input("Press Enter to continue...")
    test_tts(config)
    
    # Test 5: Session Flow
    test_session_flow(config)
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print("\nAll core components tested.")
    print("\nIf you're still experiencing issues:")
    print("  1. Check the configuration warnings above")
    print("  2. Run: python3 test_voice_diagnostic_standalone.py")
    print("  3. Adjust config.json based on diagnostic results")
    print("\n" + "="*70)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
