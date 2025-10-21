from app.audio.wake import WakeWordListener


def test_compute_required_hits_high_sensitivity():
    assert WakeWordListener._compute_required_hits(0.85) == 1


def test_compute_required_hits_medium_sensitivity():
    assert WakeWordListener._compute_required_hits(0.45) == 2


def test_compute_required_hits_low_sensitivity():
    assert WakeWordListener._compute_required_hits(0.3) == 3


def test_compute_required_hits_minimum():
    assert WakeWordListener._compute_required_hits(0.0) == 4


def test_tokens_match_handles_minor_phonetic_difference():
    assert WakeWordListener._tokens_match(["hey", "glosses"], ["hey", "glasses"])


def test_tokens_match_rejects_different_phrase():
    assert not WakeWordListener._tokens_match(["hey", "google"], ["hey", "glasses"])
