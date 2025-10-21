# Voice Assistant Complete Diagnostic & Fix Solution

## Executive Summary

Your voice assistant codebase **already has sophisticated fixes** for the three critical issues mentioned in your diagnostic guide:

1. ✅ **Wake word detection only works when shouted** → Fixed with AGC (Automatic Gain Control)
2. ✅ **Speech capture fails after wake word** → Fixed with pre-roll buffer and adaptive VAD
3. ✅ **Timeout/silence detection misjudges flow** → Fixed with robust silence detection

**What you need to do:** Run diagnostics to verify everything is working, and tune parameters if needed.

## What's Already Implemented

### 1. Automatic Gain Control (AGC)

**File:** `app/audio/agc.py`

**What it does:**
- Automatically boosts quiet microphones up to 10x
- Normalizes audio to consistent levels (target RMS: 3000)
- Prevents clipping with smart attack/release rates
- Eliminates need to shout for wake word detection

**How it works:**
```python
# In wake.py (line 81-87)
self._agc = AutomaticGainControl(
    target_rms=3000.0,    # Target normalized level
    min_gain=1.0,         # No reduction
    max_gain=10.0,        # Up to 10x boost for quiet mics
    attack_rate=0.9,      # Fast gain increase
    release_rate=0.999    # Slow gain decrease
)

# Audio is processed through AGC before wake word detection
gained_frame = self._agc.process(raw_frame)
```

**Configuration:**
```json
// config.json
{
  "enable_agc": true
}
```

**Diagnostic output:**
```
[AGC] Gain: 2.34x (+7.4dB) | RMS: 1283 → 3000 | VAD Level: 2
```

### 2. Adaptive VAD (Voice Activity Detection)

**File:** `app/audio/agc.py`

**What it does:**
- Automatically calibrates to background noise during first ~1 second
- Selects optimal VAD level (1-3) based on environment
- Prevents false speech detection in noisy environments
- Ensures reliable speech detection in quiet environments

**How it works:**
```python
# Auto-selects VAD level based on background noise:
# - Quiet environment (< 100 RMS): VAD level 1 (most sensitive)
# - Moderate noise (100-500 RMS): VAD level 2 (balanced)
# - Noisy environment (> 500 RMS): VAD level 3 (least sensitive)

# In wake.py (line 78)
self._adaptive_vad = AdaptiveVAD(sample_rate=sample_rate)

# In capture.py (line 203)
adaptive_vad = AdaptiveVAD(sample_rate=sample_rate)
```

**Diagnostic output:**
```
[AGC] Auto-selected VAD level 2 (background RMS: 234.5)
```

### 3. Pre-Roll Buffer

**Files:** `app/audio/wake.py` (line 60-69), `app/audio/capture.py` (line 232-250)

**What it does:**
- Maintains rolling buffer of audio BEFORE wake word is detected
- Captures first syllables that would otherwise be lost
- Ensures complete speech capture from the very start
- Prevents "missing beginning of speech" issue

**How it works:**
```python
# In wake.py (line 68-69)
buffer_size = max(1, int(pre_roll_ms / frame_ms))
self._rolling_buffer: collections.deque[bytes] = collections.deque(maxlen=buffer_size)

# Buffer is continuously filled during wake word listening
self._rolling_buffer.append(gained_frame)

# When wake word detected, buffer is passed to capture
buffer_copy = list(self._rolling_buffer)
self._emit_detect(buffer_copy)

# In capture.py (line 236-250)
# Pre-roll buffer is prepended to recording
pre_frames = list(pre_roll_buffer)[-ring_frames:] if pre_roll_buffer else []
for frame in pre_frames:
    frames.append(frame)
    stt.feed(frame)
```

**Configuration:**
```json
{
  "pre_roll_ms": 600  // 600ms of audio before wake word
}
```

**Diagnostic output:**
```
✓ Wake word detected! Transcript: 'hey glasses' Pre-roll buffer: 30 frames
[CAPTURE] VAD detected speech during pre-roll (4 speech frames); capturing segment
```

### 4. Robust Silence Detection

**File:** `app/audio/capture.py` (line 259-375)

**What it does:**
- Grace period (1000ms) after wake word before checking silence
- Consecutive silence frame tracking to avoid premature cutoff
- Minimum speech frames requirement before allowing timeout
- Configurable silence threshold for different speaking styles
- Tail padding to capture trailing words

