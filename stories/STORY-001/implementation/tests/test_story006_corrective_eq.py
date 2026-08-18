"""STORY-006 test_story006_corrective_eq.py
TC-612 to TC-629, TC-639, TC-642, TC-643, TC-650, TC-651, TC-654, TC-655, TC-656

Tests for corrective_eq module and config/code-review checks.
Architecture §7.1 defines the required SpectralCorrectiveAction fields.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pytest

from suno_mastering.mastering.corrective_eq import (
    SpectralCorrectiveAction,
    apply_corrective_eq,
)

# ---------------------------------------------------------------------------
# Canonical targets fixture (architecture §8.1 values)
# ---------------------------------------------------------------------------

_TARGETS = {
    "spectral_bands": {
        "sub": {
            "freq_hz": [20, 60],
            "range_db_re_mid": {"min": -3.747, "max": 1.944},
            "correction_cap_db": 2.0,
        },
        "low_mid": {
            "freq_hz": [120, 500],
            "range_db_re_mid": {"min": -0.145, "max": 8.522},
            "correction_cap_db": 2.0,
        },
    },
    "de_mud": {
        "flag_threshold_db_above_mid": 4.0,
        "correction_aim_point_db": 2.0,
    },
}

SR = 44100
_DURATION = 3.0
_N = int(SR * _DURATION)
_RNG = np.random.default_rng(42)


def _white_stereo():
    """3 s stereo white noise at a safe amplitude."""
    x = _RNG.normal(0.0, 0.01, (_N, 2)).astype(np.float64)
    return x


def _white_mono():
    return _RNG.normal(0.0, 0.01, _N).astype(np.float64)


# ---------------------------------------------------------------------------
# TC-612 — Sub below range, cap binds
# ---------------------------------------------------------------------------

def test_tc612_sub_below_range_cap_binds():
    """AC4, AC15: sub = -6.247, cap = 2.0 binds.
    SpectralCorrectiveAction fields checked per architecture §7.1.
    EXPECTED TO FAIL: SpectralCorrectiveAction missing source_db / aim_point_db (DEF-601).
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": -6.247, "low_mid": 0.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1, f"Expected exactly 1 sub action, got {len(sub_actions)}"
    a = sub_actions[0]

    assert a.trigger == "range_compliance"
    # required = -3.747 - (-6.247) = +2.500; cap = 2.0 binds
    assert abs(a.applied_db - 2.0) < 1e-9, f"applied_db expected +2.0, got {a.applied_db}"
    assert a.cap_reached is True
    # arithmetic log field: -6.247 + 2.0 = -4.247
    assert abs(a.resulting_db - (-4.247)) < 0.001

    # Architecture §7.1 required fields — EXPECTED TO FAIL (DEF-601)
    assert hasattr(a, "source_db"), (
        "SpectralCorrectiveAction missing 'source_db' field (DEF-601, architecture §7.1)"
    )
    assert abs(a.source_db - (-6.247)) < 1e-9, f"source_db expected -6.247, got {a.source_db}"

    assert hasattr(a, "aim_point_db"), (
        "SpectralCorrectiveAction missing 'aim_point_db' field (DEF-601, architecture §7.1)"
    )
    assert abs(a.aim_point_db - (-3.747)) < 0.001, (
        f"aim_point_db expected -3.747 (range_min), got {a.aim_point_db}"
    )


# ---------------------------------------------------------------------------
# TC-613 — Sub below range, cap does not bind
# ---------------------------------------------------------------------------

