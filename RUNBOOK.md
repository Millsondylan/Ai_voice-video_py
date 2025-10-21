# Diagnostic Runbook

## Overview

The diagnostic build captures every session with structured JSON logs and per-turn artifacts so regressions can be reproduced quickly.

- **Structured log file**: `~/GlassesSessions/<session_id>/events.jsonl`
  - Each line is JSON with `ts`, `event`, `session_id`, `session_state`, `turn_index`, and optional payload fields.
  - Key events: `wake.detected_at`, `segment.started_at`, `segment.stopped_at`, `stt.partial`, `stt.final_text`, `tts.text`, `tts.ms`, `session.state`, `session.turn`.
- **Per-turn artifacts** live in `~/GlassesSessions/<session_id>/<turn_index>/`:
  - `mic_raw.wav` – raw 16 kHz PCM fed to STT (includes 400 ms pre-roll + 200 ms drain).
  - `segment.mp4` – video recording when available.
  - `stt_partial.log` – timestamped partial transcripts plus `[final]` entry.
  - `stt_final.txt` – final cleaned transcript (with stop-words removed).
  - `model_input.json` – request payload (history + current user message + vision flags).
  - `model_output.txt` – final assistant reply text.
  - `model_output_raw.json` – full VLM response for replaying issues.
  - `timeline.txt` – human-readable event timeline with absolute timestamps.
  - `turn_meta.json` – stop reason, durations, extra flags (`goodbye`, etc.).

## Running a Diagnostic Session

1. Ensure the Vosk model path in `config.json` is correct.
2. From the repo root, launch the UI with:
   ```bash
   python3 app/main.py --config config.json
   ```
   (Use `python3 run_with_debug.py` for maximal stdout tracing.)
3. Speak the wake phrase (“hey glasses”) or press `Ctrl+G` to start.
4. The timeline bar shows `Wake → Recording → Thinking → Speaking → Await 15s`. The session remains active until no speech for 15 s or “bye glasses” is heard.
5. Session data is written to `~/GlassesSessions/<session_id>/` immediately after each turn.

## Verification Checklist

1. **Full capture** – Record a 10‑12 s sentence with a 1 s pause mid-way. Confirm the final transcript (in `stt_final.txt`) contains every word and the segment stop log shows `stop_reason = silence` about 1.3 s after the final word.
2. **Follow-up window** – After the assistant reply finishes, wait ~10 s, speak another question, and ensure a new turn is appended under the same session ID. Timeline should show `AwaitFollowup → Recording` without returning to `Idle`.
3. **Exit detection** – Say “bye glasses”. Verify the session ends immediately with `stop_reason = bye` and no further recordings occur.
4. **No stray “test(s)”** – Review `model_output.txt` files; the assistant should only speak user-relevant content. Check that `stt_partial.log` shows expected text and that TTS entries in `events.jsonl` mirror the spoken responses.
5. **Logging sanity** – Inspect `events.jsonl` to ensure each turn has a `segment.started_at` → `segment.stopped_at` pair, partials, final text, and corresponding `tts.ms` duration.

## Troubleshooting

- Missing first syllables? Increase `pre_roll_ms` (e.g., 500) in `config.json` and restart.
- Mid-sentence truncation? Raise `silence_ms` to 1500–1700 or lower VAD aggressiveness to 1.
- Echo or self-triggering? Ensure speakers are not too loud; the controller mutes recording during TTS and waits 300 ms before resuming.
- Wake latency too high? Confirm the mic device selection in `config.json` is correct and background noise is minimal.

For deep dives, pair `events.jsonl` with `timeline.json` to reconstruct the session precisely and, if needed, replay `mic_raw.wav` through the STT stack.