**How it works:**
```python
# Grace period prevents immediate timeout (line 259-261)
grace_period_ms = 1000
grace_period_end_time = start_time + (grace_period_ms / 1000.0)

# Consecutive silence tracking (line 266-267)
consecutive_silence_frames = 0
total_speech_frames = sum(1 for f in frames if vad.is_speech(f, sample_rate))

# Minimum speech frames requirement (line 271)
min_speech_frames = getattr(config, 'min_speech_frames', 3)

# Robust silence detection (line 367-375)
if has_spoken and total_speech_frames >= min_speech_frames:
    silence_duration_ms = (now_time - last_speech_time) * 1000
    if silence_duration_ms >= config.silence_ms:
        stop_reason = "silence"
        break

# Tail padding after silence detected (line 380-384)
if has_spoken and stop_reason not in {"manual", "cap", "timeout15"}:
    tail_padding_ms = getattr(config, 'tail_padding_ms', 300)
    tail_frames = max(1, int(tail_padding_ms / frame_ms))
    drain_tail(tail_frames)
```

**Configuration:**
```json
{
  "silence_ms": 1200,         // How long to wait for silence
  "min_speech_frames": 4,     // Min speech before timeout
  "tail_padding_ms": 400      // Audio after silence
}
```

**Diagnostic output:**
```
[CAPTURE] VAD detected speech during pre-roll (4 speech frames); grace_period=1000ms; capturing segment
[VAD→SPEECH] First voice detected at +234ms (total frames: 12)
[VAD→SILENCE] Silence for 1200ms (threshold=1200ms); ending capture
Added 400ms tail padding (20 frames)
```

### 5. Multi-Turn Conversation Support

**File:** `app/session.py`

**What it does:**
- Maintains conversation history across multiple turns
- Continues listening after each assistant response
- 15-second follow-up timeout (no need to re-wake)
- Proper lifecycle management with explicit exit ("bye glasses")
- Cooldown period to avoid detecting assistant's own voice

**How it works:**
```python
# Multi-turn conversation loop (line 128)
while not self._cancel_event.is_set():
    segment_result = self._capture_turn(...)
    # Process user input
    # Generate assistant response
    # Speak response
    # Wait for follow-up (line 220)
    follow_reason, next_pre_roll = self._await_followup(callbacks)
    if follow_reason != "speech":
        break  # End session
    # Continue to next turn

# Follow-up waiting (line 358-413)
def _await_followup(self, callbacks) -> tuple[str, Optional[List[bytes]]]:
    # Wait up to 15 seconds for user to speak again
    deadline = time.monotonic() + self.followup_timeout_ms / 1000
    while time.monotonic() < deadline:
        if vad.is_speech(frame, sample_rate):
            return "speech", pre_frames  # Continue conversation
    return "timeout15", None  # End session
```

**Configuration:**
```python
# In session.py (line 70)
followup_timeout_ms: int = 15_000  # 15-second timeout
```

**Diagnostic output:**
```
Session Turn 0: Completed. Awaiting follow-up speech...
Session Turn 0: Follow-up speech detected! Starting turn 1...
Session Turn 1: Completed. Awaiting follow-up speech...
Session Turn 1: Follow-up ended with reason: timeout15
```

### 6. Comprehensive Diagnostic Logging

**Files:** Throughout codebase

**What it does:**
- Logs AGC stats every 10 seconds during wake listening
- Logs wake word detection with timing and buffer state
- Logs VAD speech detection with frame counts
- Logs capture configuration and state transitions
- Logs silence detection with timing

**Example output:**
```
[AGC] Gain: 2.34x (+7.4dB) | RMS: 1283 → 3000 | VAD Level: 2
[WAKE] Heard: 'hey glasses'
✓ Wake word detected! Transcript: 'hey glasses' Pre-roll buffer: 30 frames
Capture config: VAD=1, silence=1200ms, pre_roll=600ms, min_speech_frames=4, chunk_ms=20ms, sample_rate=16000Hz, AGC=enabled
[CAPTURE] VAD detected speech during pre-roll (4 speech frames); grace_period=1000ms; capturing segment
[VAD→SPEECH] First voice detected at +234ms (total frames: 12)
[VAD→SILENCE] Silence for 1200ms (threshold=1200ms); ending capture
Added 400ms tail padding (20 frames)
[AGC] Capture complete: Final gain 2.34x (+7.4dB), RMS 1283/3000, Processed 156 frames
```

