from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.util.fileio import ensure_dir


@dataclass
class TurnArtifactPaths:
    root: Path
    mic_raw: Path
    video: Path
    partial_log: Path
    final_txt: Path
    model_input_json: Path
    model_output_txt: Path
    model_output_json: Path
    timeline_txt: Path
    timeline_json: Path
    meta_json: Path


class SessionArtifactWriter:
    """Persist per-turn artifacts under ``~/GlassesSessions/<session_id>/``."""

    def __init__(self, session_id: str, session_root: Path) -> None:
        self.session_id = session_id
        self.session_dir = ensure_dir(session_root / session_id)

    def _turn_paths(self, turn_index: int) -> TurnArtifactPaths:
        turn_dir = ensure_dir(self.session_dir / f"{turn_index:02d}")
        return TurnArtifactPaths(
            root=turn_dir,
            mic_raw=turn_dir / "mic_raw.wav",
            video=turn_dir / "segment.mp4",
            partial_log=turn_dir / "stt_partial.log",
            final_txt=turn_dir / "stt_final.txt",
            model_input_json=turn_dir / "model_input.json",
            model_output_txt=turn_dir / "model_output.txt",
            model_output_json=turn_dir / "model_output_raw.json",
            timeline_txt=turn_dir / "timeline.txt",
            timeline_json=turn_dir / "timeline.json",
            meta_json=turn_dir / "turn_meta.json",
        )

    def persist_turn(
        self,
        turn_index: int,
        *,
        audio_path: Path,
        video_path: Optional[Path],
        partial_events: List[Dict[str, Any]],
        final_event: Optional[Dict[str, Any]],
        final_text: str,
        model_input: Dict[str, Any],
        model_output_text: str,
        model_output_raw: Optional[Dict[str, Any]],
        timeline_lines: List[str],
        timeline_events: List[Dict[str, Any]],
        stop_reason: str,
        duration_ms: int,
        audio_ms: int,
        extra_meta: Optional[Dict[str, Any]] = None,
    ) -> TurnArtifactPaths:
        paths = self._turn_paths(turn_index)

        if audio_path.exists():
            shutil.copy2(audio_path, paths.mic_raw)
        if video_path and video_path.exists():
            shutil.copy2(video_path, paths.video)

        events_for_log = list(partial_events)
        if final_event:
            events_for_log.append(
                {
                    "ts_ms": final_event.get("ts_ms") or final_event.get("ts"),
                    "text": final_event.get("text", ""),
                    "type": "final",
                }
            )

        with paths.partial_log.open("w", encoding="utf-8") as handle:
            if not events_for_log:
                handle.write("\n")
            else:
                for event in events_for_log:
                    ts = event.get("ts_ms") or event.get("ts")
                    text = event.get("text", "")
                    label = event.get("type", "partial")
                    handle.write(f"{ts}: [{label}] {text}\n")

        paths.final_txt.write_text(final_text or "", encoding="utf-8")

        paths.model_input_json.write_text(json.dumps(model_input, indent=2, ensure_ascii=True), encoding="utf-8")
        paths.model_output_txt.write_text(model_output_text or "", encoding="utf-8")
        if model_output_raw is not None:
            paths.model_output_json.write_text(json.dumps(model_output_raw, indent=2, ensure_ascii=True), encoding="utf-8")

        paths.timeline_txt.write_text("\n".join(timeline_lines), encoding="utf-8")
        paths.timeline_json.write_text(json.dumps(timeline_events, indent=2, ensure_ascii=True), encoding="utf-8")

        meta = {
            "turn_index": turn_index,
            "stop_reason": stop_reason,
            "duration_ms": duration_ms,
            "audio_ms": audio_ms,
        }
        if extra_meta:
            meta.update(extra_meta)
        paths.meta_json.write_text(json.dumps(meta, indent=2, ensure_ascii=True), encoding="utf-8")

        return paths

    def session_directory(self) -> Path:
        return self.session_dir
