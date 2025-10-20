# Quick Start: Testing the Session FSM

## ✅ Pre-Flight Check

```bash
# 1. Verify all core files compile
python3 -m py_compile app/session.py app/audio/audioio.py app/util/artifacts.py app/util/structured_log.py app/ui.py

# 2. Run component tests (should all pass)
python3 test_components.py
```

## 🚀 First Test Run

```bash
# Start the application
python3 app/main.py
```

### Test Scenario 1: Full Word Capture (2 minutes)

1. **Trigger wake**: Say "hey glasses" (or press Ctrl+G)
2. **Speak immediately**: "hello world"
3. **Check**: Transcript should show "hello world" (not "ello world")
4. ✅ **PASS** if first syllable captured

### Test Scenario 2: Conversation Continues (3 minutes)

1. **Start**: Say "hey glasses"
2. **First turn**: "what's the weather today"
3. **Wait**: Listen to TTS response
4. **Status check**: UI should show "AwaitFollowup (Press Ctrl+G to continue, or wait 15s)"
5. **Continue**: Press Ctrl+G within 15 seconds
6. **Second turn**: "and tomorrow"
7. **Wait**: Listen to TTS response
8. ✅ **PASS** if 2 turns complete without re-triggering wake word

### Test Scenario 3: 15-Second Timeout (1 minute)

1. **Start**: Say "hey glasses"
2. **Speak**: "hello"
3. **Wait**: Listen to response
4. **Do nothing**: Don't press Ctrl+G, don't speak
5. **Wait 16 seconds**
6. **Check**: Status should return to "Idle"
7. ✅ **PASS** if session ends automatically

### Test Scenario 4: Exit Phrase (1 minute)

1. **Start**: Say "hey glasses"
2. **Speak**: "tell me a joke"
3. **Wait**: Listen to joke
4. **Exit**: Say "bye glasses"
5. **Check**: Should say "Goodbye!" and return to Idle
6. ✅ **PASS** if exits gracefully

## 📊 View Results

### Check Artifacts

```bash
# List sessions
ls -lt ~/GlassesSessions/

# View last session
SESSION=$(ls -t ~/GlassesSessions/ | head -1)
echo "Last session: $SESSION"

# Count turns
ls ~/GlassesSessions/$SESSION/ | grep turn_

# Listen to first turn
afplay ~/GlassesSessions/$SESSION/turn_0/mic_raw.wav

# Read transcript
cat ~/GlassesSessions/$SESSION/turn_0/stt_final.txt

# View timeline
cat ~/GlassesSessions/$SESSION/turn_0/timeline.txt

# View session summary
cat ~/GlassesSessions/$SESSION/session_summary.json | jq
```

### Check Structured Logs

```bash
# View all events
cat glasses_events.jsonl | jq

# View state transitions
grep "session.state" glasses_events.jsonl | jq -r '[.ts, .state] | @tsv'

# View last session timeline
grep "session.id" glasses_events.jsonl | tail -1 | jq .session_id | xargs -I {} grep {} glasses_events.jsonl | jq -r '[.event, .state // empty] | @tsv'
```

## 🐛 Quick Troubleshooting

### Issue: Still losing first syllable

```bash
# Check if pre-roll buffer is being used
grep "Using pre-roll buffer" glasses-debug.log

# Expected: "[CAPTURE] Using pre-roll buffer with N frames"
# If you see "WARNING: No pre-roll buffer", check wake.py integration
```

### Issue: Session doesn't continue

```bash
# Check state transitions
grep "session.state" glasses_events.jsonl | tail -10 | jq .state

# Expected last state: "AwaitFollowup"
# If last state is "Idle", check _on_response_ready() in ui.py
```

### Issue: Hearing echo

```bash
# Check if mic is being muted during TTS
grep -i "muted" glasses-debug.log

# Expected: "Microphone MUTED" then "Microphone UNMUTED"
# If not found, verify with_tts_guard() is wrapping tts.speak()
```

## 📋 Success Checklist

After running all 4 test scenarios:

- [ ] First syllable captured (Test 1)
- [ ] Multi-turn conversation works (Test 2)
- [ ] 15-second timeout works (Test 3)
- [ ] "bye glasses" exit works (Test 4)
- [ ] Artifacts saved in ~/GlassesSessions/
- [ ] Structured logs in glasses_events.jsonl
- [ ] No echo during TTS
- [ ] UI shows state transitions

## 🎯 All Pass?

If all tests pass:
- ✅ Implementation is working correctly
- ✅ Ready for production use

If any fail:
- 📖 Check `RUNBOOK.md` for debugging procedures
- 🔍 Review `glasses-debug.log` for errors
- 📁 Verify artifact files were created
- 📊 Check `glasses_events.jsonl` for state transitions

## 📞 Next Steps

1. **Test with real usage**: Use for actual tasks
2. **Monitor logs**: Watch for any errors or edge cases
3. **Tune parameters**: Adjust timeout (15s), silence_ms (1200ms) if needed
4. **Add auto-detection**: Implement VAD-based speech detection in AwaitFollowup (future enhancement)

---

**Total test time**: ~7 minutes
**Expected result**: All tests pass ✅
