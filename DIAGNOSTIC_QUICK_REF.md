# Diagnostic Tool Quick Reference Card

## Quick Commands

### Run All Tests
```bash
python3 diagnostic_voice_assistant.py
```

### Run Specific Test
```bash
python3 diagnostic_voice_assistant.py --test 1    # Speech capture
python3 diagnostic_voice_assistant.py --test 2    # Wake word
python3 diagnostic_voice_assistant.py --test 3    # TTS + mic
python3 diagnostic_voice_assistant.py --test 4    # Multi-turn
python3 diagnostic_voice_assistant.py --test 5    # Silence
python3 diagnostic_voice_assistant.py --test 6    # Termination
python3 diagnostic_voice_assistant.py --test 7    # Short utterances
python3 diagnostic_voice_assistant.py --test 8    # Edge cases
```

### Real-Time Monitor
```bash
python3 diagnostic_voice_assistant.py --monitor
python3 diagnostic_voice_assistant.py --monitor --monitor-duration 120
```

### Interactive Mode
```bash
python3 diagnostic_voice_assistant.py --interactive
```

### Save Logs
```bash
python3 diagnostic_voice_assistant.py --log-file results.jsonl
```

### Custom Config
```bash
python3 diagnostic_voice_assistant.py --config custom_config.json
```

### Wake Word Attempts
```bash
python3 diagnostic_voice_assistant.py --test 2 --wake-attempts 5
```

## Test Summary

| Test | Name | Duration | Tests |
|------|------|----------|-------|
| 1 | Speech Capture | ~30s | Full utterance captured, no truncation |
| 2 | Wake Word | ~30s | Reliable detection, pre-roll buffer |
| 3 | TTS + Mic | ~20s | Consistent TTS, mic reopens |
| 4 | Multi-turn | ~2-5min | Multiple turns, context preserved |
| 5 | Silence | ~20s | 15s silence handled gracefully |
| 6 | Termination | ~15s | "bye glasses" exits cleanly |
| 7 | Short Utterances | ~15s | Brief words captured ("yes", "ok") |
| 8 | Edge Cases | ~30s | Mid-sentence pauses handled |

## Common Issues & Quick Fixes

### Clipped Speech (First Syllables Lost)
```json
// config.json
{
  "pre_roll_ms": 600,        // ↑ Increase from 400
  "vad_aggressiveness": 1    // ↓ More sensitive
}
```

### Unreliable Wake Word
```json
{
  "wake_sensitivity": 0.80,  // ↑ Increase from 0.65
  "wake_variants": ["hey glasses", "hay glasses", "a glasses"]
}
```

### System Stops After First Reply
- Check Test 3 and Test 4 results
- Verify mic re-engagement delay <500ms
- Review SessionManager._await_followup() logs

### Context Lost Between Turns
```json
{
  "followup_timeout_ms": 20000  // ↑ Increase from 15000
}
```
- Check Test 4 Context logs
- Verify history is appending

### Short Words Not Captured
```python
# In capture.py or config
min_speech_frames = 2         // ↓ Reduce from 3
vad_aggressiveness = 1        // ↓ More sensitive
```

### Mid-Sentence Cuts
```json
{
  "silence_ms": 2000           // ↑ Increase from 1500
}
```

## Log Components

| Component | Description |
|-----------|-------------|
| `System` | Test execution and status |
| `VAD` | Voice activity detection |
| `WakeWord` | Wake word events |
| `STT` | Speech transcription |
| `TTS` | Text-to-speech output |
| `Session` | Session state changes |
| `Context` | Conversation memory |
| `Validator` | Automated checks |
| `Monitor` | Real-time monitoring |

## Validation Checks

| Check | Description | Pass Criteria |
|-------|-------------|---------------|
| speech_duration | Audio capture length | ≥500ms (or ≥100ms for short) |
| wake_word_success_rate | Wake detection rate | ≥66% (2/3 attempts) |
| mic_reengagement | Mic reopen delay | ≤500ms |
| context_preservation | History retention | Grows or stays same |
| multi_turn_count | Conversation turns | ≥2 turns |
| session_termination | Exit reason | "bye", "timeout15", "manual" |
| no_truncation | Complete transcript | ≥5 words (or ≥3 for short) |

## Key Metrics to Track

### Performance Baselines
- Wake word success: **>90%**
- Speech capture accuracy: **>95%**
- TTS consistency: **100%**
- Multi-turn capability: **≥3 turns**
- Mic re-engagement: **<500ms**
- Context preservation: **100%**

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | One or more tests failed |

## Help

```bash
python3 diagnostic_voice_assistant.py --help
```

Full documentation: `DIAGNOSTIC_TOOL_GUIDE.md`
