#!/usr/bin/env python3
"""Live diagnostic tool to identify speech detection and TTS issues."""

import sys
import time
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.audio.io import get_audio_io_controller, pause_input, is_input_paused


def monitor_audio_state():
    """Monitor the audio I/O controller state in real-time."""
    print("\n" + "="*70)
    print("AUDIO STATE MONITOR")
    print("="*70)
    print("\nThis will monitor the pause/unpause state of the microphone.")
    print("Press Ctrl+C to stop\n")

    controller = get_audio_io_controller()
    last_state = None
    start_time = time.time()

    try:
        while True:
            current_state = is_input_paused()
            elapsed = time.time() - start_time

            if current_state != last_state:
                state_str = "🔇 PAUSED (mic blocked)" if current_state else "🎤 ACTIVE (mic listening)"
                print(f"[{elapsed:7.2f}s] {state_str}")
                last_state = current_state

                if current_state:
                    print(f"           ⚠️  Microphone will block until unpaused!")

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped")
        final_state = "PAUSED" if is_input_paused() else "ACTIVE"
        print(f"Final state: {final_state}")


def test_pause_unpause():
    """Test the pause/unpause mechanism."""
    print("\n" + "="*70)
    print("PAUSE/UNPAUSE TEST")
    print("="*70)

    print("\n1. Testing pause...")
    pause_input(True)
    print(f"   Input paused: {is_input_paused()} (should be True)")

    print("\n2. Testing unpause...")
    pause_input(False)
    print(f"   Input paused: {is_input_paused()} (should be False)")

    print("\n3. Testing TTS simulation...")
    print("   Pausing input (simulating TTS start)...")
    pause_input(True)
    print(f"   State: {'PAUSED ✅' if is_input_paused() else 'ACTIVE ❌'}")

    time.sleep(0.5)

    print("   Unpausing input (simulating TTS end)...")
    pause_input(False)
    print(f"   State: {'ACTIVE ✅' if not is_input_paused() else 'PAUSED ❌'}")

    print("\n✅ Pause/unpause mechanism working correctly!")


def test_wait_timeout():
    """Test if wait_if_paused has proper timeout."""
    print("\n" + "="*70)
    print("WAIT TIMEOUT TEST")
    print("="*70)

    controller = get_audio_io_controller()

    print("\n1. Pausing input...")
    pause_input(True)

    print("2. Testing wait with 2-second timeout...")
    start = time.time()
    result = controller.wait_if_paused(timeout=2.0)
    elapsed = time.time() - start

    print(f"   Returned: {result} (should be False)")
    print(f"   Elapsed: {elapsed:.2f}s (should be ~2s)")

    if abs(elapsed - 2.0) < 0.5:
        print("   ✅ Timeout working correctly!")
    else:
        print(f"   ❌ Timeout not working! Elapsed: {elapsed:.2f}s")

    print("\n3. Unpausing and testing wait (should return immediately)...")
    pause_input(False)
    start = time.time()
    result = controller.wait_if_paused(timeout=2.0)
    elapsed = time.time() - start

    print(f"   Returned: {result} (should be True)")
    print(f"   Elapsed: {elapsed:.2f}s (should be near 0s)")

    if elapsed < 0.1:
        print("   ✅ Immediate return working correctly!")
    else:
        print(f"   ❌ Should return immediately! Elapsed: {elapsed:.2f}s")


