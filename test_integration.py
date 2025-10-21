#!/usr/bin/env python3
"""Test complete integration of Vosk accuracy improvements."""

import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test all new modules import correctly."""
    print("\n" + "="*70)
    print("TESTING IMPORTS")
    print("="*70)

    tests = []

    # Test 1: StreamingTranscriber with new parameters
    try:
        from app.audio.stt import StreamingTranscriber
        print("✅ StreamingTranscriber imports")
        tests.append(("StreamingTranscriber", True, None))
    except Exception as e:
        print(f"❌ StreamingTranscriber import failed: {e}")
        tests.append(("StreamingTranscriber", False, str(e)))

    # Test 2: Validation module
    try:
        from app.audio.validation import (
            validate_audio_format,
            get_audio_info,
            validate_with_suggestions,
        )
        print("✅ Audio validation module imports")
        tests.append(("Audio validation", True, None))
    except Exception as e:
        print(f"❌ Audio validation import failed: {e}")
        tests.append(("Audio validation", False, str(e)))

    # Test 3: Diagnostics module
    try:
        from app.audio.audio_diagnostics import (
            analyze_audio_quality,
            generate_quality_report,
        )
        print("✅ Audio diagnostics module imports")
        tests.append(("Audio diagnostics", True, None))
    except Exception as e:
        print(f"❌ Audio diagnostics import failed: {e}")
        tests.append(("Audio diagnostics", False, str(e)))

    # Test 4: Preprocessing module
    try:
        from app.audio.preprocessing import AudioPreprocessor
        print("✅ Audio preprocessing module imports")
        tests.append(("Audio preprocessing", True, None))
    except Exception as e:
        print(f"❌ Audio preprocessing import failed: {e}")
        tests.append(("Audio preprocessing", False, str(e)))

    # Test 5: Enhanced mic module
    try:
        from app.audio.mic import MicrophoneStream
        # Check for new methods
        assert hasattr(MicrophoneStream, 'validate_device_supports_format')
        assert hasattr(MicrophoneStream, 'get_device_details')
        assert hasattr(MicrophoneStream, 'print_device_info')
        print("✅ Enhanced MicrophoneStream imports")
        tests.append(("Enhanced MicrophoneStream", True, None))
    except Exception as e:
        print(f"❌ Enhanced MicrophoneStream failed: {e}")
        tests.append(("Enhanced MicrophoneStream", False, str(e)))

    # Test 6: Enhanced logging
    try:
        from app.util.log import get_event_logger
        logger = get_event_logger()
        # Check new signature works
        import inspect
        sig = inspect.signature(logger.log_stt_final)
        assert 'confidence' in sig.parameters
        assert 'low_confidence_words' in sig.parameters
        print("✅ Enhanced logging imports")
        tests.append(("Enhanced logging", True, None))
    except Exception as e:
        print(f"❌ Enhanced logging failed: {e}")
        tests.append(("Enhanced logging", False, str(e)))

    # Test 7: Enhanced diagnostics
    try:
        from app.util.diagnostics import SessionDiagnostics
        # Check for new methods
        assert hasattr(SessionDiagnostics, 'validate_audio')
        assert hasattr(SessionDiagnostics, 'log_stt_confidence')
        print("✅ Enhanced SessionDiagnostics imports")
        tests.append(("Enhanced SessionDiagnostics", True, None))
    except Exception as e:
        print(f"❌ Enhanced SessionDiagnostics failed: {e}")
        tests.append(("Enhanced SessionDiagnostics", False, str(e)))

    return tests


def test_transcriber_instantiation():
    """Test StreamingTranscriber with new parameters."""
    print("\n" + "="*70)
    print("TESTING STREAMINGTRANCRIBER INSTANTIATION")
    print("="*70)

    tests = []

    try:
        from app.audio.stt import StreamingTranscriber
        from vosk import Model

        # Test with large model
        model_path = "models/vosk-model-en-us-0.22"
        if not Path(model_path).exists():
            print(f"⚠️ Model not found at {model_path}")
            tests.append(("Model exists", False, "Model path not found"))
            return tests

        model = Model(model_path)
        print(f"✅ Model loaded from {model_path}")
        tests.append(("Model loading", True, None))

        # Test instantiation with new parameters
        transcriber = StreamingTranscriber(
            sample_rate=16000,
            model=model,
            enable_words=True,
            max_alternatives=3,
        )
        print("✅ StreamingTranscriber instantiated with new parameters")
        tests.append(("Transcriber instantiation", True, None))

        # Test new methods exist
        assert hasattr(transcriber, 'get_average_confidence')
        assert hasattr(transcriber, 'get_low_confidence_words')
        print("✅ New confidence methods available")
        tests.append(("Confidence methods", True, None))

        # Test calling new methods
        avg_conf = transcriber.get_average_confidence()
        low_conf = transcriber.get_low_confidence_words()
        print(f"✅ Confidence methods callable (avg: {avg_conf}, low_conf count: {len(low_conf)})")
        tests.append(("Confidence methods callable", True, None))

    except Exception as e:
        print(f"❌ Transcriber test failed: {e}")
        tests.append(("Transcriber test", False, str(e)))

    return tests


def test_config_settings():
    """Test optimized config settings."""
    print("\n" + "="*70)
    print("TESTING CONFIG SETTINGS")
    print("="*70)

    tests = []

    try:
        import json
        config_path = Path("config.json")

        if not config_path.exists():
            print("⚠️ config.json not found")
            tests.append(("Config exists", False, "File not found"))
            return tests

        with open(config_path) as f:
            config = json.load(f)

        # Check optimized settings
        checks = {
            "chunk_samples": (4096, "Should be 4096"),
            "vad_aggressiveness": (3, "Should be 3"),
            "silence_ms": (800, "Should be 800"),
            "min_speech_frames": (3, "Should be 3"),
            "tail_padding_ms": (200, "Should be 200"),
        }

        all_correct = True
        for key, (expected, desc) in checks.items():
            actual = config.get(key)
            if actual == expected:
                print(f"✅ {key}: {actual}")
                tests.append((f"Config: {key}", True, None))
            else:
                print(f"⚠️ {key}: {actual} (expected {expected} - {desc})")
                tests.append((f"Config: {key}", False, f"Got {actual}, expected {expected}"))
                all_correct = False

        if all_correct:
            print("\n✅ All config settings optimized!")

    except Exception as e:
        print(f"❌ Config test failed: {e}")
        tests.append(("Config test", False, str(e)))

    return tests


def test_main_py_integration():
    """Test that app/main.py uses new transcriber parameters."""
    print("\n" + "="*70)
    print("TESTING MAIN.PY INTEGRATION")
    print("="*70)

    tests = []

    try:
        # Read main.py and check for new parameters
        main_path = Path("app/main.py")
        with open(main_path) as f:
            content = f.read()

        # Check that enable_words and max_alternatives are used
        if "enable_words=True" in content:
            print("✅ enable_words=True found in main.py")
            tests.append(("enable_words parameter", True, None))
        else:
            print("❌ enable_words=True NOT found in main.py")
            tests.append(("enable_words parameter", False, "Not found"))

        if "max_alternatives=config.vosk_max_alternatives" in content:
            print("✅ max_alternatives uses config.vosk_max_alternatives in main.py")
            tests.append(("max_alternatives parameter", True, None))
        else:
            print("❌ max_alternatives configuration NOT found in main.py")
            tests.append(("max_alternatives parameter", False, "Not found"))

    except Exception as e:
        print(f"❌ main.py integration test failed: {e}")
        tests.append(("main.py integration", False, str(e)))

    return tests


def print_summary(all_tests):
    """Print test summary."""
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    total = len(all_tests)
    passed = sum(1 for _, success, _ in all_tests if success)
    failed = total - passed

    print(f"\nTotal tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")

    if failed > 0:
        print("\n❌ Failed tests:")
        for name, success, error in all_tests:
            if not success:
                print(f"  - {name}: {error}")
    else:
        print("\n🎉 ALL TESTS PASSED!")

    print("\n" + "="*70)

    return failed == 0


if __name__ == "__main__":
    all_tests = []

    all_tests.extend(test_imports())
    all_tests.extend(test_transcriber_instantiation())
    all_tests.extend(test_config_settings())
    all_tests.extend(test_main_py_integration())

    success = print_summary(all_tests)

    sys.exit(0 if success else 1)