def test_tc613_sub_below_range_cap_not_binding():
    """AC4, AC15: sub = -4.247, required = +0.500, cap does not bind.
    EXPECTED TO FAIL: missing source_db / aim_point_db (DEF-601).
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": -4.247, "low_mid": 0.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1
    a = sub_actions[0]

    assert a.trigger == "range_compliance"
    assert abs(a.applied_db - 0.500) < 0.001
    assert a.cap_reached is False
    assert abs(a.resulting_db - (-3.747)) < 0.001  # -4.247 + 0.500 = -3.747

    # Required fields — EXPECTED TO FAIL (DEF-601)
    assert hasattr(a, "source_db"), "Missing source_db (DEF-601)"
    assert abs(a.source_db - (-4.247)) < 1e-9

    assert hasattr(a, "aim_point_db"), "Missing aim_point_db (DEF-601)"
    assert abs(a.aim_point_db - (-3.747)) < 0.001


# ---------------------------------------------------------------------------
# TC-614 — Sub above range, cap binds
# ---------------------------------------------------------------------------

def test_tc614_sub_above_range_cap_binds():
    """AC4, AC15: sub = +5.0, aim = range_max = +1.944, cap binds.
    EXPECTED TO FAIL: missing source_db / aim_point_db (DEF-601).
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": 5.0, "low_mid": 0.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1
    a = sub_actions[0]

    assert a.trigger == "range_compliance"
    # required = 1.944 - 5.0 = -3.056; cap binds at -2.0
    assert abs(a.applied_db - (-2.0)) < 1e-9
    assert a.cap_reached is True
    assert abs(a.resulting_db - 3.0) < 0.001  # 5.0 - 2.0 = +3.0

    # Required fields — EXPECTED TO FAIL (DEF-601)
    assert hasattr(a, "source_db"), "Missing source_db (DEF-601)"
    assert abs(a.source_db - 5.0) < 1e-9

    assert hasattr(a, "aim_point_db"), "Missing aim_point_db (DEF-601)"
    assert abs(a.aim_point_db - 1.944) < 0.001  # range_max


# ---------------------------------------------------------------------------
# TC-615 — Sub within range: no correction
# ---------------------------------------------------------------------------

def test_tc615_sub_within_range_no_correction():
    """AC4, AC18: sub = 0.0, within [-3.747, +1.944] → no sub action."""
    audio = _white_stereo()
    pre_band_levels = {"sub": 0.0, "low_mid": 0.0, "mid": 0.0}
    out, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert sub_actions == [], f"Expected no sub action, got {sub_actions}"
    assert np.allclose(out, audio), "Audio should be unchanged when sub is within range"


# ---------------------------------------------------------------------------
# TC-616 — Sub at exactly range_min: no correction (boundary)
# ---------------------------------------------------------------------------

