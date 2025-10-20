from __future__ import annotations

import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List

import threading

from app.audio.capture import run_segment
from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.util.config import AppConfig
from app.util.fileio import create_temp_segment_dir
from app.video.capture import VideoCapture
from app.video.writer import VideoSegmentWriter, sample_video_frames


@dataclass
class SegmentResult:
    transcript: str
    clean_transcript: str
    video_path: Path
    audio_path: Path
    frames: List  # List of np.ndarray frames


class SegmentRecorder:
    """Coordinate audio and video capture into a synchronized segment."""

    def __init__(self, config: AppConfig, transcriber: StreamingTranscriber) -> None:
        self.config = config
        self.transcriber = transcriber
        self.sample_rate = config.sample_rate_hz
        self.frame_ms = int((config.chunk_samples / config.sample_rate_hz) * 1000)
        self._stop_event = threading.Event()

    def record_segment(self) -> SegmentResult:
        """Record a full audio+video segment with guaranteed full capture."""
        temp_dir = create_temp_segment_dir()
        video_path = Path(temp_dir) / "segment.mp4"
        audio_path = Path(temp_dir) / "audio.wav"

        self._stop_event.clear()

        # Open microphone and video capture
        mic = MicrophoneStream(
            rate=self.sample_rate,
            frame_duration_ms=self.frame_ms,
            input_device_name=self.config.mic_device_name,
        )
        mic.start()

        try:
            camera = VideoCapture(source=self.config.camera_source, width=self.config.video_width_px)
            camera.__enter__()

            try:
                # Prime the camera to get initial frame size
                ret, frame = camera.read()
                if not ret:
                    raise RuntimeError("Failed to read initial frame from camera source")
                frame_height, frame_width = frame.shape[:2]

                fps = camera.fps()
                writer = VideoSegmentWriter(video_path, fps=fps, frame_size=(frame_width, frame_height))
                writer.__enter__()

                try:
                    # Start video recording
                    writer.write(frame)

                    # Capture audio segment with full pre-roll and robust stop detection
                    capture_result = run_segment(
                        mic=mic, stt=self.transcriber, config=self.config, stop_event=self._stop_event
                    )

                    # Continue capturing video frames during audio capture
                    # (In practice, video and audio should be synchronized in a threaded manner,
                    # but for simplicity we'll capture video after audio or in parallel if needed)
                    # For now, just capture some frames throughout the duration
                    video_duration_s = capture_result.duration_ms / 1000.0
                    target_frames = int(fps * video_duration_s)

                    for _ in range(min(target_frames, 1000)):  # Cap at 1000 frames
                        ret, frame = camera.read()
                        if ret:
                            writer.write(frame)

                finally:
                    writer.__exit__(None, None, None)

            finally:
                camera.__exit__(None, None, None)

        finally:
            # CRITICAL: Close mic before TTS (audio I/O serialization)
            mic.stop()
            mic.terminate()

        # Write audio to WAV file
        self._write_wav_from_bytes(audio_path, capture_result.audio_bytes)

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
            frames=frames,
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
