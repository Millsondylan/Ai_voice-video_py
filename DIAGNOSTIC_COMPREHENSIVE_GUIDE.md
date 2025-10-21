# Comprehensive Voice Assistant Diagnostic Guide

## Overview

The `test_voice_diagnostic_comprehensive.py` script is a production-ready diagnostic tool designed to identify and log issues in your voice assistant pipeline. It tests:

1. **Reliable Speech Capture** - Verifies full utterance capture without clipping
2. **Wake Word Detection** - Measures wake word recognition accuracy
3. **Multi-turn Conversation** - Tests continuous listening after responses
4. **Conversation History** - Validates context retention across turns
5. **Timeout Logic** - Tests 15-second silence timeout
6. **Exit Phrase Handling** - Validates "bye glasses" termination

## Quick Start

### Basic Usage

```bash
# Run all diagnostic tests
python test_voice_diagnostic_comprehensive.py

# Run specific test suite
python test_voice_diagnostic_comprehensive.py --test wake
python test_voice_diagnostic_comprehensive.py --test multiturn
python test_voice_diagnostic_comprehensive.py --test timeout

# Enable verbose debug output
python test_voice_diagnostic_comprehensive.py --verbose

# Enable actual TTS output (default is simulated)
python test_voice_diagnostic_comprehensive.py --tts
```

### Available Test Suites

| Test Name | Description |
|-----------|-------------|
| `wake` | Tests wake word detection accuracy |
| `nowake` | Tests behavior without wake word (should be ignored) |
| `multiturn` | Tests multi-turn conversation continuity |
| `timeout` | Tests 15-second inactivity timeout |
| `exit` | Tests exit phrase ("bye glasses") handling |
| `all` | Runs all test suites (default) |

## How It Works

### 1. Voice Activity Detection (VAD)

The script uses WebRTC VAD with configurable parameters:

- **Pre-roll Buffer**: Captures ~90ms of audio before speech onset to avoid clipping first syllables
- **Hangover Period**: Continues recording ~300ms after silence to avoid cutting off last words
- **Aggressiveness**: Configurable (0-3) to balance sensitivity vs. noise rejection

**What to Look For in Logs:**

```
[00:00:01.234] [VAD] Speech started at frame 42 (including 3 pre-roll frames)
[00:00:03.567] [VAD] Speech ended at frame 156; segment duration 2.33s
```

**Diagnosis:**
- If captured duration is shorter than expected → Increase `pre_roll_frames` or `hangover_frames`
- If VAD triggers on noise → Increase `vad_mode` (more aggressive)
- If VAD misses soft speech → Decrease `vad_mode` (less aggressive)

### 2. Speech Transcription (STT)

Uses Vosk for speech-to-text with detailed logging:

```
[00:00:03.789] [STT] Transcription: "hey glasses what time is it"
```

**Diagnosis:**
- If transcription is empty → Check audio quality or VAD settings
- If words are missing → Likely VAD clipping issue (adjust pre-roll/hangover)
- If transcription is incorrect → May need better Vosk model or clearer speech

### 3. Wake Word Detection

Tests wake word recognition with detailed success/failure logging:

```
[00:00:03.890] [WAKE] Wake word detected!
[00:00:03.891] [CONVERSATION] Conversation activated
```

**Diagnosis:**
- If wake word missed → Check if it appears in transcription
  - If in transcription but not detected → Bug in wake word matching logic
  - If not in transcription → STT or audio capture issue
- If false positives → Wake word matching too lenient

### 4. Multi-turn Conversation

Tests continuous listening after TTS response:

```
[00:00:05.123] [TTS] Speaking: "You said: what time is it"
[00:00:05.456] [TTS] Finished speaking
[00:00:05.457] [CONVERSATION] Resuming listening for follow-up...
[00:00:07.890] [MIC] Voice detected, capturing...
```

**Diagnosis:**
- If no follow-up captured → TTS may not be releasing microphone
  - Check for pyttsx3 blocking issues
  - Verify microphone re-initialization after TTS
- If follow-up requires wake word → Conversation state not maintained

### 5. Conversation History

Logs conversation history after each turn:

```
[00:00:08.123] [CONVERSATION] History updated: 2 turns
```

**Diagnosis:**
- If history resets → State management bug
- If history missing entries → Context not being appended correctly

### 6. Timeout Handling

Tests 15-second silence timeout:

```
[00:00:20.456] [MIC] Timeout after 15s
[00:00:20.457] [CONVERSATION] Conversation ended: timeout
```

**Diagnosis:**
- If timeout doesn't trigger → Timer not implemented or not checking
- If timeout too early → Timer started at wrong time

## Configuration

### Default Settings

```python
DiagnosticConfig(
    wake_word="hey glasses",
    exit_phrase="bye glasses",
    vad_mode=1,                # 0-3, higher = more aggressive
    frame_duration_ms=30,      # 10, 20, or 30 ms
    pre_roll_frames=3,         # ~90ms pre-roll
    hangover_frames=10,        # ~300ms hangover
    followup_timeout_sec=15,   # 15 second timeout
    sample_rate=16000,         # 16kHz audio
)
```

### Tuning Parameters

#### VAD Aggressiveness (`vad_mode`)

- **0** (Least aggressive): Captures more audio, may include noise
- **1** (Default): Balanced for normal environments
- **2**: More aggressive, filters more noise
- **3** (Most aggressive): May clip soft speech

#### Pre-roll Frames (`pre_roll_frames`)

- **3 frames** @ 30ms = ~90ms of audio before speech onset
- Increase if first syllables are being cut off
- Decrease if capturing too much leading silence

