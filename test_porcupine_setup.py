#!/usr/bin/env python3
"""Quick test to verify Porcupine setup is working."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from app.util.config import load_config
from app.audio.wake_hybrid import HybridWakeWordManager, PORCUPINE_AVAILABLE

def main():
    print("=" * 60)
    print("PORCUPINE SETUP VERIFICATION")
    print("=" * 60)

    # Load environment
    load_dotenv()

    # Check 1: Porcupine module available
    print(f"\n1. Porcupine module available: {'✅ YES' if PORCUPINE_AVAILABLE else '❌ NO'}")

    # Check 2: API key configured
    api_key = os.getenv('PORCUPINE_ACCESS_KEY')
    print(f"2. API key configured: {'✅ YES' if api_key else '❌ NO'}")
    if api_key:
        print(f"   Key: {api_key[:20]}...{api_key[-10:]}")

    # Check 3: Config loads correctly
    try:
        config = load_config()
        print(f"3. Config loaded: ✅ YES")
        print(f"   - wake_word: {config.wake_word}")
        print(f"   - prefer_porcupine: {config.prefer_porcupine}")
        print(f"   - porcupine_sensitivity: {config.porcupine_sensitivity}")
        print(f"   - porcupine_access_key loaded: {'✅' if config.porcupine_access_key else '❌'}")
    except Exception as e:
        print(f"3. Config loaded: ❌ NO - {e}")
        return 1

    # Check 4: Hybrid manager detection
    print(f"\n4. Testing hybrid manager...")

    # Create a mock transcriber (we won't actually use it)
    class MockTranscriber:
        pass

    try:
        manager = HybridWakeWordManager(
            wake_word=config.wake_word,
            wake_variants=config.wake_variants,
            on_detect=lambda x: None,
            transcriber=MockTranscriber(),
            porcupine_access_key=config.porcupine_access_key,
            porcupine_sensitivity=config.porcupine_sensitivity,
            prefer_porcupine=config.prefer_porcupine,
        )

        # Check what method it would use (without actually creating listener)
        can_use_porcupine = manager._can_use_porcupine()
        print(f"   Can use Porcupine: {'✅ YES' if can_use_porcupine else '❌ NO'}")

        if can_use_porcupine:
            print(f"   Selected method: 🎯 PORCUPINE (high accuracy, low CPU)")
        else:
            print(f"   Selected method: 📝 VOSK (STT-based fallback)")

        info = manager.get_info()
        print(f"\n   Detection Info:")
        print(f"   - Porcupine available: {info['porcupine_available']}")
        print(f"   - Porcupine configured: {info['porcupine_configured']}")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Summary
    print("\n" + "=" * 60)
    if can_use_porcupine:
        print("✅ SUCCESS: Porcupine is ready to use!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Run: python app/main.py")
        print("  2. Look for: '✅ Using Porcupine wake word detection'")
        print("  3. Say 'hey glasses' to test!")
        print("\nTo train custom 'hey glasses' wake word:")
        print("  See: PORCUPINE_SETUP_GUIDE.md")
    else:
        print("⚠️  WARNING: Will fall back to Vosk STT detection")
        print("=" * 60)
        print("\nThis is fine! Vosk works well too.")
        print("To enable Porcupine:")
        print("  1. Check API key in .env")
        print("  2. Run: pip install pvporcupine")
        print("  3. See: PORCUPINE_SETUP_GUIDE.md")

    print("\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
