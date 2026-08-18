"""Tests for the per-stem, attributed STATIONARY_WHISTLE notch (see
suno_mastering.mastering.stem_whistle_repair)."""
from __future__ import annotations

import numpy as np

from suno_mastering.analysis.types import ArtifactFlag
from suno_mastering.mastering.stem_whistle_repair import attribute_and_repair_whistles

SR = 44100


def _tone(freq_hz: float, duration_s: float, amp: float = 0.2) -> np.ndarray:
    n = int(SR * duration_s)
    t = np.arange(n) / SR
    mono = amp * np.sin(2 * np.pi * freq_hz * t)
    return np.column_stack([mono, mono])


def _noise(duration_s: float, amp: float = 0.05, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * duration_s)
    return amp * rng.standard_normal((n, 2))


def _whistle_flag(freq_hz: float, start_s: float, end_s: float) -> ArtifactFlag:
    return ArtifactFlag(
        timestamp_start_s=start_s,
        timestamp_end_s=end_s,
        artifact_type="STATIONARY_WHISTLE",
        confidence_score=1.0,
        details={"frequency_hz": freq_hz, "prominence_db": 12.0},
    )


def test_dominant_stem_is_notched_others_untouched():
    freq = 9000.0
    duration = 2.0
    stems = {
        "vocals": _tone(freq, duration) + _noise(duration, seed=1),
        "drums": _noise(duration, seed=2),
        "bass": _noise(duration, seed=3),
    }
    flags = [_whistle_flag(freq, 0.2, 1.8)]

    processed, actions = attribute_and_repair_whistles(stems, SR, flags)

    assert len(actions) == 1
    assert actions[0].stem_name == "vocals"
    assert actions[0].action_type == "whistle_notch"

    # Untouched stems are bit-identical.
    assert np.array_equal(processed["drums"], stems["drums"])
    assert np.array_equal(processed["bass"], stems["bass"])

    # The vocals stem is modified only inside/around the flagged window.
    assert not np.array_equal(processed["vocals"], stems["vocals"])
    outside = processed["vocals"][: int(0.05 * SR)]
    assert np.allclose(outside, stems["vocals"][: int(0.05 * SR)])


def test_ambiguous_attribution_is_skipped():
    """When no single stem dominates the tone's energy, nothing is touched."""
    freq = 9000.0
    duration = 2.0
    tone = _tone(freq, duration)
    stems = {
        "vocals": tone.copy(),
        "other": tone.copy(),
    }
    flags = [_whistle_flag(freq, 0.2, 1.8)]

    processed, actions = attribute_and_repair_whistles(stems, SR, flags)

    assert actions == []
    assert np.array_equal(processed["vocals"], stems["vocals"])
    assert np.array_equal(processed["other"], stems["other"])


def test_non_whistle_flags_are_ignored():
    stems = {"vocals": _noise(1.0, seed=4), "drums": _noise(1.0, seed=5)}
    flags = [
        ArtifactFlag(
            timestamp_start_s=0.1,
            timestamp_end_s=0.5,
            artifact_type="SMEARED_TRANSIENT",
            confidence_score=0.8,
            details={"rise_time_ms": 30.0},
        )
    ]

    processed, actions = attribute_and_repair_whistles(stems, SR, flags)

    assert actions == []
    assert np.array_equal(processed["vocals"], stems["vocals"])
    assert np.array_equal(processed["drums"], stems["drums"])


def test_low_confidence_flag_is_not_repaired():
    freq = 9000.0
    stems = {"vocals": _tone(freq, 2.0) + _noise(2.0, seed=1), "drums": _noise(2.0, seed=2)}
    weak_flag = ArtifactFlag(
        timestamp_start_s=0.2,
        timestamp_end_s=1.8,
        artifact_type="STATIONARY_WHISTLE",
        confidence_score=0.5,  # below _CONFIDENCE_THRESHOLD
        details={"frequency_hz": freq, "prominence_db": 12.0},
    )

    processed, actions = attribute_and_repair_whistles(stems, SR, [weak_flag])

    assert actions == []
    assert np.array_equal(processed["vocals"], stems["vocals"])


def test_low_prominence_flag_is_not_repaired():
    freq = 9000.0
    stems = {"vocals": _tone(freq, 2.0) + _noise(2.0, seed=1), "drums": _noise(2.0, seed=2)}
    weak_flag = ArtifactFlag(
        timestamp_start_s=0.2,
        timestamp_end_s=1.8,
        artifact_type="STATIONARY_WHISTLE",
        confidence_score=1.0,
        details={"frequency_hz": freq, "prominence_db": 4.0},  # below _PROMINENCE_FLOOR_DB
    )

    processed, actions = attribute_and_repair_whistles(stems, SR, [weak_flag])

    assert actions == []
    assert np.array_equal(processed["vocals"], stems["vocals"])


def test_implausible_flag_volume_backs_off_entirely():
    """Many qualifying flags on one track is itself evidence of sustained
    musical content, not artifacts -- the whole stage should no-op."""
    stems = {"vocals": _noise(2.0, seed=1), "drums": _noise(2.0, seed=2)}
    many_flags = [_whistle_flag(1000.0 + i * 50, 0.1 * i, 0.1 * i + 1.5) for i in range(25)]

    processed, actions = attribute_and_repair_whistles(stems, SR, many_flags)

    assert actions == []
    assert np.array_equal(processed["vocals"], stems["vocals"])
    assert np.array_equal(processed["drums"], stems["drums"])
