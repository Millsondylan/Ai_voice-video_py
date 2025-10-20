"""
Save diagnostic artifacts per turn for debugging and analysis.

Structure:
~/GlassesSessions/<session_id>/
    turn_0/
        mic_raw.wav       # Raw audio fed to STT
        segment.mp4       # Video recording
        stt_partial.log   # STT partial results with timestamps
        stt_final.txt     # Final STT transcription
        model_input.json  # Input to VLM
        model_output.txt  # Response from VLM
        timeline.txt      # Human-readable event timeline
    turn_1/
        ...
    session_log.jsonl     # All structured log events
    session_summary.txt   # Human-readable summary
"""
from __future__ import annotations

import json
import shutil
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.util.log import now_ms


class TurnArtifacts:
    """Manages artifacts for a single turn."""

    def __init__(self, artifacts_dir: Path, turn_index: int):
        self.turn_dir = artifacts_dir / f"turn_{turn_index}"
        self.turn_dir.mkdir(parents=True, exist_ok=True)
        self.turn_index = turn_index
        self.timeline_events: List[str] = []

    def save_raw_audio(self, audio_bytes: bytes, sample_rate: int = 16000):
        """Save raw PCM audio as WAV."""
        wav_path = self.turn_dir / "mic_raw.wav"
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit PCM
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_bytes)
        self._add_timeline(f"Saved raw audio: {len(audio_bytes)} bytes")

    def save_video(self, video_path: Path):
        """Copy video segment to turn directory."""
        if video_path and video_path.exists():
            dest = self.turn_dir / "segment.mp4"
            shutil.copy2(video_path, dest)
            self._add_timeline(f"Saved video: {video_path.name}")

    def append_stt_partial(self, partial_text: str, elapsed_ms: int):
        """Append STT partial result."""
        log_path = self.turn_dir / "stt_partial.log"
        with open(log_path, "a") as f:
            f.write(f"[{elapsed_ms}ms] {partial_text}\n")

    def save_stt_final(self, final_text: str):
        """Save final STT transcription."""
        txt_path = self.turn_dir / "stt_final.txt"
        txt_path.write_text(final_text, encoding="utf-8")
        self._add_timeline(f"STT final: {len(final_text)} chars")

    def save_model_input(self, model_input: Dict[str, Any]):
        """Save VLM input as JSON."""
        json_path = self.turn_dir / "model_input.json"
        with open(json_path, "w") as f:
            json.dump(model_input, f, indent=2)
        self._add_timeline(f"Model input saved")

    def save_model_output(self, model_output: str):
        """Save VLM response."""
        txt_path = self.turn_dir / "model_output.txt"
        txt_path.write_text(model_output, encoding="utf-8")
        self._add_timeline(f"Model output: {len(model_output)} chars")

    def save_timeline(self):
        """Save timeline of events."""
        timeline_path = self.turn_dir / "timeline.txt"
        with open(timeline_path, "w") as f:
            f.write(f"Turn {self.turn_index} Timeline\n")
            f.write("=" * 60 + "\n\n")
            for event in self.timeline_events:
                f.write(f"{event}\n")

    def add_timeline_event(self, event: str):
        """Record a custom timeline event."""
        self._add_timeline(event)

    def _add_timeline(self, event: str):
        """Add event to timeline."""
        timestamp_ms = now_ms()
        self.timeline_events.append(f"[{timestamp_ms}ms] {event}")


class SessionArtifacts:
    """Manages artifacts for an entire session."""

    def __init__(self, session_id: str, base_dir: Optional[Path] = None):
        if base_dir is None:
            base_dir = Path.home() / "GlassesSessions"

        self.session_dir = base_dir / session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id
        self.log_file = self.session_dir / "session_log.jsonl"

    def get_turn_artifacts(self, turn_index: int) -> TurnArtifacts:
        """Get or create artifacts handler for a turn."""
        return TurnArtifacts(self.session_dir, turn_index)

    def append_log_event(self, log_entry: Dict[str, Any]):
        """Append structured log entry to session log."""
        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")

    def save_session_summary(self, summary: str):
        """Save human-readable session summary."""
        summary_path = self.session_dir / "session_summary.txt"
        summary_path.write_text(summary, encoding="utf-8")

    def get_session_dir(self) -> Path:
        """Get session directory path."""
        return self.session_dir


def create_session_artifacts(session_id: str, base_dir: Optional[Path] = None) -> SessionArtifacts:
    """Create artifacts manager for a session."""
    return SessionArtifacts(session_id, base_dir)


def generate_session_summary(session_id: str, turns: List[Any], duration_s: float, end_reason: str) -> str:
    """Generate human-readable session summary."""
    lines = [
        f"Session: {session_id}",
        f"Duration: {duration_s:.1f}s",
        f"Turns: {len(turns)}",
        f"End reason: {end_reason}",
        "",
        "=" * 60,
        "",
    ]

    for turn in turns:
        lines.append(f"Turn {turn.index}:")
        lines.append(f"  User: {turn.user_text}")
        lines.append(f"  Assistant: {turn.assistant_text}")
        if turn.stop_reason:
            lines.append(f"  Stop reason: {turn.stop_reason}")
        if turn.duration_ms:
            lines.append(f"  Duration: {turn.duration_ms}ms")
        lines.append("")

    return "\n".join(lines)
