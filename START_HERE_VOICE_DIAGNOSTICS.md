# Voice Assistant Diagnostics - START HERE

## Quick Start (30 seconds)

```bash
python quick_diagnostic.py
```

This will tell you if your voice assistant is working correctly.

## What This Is

You have a voice assistant with three potential issues:

1. Wake word only works when shouted
2. Speech capture fails after wake word
3. Timeout/silence detection cuts off speech

**Good news:** Your codebase already has fixes for all three issues!

**What you need to do:** Run diagnostics to verify everything works, and tune if needed.

## Documentation Structure

### 1. Quick Start

**File:** [DIAGNOSTIC_README.md](DIAGNOSTIC_README.md)

**Read this if:**
- You want to get started quickly
- You just want to know if it works
- You need quick fixes for common issues

**Time:** 5 minutes to read, 30 seconds to run diagnostic

### 2. Complete Solution Guide

**File:** [VOICE_ASSISTANT_COMPLETE_SOLUTION.md](VOICE_ASSISTANT_COMPLETE_SOLUTION.md)

**Read this if:**
- You want to understand what's already implemented
- You need detailed troubleshooting
- You want to tune parameters
- You're debugging specific issues

**Time:** 15 minutes to read, 2 minutes to run full diagnostic

### 3. Detailed Diagnostic Guide

**File:** [VOICE_DIAGNOSTIC_GUIDE.md](VOICE_DIAGNOSTIC_GUIDE.md)

**Read this if:**
- You want comprehensive technical details
- You're implementing the fixes from scratch (not needed - already done!)
- You want to understand the diagnostic output
- You're doing advanced tuning

**Time:** 30 minutes to read, includes all diagnostic phases

## Diagnostic Tools

### 1. Quick Diagnostic (Recommended First Step)

**File:** `quick_diagnostic.py`

**What it does:**
- Tests microphone levels (5 sec)
- Tests AGC functionality (3 sec)
- Tests wake word detection (20 sec)

**When to use:**
- First time setup
- Quick health check
- After changing config

**How to run:**
```bash
python quick_diagnostic.py
```

**Output:**
```
Audio Levels: ✓ PASS
AGC Test:     ✓ PASS
Wake Word:    ✓ PASS

✓ All tests passed!
```

### 2. Comprehensive Diagnostic (If Issues Found)

**File:** `diagnostic_voice_comprehensive.py`

**What it does:**
- Phase 1: Audio level analysis (5 sec)
- Phase 2: VAD configuration check
- Phase 3: Wake word sensitivity (30 sec)
- Phase 4: VAD speech capture (30 sec)
- Phase 5: Timeout behavior (10 sec)

**When to use:**
- Quick diagnostic fails
- Need detailed analysis
- Tuning parameters

**How to run:**
```bash
python diagnostic_voice_comprehensive.py
```

### 3. Real-Time Monitor (For Live Debugging)

**File:** `monitor_voice_realtime.py`

**What it does:**
- Shows live audio levels
- Shows AGC gain in real-time
- Shows VAD speech detection
- Shows live transcription

**When to use:**
- Debugging live issues
- Understanding real-time behavior
- Demonstrating to others

**How to run:**
```bash
python monitor_voice_realtime.py
```

## Decision Tree

```
START
  │
  ├─ Want quick check? ──────────────────────► Run quick_diagnostic.py
  │                                                      │
  │                                                      ├─ All pass? ──► Run app/main.py (done!)
  │                                                      │
  │                                                      └─ Any fail? ──► Continue below
  │
  ├─ Need detailed analysis? ────────────────► Run diagnostic_voice_comprehensive.py
  │                                                      │
  │                                                      ├─ Identifies issue ──► Adjust config.json
  │                                                      │                        │
  │                                                      │                        └─► Re-run quick_diagnostic.py
  │                                                      │
  │                                                      └─ Still issues? ──► Read VOICE_ASSISTANT_COMPLETE_SOLUTION.md
  │
  ├─ Want to see live behavior? ─────────────► Run monitor_voice_realtime.py
  │
  ├─ Want to understand what's implemented? ─► Read VOICE_ASSISTANT_COMPLETE_SOLUTION.md
  │
  └─ Want technical deep dive? ──────────────► Read VOICE_DIAGNOSTIC_GUIDE.md
```

