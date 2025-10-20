# Glasses Assistant - Diagnostic Runbook

## Quick Start Verification

Run the comprehensive test suite first:
```bash
python test_comprehensive_fixes.py
```

Expected output: All 5 tests should pass (✅)

## System Overview

The Glasses Assistant uses a Finite State Machine (FSM) for conversation management:

```
States:
┌─────┐ wake/hotkey ┌───────────┐ silence    ┌──────────┐
│ IDLE ├────────────►│ RECORDING ├───────────►│ THINKING │
└─────┘              └───────────┘            └────┬─────┘
   ▲                                                │
   │                                                ▼
   │ timeout 15s    ┌────────────┐    TTS    ┌──────────┐
   └────────────────┤ AWAIT      │◄──────────┤ SPEAKING │
      or bye        │ FOLLOWUP   │            └──────────┘
                    └──────┬─────┘
                           │ speech detected
                           ▼
                    [Continue session - back to RECORDING]
```

## Key Fixes Implemented

### 1. Pre-Roll Buffer (Fixes Missing First Syllables)

**Configuration:**
- `pre_roll_ms: 400` - Captures 400ms of audio before wake word
- Buffer passed from wake detector → segment recorder

**Verification:**
```bash
# Check config
grep pre_roll_ms config.json  # Should show 400

# Monitor in logs
tail -f glasses-debug.log | grep "Using pre-roll buffer"
```

**Expected Log:**
```
[CAPTURE] Using pre-roll buffer with 20 frames (400ms)
```

### 2. Session FSM with 15-Second Follow-up

**How it works:**
- After TTS completes → AWAIT_FOLLOWUP state
- 15-second timer starts
- If speech detected → continues session (new turn)
- If timeout or "bye glasses" → ends session

**Verification:**
```bash
# Watch state transitions in JSON logs
python -c "
import json, sys
for line in sys.stdin:
    try:
        j = json.loads(line)
        if 'state_change' in j.get('event', ''):
            print(f\"{j['from_state']} → {j['to_state']} ({j.get('reason','')})\")
    except: pass
" < glasses-debug.log
```

### 3. Mic Muting During TTS (Prevents Echo)

**Implementation:**
- Mic returns silence during TTS playback
- 150ms grace period after TTS
- Controlled by `AudioIOController`

**Verification:**
Look for these log lines:
```
[AUDIO_IO] 🔇 Microphone MUTED (TTS playing)
[AUDIO_IO] 🎤 Microphone UNMUTED (ready for input)
```

### 4. VAD Parameter Tuning

**Current Settings:**
- `silence_ms: 1500` - Waits 1.5s of silence before stopping
- `vad_aggressiveness: 1` - Less aggressive (captures more)
- `chunk_samples: 320` - 20ms frames

**Verification:**
```bash
# Check configuration
python -c "
import json
c = json.load(open('config.json'))
print(f'silence_ms: {c[\"silence_ms\"]} (should be ≥1500)')
print(f'vad_aggressiveness: {c[\"vad_aggressiveness\"]} (should be 1 or 2)')
print(f'pre_roll_ms: {c[\"pre_roll_ms\"]} (should be ≥400)')
"
```

### 5. Structured Logging & Artifacts

**Session Artifacts Location:**
```
~/GlassesSessions/<session_id>/
├── turn_0/
│   ├── mic_raw.wav        # Exact audio sent to STT
│   ├── segment.mp4        # Video if available
│   ├── stt_partial.log    # Partial recognitions
│   ├── stt_final.txt      # Final transcript
│   ├── model_input.json   # VLM request
│   ├── model_output.txt   # VLM response
│   └── timeline.txt       # Event sequence
├── turn_1/
│   └── ...
├── session_log.jsonl      # All structured events
└── session_summary.txt    # Human-readable summary
```

## Diagnostic Commands

### 1. Test Audio Capture
```bash
# Test wake word detection
python -c "
from app.audio.wake import WakeWordListener
from app.audio.stt import StreamingTranscriber
from app.util.config import load_config

config = load_config()
t = StreamingTranscriber(config.vosk_model_path, config.sample_rate_hz)

def on_wake(buffer):
    print(f'Wake detected! Buffer: {len(buffer)} frames')
    exit(0)

l = WakeWordListener(config.wake_variants, on_wake, t,
                    config.sample_rate_hz, config.chunk_samples,
                    pre_roll_ms=config.pre_roll_ms)
print('Say wake word...')
l.start()
l.join()
"
```

### 2. Monitor Session State
```bash
# Real-time state monitoring
tail -f glasses-debug.log | python -c "
import json, sys, time
last_state = None
for line in sys.stdin:
    try:
        j = json.loads(line)
        if 'to_state' in j:
            state = j['to_state']
            if state != last_state:
                print(f'{time.strftime(\"%H:%M:%S\")} → {state}')
                last_state = state
    except: pass
"
```

