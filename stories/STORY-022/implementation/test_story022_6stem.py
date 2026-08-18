import numpy as np
import pytest

from stem_model_registry import recombine_stems, resolve_model, split_stems


EXPECTED_6STEM = ["drums", "bass", "other", "vocals", "piano", "guitar"]
EXPECTED_4STEM = ["drums", "bass", "other", "vocals"]


def _make_audio(length: int = 32) -> np.ndarray:
    t = np.linspace(0.0, 1.0, length, endpoint=False, dtype=np.float64)
    left = np.sin(2 * np.pi * 220.0 * t) + 0.25 * np.sin(2 * np.pi * 440.0 * t)
    right = np.cos(2 * np.pi * 220.0 * t) + 0.25 * np.cos(2 * np.pi * 330.0 * t)
    return np.stack([left, right], axis=1)


def test_tc022_01_registry_supports_6stem_path():
    resolved = resolve_model("htdemucs_6s")
    assert resolved["model_name"] == "htdemucs_6s"
    assert resolved["stem_count"] == 6
    assert resolved["stem_names"] == EXPECTED_6STEM

    legacy = resolve_model("htdemucs")
    assert legacy["model_name"] == "htdemucs"
    assert legacy["stem_count"] == 4
    assert legacy["stem_names"] == EXPECTED_4STEM


def test_tc022_02_piano_and_guitar_are_explicit_outputs():
    audio = _make_audio()
    stems = split_stems(audio, 44100, "htdemucs_6s")
    assert set(stems) == set(EXPECTED_6STEM)
    assert "piano" in stems and "guitar" in stems
    for stem_name in EXPECTED_6STEM:
        assert stems[stem_name].shape == audio.shape
        assert np.all(np.isfinite(stems[stem_name]))


def test_tc022_03_partial_6stem_bundle_is_rejected():
    audio = _make_audio()
    partial = {name: audio for name in EXPECTED_6STEM[:-1]}
    with pytest.raises(ValueError, match="6-stem|piano|guitar"):
        recombine_stems(partial, mode="6-stem", target=audio)


def test_tc022_04_recombination_is_deterministic_and_identity_safe():
    audio = _make_audio(64)
    stems = split_stems(audio, 44100, "htdemucs_6s")
    recombined = recombine_stems(stems, mode="6-stem", target=audio)
    assert recombined.shape == audio.shape
    assert np.allclose(recombined, audio, atol=1e-12, rtol=1e-12)
