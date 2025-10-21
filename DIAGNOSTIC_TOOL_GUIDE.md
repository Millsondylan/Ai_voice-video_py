# Enhanced Voice Assistant Diagnostic Tool - User Guide

## Overview

The **Enhanced Voice Assistant Diagnostic Tool** (`diagnostic_voice_assistant.py`) is a comprehensive testing and debugging utility designed to identify and diagnose issues in Vosk/Whisper-based voice assistant systems. It provides detailed timing logs, real-time monitoring, and validation to pinpoint problems like:

- ✅ Partial audio capture (first syllables lost)
- ✅ Unreliable wake-word detection
- ✅ System becoming unresponsive after TTS
- ✅ Loss of conversational context
- ✅ VAD timing and threshold issues

## Quick Start

### Basic Usage

Run all diagnostic tests:
```bash
python3 diagnostic_voice_assistant.py
```

Run a specific test:
```bash
python3 diagnostic_voice_assistant.py --test 1
```

Real-time monitoring mode:
```bash
python3 diagnostic_voice_assistant.py --monitor
```

Interactive guided mode:
```bash
python3 diagnostic_voice_assistant.py --interactive
```

Save detailed logs to file:
```bash
python3 diagnostic_voice_assistant.py --log-file diagnostic_results.jsonl
```

## Execution Modes

### 1. Full Diagnostic Mode (Default)

Runs all 8 comprehensive tests automatically:

```bash
python3 diagnostic_voice_assistant.py
```

**What it does:**
- Executes all 8 diagnostic tests sequentially
- Provides detailed logging with millisecond-precision timestamps
- Validates expected behaviors automatically
- Generates comprehensive summary report
- Identifies specific issues with actionable recommendations

**When to use:**
- Initial system diagnostic
- After making configuration changes
- Before deploying to production
- Investigating intermittent issues

### 2. Individual Test Mode

Run specific tests by number (1-8):

```bash
python3 diagnostic_voice_assistant.py --test 4
```

**Available tests:**
- Test 1: Complete Speech Capture
- Test 2: Wake Word Reliability
- Test 3: TTS and Mic Re-engagement
- Test 4: Multi-turn Conversation
- Test 5: Silence Handling
- Test 6: Termination Command
- Test 7: Short Utterances
- Test 8: Edge Cases

**When to use:**
- Focused debugging of specific component
- Quick validation after fixing an issue
- Iterative testing during development

### 3. Real-Time Monitor Mode

Live display of VAD and wake word state:

```bash
python3 diagnostic_voice_assistant.py --monitor --monitor-duration 120
```

**What it shows:**
- Real-time VAD state (voice vs. silence)
- Wake word detection events
- Speech start/end timing
- Utterance count
- Continuous state updates every 10 seconds

**When to use:**
- Understanding VAD behavior patterns
- Debugging wake word detection issues
- Observing system under various acoustic conditions
- Training users on proper voice commands

### 4. Interactive Mode

Guided step-by-step testing:

```bash
python3 diagnostic_voice_assistant.py --interactive
```

**What it does:**
- Prompts you before each test
- Allows selective test execution
- Provides detailed instructions for each test
- You control the pace and flow

**When to use:**
- Learning how the system works
- Demonstrating issues to others
- Manual validation of specific scenarios
- Careful debugging of critical issues

## Test Suite Details

### Test 1: Complete Speech Capture

**Purpose:** Validates that the entire user utterance is captured without truncation

**What you'll do:**
1. Say a long sentence (10+ words) with natural pauses
2. Wait for silence detection to complete

**What it tests:**
- VAD detects speech start with correct timing
- No premature cutoff during speech
- Tail padding is applied after speech ends
- Entire utterance is transcribed

**Success criteria:**
- ✅ Stop reason is "silence", "bye", or "done"
- ✅ Transcript has at least 5 words
- ✅ Audio duration is reasonable (>500ms)
- ✅ No words are clipped or missing

**Common issues detected:**
- **Clipped beginnings:** VAD starts too late (adjust `pre_roll_ms`)
- **Clipped endings:** Insufficient tail padding (adjust `tail_padding_ms`)
- **Mid-sentence cuts:** Silence threshold too short (increase `silence_ms`)

### Test 2: Wake Word Reliability

**Purpose:** Validates consistent wake word detection

**What you'll do:**
1. Say the wake word (e.g., "hey glasses") multiple times
2. Wait 3 seconds between each attempt
3. Default: 3 attempts (configure with `--wake-attempts 5`)

