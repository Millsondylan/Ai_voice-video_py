# Voice Assistant Diagnostic Tools

## 🎯 Purpose

Comprehensive diagnostic tools to identify and fix voice assistant pipeline issues:

- ❌ **Unreliable speech capture** (clipped audio)
- ❌ **Inconsistent wake word detection**
- ❌ **Failure to continue listening** after responses
- ❌ **Lost conversation state** across turns
- ❌ **Broken timeout/exit** handling

## ⚡ Quick Start (30 seconds)

```bash
# 1. Install dependencies
pip install webrtcvad vosk pyaudio pyttsx3

# 2. Run diagnostics
python3 test_voice_diagnostic_standalone.py

# 3. Follow the prompts and speak when asked
```

That's it! The script will test all 5 core issues and generate a detailed report.

## 📦 What's Included

### Scripts

| File | Description | Use When |
|------|-------------|----------|
| `test_voice_diagnostic_standalone.py` ⭐ | Self-contained, no app/ dependencies | **Start here** - works immediately |
| `test_voice_diagnostic_comprehensive.py` | Integrated with app/ modules | Advanced testing with existing code |

### Documentation

| File | Description |
|------|-------------|
| `QUICK_DIAGNOSTIC_START.md` | Fast start guide with examples |
| `DIAGNOSTIC_COMPREHENSIVE_GUIDE.md` | Detailed reference and tuning guide |
| `DIAGNOSTIC_TOOLS_SUMMARY.md` | Complete overview and best practices |
| `README_DIAGNOSTICS.md` | This file |

## 🧪 The 5 Core Tests

### 1. Wake Word Detection ✅

**Tests:** "hey glasses" recognition accuracy

**What you'll do:** Say "hey glasses what time is it"

**Success looks like:**
```
[STT] 📝 "hey glasses what time is it"
[WAKE] ✓ Wake word detected!
```

### 2. No Wake Word ✅

**Tests:** Non-wake inputs are properly ignored

**What you'll do:** Say "what time is it" (WITHOUT wake word)

**Success looks like:**
```
[WAKE] ✓ Correctly ignored (no wake word)
```

### 3. Multi-turn Conversation ✅

**Tests:** Continuous listening after TTS response

**What you'll do:** 
1. Say "hey glasses what's the weather"
2. Then say "what about tomorrow" (no wake word)

**Success looks like:**
```
[TEST] ✓ Follow-up captured successfully!
[TEST] ✓ Conversation history retained!
```

### 4. Timeout Handling ✅

**Tests:** 15-second silence timeout

**What you'll do:** Say "hey glasses hello", then stay silent for 15s

**Success looks like:**
```
[TEST] ✓ Timeout triggered correctly!
```

### 5. Exit Phrase ✅

**Tests:** "bye glasses" termination

**What you'll do:** Say "hey glasses bye glasses"

**Success looks like:**
```
[TEST] ✓ Exit phrase detected!
```

## 📊 Example Output

### Successful Run

```
======================================================================
VOICE ASSISTANT DIAGNOSTIC TESTS
======================================================================

──────────────────────────────────────────────────────────────────────
TEST 1: Wake Word Detection
──────────────────────────────────────────────────────────────────────
>>> Say: 'hey glasses what time is it'
Press Enter when ready...

[00:01.234] [INIT        ] ✓ Loaded model: models/vosk-model-small-en-us-0.15
[00:02.345] [MIC         ] 🎤 Listening...
[00:03.456] [MIC         ] 🗣️  Voice detected
[00:05.678] [MIC         ] 🔇 Silence detected, stopping
[00:05.789] [MIC         ] ✓ Captured 2.22s
[00:05.901] [STT         ] 📝 "hey glasses what time is it"
[00:05.912] [WAKE        ] ✓ Wake word detected!

──────────────────────────────────────────────────────────────────────
TEST 3: Multi-turn Conversation
──────────────────────────────────────────────────────────────────────
>>> Turn 1: Say 'hey glasses what's the weather'
[00:10.123] [STT         ] 📝 "hey glasses what's the weather"
[00:10.234] [CONV        ] ✓ Activated
[00:10.345] [TTS         ] 🔊 "It's sunny today"
[00:10.456] [TTS         ] ✓ Finished

>>> Turn 2: Say 'what about tomorrow' (NO wake word)
[00:15.678] [STT         ] 📝 "what about tomorrow"
[00:15.789] [TEST        ] ✓ Follow-up captured successfully!
[00:15.890] [TEST        ] ✓ Conversation history retained!

======================================================================
✓ ALL TESTS COMPLETE
======================================================================

✓ Logs saved to: diagnostic_20250121_143022.json
```

