"""
Unit tests for text utilities (app/util/text.py)

Tests the strip_scene_preface() function to ensure it correctly removes
accidental scene-related prefixes from VLM responses when no images were sent.
"""

import pytest
from app.util.text import strip_scene_preface


class TestStripScenePreface:
    """Test suite for strip_scene_preface() function"""

    # --- Basic Preface Removal Tests ---

    def test_strip_i_see(self):
        text = "I see a red car in the parking lot."
        result = strip_scene_preface(text)
        assert result == "A red car in the parking lot."

    def test_strip_from_the_image(self):
        text = "From the image, this appears to be a coffee mug."
        result = strip_scene_preface(text)
        assert result == "This appears to be a coffee mug."

    def test_strip_from_the_images(self):
        text = "From the images, I can identify three objects."
        result = strip_scene_preface(text)
        assert result == "I can identify three objects."

    def test_strip_in_the_photo(self):
        text = "In the photo, there is a laptop on the desk."
        result = strip_scene_preface(text)
        assert result == "There is a laptop on the desk."

    def test_strip_in_the_picture(self):
        text = "In the picture, you can see a mountain range."
        result = strip_scene_preface(text)
        assert result == "You can see a mountain range."

    def test_strip_in_the_image(self):
        text = "In the image, the text reads 'Welcome'."
        result = strip_scene_preface(text)
        assert result == "The text reads 'Welcome'."

    def test_strip_looking_at_the_image(self):
        text = "Looking at the image, this is a bicycle."
        result = strip_scene_preface(text)
        assert result == "This is a bicycle."

    def test_strip_looking_at_photo(self):
        text = "Looking at the photo, the sky is blue."
        result = strip_scene_preface(text)
        assert result == "The sky is blue."

    def test_strip_based_on_the_image(self):
        text = "Based on the image, this is likely a smartphone."
        result = strip_scene_preface(text)
        assert result == "This is likely a smartphone."

    def test_strip_the_image_shows(self):
        text = "The image shows a person standing near a tree."
        result = strip_scene_preface(text)
        assert result == "A person standing near a tree."

    def test_strip_the_photo_shows(self):
        text = "The photo shows several books on a shelf."
        result = strip_scene_preface(text)
        assert result == "Several books on a shelf."

    def test_strip_i_can_see(self):
        text = "I can see multiple items on the table."
        result = strip_scene_preface(text)
        assert result == "Multiple items on the table."

    def test_strip_from_what_i_can_see(self):
        text = "From what I can see, the temperature is 72 degrees."
        result = strip_scene_preface(text)
        assert result == "The temperature is 72 degrees."

    def test_strip_in_this_image(self):
        text = "In this image, there are three cats."
        result = strip_scene_preface(text)
        assert result == "There are three cats."

    # --- Case Insensitivity Tests ---

    def test_case_insensitive_i_see(self):
        text = "i see a bottle of water."
        result = strip_scene_preface(text)
        assert result == "A bottle of water."

    def test_case_insensitive_from_image(self):
        text = "FROM THE IMAGE, this is a keyboard."
        result = strip_scene_preface(text)
        assert result == "This is a keyboard."

    # --- Capitalization Tests ---

    def test_capitalize_after_strip(self):
        text = "I see the color is blue."
        result = strip_scene_preface(text)
        assert result == "The color is blue."
        assert result[0].isupper()

    def test_preserve_capitalization(self):
        text = "I see NASA is mentioned in the text."
        result = strip_scene_preface(text)
        assert result == "NASA is mentioned in the text."

    # --- Text Preservation Tests ---

    def test_no_preface_unchanged(self):
        text = "This is a simple answer."
        result = strip_scene_preface(text)
        assert result == "This is a simple answer."

    def test_greeting_unchanged(self):
        text = "Hello! How can I help you?"
        result = strip_scene_preface(text)
        assert result == "Hello! How can I help you?"

    def test_normal_chat_unchanged(self):
        text = "The capital of France is Paris."
        result = strip_scene_preface(text)
        assert result == "The capital of France is Paris."

    def test_middle_occurrence_not_stripped(self):
        # Only strip from beginning
        text = "The answer is that I see three items."
        result = strip_scene_preface(text)
        assert result == "The answer is that I see three items."

    # --- Edge Cases ---

    def test_empty_string(self):
        result = strip_scene_preface("")
        assert result == ""

    def test_whitespace_only(self):
        result = strip_scene_preface("   ")
        assert result == ""

    def test_preface_only(self):
        text = "I see"
        result = strip_scene_preface(text)
        # Should strip and leave empty/whitespace
        assert result.strip() == ""

    def test_preface_with_comma(self):
        text = "From the image, the object is round."
        result = strip_scene_preface(text)
        assert result == "The object is round."

    def test_multiple_sentences(self):
        text = "I see a dog. It appears to be a golden retriever."
        result = strip_scene_preface(text)
        assert result == "A dog. It appears to be a golden retriever."

    # --- Only First Pattern Matched ---

    def test_only_first_pattern_stripped(self):
        # Should only strip the first preface, not subsequent ones
        text = "I see from the image that this is a cup."
        result = strip_scene_preface(text)
        # Should strip "I see " but leave the rest
        assert "from the image" in result.lower()

    # --- Real-World Examples ---

    def test_realistic_response_1(self):
        text = "I see a laptop computer on the desk."
        result = strip_scene_preface(text)
        assert result == "A laptop computer on the desk."

    def test_realistic_response_2(self):
        text = "From the image, the price tag shows $19.99."
        result = strip_scene_preface(text)
        assert result == "The price tag shows $19.99."

    def test_realistic_response_3(self):
        text = "Looking at the photo, this appears to be a sunset scene."
        result = strip_scene_preface(text)
        assert result == "This appears to be a sunset scene."

    def test_realistic_chat_response(self):
        # No vision preface - should be unchanged
        text = "Paris is the capital of France."
        result = strip_scene_preface(text)
        assert result == "Paris is the capital of France."

    # --- None/Null Handling ---

    def test_none_input(self):
        # Should return None/empty gracefully
        result = strip_scene_preface(None)
        assert result is None or result == ""
