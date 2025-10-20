from __future__ import annotations

import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import List

import threading

from app.audio.mic import MicrophoneStream
from app.audio.stt import StreamingTranscriber
from app.audio.vad import SilenceTracker, VoiceActivityDetector
from app.util.config import AppConfig
from app.util.fileio import create_temp_segment_dir, encode_image_to_base64
from app.video.capture import VideoCapture
from app.video.writer import VideoSegmentWriter, sample_video_frames


@dataclass
class SegmentResult:
    transcript: str
    clean_transcript: str
    video_path: Path
    audio_path: Path
    frames_base64: List[str]


class SegmentRecorder:
    """Coordinate audio and video capture into a synchronized segment."""

    def __init__(self, config: AppConfig, transcriber: StreamingTranscriber) -> None:
        self.config = config
        self.transcriber = transcriber
        self.sample_rate = 16000
        self.frame_ms = 30
        self._vad = VoiceActivityDetector(sample_rate=self.sample_rate, frame_duration_ms=self.frame_ms)
        self._stop_event = threading.Event()

    def record_segment(self) -> SegmentResult:
        temp_dir = create_temp_segment_dir()
        video_path = Path(temp_dir) / "segment.mp4"
        audio_path = Path(temp_dir) / "audio.wav"

        self.transcriber.reset()
        self._stop_event.clear()

        silence_tracker = SilenceTracker(silence_ms=self.config.silence_ms, frame_ms=self.frame_ms)

        with MicrophoneStream(rate=self.sample_rate, frame_duration_ms=self.frame_ms) as mic, VideoCapture(
            source=self.config.camera_source, width=self.config.video_width_px
        ) as camera:
            has_spoken = False
            audio_frames: List[bytes] = []

            # Prime the camera to get initial frame size.
            ret, frame = camera.read()
            if not ret:
                raise RuntimeError("Failed to read initial frame from camera source")
            frame_height, frame_width = frame.shape[:2]

            fps = camera.fps()
            with VideoSegmentWriter(video_path, fps=fps, frame_size=(frame_width, frame_height)) as writer:
                writer.write(frame)

                start_time = time.monotonic()
                max_duration_s = self.config.max_segment_s

                while True:
                    if self._stop_event.is_set():
                        break
                    if time.monotonic() - start_time > max_duration_s:
                        break

                    audio_chunk = mic.read()
                    audio_frames.append(audio_chunk)

                    stt_result = self.transcriber.accept_audio(audio_chunk)
                    combined_text = (self.transcriber.transcript + " " + stt_result.text).strip()

                    speech_detected = self._vad.is_speech(audio_chunk)
                    if speech_detected:
                        has_spoken = True

                    if has_spoken:
                        if _contains_done(combined_text):
                            break
                        if silence_tracker.update(speech_detected):
                            break
                    else:
                        silence_tracker.reset()

                    ret, frame = camera.read()
                    if not ret:
                        break
                    writer.write(frame)

            self._write_wav(audio_path, audio_frames)

        final_transcript = self.transcriber.finalize()
        clean_transcript = _strip_done_words(final_transcript)
        frames = sample_video_frames(
            video_path,
            sample_fps=self.config.frame_sample_fps,
            max_images=self.config.frame_max_images,
            max_width=self.config.video_width_px,
        )
        frames_b64 = [encode_image_to_base64(f) for f in frames]

        return SegmentResult(
            transcript=final_transcript,
            clean_transcript=clean_transcript,
            video_path=video_path,
            audio_path=audio_path,
            frames_base64=frames_b64,
        )

    def _write_wav(self, path: Path, frames: List[bytes]) -> None:
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit PCM
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(b"".join(frames))

    def request_stop(self) -> None:
        self._stop_event.set()


def _contains_done(text: str) -> bool:
    tokens = [tok.lower() for tok in text.split()]
    return "done" in tokens


def _strip_done_words(text: str) -> str:
    tokens = [tok for tok in text.split() if tok.lower() != "done"]
    return " ".join(tokens).strip()