## What's Already Fixed in Your Code

Your codebase already has these advanced features:

### ✅ Automatic Gain Control (AGC)
- **File:** `app/audio/agc.py`
- **What:** Automatically boosts quiet microphones up to 10x
- **Config:** `"enable_agc": true` in config.json
- **Log:** `[AGC] Gain: 2.34x (+7.4dB) | RMS: 1283 → 3000`

### ✅ Adaptive VAD
- **File:** `app/audio/agc.py`
- **What:** Auto-calibrates to background noise
- **Config:** Automatic (no config needed)
- **Log:** `[AGC] Auto-selected VAD level 2 (background RMS: 234.5)`

### ✅ Pre-Roll Buffer
- **Files:** `app/audio/wake.py`, `app/audio/capture.py`
- **What:** Captures audio before wake word
- **Config:** `"pre_roll_ms": 600` in config.json
- **Log:** `✓ Wake word detected! Pre-roll buffer: 30 frames`

### ✅ Robust Silence Detection
- **File:** `app/audio/capture.py`
- **What:** Prevents premature cutoff
- **Config:** `"silence_ms": 1200`, `"min_speech_frames": 4`
- **Log:** `[VAD→SILENCE] Silence for 1200ms; ending capture`

### ✅ Multi-Turn Conversations
- **File:** `app/session.py`
- **What:** No need to re-wake between turns
- **Config:** 15-second follow-up timeout (hardcoded)
- **Log:** `Session Turn 0: Follow-up speech detected! Starting turn 1...`

### ✅ Comprehensive Logging
- **Files:** Throughout codebase
- **What:** Detailed diagnostic output
- **Config:** Always enabled
- **Log:** See examples above

## Common Issues & Quick Fixes

### Issue: "AUDIO TOO QUIET"

**Quick fix:**
```bash
# 1. Check AGC is enabled
grep enable_agc config.json
# Should show: "enable_agc": true

# 2. If not, edit config.json:
# "enable_agc": true

# 3. Increase system mic volume
# macOS: System Preferences → Sound → Input
```

### Issue: "NO WAKE WORDS DETECTED"

**Quick fix:**
```json
// Edit config.json:
{
  "wake_sensitivity": 0.8,  // Increase from 0.7
  "wake_variants": [
    "hey glasses",
    "hi glasses",
    "ok glasses"
  ]
}
```

### Issue: "Speech cuts off mid-sentence"

**Quick fix:**
```json
// Edit config.json:
{
  "silence_ms": 1500,       // Increase from 1200
  "min_speech_frames": 6    // Increase from 4
}
```

### Issue: "Missing beginning of speech"

**Quick fix:**
```json
// Edit config.json:
{
  "pre_roll_ms": 800  // Increase from 600
}
```

## Recommended Workflow

### First Time Setup

1. **Run quick diagnostic:**
   ```bash
   python quick_diagnostic.py
   ```

2. **If all pass:**
   ```bash
   python app/main.py
   ```
   You're done! Enjoy your voice assistant.

3. **If any fail:**
   - Read the diagnostic output
   - Apply suggested fixes to `config.json`
   - Re-run quick diagnostic
   - If still failing, run comprehensive diagnostic

### Troubleshooting

1. **Run comprehensive diagnostic:**
   ```bash
   python diagnostic_voice_comprehensive.py
   ```

2. **Read the output carefully:**
   - Each phase identifies specific issues
   - Recommendations are provided
   - Parameter adjustments are suggested

3. **Adjust `config.json`:**
   - Apply recommended changes
   - Save file

4. **Re-test:**
   ```bash
   python quick_diagnostic.py
   ```

5. **If still issues:**
   - Read [VOICE_ASSISTANT_COMPLETE_SOLUTION.md](VOICE_ASSISTANT_COMPLETE_SOLUTION.md)
   - Check troubleshooting section
   - Run real-time monitor to see live behavior

### Advanced Tuning

1. **Run real-time monitor:**
   ```bash
   python monitor_voice_realtime.py
   ```

2. **Speak and observe:**
   - Watch audio levels
   - Watch AGC gain
   - Watch VAD detection
   - Watch transcription

3. **Adjust parameters:**
   - Edit `config.json` based on observations
   - Re-run monitor to verify changes