def test_tc616_sub_at_range_min_boundary():
    """AC4 boundary: source exactly at range_min (-3.747) → no correction."""
    audio = _white_stereo()
    pre_band_levels = {"sub": -3.747, "low_mid": 0.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert sub_actions == [], (
        f"Expected no sub action at range_min boundary, got {sub_actions}"
    )


# ---------------------------------------------------------------------------
# TC-617 — Sub at range_min − ε: correction triggered
# ---------------------------------------------------------------------------

def test_tc617_sub_just_below_range_min():
    """AC4 boundary: sub = -3.748 (1 milli-dB below range_min) → correction fires.
    EXPECTED TO FAIL: missing source_db / aim_point_db (DEF-601).
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": -3.748, "low_mid": 0.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1
    a = sub_actions[0]
    # required = -3.747 - (-3.748) = +0.001; within cap
    assert abs(a.applied_db - 0.001) < 1e-6
    assert a.cap_reached is False

    # Required fields — EXPECTED TO FAIL (DEF-601)
    assert hasattr(a, "source_db"), "Missing source_db (DEF-601)"
    assert hasattr(a, "aim_point_db"), "Missing aim_point_db (DEF-601)"


# ---------------------------------------------------------------------------
# TC-619 — Low band: informational only, no filter applied
# ---------------------------------------------------------------------------

def test_tc619_low_band_informational_only():
    """AC4, AC6: low band out-of-range → no SpectralCorrectiveAction for 'low'."""
    audio = _white_stereo()
    pre_band_levels = {"sub": 0.0, "low": 12.0, "low_mid": 0.0, "mid": 0.0}
    out, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    low_actions = [a for a in actions if a.band == "low"]
    assert low_actions == [], f"No 'low' band correction expected; got {low_actions}"
    assert np.allclose(out, audio), (
        "Audio should be unchanged when only low (informational) band is out of range"
    )


# ---------------------------------------------------------------------------
# TC-620 — Low_mid below range: range_compliance boost
# ---------------------------------------------------------------------------

def test_tc620_lowmid_below_range_boost():
    """AC4, AC15: low_mid = -1.0, aim = -0.145, required = +0.855.
    EXPECTED TO FAIL: missing source_db / aim_point_db (DEF-601).
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": 0.0, "low_mid": -1.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    lm_actions = [a for a in actions if a.band == "low_mid"]
    assert len(lm_actions) == 1
    a = lm_actions[0]
    assert a.trigger == "range_compliance"
    assert abs(a.applied_db - 0.855) < 0.001
    assert a.cap_reached is False
    assert abs(a.resulting_db - (-0.145)) < 0.001

    # Required fields — EXPECTED TO FAIL (DEF-601)
    assert hasattr(a, "source_db"), "Missing source_db (DEF-601)"
    assert abs(a.source_db - (-1.0)) < 1e-9

    assert hasattr(a, "aim_point_db"), "Missing aim_point_db (DEF-601)"
    assert abs(a.aim_point_db - (-0.145)) < 0.001


# ---------------------------------------------------------------------------
# TC-621 — Low_mid above range, below de-mud threshold: no correction
# ---------------------------------------------------------------------------

def test_tc621_lowmid_above_range_below_demud_no_correction():
    """AC4: low_mid = +3.0, within range [-0.145, +8.522] and below de-mud (>4.0).
    No action emitted (inside range, de-mud does not fire).
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": 0.0, "low_mid": 3.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    lm_actions = [a for a in actions if a.band == "low_mid"]
    assert lm_actions == [], (
        f"Expected no low_mid action (in range, de-mud not fired), got {lm_actions}"
    )


# ---------------------------------------------------------------------------
# TC-622 — De-mud fires, cap binds (source +7.0)
# ---------------------------------------------------------------------------

def test_tc622_demud_fires_cap_binds():
    """AC5, AC19: low_mid = +7.0, de-mud fires (7.0 > 4.0), cap binds.
    EXPECTED TO FAIL: missing source_db / aim_point_db (DEF-601).
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": 0.0, "low_mid": 7.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    lm_actions = [a for a in actions if a.band == "low_mid"]
    assert len(lm_actions) == 1
    a = lm_actions[0]
    assert a.trigger == "de_mud"
    # applied = clamp(2.0 - 7.0, -2.0, +2.0) = -2.0; cap reached
    assert abs(a.applied_db - (-2.0)) < 1e-9
    assert a.cap_reached is True
    assert abs(a.resulting_db - 5.0) < 0.001  # 7.0 - 2.0 = +5.0

    # Required fields — EXPECTED TO FAIL (DEF-601)
    assert hasattr(a, "source_db"), "Missing source_db (DEF-601)"
    assert abs(a.source_db - 7.0) < 1e-9

    assert hasattr(a, "aim_point_db"), "Missing aim_point_db (DEF-601)"
    assert abs(a.aim_point_db - 2.0) < 1e-9, (
        f"aim_point_db expected +2.0 (de-mud aim, not +3.394 median), got {a.aim_point_db}"
    )


# ---------------------------------------------------------------------------
# TC-623 — AC19 primary discriminator: aim_point_db == 2.0 for all de-mud cases
# ---------------------------------------------------------------------------

def test_tc623_ac19_aim_point_always_2_0():
    """AC19 (primary): de-mud fires at three source levels (4.5, 6.0, 10.0).
    All must log aim_point_db == 2.0, never 3.394.
    EXPECTED TO FAIL: SpectralCorrectiveAction missing aim_point_db (DEF-601).
    """
    audio = _white_stereo()

    for src in [4.5, 6.0, 10.0]:
        pre = {"sub": 0.0, "low_mid": src, "mid": 0.0}
        _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre)
        lm_actions = [a for a in actions if a.band == "low_mid"]
        assert len(lm_actions) == 1, f"Expected 1 low_mid action at src={src}"
        a = lm_actions[0]
        assert a.trigger == "de_mud", f"Expected de_mud trigger at src={src}"

        # PRIMARY DISCRIMINATOR — EXPECTED TO FAIL (DEF-601)
        assert hasattr(a, "aim_point_db"), (
            f"SpectralCorrectiveAction missing aim_point_db at src={src} (DEF-601)"
        )
        assert abs(a.aim_point_db - 2.0) < 1e-9, (
            f"aim_point_db expected 2.0 at src={src}, got {a.aim_point_db!r}. "
            "An impl using +3.394 (subset median) violates AC19."
        )