**What it tests:**
- Wake word triggers on correct phrase
- Pre-roll buffer captures audio before detection
- Debouncing prevents multiple triggers
- Success rate meets threshold (≥66%)

**Success criteria:**
- ✅ At least 2 out of 3 attempts successful
- ✅ Pre-roll buffer populated on detection
- ✅ Detection latency is reasonable (<2s)

**Common issues detected:**
- **Low success rate:** Wake word sensitivity too low (increase `wake_sensitivity`)
- **No detection:** Check audio input device is correct
- **False positives:** Sensitivity too high (decrease `wake_sensitivity`)
- **Slow detection:** Check CPU load or model size

### Test 3: TTS and Microphone Re-engagement

**Purpose:** Validates TTS consistency and microphone state management

**What you'll do:**
- Listen to 4 sequential TTS messages
- Observe system behavior after each message

**What it tests:**
- TTS speaks all messages without failures
- Microphone closes during TTS playback
- Microphone reopens quickly after TTS ends
- No audio device conflicts

**Success criteria:**
- ✅ All TTS messages play successfully
- ✅ Average mic re-engagement delay <500ms
- ✅ No audio device errors

**Common issues detected:**
- **TTS failures:** Audio output device conflicts
- **Slow re-engagement:** System resource contention
- **Mic stays closed:** State management bug (critical issue)

### Test 4: Multi-turn Conversation with Context

**Purpose:** Validates multi-turn conversation flow and context retention

**What you'll do:**
1. Ask at least 2 questions in a row
2. Make the second question reference the first (e.g., "What's the weather?" then "How about tomorrow?")
3. Exit with "bye glasses" or wait 15 seconds

**What it tests:**
- Multiple conversation turns without wake word
- Context is preserved across turns
- State transitions work correctly (Recording → Thinking → Speaking → AwaitFollowup)
- Session can be terminated properly

**Success criteria:**
- ✅ At least 2 conversation turns completed
- ✅ Context history grows with each turn
- ✅ Session ends with expected reason (bye/timeout15)
- ✅ Follow-up questions work without wake word

**Common issues detected:**
- **Single turn only:** Follow-up timeout too short or state bug
- **Context loss:** History not being appended correctly
- **Premature exit:** Timeout misconfigured
- **Wake word required again:** Continued conversation mode not working

### Test 5: Silence Handling

**Purpose:** Validates system behavior during prolonged silence

**What you'll do:**
- Remain completely silent for 15 seconds while the system monitors

**What it tests:**
- System handles silence gracefully without crashing
- No premature timeout (before 15s)
- System remains responsive after silence period

**Success criteria:**
- ✅ 15+ seconds of silence recorded
- ✅ No speech falsely detected during silence
- ✅ System still operational after test

**Common issues detected:**
- **False speech detection:** VAD too sensitive (reduce `vad_aggressiveness`)
- **System timeout:** Check if session timeout is configured
- **Crash during silence:** Check for resource leaks

### Test 6: Termination Command

**Purpose:** Validates proper session termination with "bye glasses"

**What you'll do:**
- Say "bye glasses" when prompted

**What it tests:**
- "bye glasses" phrase is detected in transcript
- Session terminates cleanly
- Stop reason is correctly set to "bye"

**Success criteria:**
- ✅ "bye" detected in transcript
- ✅ Stop reason is "bye"
- ✅ Session ends immediately

**Common issues detected:**
- **Not detected:** Wake word variants don't include "bye" variations
- **Detected but continues:** Stop reason handling bug
- **Wrong transcription:** STT model issue

### Test 7: Short Utterances

**Purpose:** Validates capture of very brief speech

**What you'll do:**
- Say a very short word: "yes", "ok", or "no"

**What it tests:**
- VAD sensitivity adequate for brief speech
- STT transcribes short words correctly
- Audio duration is at least 100ms

**Success criteria:**
- ✅ Short utterance is transcribed
- ✅ Audio duration ≥100ms
- ✅ No empty or missing transcript

**Common issues detected:**
- **Not captured:** VAD threshold too high or requires longer speech
- **Too brief:** Check `min_speech_frames` configuration
- **Transcription missing:** STT confidence threshold too high

### Test 8: Edge Cases

**Purpose:** Validates handling of unusual input patterns

**What you'll do:**
- Say a sentence with a deliberate 1-second pause mid-sentence
- Example: "Turn on... [pause]... the kitchen light"

**What it tests:**
- Mid-sentence pauses don't split utterance
- System recovers from unexpected inputs
- VAD uses proper hangover to bridge pauses

