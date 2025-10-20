from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import threading

from app.audio.capture import SegmentCaptureResult, run_segment
from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.util.config import AppConfig
from app.util.fileio import create_temp_segment_dir
from app.util.log import get_event_logger, logger as audio_logger
from app.video.capture import VideoCapture
from app.video.writer import VideoSegmentWriter, sample_video_frames


@dataclass
class SegmentResult:
    transcript: str
    clean_transcript: str
    video_path: Path
    audio_path: Path
    audio_bytes: bytes
    frames: List  # List of np.ndarray frames
    stop_reason: str
    duration_ms: int
    audio_ms: int
    partial_events: List[Dict[str, Any]]
    final_event: Optional[Dict[str, Any]]


class SegmentRecorder:
    """Coordinate audio and video capture into a synchronized segment."""

    def __init__(self, config: AppConfig, transcriber: StreamingTranscriber) -> None:
        self.config = config
        self.transcriber = transcriber
        self.sample_rate = config.sample_rate_hz
        self.frame_ms = int((config.chunk_samples / config.sample_rate_hz) * 1000)
        self._stop_event = threading.Event()

    def record_segment(
        self,
        *,
        pre_roll_buffer: Optional[Sequence[bytes]] = None,
        no_speech_timeout_ms: Optional[int] = None,
    ) -> SegmentResult:
        """Record a full audio+video segment with guaranteed full capture.

        Args:
            pre_roll_buffer: Optional list of PCM frames from wake word detection
            no_speech_timeout_ms: Optional timeout if no speech is detected
        """
        temp_dir = create_temp_segment_dir()
        video_path = Path(temp_dir) / "segment.mp4"
        audio_path = Path(temp_dir) / "audio.wav"

        self._stop_event.clear()
        get_event_logger().reset()

        # Open microphone and video capture
        with MicrophoneStream(
            rate=self.sample_rate,
            chunk_samples=self.config.chunk_samples,
            input_device_name=self.config.mic_device_name,
        ) as mic, VideoCapture(source=self.config.camera_source, width=self.config.video_width_px) as camera:
            ret, frame = camera.read()
            if not ret:
                raise RuntimeError("Failed to read initial frame from camera source")
            frame_height, frame_width = frame.shape[:2]

            fps = camera.fps()
            with VideoSegmentWriter(video_path, fps=fps, frame_size=(frame_width, frame_height)) as writer:
                writer.write(frame)

                def _capture_frame() -> None:
                    ok, next_frame = camera.read()
                    if ok:
                        writer.write(next_frame)

                capture_result: SegmentCaptureResult = run_segment(
                    mic=mic,
                    stt=self.transcriber,
                    config=self.config,
                    stop_event=self._stop_event,
                    on_chunk=_capture_frame,
                    pre_roll_buffer=pre_roll_buffer,
                    no_speech_timeout_ms=no_speech_timeout_ms,
                )

        # Write audio to WAV file
        self._write_wav_from_bytes(audio_path, capture_result.audio_bytes)
        audio_logger.info(
            "Captured audio bytes=%d stop_reason=%s duration_ms=%d",
            len(capture_result.audio_bytes),
            capture_result.stop_reason,
            capture_result.duration_ms,
        )

        # Sample raw frames - let routing logic decide whether to encode them
        frames = sample_video_frames(
            video_path,
            sample_fps=self.config.frame_sample_fps,
            max_images=self.config.frame_max_images,
            max_width=self.config.video_width_px,
        )

        return SegmentResult(
            transcript=capture_result.transcript,
            clean_transcript=capture_result.clean_transcript,
            video_path=video_path,
            audio_path=audio_path,
            audio_bytes=capture_result.audio_bytes,
            frames=frames,
            stop_reason=capture_result.stop_reason,
            duration_ms=capture_result.duration_ms,
            audio_ms=capture_result.audio_ms,
            partial_events=capture_result.partial_events,
            final_event=capture_result.final_event,
        )

    def _write_wav(self, path: Path, frames: List[bytes]) -> None:
        """Write WAV file from list of audio frames."""
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit PCM
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(b"".join(frames))

    def _write_wav_from_bytes(self, path: Path, audio_bytes: bytes) -> None:
        """Write WAV file from raw audio bytes."""
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit PCM
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_bytes)

    def request_stop(self) -> None:
        """Request the current recording to stop."""
        self._stop_event.set()