# ---------------------------------------------------------------------------
# TC-625 — De-mud fires within range, overrides no-correction rule
# ---------------------------------------------------------------------------

def test_tc625_demud_fires_within_range():
    """AC5: low_mid = +5.0, inside range [-0.145, +8.522] AND above de-mud threshold.
    De-mud overrides; correction IS applied.
    EXPECTED TO FAIL: missing aim_point_db (DEF-601).
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": 0.0, "low_mid": 5.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    lm_actions = [a for a in actions if a.band == "low_mid"]
    assert len(lm_actions) == 1, (
        f"De-mud must fire even when inside range (source +5.0 > threshold +4.0); got {lm_actions}"
    )
    a = lm_actions[0]
    assert a.trigger == "de_mud"

    # EXPECTED TO FAIL (DEF-601)
    assert hasattr(a, "aim_point_db"), "Missing aim_point_db (DEF-601)"
    assert abs(a.aim_point_db - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# TC-626 — De-mud at exactly threshold: no firing (strict >)
# ---------------------------------------------------------------------------

def test_tc626_demud_at_threshold_boundary():
    """AC5: low_mid = +4.0 exactly (= mid + 4.0). Strict > → does NOT fire."""
    audio = _white_stereo()
    pre_band_levels = {"sub": 0.0, "low_mid": 4.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    lm_actions = [a for a in actions if a.band == "low_mid"]
    assert lm_actions == [], (
        f"De-mud uses strict '>'; source +4.0 == threshold → no action. Got {lm_actions}"
    )


# ---------------------------------------------------------------------------
# TC-627 — De-mud at threshold + ε: fires
# ---------------------------------------------------------------------------

def test_tc627_demud_just_above_threshold():
    """AC5: low_mid = +4.001 (> 4.0) → de-mud fires; cap reached (4.001 > 2.0 + 2.0).
    EXPECTED TO FAIL: missing aim_point_db (DEF-601).
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": 0.0, "low_mid": 4.001, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    lm_actions = [a for a in actions if a.band == "low_mid"]
    assert len(lm_actions) == 1, f"Expected de-mud to fire at +4.001, got {lm_actions}"
    a = lm_actions[0]
    assert a.trigger == "de_mud"
    # required = 2.0 - 4.001 = -2.001; cap = 2.0 → applied = -2.0; cap_reached = True
    assert abs(a.applied_db - (-2.0)) < 1e-9
    assert a.cap_reached is True

    # EXPECTED TO FAIL (DEF-601)
    assert hasattr(a, "aim_point_db"), "Missing aim_point_db (DEF-601)"
    assert abs(a.aim_point_db - 2.0) < 1e-9


# ---------------------------------------------------------------------------
# TC-628 — AC18 negative control: no correction applied
# ---------------------------------------------------------------------------

def test_tc628_ac18_negative_control():
    """AC18: all bands within range, de-mud does not fire → zero actions."""
    from suno_mastering.mastering.stereo_width_corrector import apply_stereo_width_correction

    audio = _white_stereo()
    pre_band_levels = {"sub": -1.0, "low": 3.0, "low_mid": 2.0, "mid": 0.0,
                       "high_mid": -5.0, "high": -10.0, "air": -15.0}
    # sub -1.0 ∈ [-3.747, 1.944] ✓; low_mid 2.0 ∈ [-0.145, 8.522] ✓; not > 4.0 ✓
    _, eq_actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)
    assert eq_actions == [], f"Expected zero EQ actions, got {eq_actions}"

    # stereo_width key required by DEF-604/DEF-603 implementation;
    # sub=0.10 and low=0.10 are at/below threshold (0.15) so no actions fired.
    _sw = {"near_mono_threshold": 0.15, "correction_aim_point": 0.15,
           "correction_floor": 0.10, "max_correction_step": 0.15}
    width_targets = {"stereo_width": {"sub": _sw, "low": _sw}}
    pre_widths = {"sub": 0.10, "low": 0.10}
    _, w_actions = apply_stereo_width_correction(audio, SR, width_targets, pre_widths)
    assert w_actions == [], f"Expected zero width actions, got {w_actions}"