4. **Test full system:**
   ```bash
   python app/main.py
   ```

## Configuration Quick Reference

### Essential Parameters

```json
{
  // AGC (Automatic Gain Control)
  "enable_agc": true,           // ← Must be true for quiet mics
  
  // Wake Word
  "wake_sensitivity": 0.7,      // ← Increase if not detecting
  "wake_variants": [            // ← Add variants you say
    "hey glasses",
    "hi glasses"
  ],
  
  // Speech Capture
  "silence_ms": 1200,           // ← Increase if cutting off
  "pre_roll_ms": 600,           // ← Increase if missing start
  "min_speech_frames": 4,       // ← Increase if cutting off
  "tail_padding_ms": 400,       // ← Increase if missing end
  
  // VAD (Voice Activity Detection)
  "vad_aggressiveness": 1       // ← Lower = more sensitive
}
```

### Tuning Presets

**Quiet Environment:**
```json
{
  "vad_aggressiveness": 1,
  "wake_sensitivity": 0.8,
  "silence_ms": 1500
}
```

**Noisy Environment:**
```json
{
  "vad_aggressiveness": 3,
  "wake_sensitivity": 0.6,
  "silence_ms": 1000
}
```

**Fast Speaker:**
```json
{
  "silence_ms": 800,
  "min_speech_frames": 2,
  "tail_padding_ms": 200
}
```

**Slow Speaker:**
```json
{
  "silence_ms": 2000,
  "min_speech_frames": 8,
  "tail_padding_ms": 600
}
```

## File Reference

### Documentation
- **[START_HERE_VOICE_DIAGNOSTICS.md](START_HERE_VOICE_DIAGNOSTICS.md)** ← You are here
- **[DIAGNOSTIC_README.md](DIAGNOSTIC_README.md)** - Quick start guide
- **[VOICE_ASSISTANT_COMPLETE_SOLUTION.md](VOICE_ASSISTANT_COMPLETE_SOLUTION.md)** - Complete solution
- **[VOICE_DIAGNOSTIC_GUIDE.md](VOICE_DIAGNOSTIC_GUIDE.md)** - Detailed technical guide

### Diagnostic Tools
- **[quick_diagnostic.py](quick_diagnostic.py)** - 30-second quick test
- **[diagnostic_voice_comprehensive.py](diagnostic_voice_comprehensive.py)** - Full diagnostic suite
- **[monitor_voice_realtime.py](monitor_voice_realtime.py)** - Real-time monitor

### Configuration
- **[config.json](config.json)** - Main configuration file

### Source Code (Already Fixed!)
- **[app/audio/agc.py](app/audio/agc.py)** - AGC and Adaptive VAD
- **[app/audio/wake.py](app/audio/wake.py)** - Wake word detection
- **[app/audio/capture.py](app/audio/capture.py)** - Speech capture
- **[app/session.py](app/session.py)** - Multi-turn conversations

## Summary

**Your voice assistant already has all the fixes implemented!**

**To verify it works:**
```bash
python quick_diagnostic.py
```

**If all tests pass:**
```bash
python app/main.py
```

**If tests fail:**
1. Read diagnostic output
2. Adjust `config.json`
3. Re-run diagnostic
4. If still issues, read [VOICE_ASSISTANT_COMPLETE_SOLUTION.md](VOICE_ASSISTANT_COMPLETE_SOLUTION.md)

**That's it!** The diagnostic tools will guide you through any issues.

---

## Next Steps

1. **Run quick diagnostic now:**
   ```bash
   python quick_diagnostic.py
   ```

2. **Based on results:**
   - ✅ All pass → Run `python app/main.py` and enjoy!
   - ⚠️ Some fail → Follow diagnostic recommendations
   - ❌ All fail → Read [VOICE_ASSISTANT_COMPLETE_SOLUTION.md](VOICE_ASSISTANT_COMPLETE_SOLUTION.md)

3. **Get help:**
   - Check logs: `python app/main.py 2>&1 | tee voice.log`
   - Run real-time monitor: `python monitor_voice_realtime.py`
   - Read troubleshooting guide in [VOICE_ASSISTANT_COMPLETE_SOLUTION.md](VOICE_ASSISTANT_COMPLETE_SOLUTION.md)

Good luck! Your voice assistant is ready to use. 🎤
