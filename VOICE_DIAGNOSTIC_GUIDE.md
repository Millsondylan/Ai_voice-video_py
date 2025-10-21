# Voice Assistant Diagnostic & Fix Guide

## Overview

This guide helps you diagnose and fix three critical voice assistant issues:

1. **Wake word detection only works when shouted**
2. **Speech capture fails after wake word**
3. **Timeout/silence detection misjudges conversation flow**

## Quick Start

### Step 1: Run Quick Diagnostic

```bash
python quick_diagnostic.py
```

This 30-second test checks:
- Microphone audio levels
- AGC (Automatic Gain Control) functionality
- Wake word detection

### Step 2: Run Comprehensive Diagnostic (if needed)

```bash
python diagnostic_voice_comprehensive.py
```

This runs 5 detailed diagnostic phases:
1. Audio level analysis (5 seconds)
2. VAD configuration verification
3. Wake word sensitivity test (30 seconds)
4. VAD speech capture test (30 seconds)
5. Timeout behavior test (10 seconds)

## What's Already Fixed in Your Codebase

Your voice assistant already has many advanced fixes implemented:

### ✓ Automatic Gain Control (AGC)

**Location:** `app/audio/agc.py`

**What it does:**
- Automatically boosts quiet microphones (up to 10x gain)
- Normalizes audio to consistent levels (target RMS: 3000)
- Prevents clipping with smart attack/release rates

