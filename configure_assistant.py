#!/usr/bin/env python3
"""
Complete configuration checker and tester for Glasses Voice Assistant.
Verifies all components are working before running the main application.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def print_header(title):
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def check_dependencies():
    """Check all required Python packages."""
    print_header("1. CHECKING DEPENDENCIES")

    required = {
        'vosk': 'Speech recognition',
        'pvporcupine': 'Wake word detection',
        'pyttsx3': 'Text-to-speech',
        'pyaudio': 'Audio I/O',
        'webrtcvad': 'Voice activity detection',
        'PyQt6': 'GUI framework',
        'cv2': 'Computer vision (opencv-python)',
        'dotenv': 'Environment variables (python-dotenv)',
    }

    missing = []
    for package, description in required.items():
        try:
            if package == 'cv2':
                import cv2
            elif package == 'dotenv':
                from dotenv import load_dotenv
            elif package == 'PyQt6':
                from PyQt6 import QtWidgets
            else:
                __import__(package)
            print(f"  ✅ {package:20s} - {description}")
        except ImportError:
            print(f"  ❌ {package:20s} - {description} (MISSING)")
            missing.append(package)

    if missing:
        print(f"\n  ⚠️  Missing packages: {', '.join(missing)}")
        print(f"  Install with: pip install {' '.join(missing)}")
        return False

    print("\n  ✅ All dependencies installed!")
    return True

def check_configuration():
    """Check configuration files."""
    print_header("2. CHECKING CONFIGURATION")

    from dotenv import load_dotenv
    load_dotenv()

    # Check .env file
    env_file = Path('.env')
    if not env_file.exists():
        print("  ❌ .env file not found")
        return False
    print(f"  ✅ .env file exists")

    # Check required env vars
    required_env = {
        'VOSK_MODEL_PATH': os.getenv('VOSK_MODEL_PATH'),
        'VLM_API_KEY': os.getenv('VLM_API_KEY'),
        'VLM_MODEL': os.getenv('VLM_MODEL'),
        'PORCUPINE_ACCESS_KEY': os.getenv('PORCUPINE_ACCESS_KEY'),
    }

    for var, value in required_env.items():
        if value:
            masked = f"{value[:20]}..." if len(value) > 20 else value
            print(f"  ✅ {var:25s} = {masked}")
        else:
            print(f"  ⚠️  {var:25s} = (not set)")

    # Check config.json
    config_file = Path('config.json')
    if not config_file.exists():
        print("  ❌ config.json not found")
        return False
    print(f"  ✅ config.json exists")

    # Load and validate config
    try:
        from app.util.config import load_config
        config = load_config()
        print(f"\n  Configuration loaded:")
        print(f"    - Wake word: {config.wake_word}")
        print(f"    - Prefer Porcupine: {config.prefer_porcupine}")
        print(f"    - Sample rate: {config.sample_rate_hz} Hz")
        print(f"    - VAD aggressiveness: {config.vad_aggressiveness}")
        print(f"    - Silence threshold: {config.silence_ms} ms")
        print(f"  ✅ Configuration valid!")
        return config
    except Exception as e:
        print(f"  ❌ Config error: {e}")
        return None

def check_vosk_model(config):
    """Check Vosk model exists."""
    print_header("3. CHECKING VOSK MODEL")

    model_path = Path(config.vosk_model_path)
    if not model_path.exists():
        print(f"  ❌ Vosk model not found at: {model_path}")
        print(f"  Download from: https://alphacephei.com/vosk/models")
        return False

    print(f"  ✅ Vosk model found: {model_path}")

    # Try to load model
    try:
        from vosk import Model
        print(f"  Loading model...")
        model = Model(str(model_path))
        print(f"  ✅ Vosk model loaded successfully!")
        return True
    except Exception as e:
        print(f"  ❌ Failed to load model: {e}")
        return False

def check_porcupine(config):
    """Check Porcupine wake word detection."""
    print_header("4. CHECKING PORCUPINE WAKE WORD")

    try:
        import pvporcupine
        print(f"  ✅ Porcupine module available")
    except ImportError:
        print(f"  ❌ Porcupine not installed")
        return False

    if not config.porcupine_access_key:
        print(f"  ⚠️  No Porcupine access key (will use Vosk fallback)")
        return True

    print(f"  ✅ Porcupine access key configured")

    # Test hybrid manager
    try:
        from app.audio.wake_hybrid import HybridWakeWordManager

        class MockTranscriber:
            pass

        manager = HybridWakeWordManager(
            wake_word=config.wake_word,
            wake_variants=config.wake_variants,
            on_detect=lambda x: None,
            transcriber=MockTranscriber(),
            porcupine_access_key=config.porcupine_access_key,
            porcupine_sensitivity=config.porcupine_sensitivity,
            prefer_porcupine=config.prefer_porcupine,
        )

        can_use = manager._can_use_porcupine()
        if can_use:
            print(f"  ✅ Will use: PORCUPINE (high accuracy)")
        else:
            print(f"  ✅ Will use: VOSK fallback (still works great)")

        return True
    except Exception as e:
        print(f"  ❌ Porcupine test failed: {e}")
        return False

def check_microphone():
    """Check microphone access."""
    print_header("5. CHECKING MICROPHONE")

    try:
        import pyaudio
        p = pyaudio.PyAudio()

        # List devices
        device_count = p.get_device_count()
        print(f"  Found {device_count} audio devices:")

        input_devices = []
        for i in range(device_count):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                input_devices.append((i, info['name']))
                default = " (DEFAULT)" if i == p.get_default_input_device_info()['index'] else ""
                print(f"    [{i}] {info['name']}{default}")

        if not input_devices:
            print(f"  ❌ No input devices found!")
            p.terminate()
            return False

        # Test recording
        print(f"\n  Testing microphone access...")
        try:
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=320
            )
            # Read one frame
            data = stream.read(320)
            stream.stop_stream()
            stream.close()
            print(f"  ✅ Microphone access working!")
        except Exception as e:
            print(f"  ❌ Microphone test failed: {e}")
            p.terminate()
            return False

        p.terminate()
        return True

    except Exception as e:
        print(f"  ❌ Audio check failed: {e}")
        return False

def check_camera(config):
    """Check camera access."""
    print_header("6. CHECKING CAMERA")

    try:
        import cv2

        camera_source = config.camera_source
        print(f"  Opening camera: {camera_source}")

        # Try to open camera
        cap = cv2.VideoCapture(int(camera_source) if camera_source.isdigit() else camera_source)

        if not cap.isOpened():
            print(f"  ❌ Could not open camera")
            return False

        # Try to read a frame
        ret, frame = cap.read()
        if not ret:
            print(f"  ❌ Could not read from camera")
            cap.release()
            return False

        print(f"  ✅ Camera opened successfully!")
        print(f"  Resolution: {frame.shape[1]}x{frame.shape[0]}")

        cap.release()
        return True

    except Exception as e:
        print(f"  ❌ Camera check failed: {e}")
        return False

def check_tts():
    """Check text-to-speech."""
    print_header("7. CHECKING TEXT-TO-SPEECH")

    try:
        import pyttsx3

        print(f"  Initializing TTS engine...")
        engine = pyttsx3.init()

        # Get voices
        voices = engine.getProperty('voices')
        print(f"  ✅ Found {len(voices)} voices")

        # Test speaking (commented out to avoid audio during config)
        # print(f"  Testing voice output...")
        # engine.say("Configuration test")
        # engine.runAndWait()

        print(f"  ✅ TTS engine ready!")
        return True

    except Exception as e:
        print(f"  ❌ TTS check failed: {e}")
        return False

def check_vlm_connection(config):
    """Check VLM API connection."""
    print_header("8. CHECKING VLM API")

    if not config.vlm_api_key:
        print(f"  ⚠️  VLM API key not set")
        return False

    print(f"  VLM Provider: {config.vlm_provider}")
    print(f"  VLM Model: {config.vlm_model}")
    print(f"  API Key: {config.vlm_api_key[:20]}...")

    # Note: We won't actually test the API call to avoid charges
    print(f"  ✅ VLM configured (not tested - will verify on first use)")
    return True

def main():
    """Run all configuration checks."""
    print("\n" + "=" * 70)
    print("  GLASSES VOICE ASSISTANT - CONFIGURATION CHECKER")
    print("=" * 70)

    results = {}

    # 1. Dependencies
    results['dependencies'] = check_dependencies()
    if not results['dependencies']:
        print("\n❌ Please install missing dependencies first!")
        return 1

    # 2. Configuration
    config = check_configuration()
    if not config:
        print("\n❌ Configuration invalid!")
        return 1
    results['configuration'] = True

    # 3. Vosk model
    results['vosk'] = check_vosk_model(config)

    # 4. Porcupine
    results['porcupine'] = check_porcupine(config)

    # 5. Microphone
    results['microphone'] = check_microphone()

    # 6. Camera
    results['camera'] = check_camera(config)

    # 7. TTS
    results['tts'] = check_tts()

    # 8. VLM
    results['vlm'] = check_vlm_connection(config)

    # Summary
    print_header("CONFIGURATION SUMMARY")

    for component, status in results.items():
        icon = "✅" if status else "❌"
        print(f"  {icon} {component.upper():20s}")

    all_good = all(results.values())

    print("\n" + "=" * 70)
    if all_good:
        print("  ✅ ALL SYSTEMS READY!")
        print("=" * 70)
        print("\n  Your voice assistant is configured and ready to run!")
        print("\n  Start with:")
        print("    python app/main.py")
        print("\n  Or use the quick start script:")
        print("    ./start_assistant.sh")
        print()
        return 0
    else:
        print("  ⚠️  SOME COMPONENTS NEED ATTENTION")
        print("=" * 70)
        print("\n  Please fix the issues above before running.")
        print("  The assistant may still work with reduced functionality.")
        print()
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Configuration check interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