# ---------------------------------------------------------------------------
# TC-639 — EQ order: sub processed before low_mid
# ---------------------------------------------------------------------------

def test_tc639_eq_order_sub_before_lowmid():
    """AC9: sub shelf applied before low_mid bell in corrective_eq.py."""
    # Code-review check: read the file and confirm sub block precedes low_mid block
    corrective_eq_path = (
        Path(__file__).parent.parent
        / "suno_mastering" / "mastering" / "corrective_eq.py"
    )
    src = corrective_eq_path.read_text()

    idx_sub = src.find('band="sub"')
    if idx_sub == -1:
        idx_sub = src.find("band='sub'")
    idx_lm = src.find('band="low_mid"')
    if idx_lm == -1:
        idx_lm = src.find("band='low_mid'")

    assert idx_sub != -1, "Could not find sub band action in corrective_eq.py"
    assert idx_lm != -1, "Could not find low_mid band action in corrective_eq.py"
    assert idx_sub < idx_lm, (
        f"Sub band ({idx_sub}) must appear before low_mid band ({idx_lm}) "
        "in corrective_eq.py (AC9)"
    )

    # Functional confirmation: both corrections applied when both needed
    audio = _white_stereo()
    pre = {"sub": -6.247, "low_mid": 7.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre)
    bands = [a.band for a in actions]
    assert "sub" in bands and "low_mid" in bands, (
        f"Expected both sub and low_mid actions; got bands: {bands}"
    )
    # Sub action index < low_mid action index
    sub_idx = next(i for i, a in enumerate(actions) if a.band == "sub")
    lm_idx = next(i for i, a in enumerate(actions) if a.band == "low_mid")
    assert sub_idx < lm_idx, f"Sub action ({sub_idx}) must precede low_mid ({lm_idx})"


# ---------------------------------------------------------------------------
# TC-642 — High and air bands: no filter applied
# ---------------------------------------------------------------------------

def test_tc642_high_air_bands_no_filter():
    """AC6: high_mid/high/air far out of range → zero actions, audio unchanged."""
    audio = _white_stereo()
    pre = {"sub": 0.0, "low_mid": 0.0, "high_mid": -15.0, "high": -20.0, "air": -25.0, "mid": 0.0}
    out, actions = apply_corrective_eq(audio, SR, _TARGETS, pre)

    for band in ["high_mid", "high", "air"]:
        band_actions = [a for a in actions if a.band == band]
        assert band_actions == [], f"No action expected for band '{band}', got {band_actions}"

    assert np.allclose(out, audio), "Audio unchanged when only high/air bands are out of range"


# ---------------------------------------------------------------------------
# TC-643 — High_mid informational: no filter (Q3 resolution)
# ---------------------------------------------------------------------------

def test_tc643_high_mid_informational_only():
    """AC4, AC6: high_mid -15.0, far below range → no correction applied.
    Architecture Q3 resolution: high_mid is informational only.
    """
    audio = _white_stereo()
    pre = {"sub": 0.0, "low_mid": 0.0, "high_mid": -15.0, "mid": 0.0}
    out, actions = apply_corrective_eq(audio, SR, _TARGETS, pre)

    high_mid_actions = [a for a in actions if a.band == "high_mid"]
    assert high_mid_actions == [], (
        f"high_mid is informational; no correction expected. Got {high_mid_actions}"
    )
    assert np.allclose(out, audio), "Audio must be unchanged (no high_mid filter)"


# ---------------------------------------------------------------------------
# TC-650 — No hardcoded spectral target values in mastering source
# ---------------------------------------------------------------------------

def test_tc650_no_hardcoded_spectral_constants():
    """AC13: corrective_eq.py must not contain hardcoded spectral target values."""
    src_path = (
        Path(__file__).parent.parent
        / "suno_mastering" / "mastering" / "corrective_eq.py"
    )
    src = src_path.read_text()

    # Verbatim values from architecture §8.1 that must NOT be hardcoded
    forbidden_patterns = [
        r"0\.47",    # low range_min 0.471
        r"8\.52",    # low_mid range_max 8.522
        r"0\.145",   # low_mid range_min
        r"3\.394",   # de-mud wrong aim point (subset median)
        r"8\.617",   # low range_max
        r"1\.944",   # sub range_max
        r"3\.747",   # sub range_min (magnitude)
    ]
    for pat in forbidden_patterns:
        matches = re.findall(pat, src)
        assert not matches, (
            f"Hardcoded spectral constant matched by '{pat}' in corrective_eq.py: {matches} "
            "(AC13: spectral constants must come from targets dict)"
        )