**Configuration:** `config.json`
```json
{
  "enable_agc": true
}
```

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
```

### ✓ Adaptive VAD (Voice Activity Detection)

**Location:** `app/audio/agc.py`

**What it does:**
- Automatically calibrates to background noise
- Selects optimal VAD level (1-3) based on environment
- Prevents false speech detection in noisy environments

**How it works:**
```python
# Calibrates during first ~1 second
# Then auto-selects VAD level:
# - Quiet environment (< 100 RMS): VAD level 1 (most sensitive)
# - Moderate noise (100-500 RMS): VAD level 2 (balanced)
# - Noisy environment (> 500 RMS): VAD level 3 (least sensitive)
```

### ✓ Pre-Roll Buffer

**Location:** `app/audio/wake.py` (line 60-69), `app/audio/capture.py` (line 232-250)

**What it does:**
- Maintains rolling buffer of audio BEFORE wake word
- Captures first syllables that would otherwise be lost
- Ensures complete speech capture from the start

**Configuration:** `config.json`
```json
{
  "pre_roll_ms": 600
}
```

### ✓ Diagnostic Logging

**Location:** Throughout codebase

**What it does:**
- Logs AGC stats every 10 seconds (wake.py line 143-152)
- Logs wake word detection with timing (wake.py line 184-188)
- Logs VAD speech detection (capture.py line 274-283, 346-350)
- Logs capture configuration (capture.py line 214-218)

**Example output:**
```
[AGC] Gain: 2.34x (+7.4dB) | RMS: 1283 → 3000 | VAD Level: 2
[WAKE] Heard: 'hey glasses'
✓ Wake word detected! Transcript: 'hey glasses' Pre-roll buffer: 30 frames
[CAPTURE] VAD detected speech during pre-roll (4 speech frames); capturing segment
[VAD→SPEECH] First voice detected at +234ms (total frames: 12)
[VAD→SILENCE] Silence for 1200ms (threshold=1200ms); ending capture
```

### ✓ Robust Silence Detection

**Location:** `app/audio/capture.py` (line 259-375)

**What it does:**
- Grace period (1000ms) after wake word before checking silence
- Consecutive silence frame tracking
- Minimum speech frames requirement before allowing timeout
- Configurable silence threshold

**Configuration:** `config.json`
```json
{
  "silence_ms": 1200,
  "min_speech_frames": 4,
  "tail_padding_ms": 400
}
```

### ✓ Multi-Turn Conversation Support

**Location:** `app/session.py`

**What it does:**
- Maintains conversation history across turns
- 15-second follow-up timeout (no need to re-wake)
- Proper lifecycle management
- Cooldown period to avoid detecting assistant's own voice

**How it works:**
```python
# After assistant speaks, waits up to 15 seconds for user response
# If user speaks again, continues conversation without wake word
# If 15 seconds pass with no speech, ends session
```

## Common Issues and Solutions

### Issue 1: Wake Word Only Detected When Shouting

**Diagnosis:**
```bash
python quick_diagnostic.py
```

Look for "AUDIO TOO QUIET" in Phase 1.

**Solution:**

Your AGC should handle this automatically. If it doesn't:

1. **Check AGC is enabled:**
   ```json
   // config.json
   {
     "enable_agc": true
   }
   ```

2. **Verify AGC is working:**
   - Run quick diagnostic
   - Look for "Gain: X.XXx" in output
   - Should see gain > 1.0x for quiet mics

3. **Check system microphone settings:**
   - macOS: System Preferences → Sound → Input
   - Increase input volume slider
   - Enable "Use ambient noise reduction" if available

4. **Adjust wake word variants:**
   ```json
   // config.json
   {
     "wake_variants": [
       "hey glasses",
       "hi glasses",
       "ok glasses"
     ],
     "wake_sensitivity": 0.7  // Lower = more sensitive (0.5-0.9)
   }
   ```

### Issue 2: Speech Capture Fails After Wake Word

**Diagnosis:**
```bash
python diagnostic_voice_comprehensive.py
# Run Phase 4: VAD Speech Capture Test
```

**Possible Causes:**

1. **VAD too aggressive (filtering out speech)**
   
   **Solution:** Lower VAD aggressiveness
   ```json
   // config.json
   {
     "vad_aggressiveness": 1  // Try 1 or 2 (was 3)
   }
   ```

2. **Pre-roll buffer not working**
   
   **Check:** Look for this log message:
   ```
   [CAPTURE] VAD detected speech during pre-roll
   ```
   
   If missing, increase pre-roll:
   ```json
   {
     "pre_roll_ms": 800  // Increase from 600
   }
   ```

3. **Silence timeout too short**
   
   **Solution:** Increase silence threshold
   ```json
   {
     "silence_ms": 1500  // Increase from 1200
   }
   ```

### Issue 3: Timeout/Silence Detection Misjudges Flow

**Diagnosis:**
```bash
python diagnostic_voice_comprehensive.py
# Run Phase 5: Timeout Behavior Test
```

**Symptoms:**
- Cuts off mid-sentence
- Times out too quickly
- Doesn't detect end of speech

**Solutions:**

1. **Cuts off mid-sentence:**
   ```json
   {
     "silence_ms": 1500,        // Increase (was 1200)
     "min_speech_frames": 6     // Increase (was 4)
   }
   ```

2. **Times out too quickly:**
   ```json
   {
     "silence_ms": 2000,        // Longer silence threshold
     "min_speech_frames": 8     // More speech required before timeout
   }
   ```

3. **Doesn't detect end of speech:**
   ```json
   {
     "silence_ms": 1000,        // Decrease (was 1200)
     "vad_aggressiveness": 2    // More aggressive (was 1)
   }
   ```

## Configuration Parameters Reference

### Audio Capture

| Parameter | Default | Description |
|-----------|---------|-------------|
| `sample_rate_hz` | 16000 | Audio sample rate (must be 16000 for Vosk) |
| `chunk_samples` | 320 | Audio chunk size (20ms at 16kHz) |
| `silence_ms` | 1200 | Silence duration before ending capture |
| `max_segment_s` | 45 | Maximum recording duration |
| `pre_roll_ms` | 600 | Pre-wake audio buffer duration |
| `min_speech_frames` | 4 | Minimum speech frames before allowing timeout |
| `tail_padding_ms` | 400 | Audio captured after silence detected |

### VAD (Voice Activity Detection)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vad_aggressiveness` | 1 | WebRTC VAD mode (0=most sensitive, 3=least) |
| `wake_vad_level` | 1 | VAD level for wake word detection |

