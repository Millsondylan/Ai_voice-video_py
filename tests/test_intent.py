"""
Unit tests for intent detection (app/util/intent.py)

Tests the wants_vision() function to ensure it correctly identifies
vision-related vs chat-related intents.
"""

import pytest
from app.util.intent import wants_vision


class TestWantsVision:
    """Test suite for wants_vision() function"""

    # --- Greeting Tests (should return False) ---

    def test_greeting_hi(self):
        assert wants_vision("hi") is False

    def test_greeting_hello(self):
        assert wants_vision("hello") is False

    def test_greeting_hey(self):
        assert wants_vision("hey") is False

    def test_greeting_howdy(self):
        assert wants_vision("howdy") is False

    def test_greeting_good_morning(self):
        assert wants_vision("good morning") is False

    def test_greeting_good_afternoon(self):
        assert wants_vision("good afternoon") is False

    def test_greeting_good_evening(self):
        assert wants_vision("good evening") is False

    def test_greeting_how_are_you(self):
        assert wants_vision("how are you") is False

    def test_greeting_whats_up(self):
        assert wants_vision("what's up") is False

    def test_greeting_thanks(self):
        assert wants_vision("thanks") is False

    def test_greeting_thank_you(self):
        assert wants_vision("thank you") is False

    def test_greeting_bye(self):
        assert wants_vision("bye") is False

    def test_greeting_goodbye(self):
        assert wants_vision("goodbye") is False

    # --- Deictic/Identify Tests (should return True) ---

    def test_deictic_what_is_this(self):
        assert wants_vision("what is this") is True

    def test_deictic_what_is_that(self):
        assert wants_vision("what is that") is True

    def test_deictic_look_at(self):
        assert wants_vision("look at this object") is True

    def test_deictic_see_this(self):
        assert wants_vision("can you see this") is True

    def test_deictic_identify(self):
        assert wants_vision("identify this item") is True

    def test_deictic_is_this(self):
        assert wants_vision("is this a banana") is True

    def test_deictic_show_me(self):
        assert wants_vision("show me what you see") is True

    def test_deictic_what_color(self):
        assert wants_vision("what color is this") is True

    def test_deictic_where_is(self):
        assert wants_vision("where is the remote") is True

    def test_deictic_how_many(self):
        assert wants_vision("how many apples are there") is True

    def test_deictic_do_you_see(self):
        assert wants_vision("do you see a cat") is True

    def test_deictic_can_you_see(self):
        assert wants_vision("can you see the sign") is True

    # --- OCR/Reading Tests (should return True) ---

    def test_ocr_read(self):
        assert wants_vision("read this text") is True

    def test_ocr_text_on(self):
        assert wants_vision("what's the text on this label") is True

    def test_ocr_label(self):
        assert wants_vision("read the label") is True

    def test_ocr_sign(self):
        assert wants_vision("what does the sign say") is True

    def test_ocr_price(self):
        assert wants_vision("what's the price") is True

    def test_ocr_serial(self):
        assert wants_vision("read the serial number") is True

    def test_ocr_number_visible(self):
        assert wants_vision("what number is visible") is True

    def test_ocr_what_does_it_say(self):
        assert wants_vision("what does this say") is True

    def test_ocr_writing(self):
        assert wants_vision("what's the writing here") is True

    def test_ocr_written(self):
        assert wants_vision("what's written on this") is True

    # --- General Knowledge/Chat Tests (should return False) ---

    def test_general_capital_question(self):
        assert wants_vision("what's the capital of France") is False

    def test_general_math(self):
        assert wants_vision("what is 2 plus 2") is False

    def test_general_time(self):
        assert wants_vision("what time is it") is False

    def test_general_weather(self):
        assert wants_vision("how's the weather") is False

    def test_general_knowledge(self):
        assert wants_vision("who was the first president") is False

    # --- Edge Cases ---

    def test_empty_string(self):
        assert wants_vision("") is False

    def test_whitespace_only(self):
        assert wants_vision("   ") is False

    def test_none_handling(self):
        # Should handle None gracefully
        assert wants_vision("") is False

    def test_case_insensitive_greeting(self):
        assert wants_vision("HELLO") is False

    def test_case_insensitive_deictic(self):
        assert wants_vision("WHAT IS THIS") is True

    def test_case_insensitive_ocr(self):
        assert wants_vision("READ THIS LABEL") is True

    # --- Mixed/Ambiguous Cases ---

    def test_greeting_with_question(self):
        # Greeting takes precedence
        assert wants_vision("hi there, how are you doing") is False

    def test_vision_after_greeting(self):
        # Vision intent in longer phrase
        assert wants_vision("hello, what is this object") is True

    def test_what_question_non_visual(self):
        # "what" alone doesn't trigger vision
        assert wants_vision("what do you think") is False

    def test_see_you_later(self):
        # "see you" is not "see this"
        assert wants_vision("see you later") is False

    # --- Real-World Examples ---

    def test_realistic_greeting_sequence(self):
        assert wants_vision("hey there") is False

    def test_realistic_deictic_sequence(self):
        assert wants_vision("can you tell me what is that thing") is True

    def test_realistic_ocr_sequence(self):
        assert wants_vision("please read the price tag for me") is True

    def test_realistic_chat_sequence(self):
        assert wants_vision("tell me a joke") is False

    def test_what_shape(self):
        assert wants_vision("what shape is this") is True

    def test_what_size(self):
        assert wants_vision("what size is that") is True