#### Hangover Frames (`hangover_frames`)

- **10 frames** @ 30ms = ~300ms of audio after speech ends
- Increase if last words are being cut off
- Decrease if capturing too much trailing silence

## Output Files

### Log File

Timestamped JSONL file with all diagnostic events:

```
diagnostic_20250121_143022.jsonl
```

Each line is a JSON object:

```json
{
  "timestamp": "[00:00:01.234]",
  "elapsed_s": 1.234,
  "component": "VAD",
  "message": "Speech started at frame 42",
  "level": "DEBUG",
  "frame_index": 42,
  "pre_roll_frames": 3
}
```

### Summary File

Complete test summary in JSON format:

```
diagnostic_summary_20250121_143022.json
```

Contains all log entries for post-analysis.

## Interpreting Results

### Successful Test Output

```
[00:00:01.234] [INIT] Initializing diagnostic components...
[00:00:01.456] [INIT] Loaded Vosk model: models/vosk-model-small-en-us-0.15
[00:00:01.567] [INIT] VAD initialized: mode=1, frame=30ms, pre-roll=3, hangover=10
[00:00:01.678] [TEST] Starting test suite: wake
[00:00:01.789] [SCENARIO] *** Query with wake word 'hey glasses' ***
[00:00:02.000] [MIC] Listening...
[00:00:02.345] [MIC] Voice detected, capturing...
[00:00:04.567] [MIC] Silence hangover elapsed, stopping
[00:00:04.678] [CAPTURE] Captured 2.22s of audio
[00:00:04.890] [STT] Transcription: "hey glasses what time is it"
[00:00:04.901] [WAKE] Wake word detected!
[00:00:04.902] [CONVERSATION] Conversation activated
[00:00:04.903] [CONVERSATION] History updated: 1 turns
[00:00:05.000] [TTS] Speaking: "You said: what time is it"
[00:00:05.234] [TTS] Finished speaking
[00:00:05.235] [CONVERSATION] Resuming listening for follow-up...
```

### Common Issues and Solutions

#### Issue: First syllables cut off

**Symptoms:**
```
[STT] Transcription: "lasses what time is it"  # Missing "hey g"
```

**Solution:**
- Increase `pre_roll_frames` from 3 to 5 or more
- Decrease `vad_mode` to be less aggressive

#### Issue: Last words cut off

**Symptoms:**
```
[STT] Transcription: "hey glasses what time"  # Missing "is it"
```

**Solution:**
- Increase `hangover_frames` from 10 to 15 or more
- Check if VAD is too aggressive

#### Issue: Wake word not detected

**Symptoms:**
```
[STT] Transcription: "hey glasses what time is it"
[WAKE] No wake word detected
```

**Solution:**
- Check wake word matching logic (case sensitivity, exact match vs. substring)
- Verify wake word string matches expected format

#### Issue: No follow-up listening

**Symptoms:**
```
[TTS] Speaking: "You said: what time is it"
[TTS] Finished speaking
# No further output, system doesn't listen for follow-up
```

**Solution:**
- TTS blocking issue (pyttsx3 bug)
- Microphone not re-initialized after TTS
- Check conversation state management

#### Issue: Conversation history lost

**Symptoms:**
```
[CONVERSATION] History updated: 1 turns
# After second turn:
[CONVERSATION] History updated: 1 turns  # Should be 2!
```

**Solution:**
- State being reset between turns
- History not persisting across function calls

## Advanced Usage

### Custom Test Scenarios

You can modify the test scenarios in the script:

```python
TEST_SCENARIOS = {
    "custom": [
        TestScenario(
            name="custom_test",
            description="My custom test",
            expect_wake=True,
        ),
    ],
}
```

### Integration with Existing Code

The diagnostic script uses the same components as your main application:

```python
from app.audio.vad import VoiceActivityDetector
from app.audio.stt import StreamingTranscriber
from app.audio.tts import SpeechSynthesizer
from app.util.config import load_config
```

This ensures diagnostic results reflect actual production behavior.

### Automated Testing

Run diagnostics in CI/CD:

```bash
# Run with pre-recorded test files
python test_voice_diagnostic_comprehensive.py --test all --verbose > test_results.log

# Check for errors
grep ERROR test_results.log && exit 1 || exit 0
```

## Troubleshooting

### PyAudio Issues

If you get PyAudio errors:

```bash
# macOS
brew install portaudio
pip install pyaudio

# Linux
sudo apt-get install portaudio19-dev
pip install pyaudio
```

### Vosk Model Not Found

```bash
# Download Vosk model
cd models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

### pyttsx3 Issues

If TTS hangs or fails:

```bash
# Disable TTS output (use simulation)
python test_voice_diagnostic_comprehensive.py  # Default: TTS disabled

# Or fix pyttsx3
pip install --upgrade pyttsx3
```

## Best Practices

1. **Start with verbose mode** to see all debug output
2. **Run tests in a quiet environment** to avoid VAD false triggers
3. **Use consistent speech volume** for reproducible results
4. **Review log files** after each test run
5. **Compare before/after** when tuning parameters
6. **Test edge cases** (whisper, shout, background noise)

## Next Steps

After running diagnostics:

1. **Analyze log files** to identify specific issues
2. **Tune VAD parameters** based on findings
3. **Fix identified bugs** in main application
4. **Re-run diagnostics** to verify fixes
5. **Document optimal settings** for your environment

## Support

For issues or questions:

1. Check log files for detailed error messages
2. Review this guide for common issues
3. Examine the diagnostic script source code
4. Test with different Vosk models if STT accuracy is low

---

**Last Updated:** 2025-01-21