### 3. Analyze Session Performance
```bash
# Get session metrics
python -c "
import json
from pathlib import Path
import sys

session_id = sys.argv[1] if len(sys.argv) > 1 else input('Session ID: ')
session_dir = Path(f'~/GlassesSessions/{session_id}').expanduser()

if not session_dir.exists():
    print(f'Session {session_id} not found')
    exit(1)

# Count turns
turns = sorted(session_dir.glob('turn_*'))
print(f'Total turns: {len(turns)}')

# Analyze each turn
for turn_dir in turns:
    print(f'\\n{turn_dir.name}:')

    # Check transcript
    stt_file = turn_dir / 'stt_final.txt'
    if stt_file.exists():
        text = stt_file.read_text().strip()
        print(f'  User: {text[:50]}...' if len(text) > 50 else f'  User: {text}')

    # Check response
    resp_file = turn_dir / 'model_output.txt'
    if resp_file.exists():
        resp = resp_file.read_text().strip()
        print(f'  Assistant: {resp[:50]}...' if len(resp) > 50 else f'  Assistant: {resp}')

    # Check audio
    wav_file = turn_dir / 'mic_raw.wav'
    if wav_file.exists():
        import wave
        with wave.open(str(wav_file)) as w:
            frames = w.getnframes()
            rate = w.getframerate()
            duration = frames / rate
            print(f'  Audio: {duration:.1f}s')
" SESSION_ID_HERE
```

## Common Issues & Solutions

### Issue: Missing First Words

**Symptoms:**
- First syllable or word cut off
- "ey glasses" instead of "hey glasses"

**Check:**
1. Pre-roll buffer configured: `pre_roll_ms >= 400`
2. Buffer passed correctly: Look for "[CAPTURE] Using pre-roll buffer"
3. Wake listener passing buffer: Check `_on_detect` receives list[bytes]

**Fix:**
- Increase `pre_roll_ms` to 500-600 if still missing
- Verify wake.py passes buffer: `self._on_detect(list(self._rolling_buffer))`

### Issue: Session Ends After First Reply

**Symptoms:**
- Returns to wake word listening immediately
- No 15-second window

**Check:**
1. State transitions: Should go to AWAIT_FOLLOWUP after SPEAKING
2. Timer active: Look for "AwaitFollowup" in logs

**Fix:**
- Ensure SessionManager.transition_to_await_followup() called
- Check followup_timeout_ms = 15000

### Issue: Spurious "test/tests" Output

**Symptoms:**
- Assistant says "test" randomly
- Echo of previous output

**Check:**
1. Mic muting logs present
2. No test scripts running
3. STT using final_text not partial

**Fix:**
- Ensure AudioIOController.mute_input() called during TTS
- Stop any test_*.py scripts
- Check no debug strings in code

### Issue: Cuts Off Mid-Sentence

**Symptoms:**
- Stops recording during pauses
- Incomplete sentences

**Check:**
1. `silence_ms >= 1500`
2. `vad_aggressiveness <= 2`

**Fix:**
- Increase silence_ms to 2000
- Decrease vad_aggressiveness to 1
- Add post-capture drain in capture.py

## Performance Benchmarks

Expected performance with fixes:

| Metric | Target | How to Measure |
|--------|--------|---------------|
| First word capture | 100% | Check mic_raw.wav has complete wake phrase |
| Follow-up detection | <500ms | Time from end of TTS to "Recording" state |
| Session continuity | 15s window | Verify timeout in AWAIT_FOLLOWUP |
| Echo prevention | 0 echoes | No TTS output in next transcript |
| Wake latency | <250ms | Time from wake word to Recording state |

## Log Analysis Patterns

### Successful Session Flow
```
wake.detected_at
session.start {session_id: xxx}
state_change {from: Idle, to: Recording}
segment.start {turn_index: 0}
segment.stop {stop_reason: silence}
state_change {from: Recording, to: Thinking}
state_change {from: Thinking, to: Speaking}
tts.started
tts.done
state_change {from: Speaking, to: AwaitFollowup}
[... 15s window or new speech ...]
```

### Debugging Grep Patterns
```bash
# Find all state transitions
grep "state_change" glasses-debug.log

# Find session boundaries
grep -E "session\.(start|end)" glasses-debug.log

# Find capture issues
grep -E "(pre_roll|silence_ms|stop_reason)" glasses-debug.log

# Find TTS/echo issues
grep -E "(MUTED|UNMUTED|tts\.(started|done))" glasses-debug.log
```

## Validation Checklist

Before considering the system ready:

- [ ] Run `test_comprehensive_fixes.py` - all tests pass
- [ ] Manual test: Say 10-word sentence with pause - all words captured
- [ ] Manual test: After assistant replies, speak within 10s - continues session
- [ ] Manual test: Say "bye glasses" - session ends
- [ ] Manual test: Wait 15s after reply - session ends
- [ ] Check artifacts in ~/GlassesSessions - all files present
- [ ] No "test/tests" in 10 consecutive interactions
- [ ] Wake word responds in <250ms (feels instant)

## Support

If issues persist after following this runbook:

1. Collect diagnostics:
   ```bash
   tar -czf glasses-diagnostics.tar.gz \
     config.json \
     glasses-debug.log \
     ~/GlassesSessions/latest_session/
   ```

2. Check recent changes:
   ```bash
   git diff HEAD~1
   ```

3. Review structured logs for patterns:
   ```bash
   jq -r '.event' glasses-debug.log | sort | uniq -c | sort -rn
   ```

---

*Last Updated: After implementing comprehensive fixes for speech capture, session flow, and echo prevention.*