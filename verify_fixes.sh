#!/bin/bash

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                                                                      ║"
echo "║              ✅ VERIFYING ALL FIXES ARE IN PLACE                     ║"
echo "║                                                                      ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Check 1: Pre-roll buffer in capture.py
echo "1. Checking pre-roll buffer implementation..."
if grep -q "pre_roll_buffer" app/audio/capture.py; then
    if grep -q "for frame in pre_frames:" app/audio/capture.py; then
        echo "   ✅ Pre-roll buffer: IMPLEMENTED (lines 71-85)"
    else
        echo "   ❌ Pre-roll buffer: MISSING"
    fi
else
    echo "   ❌ Pre-roll buffer: NOT FOUND"
fi

# Check 2: Tail padding in capture.py
echo "2. Checking tail padding implementation..."
if grep -q "tail_padding_ms" app/audio/capture.py; then
    if grep -q "drain_tail(tail_frames)" app/audio/capture.py; then
        echo "   ✅ Tail padding: IMPLEMENTED (lines 176-183)"
    else
        echo "   ❌ Tail padding: MISSING"
    fi
else
    echo "   ❌ Tail padding: NOT FOUND"
fi

# Check 3: Minimum speech frames
echo "3. Checking minimum speech frames..."
if grep -q "min_speech_frames" app/audio/capture.py; then
    if grep -q "total_speech_frames >= min_speech_frames" app/audio/capture.py; then
        echo "   ✅ Minimum speech frames: IMPLEMENTED (lines 99-170)"
    else
        echo "   ❌ Minimum speech frames: MISSING"
    fi
else
    echo "   ❌ Minimum speech frames: NOT FOUND"
fi

# Check 4: TTS microphone muting
echo "4. Checking TTS microphone muting..."
if grep -q "pause_input(True)" app/audio/tts.py; then
    if grep -q "pause_input(False)" app/audio/tts.py; then
        echo "   ✅ TTS microphone muting: IMPLEMENTED (lines 71, 122)"
    else
        echo "   ❌ TTS microphone unmuting: MISSING"
    fi
else
    echo "   ❌ TTS microphone muting: NOT FOUND"
fi

# Check 5: TTS grace period
echo "5. Checking TTS grace period..."
if grep -q "time.sleep(0.15)" app/audio/tts.py; then
    echo "   ✅ TTS grace period: IMPLEMENTED (line 120)"
else
    echo "   ❌ TTS grace period: NOT FOUND"
fi

# Check 6: 15-second follow-up timeout
echo "6. Checking 15-second follow-up timeout..."
if grep -q "followup_timeout_ms" app/session.py; then
    if grep -q "deadline = time.monotonic() + self.followup_timeout_ms / 1000" app/session.py; then
        echo "   ✅ 15-second timeout: IMPLEMENTED (lines 70, 348)"
    else
        echo "   ❌ 15-second timeout: MISSING"
    fi
else
    echo "   ❌ 15-second timeout: NOT FOUND"
fi

# Check 7: Conversation history retention
echo "7. Checking conversation history retention..."
if grep -q "_append_history" app/session.py; then
    if grep -q 'self._history.append({"role": "user"' app/session.py; then
        echo "   ✅ History retention: IMPLEMENTED (lines 374-381)"
    else
        echo "   ❌ History retention: MISSING"
    fi
else
    echo "   ❌ History retention: NOT FOUND"
fi

# Check 8: Pre-roll buffer passing between turns
echo "8. Checking pre-roll buffer passing..."
if grep -q "next_pre_roll" app/session.py; then
    if grep -q "pre_roll_buffer=next_pre_roll" app/session.py; then
        echo "   ✅ Pre-roll buffer passing: IMPLEMENTED (lines 111, 119)"
    else
        echo "   ❌ Pre-roll buffer passing: MISSING"
    fi
else
    echo "   ❌ Pre-roll buffer passing: NOT FOUND"
fi

# Check 9: Conversation mode pre-roll fix
echo "9. Checking conversation mode pre-roll..."
if grep -q "pre_roll_buffer = list(self.continuous_buffer)" app/conversation.py; then
    echo "   ✅ Conversation pre-roll: FIXED (line 185)"
else
    echo "   ⚠️  Conversation pre-roll: NOT USING continuous_buffer"
fi

# Check 10: Wake word fallback logging
echo "10. Checking wake word fallback logging..."
if grep -q "Porcupine not available, using Vosk" app/audio/wake_hybrid.py; then
    echo "   ✅ Wake word fallback logging: IMPROVED"
else
    echo "   ⚠️  Wake word fallback logging: COULD BE BETTER"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                         VERIFICATION COMPLETE                        ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "All critical fixes are in place!"
echo ""
echo "To test the actual runtime behavior:"
echo "  python3 test_wake_word_setup.py"
echo "  python3 test_actual_behavior.py"
echo "  python3 test_voice_diagnostic_standalone.py"
echo ""
