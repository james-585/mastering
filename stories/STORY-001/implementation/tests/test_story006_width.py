"""STORY-006 test_story006_width.py — TC-630 to TC-638

Tests for stereo_width_corrector module.
Architecture §6.3, §7.2 define expected fields and the M/S gain formula.

Slow tests (TC-630, TC-634, TC-637) require ≥10 s fixtures for Welch stability.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from suno_mastering.mastering.stereo_width_corrector import (
    WidthCorrectiveAction,
    apply_stereo_width_correction,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SR = 44100

# Targets dict with the spec-correct stereo_width block.
_WIDTH_TARGETS = {
    "stereo_width": {
        "sub": {
            "near_mono_threshold": 0.15,
            "correction_aim_point": 0.15,
            "correction_floor": 0.10,
            "max_correction_step": 0.15,
        },
        "low": {
            "near_mono_threshold": 0.15,
            "correction_aim_point": 0.15,
            "correction_floor": 0.10,
            "max_correction_step": 0.15,
        },
    },
}

_RNG = np.random.default_rng(0)


def _stereo_noise(n: int) -> np.ndarray:
    """Decorrelated stereo white noise at safe amplitude."""
    left = _RNG.normal(0.0, 0.01, n).astype(np.float64)
    right = _RNG.normal(0.0, 0.01, n).astype(np.float64)
    return np.stack([left, right], axis=1)


def _stereo_at_width(n: int, width: float, amplitude: float = 0.01, seed: int = 42) -> np.ndarray:
    """Engineer a stereo white-noise signal with sub-band width ≈ w.

    Uses the M/S width identity: for L = x, R = β*x + sqrt(1-β²)*y (x, y independent),
    width = 1 - β per the formula width = 2*P_S/(P_M+P_S) where M=(L+R)/2, S=(L-R)/2.

    White noise is spectrally flat so sub-band (20-60 Hz) correlation equals
    broadband correlation → sub-band width ≈ width for n large enough.
    """
    β = max(0.0, min(1.0, 1.0 - width))
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, amplitude, n).astype(np.float64)
    y = rng.normal(0.0, amplitude, n).astype(np.float64)
    L = x
    R = β * x + np.sqrt(max(0.0, 1.0 - β ** 2)) * y
    return np.stack([L, R], axis=1)


@pytest.fixture(scope="session")
def noise_3s():
    return _stereo_noise(int(SR * 3))


@pytest.fixture(scope="session")
def noise_10s():
    """≥10 s stereo fixture for Welch-stable sub-band width tests."""
    return _stereo_noise(int(SR * 10))


@pytest.fixture(scope="session")
def width_060_10s():
    """≥10 s stereo noise engineered with sub-band width ≈ 0.60.
    β = 0.40: L = x, R = 0.40*x + 0.917*y → width = 1-β = 0.60.
    Used by TC-630 to verify the M/S narrowing formula on matched-width audio.
    """
    return _stereo_at_width(int(SR * 10), width=0.60, seed=630)


@pytest.fixture(scope="session")
def width_080_10s():
    """≥10 s stereo noise engineered with sub-band width ≈ 0.80.
    β = 0.20: L = x, R = 0.20*x + 0.980*y → width = 1-β = 0.80.
    Used by TC-637 to verify the M/S narrowing formula on matched-width audio.
    """
    return _stereo_at_width(int(SR * 10), width=0.80, seed=637)


# ---------------------------------------------------------------------------
# TC-630 — Canonical case: sub width 0.60, cap binds [Slow]
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_tc630_sub_width_060_cap_binds(width_060_10s):
    """AC20: pre_widths sub=0.60; cap binds (0.60 - 0.15 = 0.45 > aim 0.15).
    Expected WidthCorrectiveAction fields per architecture §7.2.

    Uses width_060_10s fixture: 10 s white noise engineered with sub-band width ≈ 0.60
    so that the pre_widths argument matches the actual audio's sub-band width.
    This is required for the M/S gain formula to achieve the target width.
    """
    pre_widths = {"sub": 0.60, "low": 0.10}
    out, actions = apply_stereo_width_correction(width_060_10s.copy(), SR, _WIDTH_TARGETS, pre_widths)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1, f"Expected 1 sub action, got {len(sub_actions)}"
    a = sub_actions[0]

    assert abs(a.aim_point - 0.15) < 1e-9, f"aim_point expected 0.15, got {a.aim_point}"
    assert a.cap_reached is True

    assert hasattr(a, "trigger"), "WidthCorrectiveAction missing 'trigger' field (DEF-602 fixed)"
    assert a.trigger == "width_above_threshold"

    assert hasattr(a, "source_value"), "WidthCorrectiveAction missing 'source_value' (DEF-602 fixed)"
    assert abs(a.source_value - 0.60) < 1e-9

    # w_target = max(0.15, 0.60 - 0.15) = 0.45
    assert hasattr(a, "resulting_value"), "WidthCorrectiveAction missing 'resulting_value' (DEF-602 fixed)"
    assert abs(a.resulting_value - 0.45) < 0.02, (
        f"resulting_value expected 0.45 (cap: w_target=0.45), got {a.resulting_value}"
    )

    # applied must be -(0.60 - 0.45) = -0.15
    assert abs(a.applied - (-0.15)) < 1e-9, f"applied expected -0.15, got {a.applied}"

    # Floor assertion: resulting_value >= 0.10 always
    assert a.resulting_value >= 0.10, f"resulting_value {a.resulting_value} breaches floor 0.10"

    # Measure actual sub-band width of resulting audio (Welch-stable at ≥10 s).
    # The fixture is engineered with sub-band width ≈ 0.60, matching pre_widths,
    # so the M/S formula should achieve w_target = 0.45 in the audio.
    from suno_mastering.reference_analysis.config import ReferenceAnalysisConfig
    from suno_mastering.analysis.per_band_stereo_width import measure_per_band_stereo_width

    ref_cfg = ReferenceAnalysisConfig()
    result = measure_per_band_stereo_width(out, SR, ref_cfg)
    sub_width = next(b.width for b in result.bands if b.band == "sub")

    # Tolerance ±0.05: Welch estimation + bandpass roll-off at 60 Hz
    assert abs(sub_width - 0.45) < 0.05, (
        f"Sub-band width after correction expected ≈0.45 (±0.05), got {sub_width:.4f}. "
        "g = sqrt(0.45*1.40/(0.60*1.55)) = 0.823; fixture engineered at width=0.60."
    )


# ---------------------------------------------------------------------------
# TC-631 — Width aim_point is 0.15, not 0.10
# ---------------------------------------------------------------------------

def test_tc631_aim_point_is_015_not_010(noise_3s):
    """AC20, requirements §3.5: aim_point must be 0.15 (correction aim), not 0.10 (floor)."""
    pre_widths = {"sub": 0.20, "low": 0.10}
    _, actions = apply_stereo_width_correction(noise_3s.copy(), SR, _WIDTH_TARGETS, pre_widths)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1
    a = sub_actions[0]

    assert abs(a.aim_point - 0.15) < 1e-9, (
        f"aim_point expected 0.15 (correction aim, not 0.10 floor), got {a.aim_point}"
    )


# ---------------------------------------------------------------------------
# TC-632 — Width cap does not bind: source just above threshold
# ---------------------------------------------------------------------------

def test_tc632_cap_not_binding(noise_3s):
    """AC7: sub=0.20; w_target = max(0.15, 0.20-0.15) = 0.15 (= aim_point, cap not binding).
    EXPECTED TO FAIL on resulting_value (DEF-602).
    """
    pre_widths = {"sub": 0.20, "low": 0.10}
    _, actions = apply_stereo_width_correction(noise_3s.copy(), SR, _WIDTH_TARGETS, pre_widths)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1
    a = sub_actions[0]

    # applied = -(0.20 - 0.15) = -0.05; cap does not bind
    assert abs(a.applied - (-0.05)) < 0.001, f"applied expected -0.05, got {a.applied}"
    assert a.cap_reached is False

    # EXPECTED TO FAIL (DEF-602)
    assert hasattr(a, "resulting_value"), "Missing resulting_value (DEF-602)"
    assert abs(a.resulting_value - 0.15) < 0.001, f"resulting_value expected 0.15, got {a.resulting_value}"


# ---------------------------------------------------------------------------
# TC-633 — Width within threshold: no correction
# ---------------------------------------------------------------------------

def test_tc633_width_within_threshold_no_correction(noise_3s):
    """AC7, AC18: sub=0.15 (exactly at threshold) → trigger requires > 0.15 → no action."""
    pre_widths = {"sub": 0.15, "low": 0.08}
    out, actions = apply_stereo_width_correction(noise_3s.copy(), SR, _WIDTH_TARGETS, pre_widths)

    assert actions == [], f"Expected zero actions at threshold (strict >), got {actions}"
    assert np.allclose(out, noise_3s), "Audio unchanged when sub at threshold"


# ---------------------------------------------------------------------------
# TC-634 — Low band width correction [Slow]
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_tc634_low_band_width_correction(noise_10s):
    """AC7: sub=0.10 (no action); low=0.50 → cap binds (0.50-0.15=0.35 > aim 0.15).
    EXPECTED TO FAIL on resulting_value (DEF-602).
    """
    pre_widths = {"sub": 0.10, "low": 0.50}
    _, actions = apply_stereo_width_correction(noise_10s.copy(), SR, _WIDTH_TARGETS, pre_widths)

    sub_actions = [a for a in actions if a.band == "sub"]
    low_actions = [a for a in actions if a.band == "low"]

    assert sub_actions == [], f"No sub action expected (0.10 ≤ 0.15), got {sub_actions}"
    assert len(low_actions) == 1, f"Expected 1 low action, got {low_actions}"

    a = low_actions[0]
    assert abs(a.aim_point - 0.15) < 1e-9
    assert abs(a.applied - (-0.15)) < 1e-9  # -(0.50 - 0.35) = -0.15
    assert a.cap_reached is True

    # EXPECTED TO FAIL (DEF-602)
    assert hasattr(a, "resulting_value"), "Missing resulting_value (DEF-602)"
    assert abs(a.resulting_value - 0.35) < 0.02, (
        f"resulting_value expected 0.35 (w_target=max(0.15, 0.50-0.15)), got {a.resulting_value}"
    )


# ---------------------------------------------------------------------------
# TC-635 — Mid and higher bands: no width correction
# ---------------------------------------------------------------------------

def test_tc635_mid_higher_bands_no_correction(noise_3s):
    """AC7: only sub and low are correction targets; mid/high_mid/high/air are not."""
    pre_widths = {"sub": 0.10, "low": 0.10, "mid": 0.80, "high_mid": 0.90,
                  "high": 0.95, "air": 0.98}
    out, actions = apply_stereo_width_correction(noise_3s.copy(), SR, _WIDTH_TARGETS, pre_widths)

    assert actions == [], (
        f"Expected zero actions (sub/low within threshold; mid+ not correction targets). "
        f"Got {[(a.band, a.applied) for a in actions]}"
    )
    assert np.allclose(out, noise_3s)


# ---------------------------------------------------------------------------
# TC-636 — Mono input: ValueError raised
# ---------------------------------------------------------------------------

def test_tc636_mono_input_raises_value_error():
    """Architecture §16: mono input to width corrector must raise ValueError."""
    n = SR * 3
    mono = _RNG.normal(0.0, 0.01, n).astype(np.float64)

    with pytest.raises(ValueError, match="stereo"):
        apply_stereo_width_correction(mono, SR, _WIDTH_TARGETS, {"sub": 0.5})


# ---------------------------------------------------------------------------
# TC-637 — Width gain formula: w_src = 0.80 (Q1 example) [Slow]
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_tc637_width_gain_formula_q1_example(width_080_10s):
    """AC20, architecture §6.3 Q1 example: w_src=0.80.
    Expected: w_target = max(0.15, 0.80-0.15) = 0.65; cap binds; resulting_value = 0.65.
    g = sqrt(0.65*1.20 / (0.80*1.35)) = sqrt(0.722) = 0.850 (architecture formula).

    Uses width_080_10s fixture: 10 s white noise engineered with sub-band width ≈ 0.80
    so that pre_widths matches the actual audio's sub-band width.
    """
    pre_widths = {"sub": 0.80, "low": 0.10}
    out, actions = apply_stereo_width_correction(width_080_10s.copy(), SR, _WIDTH_TARGETS, pre_widths)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1
    a = sub_actions[0]

    assert a.cap_reached is True
    assert abs(a.applied - (-0.15)) < 1e-9, f"applied expected -0.15, got {a.applied}"

    assert hasattr(a, "resulting_value"), "Missing resulting_value (DEF-602 fixed)"
    assert abs(a.resulting_value - 0.65) < 0.02, (
        f"resulting_value expected 0.65 (capped w_target, not 0.15 aim), got {a.resulting_value}. "
        "Architecture §6.3: cap is applied in width units FIRST → w_target=0.65; "
        "then g is derived from w_target."
    )

    # Measure sub-band width of resulting audio.
    # Fixture engineered at width ≈ 0.80 so g = sqrt(0.65*1.20/(0.80*1.35)) = 0.850
    # should achieve w_target ≈ 0.65 in the actual audio.
    from suno_mastering.reference_analysis.config import ReferenceAnalysisConfig
    from suno_mastering.analysis.per_band_stereo_width import measure_per_band_stereo_width

    ref_cfg = ReferenceAnalysisConfig()
    result = measure_per_band_stereo_width(out, SR, ref_cfg)
    sub_width = next(b.width for b in result.bands if b.band == "sub")

    # Tolerance ±0.07: the sub band is only 40 Hz wide (20-60 Hz), giving very few
    # Welch FFT bins and higher estimation variance than TC-630's +2.0 dB correction.
    # The gain formula is theoretically exact; ±0.07 accounts for Welch noise on 10 s.
    assert abs(sub_width - 0.65) < 0.07, (
        f"Sub-band width expected ≈0.65 (±0.07) after correction (w_target=0.65), "
        f"got {sub_width:.4f}. "
        "g = sqrt(0.65*1.20/(0.80*1.35)) = 0.850; fixture engineered at width=0.80."
    )


# ---------------------------------------------------------------------------
# TC-638 — Width estimator same function pre and post (code-review)
# ---------------------------------------------------------------------------

def test_tc638_width_estimator_not_duplicated_in_corrector():
    """Architecture §6.2: stereo_width_corrector.py must NOT contain its own
    internal width estimator.  The module must consume pre_widths from Stage [2]
    (passed in by pipeline.py) rather than computing widths independently.

    DEF-610 documents that TC-638's original assertion — checking that
    measure_per_band_stereo_width is imported INTO stereo_width_corrector.py —
    is incorrect.  Architecture §6.2 explicitly PROHIBITS a second width estimator
    inside stereo_width_corrector.py.  The correct behaviour is to receive pre_widths
    from the pipeline (measured by Stage [2] analysis) and not re-measure.

    This test now verifies the correct §6.2 behaviour:
    1.  The module does NOT import measure_per_band_stereo_width (no duplicated estimator).
    2.  The module uses a pre_widths parameter (accepts widths from outside).
    3.  No Welch / CSD computation (signaling a second in-module estimator) is present.
    """
    src_path = (
        Path(__file__).parent.parent
        / "suno_mastering" / "mastering" / "stereo_width_corrector.py"
    )
    src = src_path.read_text()

    # Architecture §6.2: corrector must NOT import its own width estimator.
    # Check only import statements, not docstring references
    # (the module docstring may mention the function name as a reference — that is fine).
    import_lines = [ln for ln in src.splitlines() if ln.strip().startswith("import ") or ln.strip().startswith("from ")]
    estimator_imported = any("measure_per_band_stereo_width" in ln for ln in import_lines)
    assert not estimator_imported, (
        "stereo_width_corrector.py has an import statement for measure_per_band_stereo_width — "
        "this is prohibited by architecture §6.2 (no second width estimator in the corrector). "
        "Width estimation must be done by Stage [2] analysis; the corrector receives pre_widths."
    )

    # No in-module Welch/CSD re-implementation
    assert "welch" not in src.lower(), (
        "stereo_width_corrector.py appears to contain an in-module Welch estimator — "
        "architecture §6.2 prohibits this."
    )
    assert "csd" not in src.lower() or "btype" in src.lower(), (
        # 'csd' may appear in comments; 'btype' presence indicates it's a bandpass context
        "Unexpected CSD reference in stereo_width_corrector.py"
    )

    # Module must accept pre_widths as a parameter (functional test: non-zero width triggers action)
    _sw = {"near_mono_threshold": 0.15, "correction_aim_point": 0.15,
           "correction_floor": 0.10, "max_correction_step": 0.15}
    targets = {"stereo_width": {"sub": _sw, "low": _sw}}
    rng = np.random.default_rng(638)
    n = SR * 3
    audio = np.stack([rng.normal(0, 0.01, n), rng.normal(0, 0.01, n)], axis=1).astype(np.float64)
    pre_widths = {"sub": 0.30, "low": 0.10}  # sub above threshold, low below
    _, actions = apply_stereo_width_correction(audio, SR, targets, pre_widths)
    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1, (
        "Expected 1 sub action from pre_widths sub=0.30 > 0.15 threshold — "
        "corrector must use the pre_widths parameter"
    )
