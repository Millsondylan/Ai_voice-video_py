# 🚀 START HERE - Voice Assistant Diagnostics

## ⚡ Fastest Path to Results

**Want to test your voice assistant right now?**

```bash
# 1. Install (if needed)
pip install webrtcvad vosk pyaudio pyttsx3

# 2. Run
python3 test_voice_diagnostic_standalone.py

# 3. Follow the prompts
```

**That's it!** The script will guide you through 5 comprehensive tests.

---

## 📚 Documentation Guide

### 🎯 Choose Your Path

#### Path 1: I Want to Run Tests NOW ⚡
→ **Run this command:**
```bash
python3 test_voice_diagnostic_standalone.py
```

→ **Read this:** `QUICK_DIAGNOSTIC_START.md`

#### Path 2: I Want to Understand Everything First 📖
→ **Read this:** `README_DIAGNOSTICS.md`

→ **Then read:** `DIAGNOSTIC_COMPREHENSIVE_GUIDE.md`

#### Path 3: I Want a Quick Overview 👀
→ **Read this:** `DIAGNOSTIC_TOOLS_SUMMARY.md`

#### Path 4: I Have Specific Issues 🔧
→ **Read this:** `DIAGNOSTIC_COMPREHENSIVE_GUIDE.md` (Section: "Common Issues & Solutions")

---

## 📁 File Guide

### 🔴 **START WITH THESE**

| File | Purpose | Read Time |
|------|---------|-----------|
| `README_DIAGNOSTICS.md` | Main reference, all 5 tests explained | 5 min |
| `QUICK_DIAGNOSTIC_START.md` | Fast start, common issues | 3 min |

### 🟡 **READ THESE NEXT**

| File | Purpose | Read Time |
|------|---------|-----------|
| `DIAGNOSTIC_COMPREHENSIVE_GUIDE.md` | Detailed tuning and troubleshooting | 15 min |
| `DIAGNOSTIC_TOOLS_SUMMARY.md` | Complete overview and best practices | 10 min |

### 🟢 **REFERENCE MATERIALS**

| File | Purpose |
|------|---------|
| `DIAGNOSTIC_IMPLEMENTATION_COMPLETE.md` | Implementation summary |
| `START_HERE_DIAGNOSTICS.md` | This file |

---

## 🎯 What Gets Tested

### Test 1: Wake Word Detection ✅
**What:** "hey glasses" recognition accuracy  
**Time:** 30 seconds  
**You say:** "hey glasses what time is it"

### Test 2: No Wake Word ✅
**What:** Non-wake inputs properly ignored  
**Time:** 30 seconds  
**You say:** "what time is it" (WITHOUT wake word)

### Test 3: Multi-turn Conversation ✅
**What:** Continuous listening after response  
**Time:** 2 minutes  
**You say:** 
1. "hey glasses what's the weather"
2. "what about tomorrow" (no wake word)

### Test 4: Timeout Handling ✅
**What:** 15-second silence timeout  
**Time:** 2 minutes  
**You say:** "hey glasses hello" then stay silent

### Test 5: Exit Phrase ✅
**What:** "bye glasses" termination  
**Time:** 30 seconds  
**You say:** "hey glasses bye glasses"

**Total test time: ~5 minutes**

---

## 🎬 What Happens When You Run

```
======================================================================
VOICE ASSISTANT DIAGNOSTIC TESTS
======================================================================

──────────────────────────────────────────────────────────────────────
TEST 1: Wake Word Detection
──────────────────────────────────────────────────────────────────────
>>> Say: 'hey glasses what time is it'
Press Enter when ready...

[00:01.234] [INIT] ✓ Loaded model: models/vosk-model-small-en-us-0.15
[00:02.345] [MIC] 🎤 Listening...
[00:03.456] [MIC] 🗣️  Voice detected
[00:05.678] [MIC] ✓ Captured 2.22s
[00:05.789] [STT] 📝 "hey glasses what time is it"
[00:05.890] [WAKE] ✓ Wake word detected!

... (4 more tests) ...

======================================================================
✓ ALL TESTS COMPLETE
======================================================================

✓ Logs saved to: diagnostic_20250121_143022.json
```

