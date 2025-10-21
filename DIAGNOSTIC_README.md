# Voice Assistant Diagnostics - Quick Start

## TL;DR

Your voice assistant has three potential issues:
1. Wake word only works when shouted
2. Speech capture fails after wake word
3. Timeout/silence detection cuts off speech

**Run this to diagnose:**

```bash
python quick_diagnostic.py
```

**30 seconds, tells you exactly what's wrong.**

## What's Already Fixed

Your codebase already has these advanced features:

- ✅ **AGC (Automatic Gain Control)** - Boosts quiet mics automatically
- ✅ **Adaptive VAD** - Auto-calibrates to your environment
- ✅ **Pre-roll buffer** - Captures audio before wake word
- ✅ **Smart silence detection** - Doesn't cut off mid-sentence
- ✅ **Multi-turn conversations** - No need to say wake word again

## Diagnostic Tools

### 1. Quick Diagnostic (Start Here)

```bash
python quick_diagnostic.py
```

**What it does:**
- Tests microphone levels (5 sec)
- Tests AGC functionality (3 sec)
- Tests wake word detection (20 sec)

**Total time:** ~30 seconds

**Output:**
```
Audio Levels: ✓ PASS
AGC Test:     ✓ PASS
Wake Word:    ✓ PASS

✓ All tests passed! Your voice assistant should work.
```

### 2. Comprehensive Diagnostic (If Issues Found)

```bash
python diagnostic_voice_comprehensive.py
```

**What it does:**
- Phase 1: Audio level analysis (5 sec)
- Phase 2: VAD configuration check
- Phase 3: Wake word sensitivity test (30 sec)
- Phase 4: VAD speech capture test (30 sec)
- Phase 5: Timeout behavior test (10 sec)

**Total time:** ~2 minutes

**Use this when:**
- Quick diagnostic fails
- You need detailed analysis
- You're tuning parameters

## Common Issues & Quick Fixes

### Issue: "AUDIO TOO QUIET"

**Quick fix:**

1. Check AGC is enabled:
   ```bash
   grep enable_agc config.json
   # Should show: "enable_agc": true
   ```

2. If disabled, enable it:
   ```json
   {
     "enable_agc": true
   }
   ```

3. Increase system mic volume:
   - macOS: System Preferences → Sound → Input
   - Slide "Input volume" to the right

### Issue: "NO WAKE WORDS DETECTED"

**Quick fix:**

1. Check wake words match what you're saying:
   ```bash
   grep wake_variants config.json
   ```

2. Try different wake words:
   ```json
   {
     "wake_variants": [
       "hey glasses",
       "hi glasses",
       "ok glasses"
     ]
   }
   ```

3. Increase sensitivity:
   ```json
   {
     "wake_sensitivity": 0.8
   }
   ```

### Issue: "Speech cuts off mid-sentence"

**Quick fix:**

```json
{
  "silence_ms": 1500,
  "min_speech_frames": 6,
  "tail_padding_ms": 500
}
```

### Issue: "Missing beginning of speech"

**Quick fix:**

```json
{
  "pre_roll_ms": 800
}
```

## Configuration Quick Reference

Edit `config.json`:

```json
{
  // Audio capture
  "silence_ms": 1200,          // How long to wait for silence
  "pre_roll_ms": 600,          // Audio buffer before wake word
  "min_speech_frames": 4,      // Min speech before timeout
  "tail_padding_ms": 400,      // Audio after silence
  
  // VAD (Voice Activity Detection)
  "vad_aggressiveness": 1,     // 0=sensitive, 3=aggressive
  
  // Wake word
  "wake_sensitivity": 0.7,     // 0.0=strict, 1.0=loose
  "wake_variants": [
    "hey glasses",
    "hi glasses"
  ],
  
  // AGC (Automatic Gain Control)
  "enable_agc": true            // Auto-boost quiet mics
}
```

## Testing Workflow

### Step 1: Quick Test

```bash
python quick_diagnostic.py
```

**If all pass:** You're good! Run the full assistant:
```bash
python app/main.py
```

**If any fail:** Continue to Step 2.

### Step 2: Comprehensive Test

```bash
python diagnostic_voice_comprehensive.py
```

Follow the prompts for each phase. The tool will tell you exactly what's wrong.

### Step 3: Adjust Config

Based on diagnostic output, edit `config.json`.

Common adjustments:

| Problem | Solution |
|---------|----------|
| Audio too quiet | Enable AGC, increase system mic volume |
| Wake word not detected | Increase wake_sensitivity, check wake_variants |
| Speech cut off | Increase silence_ms, min_speech_frames |
| Missing start of speech | Increase pre_roll_ms |
| Missing end of speech | Increase tail_padding_ms |

### Step 4: Test Full System

```bash
python app/main.py
```

1. Say "hey glasses"
2. Wait for confirmation
3. Say your command
4. Verify full command was captured

## Detailed Documentation

For complete documentation, see:

- **[VOICE_DIAGNOSTIC_GUIDE.md](VOICE_DIAGNOSTIC_GUIDE.md)** - Complete diagnostic guide
- **[config.json](config.json)** - Current configuration
- **[app/audio/agc.py](app/audio/agc.py)** - AGC implementation
- **[app/audio/wake.py](app/audio/wake.py)** - Wake word detection
- **[app/audio/capture.py](app/audio/capture.py)** - Speech capture

## Getting Help

### Check Logs

The system logs detailed diagnostics:

```bash
python app/main.py 2>&1 | tee voice.log
```

Look for:
- `[AGC]` - Gain control stats
- `[WAKE]` - Wake word detection
- `[CAPTURE]` - Speech capture
- `[VAD→SPEECH]` - Speech detection
- `[VAD→SILENCE]` - Silence detection

### Common Log Messages

**Good (working correctly):**
```
[AGC] Gain: 2.34x (+7.4dB) | RMS: 1283 → 3000 | VAD Level: 2
✓ Wake word detected! Transcript: 'hey glasses' Pre-roll buffer: 30 frames
[VAD→SPEECH] First voice detected at +234ms (total frames: 12)
[VAD→SILENCE] Silence for 1200ms (threshold=1200ms); ending capture
```

**Bad (issues detected):**
```
⚠️  AUDIO TOO QUIET
❌ NO WAKE WORDS DETECTED
[CAPTURE] No speech in pre-roll buffer
```

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────┐
│ VOICE ASSISTANT DIAGNOSTIC QUICK REFERENCE              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ QUICK TEST:                                             │
│   python quick_diagnostic.py                            │
│                                                         │
│ FULL TEST:                                              │
│   python diagnostic_voice_comprehensive.py              │
│                                                         │
│ RUN ASSISTANT:                                          │
│   python app/main.py                                    │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ COMMON FIXES:                                           │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Audio too quiet:                                        │
│   "enable_agc": true                                    │
│   Increase system mic volume                            │
│                                                         │
│ Wake word not detected:                                 │
│   "wake_sensitivity": 0.8                               │
│   Check "wake_variants"                                 │
│                                                         │
│ Speech cut off:                                         │
│   "silence_ms": 1500                                    │
│   "min_speech_frames": 6                                │
│                                                         │
│ Missing start of speech:                                │
│   "pre_roll_ms": 800                                    │
│                                                         │
│ Missing end of speech:                                  │
│   "tail_padding_ms": 500                                │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Next Steps

1. **Run quick diagnostic** to identify issues
2. **Adjust config.json** based on results
3. **Run full assistant** and test
4. **Check logs** if issues persist
5. **Read full guide** for advanced tuning

That's it! The diagnostic tools will tell you exactly what needs fixing.