### Wake Word Detection

| Parameter | Default | Description |
|-----------|---------|-------------|
| `wake_variants` | ["hey glasses", ...] | Wake word phrases to recognize |
| `wake_sensitivity` | 0.7 | Detection sensitivity (0.0-1.0) |
| `wake_match_window_ms` | 1200 | Time window for wake word matching |

### AGC (Automatic Gain Control)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_agc` | true | Enable automatic gain control |

**AGC is configured in code:**
- `target_rms`: 3000.0 (target audio level)
- `min_gain`: 1.0 (no reduction)
- `max_gain`: 10.0 (up to 10x boost)
- `attack_rate`: 0.9 (fast gain increase)
- `release_rate`: 0.999 (slow gain decrease)

## Diagnostic Output Interpretation

### Audio Level Check

```
RMS - Min:   234 | Avg:   456 | Max:  1234
```

**Interpretation:**
- **Avg < 500:** Too quiet, AGC will boost
- **Avg 500-5000:** Good range
- **Avg > 15000:** Too loud, may clip

### AGC Stats

```
[AGC] Gain: 2.34x (+7.4dB) | RMS: 1283 → 3000 | VAD Level: 2
```

**Interpretation:**
- **Gain 1.0x:** No boost needed (good mic level)
- **Gain 2-5x:** Moderate boost (typical for built-in mics)
- **Gain 5-10x:** Heavy boost (very quiet mic)
- **RMS before → after:** Shows normalization working

### Wake Word Detection

```
✓ DETECTED at 5.2s: 'hey glasses' (RMS: 456 → 3012, Gain: 6.60x)
```

**Interpretation:**
- **RMS before:** Original microphone level
- **RMS after:** AGC-boosted level (should be ~3000)
- **Gain:** How much AGC boosted the signal

## Troubleshooting Workflow

### 1. Start with Quick Diagnostic

```bash
python quick_diagnostic.py
```

**If all tests pass:** Your system is working correctly!

**If audio test fails:**
- Check system microphone settings
- Verify AGC is enabled in config.json
- Try different microphone

**If wake word test fails:**
- Check wake_variants in config.json match what you're saying
- Try speaking more clearly
- Increase wake_sensitivity (0.7 → 0.8)

### 2. Run Comprehensive Diagnostic

```bash
python diagnostic_voice_comprehensive.py
```

**Phase 1 (Audio Levels):**
- Shows exact RMS levels
- Recommends gain adjustments
- Verifies AGC target

**Phase 2 (VAD Config):**
- Verifies WebRTC VAD setup
- Tests all aggressiveness modes
- Checks frame size calculations

**Phase 3 (Wake Word):**
- Tests wake word at different volumes
- Shows AGC gain in real-time
- Identifies detection failures

**Phase 4 (VAD Capture):**
- Tests full wake → capture flow
- Verifies pre-roll buffer
- Shows speech detection timing

**Phase 5 (Timeout):**
- Tests silence detection
- Verifies timeout thresholds
- Shows speech/silence transitions

### 3. Adjust Configuration

Based on diagnostic results, edit `config.json`:

```json
{
  // If wake word not detected:
  "wake_sensitivity": 0.8,  // Increase from 0.7
  "vad_aggressiveness": 1,  // Lower from 2
  
  // If speech cut off mid-sentence:
  "silence_ms": 1500,       // Increase from 1200
  "min_speech_frames": 6,   // Increase from 4
  
  // If not capturing full speech:
  "pre_roll_ms": 800,       // Increase from 600
  "tail_padding_ms": 500    // Increase from 400
}
```

### 4. Test Full System

```bash
python app/main.py
```

Say "hey glasses" and verify:
1. Wake word detected
2. Full command captured
3. Response generated
4. Can continue conversation without re-waking

## Advanced Debugging

### Enable Detailed Logging

The system already has comprehensive logging. To see all logs:

```bash
# Run with debug output
python app/main.py 2>&1 | tee voice_assistant.log
```

**Look for these log messages:**