## New Diagnostic Tools

I've created three diagnostic tools to help you verify and tune your system:

### 1. Quick Diagnostic (30 seconds)

**File:** `quick_diagnostic.py`

**What it does:**
- Tests microphone audio levels (5 sec)
- Tests AGC functionality (3 sec)
- Tests wake word detection (20 sec)

**When to use:**
- First-time setup
- Quick health check
- After changing microphone
- After changing configuration

**How to run:**
```bash
python quick_diagnostic.py
```

**Expected output:**
```
Audio Levels: ✓ PASS
AGC Test:     ✓ PASS
Wake Word:    ✓ PASS

✓ All tests passed! Your voice assistant should work.
```

### 2. Comprehensive Diagnostic (~2 minutes)

**File:** `diagnostic_voice_comprehensive.py`

**What it does:**
- Phase 1: Audio level analysis (5 sec)
- Phase 2: VAD configuration verification
- Phase 3: Wake word sensitivity test (30 sec)
- Phase 4: VAD speech capture test (30 sec)
- Phase 5: Timeout behavior test (10 sec)

**When to use:**
- Quick diagnostic fails
- Need detailed analysis
- Tuning parameters
- Troubleshooting specific issues

**How to run:**
```bash
python diagnostic_voice_comprehensive.py
```

**Expected output:**
```
DIAGNOSTIC SUMMARY
==================
Audio Levels:
  Average RMS: 1234
  Status: audio_good

VAD Configuration:
  Status: ✓ OK

Wake Word Detection:
  Status: ✓ OK

Next steps:
  1. All diagnostics passed!
  2. Test the full voice assistant
```

### 3. Real-Time Monitor

**File:** `monitor_voice_realtime.py`

**What it does:**
- Shows live audio levels (before/after AGC)
- Shows AGC gain in real-time
- Shows VAD speech detection
- Shows live transcription
- Shows wake word detections

**When to use:**
- Debugging live issues
- Understanding what's happening in real-time
- Tuning parameters interactively
- Demonstrating system behavior

**How to run:**
```bash
python monitor_voice_realtime.py
```

**Expected output:**
```
======================================================================
                    VOICE ASSISTANT MONITOR
======================================================================

┌─ AUDIO LEVELS ──────────────────────────────────────────────────┐
│
│  RMS (before AGC): [████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  1234
│  Status: GOOD
│
│  RMS (after AGC):  [████████████████████████░░░░░░░░░░░░░░░░]  3012
│  Status: ON TARGET
│
└──────────────────────────────────────────────────────────────────┘

┌─ AGC (AUTOMATIC GAIN CONTROL) ───────────────────────────────────┐
│
│  Gain:   [████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░] 2.34x (+7.4dB)
│  Status: MODERATE
│  Target RMS: 3000
│  Current RMS: 1283
│
└──────────────────────────────────────────────────────────────────┘

┌─ VAD (VOICE ACTIVITY DETECTION) ─────────────────────────────────┐
│
│  Status: ● SPEECH DETECTED
│  VAD Level: 2 (auto-selected)
│
└──────────────────────────────────────────────────────────────────┘

┌─ TRANSCRIPTION ──────────────────────────────────────────────────┐
│
│  hey glasses what is the weather today
│
└──────────────────────────────────────────────────────────────────┘
```

## Diagnostic Workflow

### Step 1: Quick Health Check

```bash
python quick_diagnostic.py
```

**If all pass:** ✅ System is working! Skip to Step 4.

**If any fail:** ⚠️ Continue to Step 2.

### Step 2: Comprehensive Diagnostic

```bash
python diagnostic_voice_comprehensive.py
```

Follow the prompts for each phase. The tool will identify exactly what's wrong.

**Common findings:**

| Finding | Meaning | Solution |
|---------|---------|----------|
| "AUDIO TOO QUIET" | Microphone too quiet | Enable AGC, increase system mic volume |
| "NO WAKE WORDS DETECTED" | Wake word not recognized | Check wake_variants, increase wake_sensitivity |
| "VAD frame size mismatch" | Configuration error | Fix VAD frame size (should be 960 bytes at 16kHz/30ms) |
| "Speech cut off" | Timeout too short | Increase silence_ms, min_speech_frames |

### Step 3: Adjust Configuration

Based on diagnostic results, edit `config.json`:

```json
{
  // Common adjustments based on diagnostics
  
  // If wake word not detected:
  "wake_sensitivity": 0.8,      // Increase from 0.7
  "vad_aggressiveness": 1,      // Lower from 2 (more sensitive)
  
  // If speech cut off mid-sentence:
  "silence_ms": 1500,           // Increase from 1200
  "min_speech_frames": 6,       // Increase from 4
  
  // If missing beginning of speech:
  "pre_roll_ms": 800,           // Increase from 600
  
  // If missing end of speech:
  "tail_padding_ms": 500,       // Increase from 400
  
  // If AGC not working:
  "enable_agc": true            // Ensure enabled
}
```

### Step 4: Test Full System

```bash
python app/main.py
```

**Test sequence:**
1. Say "hey glasses"
2. Wait for confirmation
3. Say your command (e.g., "what is the weather today")
4. Verify full command was captured
5. Listen to assistant response
6. Continue conversation without re-waking (say another command)
7. Say "bye glasses" to end session

**Expected behavior:**
```
[AGC] Gain: 2.34x (+7.4dB) | RMS: 1283 → 3000 | VAD Level: 2
[WAKE] Listening...
[WAKE] Heard: 'hey glasses'
✓ Wake word detected! Transcript: 'hey glasses' Pre-roll buffer: 30 frames
[CAPTURE] VAD detected speech during pre-roll (4 speech frames); capturing segment
[VAD→SPEECH] First voice detected at +234ms (total frames: 12)
[VAD→SILENCE] Silence for 1200ms (threshold=1200ms); ending capture
Session Turn 0: Completed. Awaiting follow-up speech...
Session Turn 0: Follow-up speech detected! Starting turn 1...
```

### Step 5: Real-Time Monitoring (Optional)

For live debugging, run the monitor:

```bash
python monitor_voice_realtime.py
```

This shows exactly what's happening in real-time as you speak.

## Configuration Quick Reference

### Audio Capture Parameters

```json
{
  "sample_rate_hz": 16000,      // Must be 16000 for Vosk
  "chunk_samples": 320,         // 20ms chunks at 16kHz
  "silence_ms": 1200,           // Silence before ending capture
  "max_segment_s": 45,          // Max recording duration
  "pre_roll_ms": 600,           // Pre-wake buffer duration
  "min_speech_frames": 4,       // Min speech before timeout
  "tail_padding_ms": 400        // Audio after silence
}
```

### VAD Parameters

```json
{
  "vad_aggressiveness": 1,      // 0=most sensitive, 3=least
  "wake_vad_level": 1           // VAD level for wake detection
}
```

### Wake Word Parameters

```json
{
  "wake_variants": [
    "hey glasses",
    "hi glasses",
    "ok glasses"
  ],
  "wake_sensitivity": 0.7,      // 0.0=strict, 1.0=loose
  "wake_match_window_ms": 1200  // Time window for matching
}
```

### AGC Parameters

```json
{
  "enable_agc": true             // Enable automatic gain control
}
```

**AGC is configured in code (`app/audio/agc.py`):**
- `target_rms`: 3000.0 (target audio level)
- `min_gain`: 1.0 (no reduction)
- `max_gain`: 10.0 (up to 10x boost)
- `attack_rate`: 0.9 (fast gain increase)
- `release_rate`: 0.999 (slow gain decrease)

## Tuning Presets

### Quiet Environment

```json
{
  "vad_aggressiveness": 1,      // More sensitive
  "wake_sensitivity": 0.8,      // More sensitive
  "silence_ms": 1500            // Longer timeout
}
```

### Noisy Environment

```json
{
  "vad_aggressiveness": 3,      // Less sensitive
  "wake_sensitivity": 0.6,      // Less sensitive
  "silence_ms": 1000            // Shorter timeout
}
```

### Fast Speakers

```json
{
  "silence_ms": 800,            // Shorter timeout
  "min_speech_frames": 2,       // Fewer frames required
  "tail_padding_ms": 200        // Less tail padding
}
```

### Slow/Deliberate Speakers

```json
{
  "silence_ms": 2000,           // Longer timeout
  "min_speech_frames": 8,       // More frames required
  "tail_padding_ms": 600        // More tail padding
}
```

## Troubleshooting Guide

### Problem: Wake word only detected when shouting

**Diagnosis:**
```bash
python quick_diagnostic.py
# Look for "AUDIO TOO QUIET"
```

**Solutions:**

