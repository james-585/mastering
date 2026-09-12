import numpy as np
from scipy.signal import sosfiltfilt

from suno_mastering.analysis.types import BandMeasurement, FrequencyBalanceResult
from suno_mastering.mastering.adaptive_harshness import (
    AdaptiveHarshnessConfig,
    AdaptiveHarshnessAction,
    apply_adaptive_harshness,
    _peaking_sos,
    _low_shelf_sos,
    _band_center_hz,
    _band_width_octaves,
)


def _fb(presence_rel_db: float, low_mid_rel_db: float) -> FrequencyBalanceResult:
    return FrequencyBalanceResult(
        low_end=BandMeasurement((20.0, 120.0), -1.0, -1.0, 0.0, False),
        low_mid_mud=BandMeasurement((200.0, 500.0), low_mid_rel_db, -3.0, low_mid_rel_db - (-3.0), False),
        presence_harsh=BandMeasurement((2000.0, 5000.0), presence_rel_db, -4.0, presence_rel_db - (-4.0), True, "harshness"),
    )


def test_tc0101_broad_brightness_triggers_shelf():
    audio = np.random.default_rng(0).normal(0.0, 0.01, (4096, 2)).astype(np.float64)
    cfg = AdaptiveHarshnessConfig(enabled=True)
    out, actions = apply_adaptive_harshness(audio, 44100, _fb(5.5, -1.0), cfg)

    assert out.shape == audio.shape
    assert any(a.method == "broad_shelf" for a in actions)
    assert actions[0].reason == "broad_brighness"


def test_tc0102_narrow_peak_triggers_notch():
    audio = np.random.default_rng(1).normal(0.0, 0.01, 4096).astype(np.float64)
    cfg = AdaptiveHarshnessConfig(enabled=True)
    out, actions = apply_adaptive_harshness(audio, 44100, _fb(6.0, 3.5), cfg)

    assert out.shape == audio.shape
    assert any(a.method == "narrow_cut" for a in actions)
    assert actions[0].reason == "narrow_resonance"


def test_tc0104_balanced_material_is_noop():
    audio = np.random.default_rng(2).normal(0.0, 0.01, 2048).astype(np.float64)
    cfg = AdaptiveHarshnessConfig(enabled=True)
    out, actions = apply_adaptive_harshness(audio, 44100, _fb(-2.0, -1.0), cfg)

    assert out.shape == audio.shape
    assert actions == []


def test_tc0105_action_logs_method_and_reason():
    audio = np.random.default_rng(3).normal(0.0, 0.01, 2048).astype(np.float64)
    cfg = AdaptiveHarshnessConfig(enabled=True)
    out, actions = apply_adaptive_harshness(audio, 44100, _fb(7.0, -0.2), cfg)

    assert len(actions) == 1
    action = actions[0]
    assert isinstance(action, AdaptiveHarshnessAction)
    assert action.method in {"broad_shelf", "narrow_cut"}
    assert action.reason in {"broad_brighness", "narrow_resonance"}


# DEF-027-008: verify sosfiltfilt delivers gain_db at ω₀, not 2×gain_db.

def test_tc_def027008_peaking_gain_delivery():
    """_peaking_sos with gain_db/2 design parameter + sosfiltfilt delivers gain_db at ω₀ ±0.5 dB."""
    sr = 44100
    f0 = _band_center_hz((2000.0, 5000.0))  # ≈ 3162 Hz
    bw = _band_width_octaves((2000.0, 5000.0))
    gain_db = -3.0
    t = np.linspace(0, 2.0, int(sr * 2), endpoint=False)
    x = np.sin(2 * np.pi * f0 * t)
    sos = _peaking_sos(sr, f0, gain_db / 2, bw)
    y = sosfiltfilt(sos, x)
    i0 = int(0.1 * sr)
    delivered_db = 20 * np.log10(np.sqrt(np.mean(y[i0:] ** 2)) / np.sqrt(np.mean(x[i0:] ** 2)))
    assert abs(delivered_db - gain_db) < 0.5, f"Delivered {delivered_db:.3f} dB, expected {gain_db:.1f} dB"


def test_tc_def027008_shelf_gain_delivery():
    """_low_shelf_sos with gain_db/2 design parameter + sosfiltfilt delivers gain_db at low freq ±0.5 dB."""
    sr = 44100
    f0_shelf = 3500.0
    gain_db = -2.0
    # Measure delivered gain at a low frequency well below the shelf corner (100 Hz).
    f_measure = 100.0
    t = np.linspace(0, 2.0, int(sr * 2), endpoint=False)
    x = np.sin(2 * np.pi * f_measure * t)
    sos = _low_shelf_sos(sr, f0_shelf, gain_db / 2)
    y = sosfiltfilt(sos, x)
    i0 = int(0.1 * sr)
    delivered_db = 20 * np.log10(np.sqrt(np.mean(y[i0:] ** 2)) / np.sqrt(np.mean(x[i0:] ** 2)))
    assert abs(delivered_db - gain_db) < 0.5, f"Delivered {delivered_db:.3f} dB, expected {gain_db:.1f} dB"