# ---------------------------------------------------------------------------
# TC-651 — Retired config fields removed (Architectural)
# ---------------------------------------------------------------------------

def test_tc651_retired_config_fields_absent():
    """AC13: architecture §14 (as corrected by §23) specifies which fields are actually retired.

    DEF-610 notes that TC-651's original assertion of 8 fields was written against the stale
    §14 disposition.  Architecture §23 corrects this: only eq_max_gain_db is actually removed.
    Six other fields (thin_low_end_threshold_db, muddiness_threshold_db, harshness_threshold_db,
    freq_low_band_hz, freq_mud_band_hz, freq_presence_band_hz) are consumed by
    analysis/frequency_balance.py for Stage [2] and MUST be retained.
    reference_curve_path is retained because analysis/frequency_balance.py:44 calls
    config.reference_curve() — the §23 grep used the wrong method name.

    DEF-007 update: eq_max_gain_db has been added back to config.py as it is required by
    mastering/eq.py (old genre-curve EQ, still unit-tested via TC-060–065).  The §23 absence
    assertion is removed.  All other §23 retention assertions are unchanged.
    """
    config_path = (
        Path(__file__).parent.parent
        / "suno_mastering" / "config.py"
    )
    src = config_path.read_text()

    # targets_json_path must be present (new field per §14)
    assert "targets_json_path" in src, (
        "config.py missing 'targets_json_path' field (architecture §14)"
    )

    # reference_curve_path must be RETAINED (live code in analysis/frequency_balance.py:44)
    assert "reference_curve_path" in src, (
        "config.py must retain 'reference_curve_path' — it is a live Stage [2] dependency "
        "(analysis/frequency_balance.py:44 calls config.reference_curve()). "
        "Architecture §23 incorrectly marked it for removal; developer correctly retained it."
    )

    # Stage [2] frequency balance fields must be retained
    stage2_fields = [
        "thin_low_end_threshold_db",
        "muddiness_threshold_db",
        "harshness_threshold_db",
        "freq_low_band_hz",
        "freq_mud_band_hz",
        "freq_presence_band_hz",
    ]
    for f in stage2_fields:
        assert f in src, (
            f"config.py must retain '{f}' — it is consumed by analysis/frequency_balance.py "
            "(Stage [2] analysis). Architecture §14 incorrectly marked it for removal; §23 corrects this."
        )


# ---------------------------------------------------------------------------
# TC-654 — sosfiltfilt design parameter halved: delivered gain matches applied_db
# ---------------------------------------------------------------------------

def test_tc654_sosfiltfilt_gain_halved_correctly():
    """Architecture §5.2 BLOCKER 1 resolution: design param = applied/2 → sosfiltfilt doubles it.
    Verify: 20 Hz pure sine boosted by +2.0 dB applied_db → output gain ≈ +2.0 dB (not +4.0 dB).
    Tolerance: ±0.5 dB (shelf at 20 Hz, corner at 60 Hz — solidly in the plateau region).
    """
    # Use 5 s signal so filter transients are negligible relative to steady state
    n = int(SR * 5.0)
    t = np.arange(n) / SR
    freq = 20.0  # 20 Hz: 1/3 of shelf corner (60 Hz), firmly in shelf plateau
    amplitude = 0.01
    tone_20hz = amplitude * np.sin(2 * np.pi * freq * t).astype(np.float64)
    audio_stereo = np.stack([tone_20hz, tone_20hz], axis=1)

    # sub = -5.247: required = -3.747 - (-5.247) = +1.500; cap = 2.0 does not bind
    # applied_db = +1.500
    pre_band_levels = {"sub": -5.247, "low_mid": 0.0, "mid": 0.0}
    out, actions = apply_corrective_eq(audio_stereo, SR, _TARGETS, pre_band_levels)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1
    applied = sub_actions[0].applied_db
    assert applied > 0.0, f"Expected positive applied_db for sub below range, got {applied}"

    # Measure RMS of the output on the central 4s to avoid filter transients
    start = int(0.5 * SR)
    end = int(4.5 * SR)
    rms_before = np.sqrt(np.mean(tone_20hz[start:end] ** 2))
    rms_after_L = np.sqrt(np.mean(out[start:end, 0] ** 2))

    gain_db = 20.0 * np.log10(rms_after_L / rms_before)

    assert abs(gain_db - applied) < 0.5, (
        f"Expected gain at 20 Hz ≈ +{applied:.3f} dB (= applied_db), got {gain_db:.3f} dB. "
        f"If gain ≈ {2 * applied:.1f} dB, the design parameter was NOT halved before sosfiltfilt."
    )