**Success criteria:**
- ✅ Both parts of sentence are captured together
- ✅ At least 3 words in transcript
- ✅ Not split into multiple segments

**Common issues detected:**
- **Sentence split:** Silence threshold too short
- **Only first part:** VAD ends too quickly (needs hangover)
- **Only last part:** Pre-roll buffer insufficient

## Understanding the Output

### Log Format

All logs use structured format with millisecond-precision timestamps:

```
[HH:MM:SS.mmm] Component    : Message
```

**Components:**
- `System` - Overall test execution and status
- `VAD` - Voice Activity Detection events
- `WakeWord` - Wake word detection events
- `STT` - Speech-to-Text transcription
- `TTS` - Text-to-Speech output
- `Session` - Session management and state changes
- `Context` - Conversation context and memory
- `Validator` - Automated validation checks
- `Monitor` - Real-time monitoring events

**Log Levels:**
- `INFO` (white) - Normal informational messages
- `SUCCESS` (green) - Successful operations
- `WARNING` (yellow) - Warnings and non-critical issues
- `ERROR` (red) - Errors and failures
- `DEBUG` (gray) - Detailed diagnostic information

### Example Output

```
[00:00:00.000] System       : ================================================================================
[00:00:00.001] System       : TEST 1: COMPLETE SPEECH CAPTURE
[00:00:00.001] System       : ================================================================================
[00:00:00.002] System       : Instructions:
[00:00:00.002] System       :   1. Say a LONG sentence (10+ words) with natural pauses
[00:00:02.350] VAD          : 🗣️  Speech STARTED (utterance #1)
[00:00:04.120] VAD          : 🔇 Speech ENDED (duration: 1.770s)
[00:00:04.500] STT          : Transcript: 'Turn on the lights in the kitchen and dining room'
[00:00:04.501] STT          : Stop Reason: silence
[00:00:04.501] STT          : Duration: 4499ms
[00:00:04.501] STT          : Audio Captured: 1800ms
[00:00:04.502] STT          : Word Count: 10
[00:00:04.503] Validator    : ✅ speech_duration: Speech duration 1800ms (min: 500ms)
[00:00:04.504] Validator    : ✅ no_truncation: Transcript has 10 words (min: 5)
[00:00:04.505] System       : ✅ PASSED: Full speech captured successfully
```

### Validation Results

After each test, you'll see validation checks:

```
✅ speech_duration: Speech duration 1800ms (min: 500ms)
✅ no_truncation: Transcript has 10 words (min: 5)
✅ wake_word_success_rate: Wake word success rate: 100.0% (3/3)
❌ mic_reengagement: Mic re-engagement delay: 650.2ms
```

- ✅ Green checkmark = Validation passed
- ❌ Red X = Validation failed

### Final Summary

At the end of all tests, you'll get a comprehensive summary:

```
================================================================================
FINAL TEST SUMMARY
================================================================================
[00:05:23.456] System       : Tests Run: 8
[00:05:23.456] System       : Passed: 7
[00:05:23.456] System       : Failed: 1

[00:05:23.457] System       : Individual Test Results:
[00:05:23.457] System       :   Test 1 (Complete Speech Capture): ✅ PASSED
[00:05:23.457] System       :   Test 2 (Wake Word Reliability): ✅ PASSED
[00:05:23.457] System       :   Test 3 (TTS and Mic Re-engagement): ❌ FAILED
[00:05:23.457] System       :   Test 4 (Multi-turn Conversation): ✅ PASSED
...

================================================================================
VALIDATION SUMMARY
================================================================================
[00:05:23.460] Validator    : Total Checks: 15 | Passed: 14 | Failed: 1 | Rate: 93.3%
[00:05:23.461] Validator    : Failed checks:
[00:05:23.461] Validator    :   ❌ Test3 / mic_reengagement: Mic re-engagement delay: 650.2ms
```

## Troubleshooting Common Issues

### Issue: Clipped Speech (First Syllables Lost)

**Symptoms:**
- Test 1 fails with truncated transcript
- VAD speech start happens after user started speaking
- First words of utterance missing

**Root causes:**
1. Pre-roll buffer too small
2. VAD threshold too high
3. VAD activates too slowly

**Solutions:**
```json
// In config.json, increase pre_roll_ms:
{
  "pre_roll_ms": 600,  // Increase from 400
  "vad_aggressiveness": 1  // Reduce from 2 (more sensitive)
}
```

**Validation:**
- Re-run Test 1 with longer sentence
- Check VAD speech start timestamp matches when you actually started speaking
- Verify transcript includes all words