### Failed Test Example

```
[00:05.901] [STT         ] 📝 "lasses what time is it"  # ❌ Missing "hey g"
[00:05.912] [WAKE        ] ❌ Wake word NOT detected

[00:15.678] [TEST        ] ❌ Follow-up not captured (timeout)
```

## 🔧 Common Issues & Fixes

### Issue 1: First Syllables Cut Off

**Symptom:**
```
[STT] 📝 "lasses what time is it"  # Missing "hey g"
```

**Fix:** Edit script, increase `pre_roll_frames`:
```python
pre_roll_frames: int = 5  # Changed from 3
```

### Issue 2: Last Words Cut Off

**Symptom:**
```
[STT] 📝 "hey glasses what time"  # Missing "is it"
```

**Fix:** Edit script, increase `hangover_frames`:
```python
hangover_frames: int = 15  # Changed from 10
```

### Issue 3: Follow-up Not Captured

**Symptom:**
```
[TEST] ❌ Follow-up not captured (timeout)
```

**Cause:** TTS blocking microphone (pyttsx3 bug)

**Fix:** Use simulated TTS (default) or fix pyttsx3 in main app

### Issue 4: History Lost

**Symptom:**
```
[CONV] 📚 History: 1 turns  # Should be 2 after second turn!
```

**Cause:** Conversation state being reset

**Fix:** Check state management in main app

## 🎛️ Command Line Options

```bash
# Basic run
python3 test_voice_diagnostic_standalone.py

# Verbose debug output
python3 test_voice_diagnostic_standalone.py --verbose

# Enable actual TTS (default is simulated)
python3 test_voice_diagnostic_standalone.py --tts

# Use different Vosk model
python3 test_voice_diagnostic_standalone.py --model models/vosk-model-en-us-0.22

# Combine options
python3 test_voice_diagnostic_standalone.py --verbose --tts
```

## 📁 Output Files

After running, you'll get:

```
diagnostic_20250121_143022.json
```

This JSON file contains all timestamped events for detailed analysis.

**Analyze with jq:**
```bash
# Show all errors
cat diagnostic_*.json | jq '.[] | select(.level == "ERROR")'

# Show all transcriptions
cat diagnostic_*.json | jq '.[] | select(.component == "STT") | .text'

# Show timing
cat diagnostic_*.json | jq '.[] | {timestamp, component, message}'
```

## 🐛 Troubleshooting

### PyAudio Installation

```bash
# macOS
brew install portaudio
pip install pyaudio

# Linux
sudo apt-get install portaudio19-dev
pip install pyaudio

# Windows
pip install pipwin
pipwin install pyaudio
```

### Vosk Model Download

```bash
cd models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

### Microphone Permission

**macOS:** System Preferences → Security & Privacy → Microphone → Enable for Terminal

**Linux:** Check PulseAudio/ALSA settings

### List Available Microphones

```bash
python3 -c "import pyaudio; pa = pyaudio.PyAudio(); [print(f'{i}: {pa.get_device_info_by_index(i)[\"name\"]}') for i in range(pa.get_device_count())]"
```

## 📚 Documentation

For more details, see:

- **Quick Start:** `QUICK_DIAGNOSTIC_START.md`
- **Full Guide:** `DIAGNOSTIC_COMPREHENSIVE_GUIDE.md`
- **Summary:** `DIAGNOSTIC_TOOLS_SUMMARY.md`

## 🎯 Success Criteria

Your system is working when all tests show:

- ✅ Wake word detected 100% of the time
- ✅ No audio clipping (complete transcriptions)
- ✅ Follow-up queries work without wake word
- ✅ Conversation history grows across turns
- ✅ Timeout triggers at 15 seconds
- ✅ Exit phrase terminates session

## 🚀 Next Steps

1. **Run the diagnostic** to establish baseline
2. **Review the output** to identify issues
3. **Tune parameters** based on findings
4. **Apply fixes** to main application
5. **Re-run tests** to verify improvements

## 💡 Pro Tips

- Run in a **quiet environment** for best results
- Use **consistent speech volume**
- Test **multiple times** to verify consistency
- **Save log files** to track improvements
- **Compare before/after** when making changes

---

**Ready to start?**

```bash
python3 test_voice_diagnostic_standalone.py
```

**Questions?** Check the documentation files or review the script source code.

---

**Last Updated:** 2025-01-21  
**Status:** Production Ready ✅
