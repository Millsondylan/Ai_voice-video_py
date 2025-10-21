#!/usr/bin/env python3
"""
Test wake word setup to see which method is actually being used.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.util.config import load_config
from app.audio.stt import StreamingTranscriber
from app.audio.wake_hybrid import create_wake_listener
from vosk import Model
import os

def test_wake_word_setup():
    print("\n" + "="*70)
    print("WAKE WORD SETUP TEST")
    print("="*70)
    
    # Load config
    print("\n1. Loading configuration...")
    config = load_config()
    print(f"   wake_word: {config.wake_word}")
    print(f"   wake_variants: {config.wake_variants}")
    print(f"   prefer_porcupine: {config.prefer_porcupine}")
    print(f"   porcupine_access_key: {'SET' if config.porcupine_access_key else 'NOT SET'}")
    print(f"   porcupine_keyword_path: {config.porcupine_keyword_path or 'NOT SET'}")
    
    # Check environment
    print("\n2. Checking environment...")
    porcupine_key_env = os.getenv("PORCUPINE_ACCESS_KEY")
    print(f"   PORCUPINE_ACCESS_KEY env: {'SET' if porcupine_key_env else 'NOT SET'}")
    
    # Load Vosk model
    print("\n3. Loading Vosk model...")
    model_path = config.vosk_model_path or os.getenv("VOSK_MODEL_PATH")
    if not model_path:
        print("   ❌ No Vosk model path")
        return
    
    model = Model(model_path)
    transcriber = StreamingTranscriber(sample_rate=config.sample_rate_hz, model=model)
    print(f"   ✓ Vosk model loaded: {model_path}")
    
    # Create wake listener
    print("\n4. Creating wake word listener...")
    print("   (Watch for log messages about which method is used)")
    print()
    
    def dummy_callback(buffer):
        print(f"   Wake word detected! (buffer size: {len(buffer)})")
    
    try:
        listener = create_wake_listener(
            config=config,
            transcriber=transcriber,
            on_detect=dummy_callback,
        )
        
        print()
        print("="*70)
        print("RESULT")
        print("="*70)
        print(f"✓ Wake listener created successfully")
        print(f"  Type: {type(listener).__name__}")
        
        # Detection method is shown in the logs above
        
        return listener
        
    except Exception as e:
        print(f"\n❌ Failed to create wake listener: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    listener = test_wake_word_setup()
    
    if listener:
        print("\n" + "="*70)
        print("RECOMMENDATION")
        print("="*70)
        
        if type(listener).__name__ == "WakeWordListener":
            print("✓ Using Vosk STT-based wake word detection")
            print("  This is working correctly!")
            print()
            print("  If wake word detection is unreliable:")
            print("  1. Adjust wake_sensitivity in config.json (try 0.5)")
            print("  2. Add more wake_variants")
            print("  3. Speak more clearly")
        else:
            print("✓ Using Porcupine wake word detection")
            print("  This should be more accurate than Vosk")
        
        print()