**AGC Status (every 10 seconds):**
```
[AGC] Gain: 2.34x (+7.4dB) | RMS: 1283 → 3000 | VAD Level: 2
```

**Wake Word Detection:**
```
[WAKE] Heard: 'hey glasses'
✓ Wake word detected! Transcript: 'hey glasses' Pre-roll buffer: 30 frames
```

**Capture Start:**
```
[CAPTURE] VAD detected speech during pre-roll (4 speech frames); capturing segment
Capture config: VAD=1, silence=1200ms, pre_roll=600ms, min_speech_frames=4
```

**Speech Detection:**
```
[VAD→SPEECH] First voice detected at +234ms (total frames: 12)
```

**Capture End:**
```
[VAD→SILENCE] Silence for 1200ms (threshold=1200ms); ending capture
Added 400ms tail padding (20 frames)
```

### Monitor AGC in Real-Time

AGC stats are printed every 10 seconds during wake word listening:

```
[AGC] Gain: 2.34x (+7.4dB) | RMS: 1283 → 3000 | VAD Level: 2
```

**What to look for:**
- **Gain increasing:** Microphone is quiet, AGC is boosting
- **Gain stable:** Audio level is consistent
- **RMS near target (3000):** AGC is working correctly
- **VAD Level:** Auto-selected based on background noise

### Check Pre-Roll Buffer

When wake word is detected, you should see:

```
✓ Wake word detected! Transcript: 'hey glasses' Pre-roll buffer: 30 frames
```

**If buffer is 0 frames:** Pre-roll not working, check configuration

**If buffer is full (30+ frames):** Pre-roll working correctly

### Verify Capture Flow

Complete capture should show this sequence:

```
1. [CAPTURE] VAD detected speech during pre-roll
2. [VAD→SPEECH] First voice detected at +234ms
3. [VAD→SILENCE] Silence for 1200ms; ending capture
4. Added 400ms tail padding
5. [AGC] Capture complete: Final gain 2.34x
```

**If sequence is incomplete:** Check which step is missing

## Performance Tuning

### For Quiet Environments

```json
{
  "vad_aggressiveness": 1,    // More sensitive
  "wake_sensitivity": 0.8,    // More sensitive
  "silence_ms": 1500          // Longer timeout
}
```

### For Noisy Environments

```json
{
  "vad_aggressiveness": 3,    // Less sensitive
  "wake_sensitivity": 0.6,    // Less sensitive
  "silence_ms": 1000          // Shorter timeout
}
```

### For Fast Speakers

```json
{
  "silence_ms": 800,          // Shorter timeout
  "min_speech_frames": 2,     // Fewer frames required
  "tail_padding_ms": 200      // Less tail padding
}
```

### For Slow/Deliberate Speakers

```json
{
  "silence_ms": 2000,         // Longer timeout
  "min_speech_frames": 8,     // More frames required
  "tail_padding_ms": 600      // More tail padding
}
```

## Summary

Your voice assistant already has sophisticated fixes in place:

✓ **AGC** - Automatically boosts quiet microphones  
✓ **Adaptive VAD** - Auto-calibrates to environment  
✓ **Pre-roll buffer** - Captures audio before wake word  
✓ **Robust silence detection** - Prevents premature cutoff  
✓ **Multi-turn conversations** - No need to re-wake  
✓ **Comprehensive logging** - Detailed diagnostic output  

**To diagnose issues:**

1. Run `python quick_diagnostic.py` (30 seconds)
2. If issues found, run `python diagnostic_voice_comprehensive.py` (full diagnostic)
3. Adjust `config.json` based on results
4. Test with `python app/main.py`

**Most common fixes:**

- **Wake word not detected:** Check AGC is enabled, increase wake_sensitivity
- **Speech cut off:** Increase silence_ms, increase min_speech_frames
- **Missing beginning of speech:** Increase pre_roll_ms
- **Missing end of speech:** Increase tail_padding_ms

The diagnostic tools will identify exactly which parameters need adjustment for your specific setup.
