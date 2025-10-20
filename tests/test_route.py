"""
Integration tests for routing logic (app/route.py)

Tests the route_and_respond() function with mocked VLM client to ensure
correct intent-based routing and frame processing.
"""

import pytest
import numpy as np
from unittest.mock import Mock, MagicMock

from app.route import route_and_respond
from app.util.config import AppConfig


class TestRouteAndRespond:
    """Test suite for route_and_respond() integration"""

    def setup_method(self):
        """Set up test fixtures"""
        self.config = AppConfig(
            frame_max_images=6,
            video_width_px=960,
            center_crop_ratio=0.38,
        )

        # Mock VLM client
        self.mock_vlm_client = Mock()

        # Create sample frames (1920x1080, 10 frames)
        self.sample_frames = [
            np.random.randint(0, 256, (1080, 1920, 3), dtype=np.uint8)
            for _ in range(10)
        ]

    # --- Greeting/Chat Tests (No Vision) ---

    def test_greeting_no_images_sent(self):
        """Test that greetings don't send images"""
        # Mock VLM response
        self.mock_vlm_client.infer.return_value = {
            "text": "Hello! How can I help you?",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="hi there",
            segment_frames=self.sample_frames,
        )

        # Verify VLM was called with empty image list
        self.mock_vlm_client.infer.assert_called_once()
        call_args = self.mock_vlm_client.infer.call_args
        transcript_arg = call_args[0][0]
        images_arg = call_args[0][1]

        assert transcript_arg == "hi there"
        assert images_arg == []  # No images sent
        assert result["vision_used"] is False
        assert result["image_count"] == 0

    def test_how_are_you_no_images(self):
        """Test small talk doesn't trigger vision"""
        self.mock_vlm_client.infer.return_value = {
            "text": "I'm doing well, thank you!",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="how are you",
            segment_frames=self.sample_frames,
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]
        assert images_arg == []
        assert result["vision_used"] is False

    def test_general_knowledge_no_images(self):
        """Test general knowledge questions don't use vision"""
        self.mock_vlm_client.infer.return_value = {
            "text": "The capital of France is Paris.",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="what's the capital of France",
            segment_frames=self.sample_frames,
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]
        assert images_arg == []
        assert result["vision_used"] is False

    # --- Deictic/Vision Tests (With Images) ---

    def test_what_is_this_sends_images(self):
        """Test deictic query sends images"""
        self.mock_vlm_client.infer.return_value = {
            "text": "That's a coffee mug.",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="what is this",
            segment_frames=self.sample_frames,
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]

        # Should send images (max 6)
        assert len(images_arg) > 0
        assert len(images_arg) <= 6
        # Images should be base64 strings
        assert all(isinstance(img, str) for img in images_arg)
        assert result["vision_used"] is True
        assert result["image_count"] == len(images_arg)

    def test_look_at_sends_images(self):
        """Test 'look at' query sends images"""
        self.mock_vlm_client.infer.return_value = {
            "text": "I see a laptop on the desk.",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="look at this object",
            segment_frames=self.sample_frames,
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]
        assert len(images_arg) > 0
        assert result["vision_used"] is True

    def test_where_is_sends_images(self):
        """Test spatial queries send images"""
        self.mock_vlm_client.infer.return_value = {
            "text": "The remote is on the coffee table.",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="where is the remote",
            segment_frames=self.sample_frames,
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]
        assert len(images_arg) > 0
        assert result["vision_used"] is True

    # --- OCR/Reading Tests (With Images) ---

    def test_read_this_sends_images(self):
        """Test OCR query sends images"""
        self.mock_vlm_client.infer.return_value = {
            "text": "$19.99",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="read this price tag",
            segment_frames=self.sample_frames,
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]
        assert len(images_arg) > 0
        assert result["vision_used"] is True

    def test_text_on_label_sends_images(self):
        """Test label reading sends images"""
        self.mock_vlm_client.infer.return_value = {
            "text": "Organic Milk, Expires 12/25",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="what's the text on this label",
            segment_frames=self.sample_frames,
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]
        assert len(images_arg) > 0
        assert result["vision_used"] is True

    # --- Scene Preface Stripping ---

    def test_strip_scene_preface_when_no_vision(self):
        """Test that scene prefixes are stripped when no images sent"""
        self.mock_vlm_client.infer.return_value = {
            "text": "I see you're asking about greetings.",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="hello",
            segment_frames=self.sample_frames,
        )

        # Should have stripped "I see"
        assert not result["text"].startswith("I see")
        assert "you're asking" in result["text"].lower()
        assert result["vision_used"] is False

    def test_preserve_scene_reference_when_vision_used(self):
        """Test that scene references are preserved when images are sent"""
        self.mock_vlm_client.infer.return_value = {
            "text": "I see a laptop on the desk.",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="what is this",
            segment_frames=self.sample_frames,
        )

        # Should NOT strip "I see" because vision was used
        assert result["text"] == "I see a laptop on the desk."
        assert result["vision_used"] is True

    # --- Frame Processing Tests ---

    def test_max_images_respected(self):
        """Test that max_images config is respected"""
        self.mock_vlm_client.infer.return_value = {
            "text": "Multiple objects visible.",
            "payload": {},
            "response": {},
        }

        # Create many frames (more than max)
        many_frames = [
            np.random.randint(0, 256, (1080, 1920, 3), dtype=np.uint8)
            for _ in range(20)
        ]

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="what is this",
            segment_frames=many_frames,
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]

        # Should not exceed max_images (6)
        assert len(images_arg) <= 6

    def test_empty_frames_no_images(self):
        """Test handling of empty frame list"""
        self.mock_vlm_client.infer.return_value = {
            "text": "Can you show me something?",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="what is this",
            segment_frames=[],  # No frames
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]

        # Even though intent wants vision, no frames available
        assert images_arg == []
        assert result["image_count"] == 0

    def test_fewer_frames_than_max(self):
        """Test with fewer frames than max_images"""
        self.mock_vlm_client.infer.return_value = {
            "text": "A small set of frames.",
            "payload": {},
            "response": {},
        }

        few_frames = [
            np.random.randint(0, 256, (1080, 1920, 3), dtype=np.uint8)
            for _ in range(3)
        ]

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="what is this",
            segment_frames=few_frames,
        )

        call_args = self.mock_vlm_client.infer.call_args
        images_arg = call_args[0][1]

        # Should send all 3 frames
        assert len(images_arg) == 3
        assert result["image_count"] == 3

    # --- Metadata Tests ---

    def test_metadata_vision_used_true(self):
        """Test vision_used metadata is correct"""
        self.mock_vlm_client.infer.return_value = {
            "text": "That's a book.",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="what is that",
            segment_frames=self.sample_frames,
        )

        assert "vision_used" in result
        assert result["vision_used"] is True
        assert "image_count" in result
        assert result["image_count"] > 0

    def test_metadata_vision_used_false(self):
        """Test vision_used metadata for chat queries"""
        self.mock_vlm_client.infer.return_value = {
            "text": "Hello!",
            "payload": {},
            "response": {},
        }

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="hi",
            segment_frames=self.sample_frames,
        )

        assert "vision_used" in result
        assert result["vision_used"] is False
        assert "image_count" in result
        assert result["image_count"] == 0

    # --- Response Passthrough Tests ---

    def test_response_passthrough(self):
        """Test that VLM response is passed through correctly"""
        mock_response = {
            "text": "Test response",
            "payload": {"model": "test-model"},
            "response": {"choices": []},
        }
        self.mock_vlm_client.infer.return_value = mock_response

        result = route_and_respond(
            config=self.config,
            vlm_client=self.mock_vlm_client,
            transcript="hello",
            segment_frames=self.sample_frames,
        )

        assert result["text"] == "Test response"
        assert result["payload"] == {"model": "test-model"}
        assert "response" in result