### Issue: Unreliable Wake Word Detection

**Symptoms:**
- Test 2 fails with <66% success rate
- Wake word sometimes doesn't trigger
- Multiple attempts needed

**Root causes:**
1. Wake word sensitivity too low
2. Background noise interfering
3. Microphone quality issues
4. Wake word pronunciation unclear

**Solutions:**
```json
// In config.json, increase sensitivity:
{
  "wake_sensitivity": 0.80,  // Increase from 0.65
  "wake_variants": [
    "hey glasses",
    "hay glasses",
    "hey-glasses",
    "a glasses"  // Add phonetic variants
  ]
}
```

**Validation:**
- Re-run Test 2 with 5 attempts: `--wake-attempts 5`
- Try from different distances/angles
- Check microphone input levels

### Issue: System Unresponsive After TTS

**Symptoms:**
- Test 3 or Test 4 fails
- Only first response works
- System doesn't listen after speaking
- Wake word required again

**Root causes:**
1. Microphone not reopening after TTS
2. State management bug in session manager
3. Audio device conflict

**Solutions:**
1. Check logs for "🎤 TTS ENDED - mic should reopen now"
2. Verify mic re-engagement delay is <500ms
3. Inspect session state transitions
4. Review `SessionManager._await_followup()` implementation

**Validation:**
- Run Test 4 with verbose logging
- Check if `AwaitFollowup` state is reached
- Monitor audio device in system settings during TTS

### Issue: Context Loss or Single-Turn Only

**Symptoms:**
- Test 4 completes only 1 turn
- Follow-up questions don't work
- Context history is empty
- System exits after first response

**Root causes:**
1. Follow-up timeout too short
2. Context not being appended to history
3. VAD not detecting follow-up speech
4. Session ending prematurely

**Solutions:**
```json
// In SessionManager initialization:
{
  "followup_timeout_ms": 20000  // Increase from 15000
}
```

Check context tracking:
```python
# In session manager, verify:
self._append_history(user_text, assistant_text)
# Is actually populating self._history
```

**Validation:**
- Re-run Test 4 and wait full 15s between questions
- Check Context logs show growing history
- Verify state transitions include AwaitFollowup

### Issue: Short Utterances Not Captured

**Symptoms:**
- Test 7 fails
- Words like "yes", "ok", "no" don't register
- Very brief audio captured (<100ms)

**Root causes:**
1. VAD requires minimum speech duration
2. min_speech_frames threshold too high
3. VAD aggressiveness too high

**Solutions:**
```python
# In config or capture.py:
min_speech_frames = 2  # Reduce from 3
vad_aggressiveness = 1  # More sensitive
```

**Validation:**
- Re-run Test 7 multiple times
- Try slightly longer words ("okay" instead of "ok")
- Check VAD logs show speech detection

### Issue: Mid-Sentence Pauses Split Utterance

**Symptoms:**
- Test 8 fails
- Sentence captured in multiple parts
- Context shows split transcripts
- Unnatural conversation flow

**Root causes:**
1. Silence threshold too short
2. No VAD hangover to bridge pauses
3. Consecutive silence frames trigger stop too quickly

**Solutions:**
```json
{
  "silence_ms": 2000  // Increase from 1500
}
```

Implement VAD hangover:
```python
# Allow brief silence during speech
if has_spoken and total_speech_frames >= min_speech_frames:
    silence_duration_ms = (now - last_speech_time) * 1000
    if silence_duration_ms >= config.silence_ms:
        # Only stop if silence exceeds threshold
```

**Validation:**
- Re-run Test 8 with deliberate pauses
- Try natural speech with "um", "uh" filler words
- Check transcript is complete sentence

## Advanced Configuration

### Tuning VAD Parameters

```json
{
  "vad_aggressiveness": 2,    // 0-3: 0=most sensitive, 3=least sensitive
  "pre_roll_ms": 400,         // Audio buffer before speech detection
  "silence_ms": 1500,         // Silence duration to end utterance
  "min_speech_frames": 3,     // Minimum consecutive speech frames
  "tail_padding_ms": 300      // Extra audio after speech ends
}
```

**Guidelines:**
- **Quiet environment:** `vad_aggressiveness: 3` (less sensitive, fewer false positives)
- **Noisy environment:** `vad_aggressiveness: 1` (more sensitive, captures softer speech)
- **Long utterances:** Increase `silence_ms` to 2000-3000
- **Quick responses:** Decrease `silence_ms` to 1000-1200
- **Clipped beginnings:** Increase `pre_roll_ms` to 500-800
- **Clipped endings:** Increase `tail_padding_ms` to 400-500