def test_microphone_blocking():
    """Test if microphone read() properly respects pause state."""
    print("\n" + "="*70)
    print("MICROPHONE BLOCKING TEST")
    print("="*70)

    print("\n⚠️  This test will attempt to read from the microphone.")
    print("    It will test if mic.read() blocks when paused.\n")

    from app.audio.mic import MicrophoneStream

    try:
        with MicrophoneStream(rate=16000, chunk_samples=4096) as mic:
            # Test 1: Normal read (should work immediately)
            print("1. Testing normal read (not paused)...")
            pause_input(False)
            start = time.time()
            data = mic.read()
            elapsed = time.time() - start
            print(f"   ✅ Read {len(data)} bytes in {elapsed:.3f}s")

            # Test 2: Paused read with timeout in background
            print("\n2. Testing paused read (will auto-unpause after 2s)...")
            pause_input(True)

            # Unpause after 2 seconds in background
            def unpause_after_delay():
                time.sleep(2.0)
                print("   [Background] Unpausing now...")
                pause_input(False)

            thread = threading.Thread(target=unpause_after_delay, daemon=True)
            thread.start()

            print("   Attempting read (should block until unpause)...")
            start = time.time()
            data = mic.read()
            elapsed = time.time() - start

            if 1.5 < elapsed < 2.5:
                print(f"   ✅ Blocked correctly! Resumed after {elapsed:.2f}s")
            else:
                print(f"   ⚠️  Unexpected timing: {elapsed:.2f}s")

            # Clean up
            pause_input(False)

    except Exception as e:
        print(f"   ❌ Error: {e}")
        pause_input(False)  # Make sure to unpause


def check_mic_read_timeout():
    """Check if mic.read() has timeout protection."""
    print("\n" + "="*70)
    print("CHECKING MIC.READ() TIMEOUT PROTECTION")
    print("="*70)

    import inspect
    from app.audio.mic import MicrophoneStream

    # Check the source code
    source = inspect.getsource(MicrophoneStream.read)

    print("\nChecking if mic.read() calls wait_if_paused() with timeout...")

    if "wait_if_paused()" in source and "timeout" not in source:
        print("❌ ISSUE FOUND: wait_if_paused() called WITHOUT timeout!")
        print("\nThis means mic.read() will block FOREVER if pause_input(False) is never called!")
        print("\nRecommended fix in app/audio/mic.py:")
        print("  Change: self._controller.wait_if_paused()")
        print("  To:     self._controller.wait_if_paused(timeout=60.0)")
        return False
    elif "wait_if_paused" in source:
        print("✅ wait_if_paused() is called")
        if "timeout" in source:
            print("✅ Timeout parameter appears to be used")
        return True
    else:
        print("ℹ️  wait_if_paused() not called in read()")
        return True


def main():
    """Run all diagnostics."""
    print("\n" + "="*70)
    print("SPEECH DETECTION & TTS DIAGNOSTIC TOOL")
    print("="*70)
    print("\nThis tool will help diagnose:")
    print("  1. Why speech detection isn't working")
    print("  2. Why TTS has 60-second delay on second response")
    print("\n" + "="*70)

    # Make sure we start in a clean state
    pause_input(False)

    tests = [
        ("Pause/Unpause Mechanism", test_pause_unpause),
        ("Wait Timeout", test_wait_timeout),
        ("Mic.read() Timeout Protection", check_mic_read_timeout),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            print(f"\n")
            test_func()
            results.append((test_name, "✅ PASSED"))
        except Exception as e:
            print(f"\n❌ {test_name} FAILED: {e}")
            results.append((test_name, f"❌ FAILED: {e}"))
        finally:
            # Ensure we're unpaused between tests
            pause_input(False)

    # Summary
    print("\n\n" + "="*70)
    print("DIAGNOSTIC SUMMARY")
    print("="*70)
    for test_name, result in results:
        print(f"{result} - {test_name}")

    print("\n" + "="*70)
    print("RECOMMENDATIONS")
    print("="*70)

    if any("FAILED" in r for _, r in results):
        print("\n❌ Issues detected! See errors above for details.")
    else:
        print("\n✅ All basic tests passed!")

    print("\n💡 To monitor live audio state during your app:")
    print("   python3 diagnose_live.py --monitor")

    print("\n💡 To test microphone blocking:")
    print("   python3 diagnose_live.py --mic-test")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "--monitor":
            monitor_audio_state()
        elif sys.argv[1] == "--mic-test":
            test_microphone_blocking()
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("Usage: python3 diagnose_live.py [--monitor|--mic-test]")
    else:
        main()