# ---------------------------------------------------------------------------
# TC-655 — AC16 uses Stage [9] measurement, not resulting_db
# TC-656 — Mid-band bleed from low_mid bell cut
# These are pipeline-level checks; placed here as code-review assertions.
# ---------------------------------------------------------------------------

def test_tc655_ac16_source_distinction_documented():
    """AC16: resulting_db and Stage [9] are distinct quantities.
    TC-613 case: cap_reached=False, arithmetic resulting_db = range_min = -3.747.
    Stage [9] ≈ source + 0.60 × applied = -4.247 + 0.60 × 0.500 = -3.947 (below range_min).
    This test confirms the action log fields are arithmetically consistent and that
    resulting_db is NOT the Stage [9] measurement.
    """
    audio = _white_stereo()
    pre_band_levels = {"sub": -4.247, "low_mid": 0.0, "mid": 0.0}
    _, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    sub_actions = [a for a in actions if a.band == "sub"]
    assert len(sub_actions) == 1
    a = sub_actions[0]

    # Arithmetic log field check
    assert abs(a.resulting_db - (-3.747)) < 0.001, (
        f"resulting_db expected -3.747 (source + applied = -4.247 + 0.500), got {a.resulting_db}"
    )
    # Stage [9] expected ≈ -3.947; this differs from resulting_db (-3.747)
    # The test documents the gap rather than measuring Stage [9] directly here.
    # AC16 classification must use Stage [9], not resulting_db.

    # Plausibility: resulting_db must equal source_db + applied_db
    if hasattr(a, "source_db"):
        assert abs(a.resulting_db - (a.source_db + a.applied_db)) < 1e-9, (
            "resulting_db must equal source_db + applied_db (arithmetic identity)"
        )


def test_tc656_lowmid_bell_mid_bleed_documented():
    """AC14, architecture §5.3: low_mid peaking bell bleed into mid band.
    Code-review: corrective_eq uses _peaking_sos (bell), not _low_shelf_sos, for low_mid.
    A bell centered at 244.9 Hz (geometric mean of 120-500 Hz) has bandwidth 2.06 oct.
    At 500 Hz (mid band edge), the bell's tail bleeds approximately -0.15 dB per -2.0 dB cut.
    This test verifies the filter type (bell not shelf) and checks audio is modified.
    """
    from suno_mastering.mastering.corrective_eq import apply_corrective_eq

    audio = _white_stereo()
    # Trigger de-mud: low_mid = +7.0 → applied = -2.0 dB bell at ~244.9 Hz
    pre_band_levels = {"sub": 0.0, "low_mid": 7.0, "mid": 0.0}
    out, actions = apply_corrective_eq(audio, SR, _TARGETS, pre_band_levels)

    lm_actions = [a for a in actions if a.band == "low_mid"]
    assert len(lm_actions) == 1, "Expected one low_mid action for de-mud"
    a = lm_actions[0]
    assert abs(a.applied_db - (-2.0)) < 1e-9, f"Expected applied_db=-2.0, got {a.applied_db}"

    # Audio must be modified (filter was applied)
    assert not np.allclose(out, audio), "Audio must be modified by bell filter"

    # Code-review: low_mid uses _peaking_sos, not _low_shelf_sos
    src_path = (
        Path(__file__).parent.parent
        / "suno_mastering" / "mastering" / "corrective_eq.py"
    )
    src = src_path.read_text()
    assert "_peaking_sos" in src, (
        "corrective_eq.py must use _peaking_sos (bell) for low_mid band, not a shelf"
    )