---

## 🔍 What You'll Learn

After running the diagnostic, you'll know:

- ✅ If audio is being clipped (first/last syllables lost)
- ✅ If wake word detection is working
- ✅ If follow-up listening works after responses
- ✅ If conversation state is maintained
- ✅ If timeout and exit handling work

---

## 🛠️ Common Issues & Quick Fixes

### Issue: First syllables cut off
**Symptom:** Transcription shows "lasses" instead of "hey glasses"  
**Fix:** Edit script, increase `pre_roll_frames` from 3 to 5

### Issue: Last words cut off
**Symptom:** Transcription shows "what time" instead of "what time is it"  
**Fix:** Edit script, increase `hangover_frames` from 10 to 15

### Issue: Follow-up not captured
**Symptom:** After first response, system doesn't listen again  
**Fix:** TTS blocking microphone (pyttsx3 bug) - use simulated TTS

### Issue: History lost
**Symptom:** Conversation history shows 1 turn after second query  
**Fix:** State management bug in main application

---

## 📊 Output Files

After running, you get:

```
diagnostic_20250121_143022.json
```

This JSON file contains all timestamped events.

**Analyze it:**
```bash
# Show all errors
cat diagnostic_*.json | jq '.[] | select(.level == "ERROR")'

# Show transcriptions
cat diagnostic_*.json | jq '.[] | select(.component == "STT") | .text'
```

---

## 🎓 Learning Path

### Beginner (Just want it to work)
1. Run `python3 test_voice_diagnostic_standalone.py`
2. Read `QUICK_DIAGNOSTIC_START.md`
3. Fix issues based on output
4. Re-run to verify

### Intermediate (Want to understand)
1. Read `README_DIAGNOSTICS.md`
2. Run `python3 test_voice_diagnostic_standalone.py --verbose`
3. Read `DIAGNOSTIC_COMPREHENSIVE_GUIDE.md`
4. Tune parameters based on findings

### Advanced (Want to customize)
1. Read `DIAGNOSTIC_TOOLS_SUMMARY.md`
2. Study the script source code
3. Modify parameters for your environment
4. Integrate with your application

---

## 💡 Pro Tips

1. **Run in a quiet room** for best results
2. **Use consistent volume** when speaking
3. **Test multiple times** to verify consistency
4. **Save log files** to track improvements
5. **Start with defaults** before tuning

---

## 🆘 Troubleshooting

### Can't install PyAudio?
```bash
# macOS
brew install portaudio
pip install pyaudio
```

### Vosk model not found?
```bash
cd models
wget https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
```

### Microphone not working?
**macOS:** System Preferences → Security & Privacy → Microphone → Enable for Terminal

---

## 🎯 Next Steps

### Right Now (5 minutes)
```bash
python3 test_voice_diagnostic_standalone.py
```

### Today (30 minutes)
1. Review test output
2. Read `README_DIAGNOSTICS.md`
3. Identify issues
4. Plan fixes

### This Week
1. Tune parameters
2. Fix bugs in main app
3. Re-run tests
4. Document optimal settings

---

## 📞 Need Help?

1. **Check the logs** - Most issues are logged with details
2. **Read the docs** - Comprehensive guides included
3. **Try different settings** - Tuning often solves issues
4. **Review the script** - Well-commented source code

---

## ✅ Success Criteria

You're done when all tests show:

- ✅ Wake word detected 100%
- ✅ No audio clipping
- ✅ Follow-up works without wake word
- ✅ History grows across turns
- ✅ Timeout triggers at 15s
- ✅ Exit phrase works

---

## 🎉 Ready to Start?

**Run this now:**
```bash
python3 test_voice_diagnostic_standalone.py
```

**Questions?** Read `README_DIAGNOSTICS.md`

**Issues?** Check `DIAGNOSTIC_COMPREHENSIVE_GUIDE.md`

---

**Last Updated:** 2025-01-21  
**Status:** ✅ Production Ready  
**Next Action:** Run the diagnostic!
