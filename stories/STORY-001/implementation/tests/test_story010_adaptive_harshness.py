import numpy as np

from suno_mastering.analysis.types import BandMeasurement, FrequencyBalanceResult
from suno_mastering.mastering.adaptive_harshness import (
    AdaptiveHarshnessConfig,
    AdaptiveHarshnessAction,
    apply_adaptive_harshness,
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
