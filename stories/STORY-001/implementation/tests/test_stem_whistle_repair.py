"""Tests for the per-stem, attributed STATIONARY_WHISTLE notch (see
suno_mastering.mastering.stem_whistle_repair), and for the §6b harmonic guard
inside apply_whistle_repair (see suno_mastering.mastering.whistle_repair)."""
from __future__ import annotations

from datetime import datetime

import numpy as np

from suno_mastering.analysis.types import ArtifactDetectionResult, ArtifactFlag
from suno_mastering.config import RepairWhistlesConfig
from suno_mastering.mastering.stem_whistle_repair import attribute_and_repair_whistles
from suno_mastering.mastering.whistle_repair import WhistleRepairSummary, apply_whistle_repair

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


# ---------------------------------------------------------------------------
# §6b.5 harmonic guard tests — operate on apply_whistle_repair directly
# ---------------------------------------------------------------------------


def _make_detection_result(flags: list) -> ArtifactDetectionResult:
    return ArtifactDetectionResult(
        total_artifacts_found=len(flags),
        artifact_flags=flags,
        overall_artifact_density_score=0.5,
        detected_at=datetime.utcnow(),
    )


def test_harmonic_guard_suppresses_musical_harmonic():
    """TC-6b-a: 440 Hz sawtooth approximation; flag at 1320 Hz (3rd harmonic);
    guard must fire, suppress 1320 Hz, and return bit-identical audio.

    Verification: find_peaks sees 441 Hz (bin 82) below 1320 Hz, r=2.990,
    dev=0.010 <= 0.08; sibling 1760 Hz (4th harmonic) is present → suppress=True.
    Early return (target_frequencies empty) means no DSP round-trip → exact
    copy, so np.array_equal holds rather than np.allclose.
    """
    sr = 44100
    duration = 3.0
    t = np.arange(int(sr * duration)) / sr
    audio = sum(np.sin(2 * np.pi * n * 440 * t) / n for n in range(1, 11))
    audio = audio / max(abs(audio.max()), abs(audio.min())) * 0.9

    flag = ArtifactFlag(
        artifact_type="STATIONARY_WHISTLE",
        confidence_score=0.85,
        details={"frequency_hz": 1320.0, "prominence_db": 15.0},
        timestamp_start_s=0.5,
        timestamp_end_s=2.5,
    )
    detection = _make_detection_result([flag])
    config = RepairWhistlesConfig(enabled=True, prominence_floor_db=10.0)

    output, actions = apply_whistle_repair(audio, sr, detection, config)

    summary = next(a for a in actions if isinstance(a, WhistleRepairSummary))
    assert 1320.0 in summary.harmonic_guard_suppressed, (
        f"expected 1320.0 in harmonic_guard_suppressed; got {summary.harmonic_guard_suppressed}"
    )
    assert 1320.0 not in summary.frequencies_notched, (
        f"1320.0 must not appear in frequencies_notched; got {summary.frequencies_notched}"
    )
    assert np.array_equal(output, audio), (
        "when all flags are suppressed, output must be bit-identical to input audio "
        "(early return via audio.copy() — no DSP round-trip)"
    )


def test_harmonic_guard_passes_isolated_tone():
    """TC-6b-b: pure sine at 6427 Hz; no prominent energy below it; guard must
    NOT fire, and 6427 Hz must appear in frequencies_notched.

    Verification: find_peaks finds 0 peaks below 6427 Hz with prominence >= 6 dB;
    suppress=False → flag forwarded. suno_dsp unavailable in test environment;
    function still completes and records frequencies_notched correctly.
    """
    sr = 44100
    duration = 3.0
    t = np.arange(int(sr * duration)) / sr
    audio = 0.5 * np.sin(2 * np.pi * 6427 * t)

    flag = ArtifactFlag(
        artifact_type="STATIONARY_WHISTLE",
        confidence_score=0.85,
        details={"frequency_hz": 6427.0, "prominence_db": 15.0},
        timestamp_start_s=0.5,
        timestamp_end_s=2.5,
    )
    detection = _make_detection_result([flag])
    config = RepairWhistlesConfig(enabled=True, prominence_floor_db=10.0)

    output, actions = apply_whistle_repair(audio, sr, detection, config)

    summary = next(a for a in actions if isinstance(a, WhistleRepairSummary))
    assert summary.harmonic_guard_suppressed == [], (
        f"expected no suppressed frequencies; got {summary.harmonic_guard_suppressed}"
    )
    assert 6427.0 in summary.frequencies_notched, (
        f"expected 6427.0 in frequencies_notched; got {summary.frequencies_notched}"
    )


def test_harmonic_guard_degeneracy_probe():
    """TC-6b-c: 4327 Hz is not a harmonic of 70 Hz or 500 Hz; guard must not fire.

    Signal: 70 Hz sawtooth (harmonics 70..700 Hz) + 500 Hz sine (amp 0.3) +
    4327 Hz sine (amp 0.05), normalised to peak <= 0.9.

    Spectral verification (pre-run): 13 peaks found below 4327 Hz. Tightest
    within-N_MAX candidate is 490 Hz: r=8.833, dev=0.167 > 0.08 (no match).
    Candidates >= N_MAX (e.g. 70 Hz, n_nearest=62) are skipped by the
    _HARMONIC_GUARD_N_MAX guard. All 13 peaks fail the ratio test.

    This test fails loudly if _HARMONIC_GUARD_DELTA is inflated to >= 0.167
    (the tightest actual miss), making it a discriminating probe for the
    constant's correctness.
    """
    sr = 44100
    duration = 3.0
    t = np.arange(int(sr * duration)) / sr
    sawtooth_70 = sum(np.sin(2 * np.pi * n * 70 * t) / n for n in range(1, 11))
    sine_500 = 0.3 * np.sin(2 * np.pi * 500 * t)
    sine_4327 = 0.05 * np.sin(2 * np.pi * 4327 * t)
    mix = sawtooth_70 + sine_500 + sine_4327
    peak = max(abs(mix.max()), abs(mix.min()))
    audio = mix / peak * 0.9

    flag = ArtifactFlag(
        artifact_type="STATIONARY_WHISTLE",
        confidence_score=0.85,
        details={"frequency_hz": 4327.0, "prominence_db": 15.0},
        timestamp_start_s=0.5,
        timestamp_end_s=2.5,
    )
    detection = _make_detection_result([flag])
    config = RepairWhistlesConfig(enabled=True, prominence_floor_db=10.0)

    output, actions = apply_whistle_repair(audio, sr, detection, config)

    summary = next(a for a in actions if isinstance(a, WhistleRepairSummary))
    assert summary.harmonic_guard_suppressed == [], (
        f"4327 Hz must not be suppressed; got {summary.harmonic_guard_suppressed}"
    )
    assert 4327.0 in summary.frequencies_notched, (
        f"4327.0 must be forwarded to frequencies_notched; got {summary.frequencies_notched}"
    )