1. **Check AGC is enabled:**
   ```bash
   grep enable_agc config.json
   # Should show: "enable_agc": true
   ```

2. **Verify AGC is working:**
   - Run quick diagnostic
   - Look for "Gain: X.XXx" in output
   - Should see gain > 1.0x for quiet mics

3. **Increase system microphone volume:**
   - macOS: System Preferences → Sound → Input
   - Slide "Input volume" to the right

4. **Adjust wake word sensitivity:**
   ```json
   {
     "wake_sensitivity": 0.8  // Increase from 0.7
   }
   ```

### Problem: Speech capture fails after wake word

**Diagnosis:**
```bash
python diagnostic_voice_comprehensive.py
# Run Phase 4: VAD Speech Capture Test
```

**Solutions:**

1. **VAD too aggressive:**
   ```json
   {
     "vad_aggressiveness": 1  // Lower from 2 or 3
   }
   ```

2. **Pre-roll buffer not working:**
   - Check logs for: `[CAPTURE] VAD detected speech during pre-roll`
   - If missing:
   ```json
   {
     "pre_roll_ms": 800  // Increase from 600
   }
   ```

3. **Silence timeout too short:**
   ```json
   {
     "silence_ms": 1500  // Increase from 1200
   }
   ```

### Problem: Timeout/silence detection cuts off speech

**Diagnosis:**
```bash
python diagnostic_voice_comprehensive.py
# Run Phase 5: Timeout Behavior Test
```

**Solutions:**

1. **Cuts off mid-sentence:**
   ```json
   {
     "silence_ms": 1500,        // Increase
     "min_speech_frames": 6     // Increase
   }
   ```

2. **Times out too quickly:**
   ```json
   {
     "silence_ms": 2000,        // Longer threshold
     "min_speech_frames": 8     // More speech required
   }
   ```

3. **Doesn't detect end of speech:**
   ```json
   {
     "silence_ms": 1000,        // Decrease
     "vad_aggressiveness": 2    // More aggressive
   }
   ```

### Problem: Missing beginning of speech

**Solution:**
```json
{
  "pre_roll_ms": 800  // Increase from 600
}
```

### Problem: Missing end of speech

**Solution:**
```json
{
  "tail_padding_ms": 500  // Increase from 400
}
```

## Summary

Your voice assistant codebase already has comprehensive fixes for all three critical issues:

✅ **AGC** - Automatically boosts quiet microphones (up to 10x)  
✅ **Adaptive VAD** - Auto-calibrates to environment  
✅ **Pre-roll buffer** - Captures audio before wake word  
✅ **Robust silence detection** - Prevents premature cutoff  
✅ **Multi-turn conversations** - No need to re-wake  
✅ **Comprehensive logging** - Detailed diagnostic output  

**To verify and tune your system:**

1. **Run quick diagnostic** (30 seconds)
   ```bash
   python quick_diagnostic.py
   ```

2. **If issues found, run comprehensive diagnostic** (~2 minutes)
   ```bash
   python diagnostic_voice_comprehensive.py
   ```

3. **Adjust `config.json`** based on diagnostic results

4. **Test full system**
   ```bash
   python app/main.py
   ```

5. **Use real-time monitor** for live debugging (optional)
   ```bash
   python monitor_voice_realtime.py
   ```

The diagnostic tools will identify exactly which parameters need adjustment for your specific setup. Most users will find that the default configuration works well with AGC enabled.

## Documentation Files

- **[DIAGNOSTIC_README.md](DIAGNOSTIC_README.md)** - Quick start guide
- **[VOICE_DIAGNOSTIC_GUIDE.md](VOICE_DIAGNOSTIC_GUIDE.md)** - Complete diagnostic guide
- **[quick_diagnostic.py](quick_diagnostic.py)** - 30-second quick test
- **[diagnostic_voice_comprehensive.py](diagnostic_voice_comprehensive.py)** - Full diagnostic suite
- **[monitor_voice_realtime.py](monitor_voice_realtime.py)** - Real-time monitor

## Next Steps

1. Run `python quick_diagnostic.py` to verify your system
2. If all tests pass, run `python app/main.py` and start using your voice assistant
3. If tests fail, run `python diagnostic_voice_comprehensive.py` for detailed analysis
4. Adjust `config.json` based on diagnostic recommendations
5. Re-test until all diagnostics pass

Your voice assistant is ready to use! The diagnostic tools will help you fine-tune it for your specific environment and speaking style.