### Tuning Wake Word Detection

```json
{
  "wake_word": "hey glasses",
  "wake_variants": [
    "hey glasses",
    "hay glasses",
    "hey-glasses",
    "a glasses"
  ],
  "wake_sensitivity": 0.65,   // 0.0-1.0: higher = more sensitive
  "porcupine_sensitivity": 0.65
}
```

**Guidelines:**
- **Missing detections:** Increase `wake_sensitivity` to 0.75-0.85
- **False positives:** Decrease `wake_sensitivity` to 0.50-0.60
- **Accent variations:** Add phonetic variants to `wake_variants`
- **Fast speech:** Add compressed variants ("heyglasses")

### Custom Test Scenarios

You can modify the diagnostic script to add custom tests:

```python
def test_9_custom_scenario(
    config: AppConfig,
    transcriber: StreamingTranscriber,
    logger: DiagnosticLogger,
    validator: TestValidator,
) -> bool:
    """Custom test for specific use case."""
    logger.section("TEST 9: CUSTOM SCENARIO")

    # Your test implementation here

    return success
```

Add to main():
```python
elif test_num == 9:
    result = test_9_custom_scenario(config, segment_transcriber, logger, validator)
```

## Log File Analysis

When using `--log-file`, logs are saved in JSON Lines format for programmatic analysis:

```bash
python3 diagnostic_voice_assistant.py --log-file results.jsonl
```

Each line is a JSON object:
```json
{
  "timestamp": "[00:00:02.350]",
  "elapsed_s": 2.350,
  "component": "VAD",
  "message": "🗣️  Speech STARTED (utterance #1)",
  "level": "INFO",
  "event": "speech_start",
  "utterance_num": 1
}
```

### Analyzing Logs with jq

Extract all VAD events:
```bash
cat results.jsonl | jq 'select(.component == "VAD")'
```

Calculate average speech duration:
```bash
cat results.jsonl | jq 'select(.event == "speech_end") | .duration_s' | awk '{sum+=$1; n++} END {print sum/n}'
```

Find all validation failures:
```bash
cat results.jsonl | jq 'select(.component == "Validator" and .level == "ERROR")'
```

## Best Practices

### Regular Diagnostic Runs

Run diagnostics:
- **Weekly:** During active development
- **After changes:** Any config or code modifications
- **Before deployment:** Validate production readiness
- **On user reports:** Reproduce reported issues

### Interpreting Results

**All tests passing:**
- ✅ System is functioning correctly
- Continue monitoring in production

**1-2 tests failing:**
- ⚠️ Specific component issue
- Focus debugging on failed tests
- Check related configuration

**3+ tests failing:**
- 🚨 Systemic issue
- Check fundamental setup (audio devices, models, etc.)
- Review recent changes

**All tests failing:**
- 💥 Critical system issue
- Verify audio input/output devices
- Check Vosk model installation
- Confirm configuration file is valid

### Performance Baselines

Establish baselines for your system:

```
Target Performance Metrics:
- Wake word success rate: >90%
- Speech capture accuracy: >95%
- TTS consistency: 100%
- Multi-turn capability: ≥3 turns
- Mic re-engagement: <500ms
- Context preservation: 100%
```

Document your baselines and track changes over time.

## Support and Contributing

### Getting Help

If diagnostic tests reveal issues you can't resolve:

1. Review this guide's troubleshooting section
2. Check existing documentation (RUNBOOK.md, TROUBLESHOOTING.md)
3. Examine detailed logs with `--log-file`
4. Run individual tests to isolate the issue
5. Use `--monitor` mode to observe real-time behavior

### Reporting Issues

When reporting issues, include:
- Full diagnostic output
- Log file (if available)
- Configuration file (config.json)
- System information (OS, Python version, Vosk model)
- Steps to reproduce

### Contributing

To add new diagnostic tests:

1. Create a new test function following the existing pattern
2. Add validation checks with TestValidator
3. Include detailed logging at key points
4. Update this guide with test documentation
5. Add the test to the main test suite

## Conclusion

The Enhanced Voice Assistant Diagnostic Tool is your comprehensive resource for:
- **Identifying issues** in voice pipeline components
- **Validating fixes** with automated checks
- **Monitoring behavior** in real-time
- **Understanding** system internals

Use it regularly to maintain a robust, reliable voice assistant system.

---

**Version:** 1.0
**Last Updated:** 2025-10-20
**Compatibility:** Python 3.8+, Vosk, WebRTC VAD
