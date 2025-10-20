"""
Unit tests for video utilities (app/video/utils.py)

Tests frame processing functions including center cropping, resizing,
JPEG encoding, and the full processing pipeline.
"""

import base64
import pytest
import numpy as np
import cv2

from app.video.utils import (
    center_crop,
    resize_frame,
    frame_to_jpeg_b64,
    sample_frames,
    process_frames_for_vision,
)


class TestCenterCrop:
    """Test suite for center_crop() function"""

    def test_center_crop_basic(self):
        # Create a 100x100 frame
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        # Crop to 50% (50x50)
        cropped = center_crop(frame, ratio=0.5)
        assert cropped.shape[0] == 50  # height
        assert cropped.shape[1] == 50  # width
        assert cropped.shape[2] == 3   # channels

    def test_center_crop_38_percent(self):
        # Test the default 38% crop ratio
        frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
        cropped = center_crop(frame, ratio=0.38)
        assert cropped.shape[0] == 380  # 38% of 1000
        assert cropped.shape[1] == 380

    def test_center_crop_rectangular(self):
        # Test with non-square frame
        frame = np.zeros((200, 400, 3), dtype=np.uint8)
        cropped = center_crop(frame, ratio=0.5)
        assert cropped.shape[0] == 100  # 50% of 200
        assert cropped.shape[1] == 200  # 50% of 400

    def test_center_crop_preserves_center(self):
        # Mark the center pixel with white
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[50, 50] = [255, 255, 255]  # White center pixel

        cropped = center_crop(frame, ratio=0.5)
        # Center of original should be at center of crop
        center_y, center_x = cropped.shape[0] // 2, cropped.shape[1] // 2
        assert np.array_equal(cropped[center_y, center_x], [255, 255, 255])

    def test_center_crop_invalid_ratio_zero(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(ValueError):
            center_crop(frame, ratio=0.0)

    def test_center_crop_invalid_ratio_one(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(ValueError):
            center_crop(frame, ratio=1.0)

    def test_center_crop_invalid_ratio_negative(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(ValueError):
            center_crop(frame, ratio=-0.5)

    def test_center_crop_invalid_ratio_over_one(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        with pytest.raises(ValueError):
            center_crop(frame, ratio=1.5)


class TestResizeFrame:
    """Test suite for resize_frame() function"""

    def test_resize_frame_basic(self):
        # Create a 1000x1000 frame
        frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
        resized = resize_frame(frame, max_width=500)
        assert resized.shape[1] == 500  # width
        assert resized.shape[0] == 500  # height (maintains aspect ratio)

    def test_resize_frame_maintains_aspect_ratio(self):
        # Create a 1000x500 frame (2:1 aspect ratio)
        frame = np.zeros((500, 1000, 3), dtype=np.uint8)
        resized = resize_frame(frame, max_width=400)
        assert resized.shape[1] == 400  # width
        assert resized.shape[0] == 200  # height (maintains 2:1 ratio)

    def test_resize_frame_no_resize_needed(self):
        # Frame already smaller than max_width
        frame = np.zeros((100, 200, 3), dtype=np.uint8)
        resized = resize_frame(frame, max_width=500)
        assert resized.shape == frame.shape  # unchanged

    def test_resize_frame_exact_width(self):
        # Frame exactly at max_width
        frame = np.zeros((100, 500, 3), dtype=np.uint8)
        resized = resize_frame(frame, max_width=500)
        assert resized.shape == frame.shape  # unchanged

    def test_resize_frame_preserves_channels(self):
        frame = np.zeros((1000, 1000, 3), dtype=np.uint8)
        resized = resize_frame(frame, max_width=500)
        assert resized.shape[2] == 3  # RGB channels preserved


class TestFrameToJpegB64:
    """Test suite for frame_to_jpeg_b64() function"""

    def test_frame_to_jpeg_b64_basic(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        b64_str = frame_to_jpeg_b64(frame, quality=85)
        assert isinstance(b64_str, str)
        assert len(b64_str) > 0

    def test_frame_to_jpeg_b64_is_valid_base64(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        b64_str = frame_to_jpeg_b64(frame, quality=85)
        # Should be able to decode
        decoded = base64.b64decode(b64_str)
        assert len(decoded) > 0

    def test_frame_to_jpeg_b64_is_valid_jpeg(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        b64_str = frame_to_jpeg_b64(frame, quality=85)
        # Decode base64 and check if it's a valid JPEG
        jpg_bytes = base64.b64decode(b64_str)
        # Try to decode as image
        np_buffer = np.frombuffer(jpg_bytes, dtype=np.uint8)
        img = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
        assert img is not None
        assert img.shape == (100, 100, 3)

    def test_frame_to_jpeg_b64_quality_affects_size(self):
        # Create a more complex frame (not all black)
        frame = np.random.randint(0, 256, (500, 500, 3), dtype=np.uint8)

        low_quality = frame_to_jpeg_b64(frame, quality=10)
        high_quality = frame_to_jpeg_b64(frame, quality=95)

        # Lower quality should produce smaller encoded size
        assert len(low_quality) < len(high_quality)

    def test_frame_to_jpeg_b64_colored_frame(self):
        # Create a red frame
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        frame[:, :] = [0, 0, 255]  # BGR format - red

        b64_str = frame_to_jpeg_b64(frame, quality=85)
        # Decode and verify color is preserved (roughly)
        jpg_bytes = base64.b64decode(b64_str)
        np_buffer = np.frombuffer(jpg_bytes, dtype=np.uint8)
        img = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)

        # Check that the image is predominantly red (allow for JPEG compression)
        assert img[:, :, 2].mean() > 200  # R channel


class TestSampleFrames:
    """Test suite for sample_frames() function"""

    def test_sample_frames_basic(self):
        frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(10)]
        sampled = sample_frames(frames, max_count=5, interval=1)
        assert len(sampled) == 5

    def test_sample_frames_with_interval(self):
        frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(10)]
        sampled = sample_frames(frames, max_count=10, interval=2)
        assert len(sampled) == 5  # Every 2nd frame

    def test_sample_frames_fewer_than_max(self):
        frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(3)]
        sampled = sample_frames(frames, max_count=10, interval=1)
        assert len(sampled) == 3  # All frames returned

    def test_sample_frames_empty_list(self):
        sampled = sample_frames([], max_count=5, interval=1)
        assert len(sampled) == 0

    def test_sample_frames_max_count_zero(self):
        frames = [np.zeros((100, 100, 3), dtype=np.uint8) for _ in range(10)]
        sampled = sample_frames(frames, max_count=0, interval=1)
        assert len(sampled) == 0


class TestProcessFramesForVision:
    """Test suite for process_frames_for_vision() function"""

    def test_process_frames_basic(self):
        # Create 10 frames
        frames = [np.zeros((1000, 1000, 3), dtype=np.uint8) for _ in range(10)]
        processed = process_frames_for_vision(
            frames,
            max_count=6,
            crop_ratio=0.38,
            max_width=960,
            jpeg_quality=85,
        )
        assert len(processed) == 6
        assert all(isinstance(frame, str) for frame in processed)

    def test_process_frames_fewer_than_max(self):
        frames = [np.zeros((1000, 1000, 3), dtype=np.uint8) for _ in range(3)]
        processed = process_frames_for_vision(frames, max_count=6)
        assert len(processed) == 3

    def test_process_frames_empty_list(self):
        processed = process_frames_for_vision([])
        assert len(processed) == 0

    def test_process_frames_applies_crop(self):
        # Create large frames
        frames = [np.zeros((1000, 1000, 3), dtype=np.uint8) for _ in range(2)]
        processed = process_frames_for_vision(
            frames,
            max_count=2,
            crop_ratio=0.5,  # 50% crop
            max_width=2000,   # No resize needed
            jpeg_quality=85,
        )

        # Decode first frame and check size
        jpg_bytes = base64.b64decode(processed[0])
        np_buffer = np.frombuffer(jpg_bytes, dtype=np.uint8)
        img = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)

        # Should be cropped to 500x500 (50% of 1000x1000)
        assert img.shape[0] == 500
        assert img.shape[1] == 500

    def test_process_frames_applies_resize(self):
        # Create large frames
        frames = [np.zeros((2000, 2000, 3), dtype=np.uint8) for _ in range(2)]
        processed = process_frames_for_vision(
            frames,
            max_count=2,
            crop_ratio=0.5,   # Crop to 1000x1000
            max_width=500,    # Then resize to 500x500
            jpeg_quality=85,
        )

        # Decode and check final size
        jpg_bytes = base64.b64decode(processed[0])
        np_buffer = np.frombuffer(jpg_bytes, dtype=np.uint8)
        img = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)

        # Should be resized to 500x500
        assert img.shape[0] == 500
        assert img.shape[1] == 500

    def test_process_frames_default_params(self):
        frames = [np.zeros((1000, 1000, 3), dtype=np.uint8) for _ in range(10)]
        processed = process_frames_for_vision(frames)
        # Should use defaults: max_count=6, crop_ratio=0.38, max_width=960
        assert len(processed) == 6

    def test_process_frames_full_pipeline(self):
        # Create diverse frames
        frames = []
        for i in range(12):
            frame = np.random.randint(0, 256, (1920, 1080, 3), dtype=np.uint8)
            frames.append(frame)

        processed = process_frames_for_vision(
            frames,
            max_count=6,
            crop_ratio=0.38,
            max_width=960,
            jpeg_quality=85,
        )

        assert len(processed) == 6
        # Verify all are valid base64 JPEG strings
        for b64_str in processed:
            jpg_bytes = base64.b64decode(b64_str)
            np_buffer = np.frombuffer(jpg_bytes, dtype=np.uint8)
            img = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
            assert img is not None
            # Width should be <= 960 after processing
            assert img.shape[1] <= 960
