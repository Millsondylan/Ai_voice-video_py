from __future__ import annotations

import math
from pathlib import Path
from typing import List

import cv2
import numpy as np


class VideoSegmentWriter:
    """Simple MP4 writer around OpenCV."""

    def __init__(self, target_path: Path, fps: float, frame_size: tuple[int, int]) -> None:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(str(target_path), fourcc, fps, frame_size)
        if not self._writer.isOpened():
            raise RuntimeError(f"Failed to open video writer for {target_path}")

    def write(self, frame) -> None:
        self._writer.write(frame)

    def close(self) -> None:
        self._writer.release()

    def __enter__(self) -> "VideoSegmentWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def sample_video_frames(
    video_path: Path,
    sample_fps: float,
    max_images: int,
    max_width: int,
) -> List[np.ndarray]:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open video for sampling: {video_path}")

    native_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    frame_interval = max(int(native_fps / sample_fps), 1)

    frames: List[np.ndarray] = []
    frame_index = 0

    success, frame = capture.read()
    while success and len(frames) < max_images:
        if frame_index % frame_interval == 0:
            frame = _downscale_frame(frame, max_width)
            frames.append(frame)
        frame_index += 1
        success, frame = capture.read()

    capture.release()
    return frames


def _downscale_frame(frame: np.ndarray, max_width: int) -> np.ndarray:
    height, width = frame.shape[:2]
    if width <= max_width:
        return frame
    scale = max_width / float(width)
    new_size = (int(width * scale), int(height * scale))
    return cv2.resize(frame, new_size)
