from __future__ import annotations

from typing import Optional, Union

import cv2


class VideoCapture:
    """Wrapper over OpenCV VideoCapture supporting USB and RTSP sources."""

    def __init__(self, source: Union[int, str] = 0, width: Optional[int] = None) -> None:
        if isinstance(source, str) and source.isdigit():
            self.source: Union[int, str] = int(source)
        else:
            self.source = source
        self.width = width
        self._capture: Optional[cv2.VideoCapture] = None

    def start(self) -> None:
        if self._capture:
            return
        self._capture = cv2.VideoCapture(self.source)
        if not self._capture.isOpened():
            raise RuntimeError(f"Failed to open video source: {self.source}")
        if self.width:
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)

    def read(self):
        if not self._capture:
            raise RuntimeError("VideoCapture not started")
        return self._capture.read()

    def fps(self) -> float:
        if not self._capture:
            raise RuntimeError("VideoCapture not started")
        fps_val = self._capture.get(cv2.CAP_PROP_FPS)
        if not fps_val or fps_val != fps_val:  # handle NaN / zero
            fps_val = 30.0
        return fps_val

    def release(self) -> None:
        if self._capture:
            self._capture.release()
            self._capture = None

    def __enter__(self) -> "VideoCapture":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

