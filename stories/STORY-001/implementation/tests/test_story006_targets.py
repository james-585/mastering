"""STORY-006 test_story006_targets.py — TC-601 to TC-611

Tests for the targets_generator module (AC1, AC2, AC3, AC8, AC21).
All tests call targets_generator.main() directly and inspect the produced dict.

Architecture §8.1 and §9 provide the 3-dp expected values.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_TESTS_DIR = Path(__file__).resolve().parent
_IMPL_DIR = _TESTS_DIR.parent
_REPO_ROOT = _IMPL_DIR.parent.parent.parent  # stories/STORY-001/implementation/../../..  = suno-mastering/
_REAL_REPORT = _REPO_ROOT / "Reference Tracks" / "reference_set_report.json"

# Import the generator
from suno_mastering.targets.targets_generator import main as _generate
from suno_mastering.targets.targets_generator import CONTRIBUTING as _CONTRIBUTING

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_track_entry(label, sr, sub_db, low_db, low_mid_db, mid_db,
                      high_mid_db, high_db, air_db, sub_width, low_width,
                      low_mid_width, mid_width, high_mid_width, high_width,
                      air_width, dr_db):
    """Build a minimal reference_set_report entry."""
    bands_spectral = [
        {"band": "sub",      "relative_db": sub_db},
        {"band": "low",      "relative_db": low_db},
        {"band": "low_mid",  "relative_db": low_mid_db},
        {"band": "mid",      "relative_db": mid_db},
        {"band": "high_mid", "relative_db": high_mid_db},
        {"band": "high",     "relative_db": high_db},
        {"band": "air",      "relative_db": air_db},
    ]
    bands_width = [
        {"band": "sub",      "width": sub_width},
        {"band": "low",      "width": low_width},
        {"band": "low_mid",  "width": low_mid_width},
        {"band": "mid",      "width": mid_width},
        {"band": "high_mid", "width": high_mid_width},
        {"band": "high",     "width": high_width},
        {"band": "air",      "width": air_width},
    ]
    return {
        "label": label,
        "track_path": f"Reference Tracks/{label}.wav",
        "core": {"sample_rate": sr, "channels": 2, "duration_s": 300.0},
        "seven_band": {"bands": bands_spectral},
        "per_band_stereo_width": {"bands": bands_width},
        "dynamic_range_db_exact": dr_db,
    }


def _make_44100_report(tmp_path):
    """Synthetic report with three contributing tracks all at 44100 Hz (TC-605).
    Uses exact CONTRIBUTING labels to ensure generator fuzzy match works.
    """
    chem = _make_track_entry(
        _CONTRIBUTING[0], 44100,
        sub_db=1.944, low_db=8.617, low_mid_db=-0.145, mid_db=0.0,
        high_mid_db=-1.243, high_db=-4.060, air_db=-11.444,
        sub_width=0.009162, low_width=0.016501, low_mid_width=0.173498,
        mid_width=0.419776, high_mid_width=0.454781, high_width=0.128586,
        air_width=0.109759, dr_db=8.265556,
    )
    gusgus = _make_track_entry(
        _CONTRIBUTING[1], 44100,
        sub_db=-3.085, low_db=4.335, low_mid_db=3.394, mid_db=0.0,
        high_mid_db=-6.714, high_db=-9.772, air_db=-16.015,
        sub_width=0.001253, low_width=0.000782, low_mid_width=0.408491,
        mid_width=0.460980, high_mid_width=0.578686, high_width=0.160436,
        air_width=0.123844, dr_db=8.645556,
    )
    black_flute = _make_track_entry(
        _CONTRIBUTING[2], 44100,
        sub_db=-3.747, low_db=0.471, low_mid_db=8.522, mid_db=0.0,
        high_mid_db=-13.408, high_db=-17.062, air_db=-20.053,
        sub_width=0.040360, low_width=0.146910, low_mid_width=0.173498,
        mid_width=0.669595, high_mid_width=0.608460, high_width=0.656631,
        air_width=0.126876, dr_db=6.598619,
    )
    leftfield = _make_track_entry(
        "Leftfield Melt", 44100,
        sub_db=-1.0, low_db=2.0, low_mid_db=0.5, mid_db=0.0,
        high_mid_db=-5.0, high_db=-10.0, air_db=-15.0,
        sub_width=0.1, low_width=0.1, low_mid_width=0.2, mid_width=0.3,
        high_mid_width=0.4, high_width=0.5, air_width=0.6, dr_db=9.0,
    )
    wavy = _make_track_entry(
        "Wavy Gravy", 44100,
        sub_db=-2.0, low_db=3.0, low_mid_db=1.0, mid_db=0.0,
        high_mid_db=-4.0, high_db=-8.0, air_db=-12.0,
        sub_width=0.05, low_width=0.1, low_mid_width=0.25, mid_width=0.35,
        high_mid_width=0.45, high_width=0.55, air_width=0.65, dr_db=8.0,
    )
    report = [chem, gusgus, black_flute, leftfield, wavy]
    p = tmp_path / "report_44100.json"
    p.write_text(json.dumps(report), encoding="utf-8")
    return str(p)


def _run_generator(report_path, tmp_path, suffix="targets.json"):
    out = str(tmp_path / suffix)
    _generate(report_path, out)
    with open(out, encoding="utf-8") as f:
        return json.load(f), out


# ---------------------------------------------------------------------------
# TC-601 — Generator provenance block: contributing tracks only
# ---------------------------------------------------------------------------

def test_tc601_provenance_contributing_only(tmp_path):
    """AC1: provenance.contributing_tracks contains exactly the 3 required entries;
    excluded_tracks contains Leftfield and Wavy Gravy only."""
    if not _REAL_REPORT.exists():
        pytest.skip("reference_set_report.json not found")

    targets, _ = _run_generator(str(_REAL_REPORT), tmp_path)

    prov = targets["provenance"]
    contributing = prov["contributing_tracks"]
    excluded = prov["excluded_tracks"]

    # Use CONTRIBUTING constant from the generator to avoid string encoding ambiguity
    expected_contrib = set(_CONTRIBUTING)
    assert set(contributing) == expected_contrib, (
        f"Expected contributing tracks {expected_contrib}, got {set(contributing)}"
    )
    assert len(contributing) == 3

    # Check contributing track content by keyword (avoids em-dash encoding comparison on Windows)
    contrib_str = " ".join(contributing).lower()
    assert "chemical" in contrib_str, f"Chemical Brothers not found in contributing: {contributing}"
    assert "gusgus" in contrib_str or "gus" in contrib_str, f"GusGus not found: {contributing}"
    assert "black flute" in contrib_str or "black" in contrib_str, f"Black Flute not found: {contributing}"

    # Excluded must name Leftfield and Wavy Gravy (exact match or substring)
    excluded_str = " ".join(excluded).lower()
    assert "leftfield" in excluded_str, f"'Leftfield' not in excluded_tracks: {excluded}"
    assert "wavy" in excluded_str, f"'Wavy Gravy' not in excluded_tracks: {excluded}"


# ---------------------------------------------------------------------------
# TC-602 — Hard targets match specified values (key names)
# ---------------------------------------------------------------------------

def test_tc602_hard_targets(tmp_path):
    """AC3: hard_targets must have specific key names from architecture §7/§8.
    Derivation: target_median=8.26, range_min=6.60, range_max=8.65.
    EXPECTED TO FAIL: generator uses {median, min, max} not {target_median, range_min, range_max}.
    """
    if not _REAL_REPORT.exists():
        pytest.skip("reference_set_report.json not found")

    targets, _ = _run_generator(str(_REAL_REPORT), tmp_path)
    ht = targets["hard_targets"]

    assert ht["integrated_lufs"]["value"] == -13.5
    assert ht["true_peak_dbtp"]["ceiling"] == -1.0

    dr = ht["dynamic_range_db"]
    # architecture §7.3 requires these key names
    assert "target_median" in dr, (
        f"dynamic_range_db missing 'target_median' key; got keys: {list(dr.keys())} "
        "(DEF-604: generator uses 'median' not 'target_median')"
    )
    assert "range_min" in dr, (
        f"dynamic_range_db missing 'range_min' key; got keys: {list(dr.keys())} "
        "(DEF-604: generator uses 'min' not 'range_min')"
    )
    assert "range_max" in dr, (
        f"dynamic_range_db missing 'range_max' key; got keys: {list(dr.keys())} "
        "(DEF-604: generator uses 'max' not 'range_max')"
    )
    # Values (checked after key names so failure is informative)
    assert abs(dr["target_median"] - 8.26) < 0.01
    assert abs(dr["range_min"] - 6.60) < 0.01
    assert abs(dr["range_max"] - 8.65) < 0.01


# ---------------------------------------------------------------------------
# TC-603 — Sub band statistics and required fields
# ---------------------------------------------------------------------------

def test_tc603_sub_band_statistics(tmp_path):
    """AC2, AC3: spectral_bands.sub must have correct values AND classification/correction_cap_db.
    EXPECTED TO FAIL on classification and correction_cap_db (not emitted by generator).
    """
    if not _REAL_REPORT.exists():
        pytest.skip("reference_set_report.json not found")

    targets, _ = _run_generator(str(_REAL_REPORT), tmp_path)
    sub = targets["spectral_bands"]["sub"]

    # Values should be correct (architecture §8.1)
    assert abs(sub["range_db_re_mid"]["min"] - (-3.747)) < 0.002, (
        f"sub range_min expected -3.747, got {sub['range_db_re_mid']['min']}"
    )
    assert abs(sub["range_db_re_mid"]["max"] - 1.944) < 0.002, (
        f"sub range_max expected +1.944, got {sub['range_db_re_mid']['max']}"
    )
    assert abs(sub["median_db_re_mid"] - (-3.085)) < 0.002, (
        f"sub median expected -3.085, got {sub['median_db_re_mid']}"
    )
    assert sub["freq_hz"] == [20, 60], f"sub freq_hz expected [20, 60], got {sub['freq_hz']}"

    # Required fields per architecture §7.3 — EXPECTED TO FAIL
    assert "classification" in sub, (
        "spectral_bands.sub missing 'classification' field (DEF-604: generator omits this) "
        "expected 'soft'"
    )
    assert sub["classification"] == "soft"

    assert "correction_cap_db" in sub, (
        "spectral_bands.sub missing 'correction_cap_db' field (DEF-604: generator omits this) "
        "expected 2.0"
    )
    assert sub["correction_cap_db"] == 2.0


# ---------------------------------------------------------------------------
# TC-604 — Low_mid band statistics and de-mud block
# ---------------------------------------------------------------------------

def test_tc604_lowmid_band_and_demud(tmp_path):
    """AC2, AC5: low_mid values and de_mud block must match architecture §8.1.
    EXPECTED TO FAIL on de_mud.applies_to_band (not emitted by generator).
    """
    if not _REAL_REPORT.exists():
        pytest.skip("reference_set_report.json not found")

    targets, _ = _run_generator(str(_REAL_REPORT), tmp_path)
    lm = targets["spectral_bands"]["low_mid"]
    dm = targets["de_mud"]

    assert abs(lm["range_db_re_mid"]["min"] - (-0.145)) < 0.002
    assert abs(lm["range_db_re_mid"]["max"] - 8.522) < 0.002
    assert abs(lm["median_db_re_mid"] - 3.394) < 0.002

    assert dm["flag_threshold_db_above_mid"] == 4.0
    assert dm["correction_aim_point_db"] == 2.0, (
        f"de_mud.correction_aim_point_db expected 2.0 (not 3.394), got {dm['correction_aim_point_db']}"
    )

    # Required field per architecture §7.4 — EXPECTED TO FAIL
    assert "applies_to_band" in dm, (
        "de_mud missing 'applies_to_band' field (DEF-604: generator omits this) "
        "expected 'low_mid'"
    )
    assert dm["applies_to_band"] == "low_mid"


# ---------------------------------------------------------------------------
# TC-605 — Air band upper edge resolved correctly
# ---------------------------------------------------------------------------

def test_tc605_air_band_upper_edge(tmp_path):
    """AC2, AC8: air band upper edge = min(24000, min Nyquist of contributing tracks).
    Using synthetic 44100 Hz fixture: expected upper edge = 22050.
    EXPECTED TO FAIL on freq_hz[0] = 10000: generator uses int(air_upper * 0.6) = 13230.
    """
    report_path = _make_44100_report(tmp_path)
    targets, _ = _run_generator(report_path, tmp_path, "targets_605.json")

    air = targets["spectral_bands"]["air"]
    air_freq = air["freq_hz"]

    # Upper edge: min(24000, 44100//2) = min(24000, 22050) = 22050
    assert air_freq[1] == 22050, (
        f"Air band upper edge expected 22050 Hz (for 44100 Hz tracks), got {air_freq[1]}"
    )

    # Lower edge: architecture §8.1 defines air band as [10000, 22050]
    # Generator uses int(air_upper * 0.6) = 13230 — EXPECTED TO FAIL (DEF-604)
    assert air_freq[0] == 10000, (
        f"Air band lower edge expected 10000 Hz (seven-band scheme boundary), "
        f"got {air_freq[0]} (DEF-604: generator uses 60% of air_upper = {int(air_freq[1] * 0.6)})"
    )


# ---------------------------------------------------------------------------
# TC-606 — All value fields are numeric literals
# ---------------------------------------------------------------------------

def test_tc606_all_values_numeric(tmp_path):
    """AC8: every value field in targets.json must be a numeric type (float/int), not string."""
    if not _REAL_REPORT.exists():
        pytest.skip("reference_set_report.json not found")

    targets, _ = _run_generator(str(_REAL_REPORT), tmp_path)

    def check_numeric(name, val):
        assert isinstance(val, (int, float)), (
            f"{name} is not numeric: {val!r} (type {type(val).__name__})"
        )

    ht = targets["hard_targets"]
    check_numeric("integrated_lufs.value", ht["integrated_lufs"]["value"])
    check_numeric("true_peak_dbtp.ceiling", ht["true_peak_dbtp"]["ceiling"])

    for band, bdata in targets["spectral_bands"].items():
        check_numeric(f"spectral_bands.{band}.range_db_re_mid.min", bdata["range_db_re_mid"]["min"])
        check_numeric(f"spectral_bands.{band}.range_db_re_mid.max", bdata["range_db_re_mid"]["max"])
        check_numeric(f"spectral_bands.{band}.median_db_re_mid", bdata["median_db_re_mid"])

    dm = targets["de_mud"]
    check_numeric("de_mud.flag_threshold_db_above_mid", dm["flag_threshold_db_above_mid"])
    check_numeric("de_mud.correction_aim_point_db", dm["correction_aim_point_db"])


# ---------------------------------------------------------------------------
# TC-607 — Excluded tracks removed from report: no derived value changes
# ---------------------------------------------------------------------------

def test_tc607_excluded_tracks_do_not_affect_derived_values(tmp_path):
    """AC21: removing Leftfield and Wavy Gravy from the input report must not
    change any numeric derived value."""
    report_path = _make_44100_report(tmp_path)
    targets_a, _ = _run_generator(report_path, tmp_path, "targets_A.json")

    # Build report without excluded tracks
    with open(report_path, encoding="utf-8") as f:
        entries = json.load(f)

    contributing_labels = {
        "chemical brothers", "gusgus", "black flute",
    }
    kept = [
        e for e in entries
        if any(kw in e["label"].lower() for kw in contributing_labels)
        or e["label"] in _CONTRIBUTING
    ]
    report_b = tmp_path / "report_B.json"
    report_b.write_text(json.dumps(kept), encoding="utf-8")

    targets_b, _ = _run_generator(str(report_b), tmp_path, "targets_B.json")

    # Compare all spectral band numeric values
    for band in ["sub", "low", "low_mid", "mid", "high_mid", "high", "air"]:
        a_min = targets_a["spectral_bands"][band]["range_db_re_mid"]["min"]
        b_min = targets_b["spectral_bands"][band]["range_db_re_mid"]["min"]
        assert a_min == b_min, f"band {band} range_min differs: A={a_min}, B={b_min}"

        a_max = targets_a["spectral_bands"][band]["range_db_re_mid"]["max"]
        b_max = targets_b["spectral_bands"][band]["range_db_re_mid"]["max"]
        assert a_max == b_max, f"band {band} range_max differs: A={a_max}, B={b_max}"

        a_med = targets_a["spectral_bands"][band]["median_db_re_mid"]
        b_med = targets_b["spectral_bands"][band]["median_db_re_mid"]
        assert a_med == b_med, f"band {band} median differs: A={a_med}, B={b_med}"


# ---------------------------------------------------------------------------
# TC-608 — Contributing track perturbation shifts output
# ---------------------------------------------------------------------------

def test_tc608_contributing_track_perturbation_shifts_output(tmp_path):
    """AC21: changing a contributing track's value changes the derived target."""
    report_path = _make_44100_report(tmp_path)
    targets_a, _ = _run_generator(report_path, tmp_path, "targets_A.json")

    with open(report_path, encoding="utf-8") as f:
        entries = json.load(f)

    # Shift Chemical Brothers low_mid from -0.145 to -2.145
    for e in entries:
        if "Chemical Brothers" in e["label"] or "chemical" in e["label"].lower():
            for b in e["seven_band"]["bands"]:
                if b["band"] == "low_mid":
                    b["relative_db"] = -2.145

    report_c = tmp_path / "report_C.json"
    report_c.write_text(json.dumps(entries), encoding="utf-8")
    targets_c, _ = _run_generator(str(report_c), tmp_path, "targets_C.json")

    a_min = targets_a["spectral_bands"]["low_mid"]["range_db_re_mid"]["min"]
    c_min = targets_c["spectral_bands"]["low_mid"]["range_db_re_mid"]["min"]
    assert abs(a_min - (-0.145)) < 0.002, f"Fixture A low_mid min expected -0.145, got {a_min}"
    assert abs(c_min - (-2.145)) < 0.002, f"Fixture C low_mid min expected -2.145, got {c_min}"


# ---------------------------------------------------------------------------
# TC-609 — Missing reference_set_report.json → FileNotFoundError
# ---------------------------------------------------------------------------

def test_tc609_missing_report_raises(tmp_path):
    """Architecture §16: generator must fail with an explicit error on missing input."""
    missing = str(tmp_path / "nonexistent_report.json")
    with pytest.raises((FileNotFoundError, OSError)):
        _generate(missing, str(tmp_path / "targets.json"))


# ---------------------------------------------------------------------------
# TC-610 — Missing contributing track → ValueError
# ---------------------------------------------------------------------------

def test_tc610_missing_contributing_track_raises(tmp_path):
    """AC1, architecture §4.2, §16: ValueError if Chemical Brothers absent."""
    # Build report with only GusGus and Black Flute
    report_path = _make_44100_report(tmp_path)
    with open(report_path, encoding="utf-8") as f:
        entries = json.load(f)
    filtered = [
        e for e in entries
        if "chemical" not in e["label"].lower()
    ]
    report_d = tmp_path / "report_D.json"
    report_d.write_text(json.dumps(filtered), encoding="utf-8")

    with pytest.raises(ValueError):
        _generate(str(report_d), str(tmp_path / "targets.json"))


# ---------------------------------------------------------------------------
# TC-611 — Stereo width statistics in targets.json
# ---------------------------------------------------------------------------

def test_tc611_stereo_width_in_targets(tmp_path):
    """AC2: targets.json must contain stereo_width block with per-band correction params.
    EXPECTED TO FAIL: generator emits 'per_band_stereo_width' (no correction params),
    not 'stereo_width' with near_mono_threshold/correction_aim_point/correction_floor/
    max_correction_step (DEF-604).
    """
    if not _REAL_REPORT.exists():
        pytest.skip("reference_set_report.json not found")

    targets, _ = _run_generator(str(_REAL_REPORT), tmp_path)

    # Architecture §7.5 requires this top-level key
    assert "stereo_width" in targets, (
        f"targets.json missing 'stereo_width' key; found 'per_band_stereo_width' instead. "
        f"Keys: {list(targets.keys())} (DEF-604)"
    )
    sw = targets["stereo_width"]

    # Per-track sub widths from architecture §8.2: Chemical=0.00916, GusGus=0.00125, Black=0.04036
    sub_sw = sw["sub"]
    assert abs(sub_sw["min"] - 0.001) < 0.001, f"sub width min expected ~0.001, got {sub_sw['min']}"
    assert abs(sub_sw["median"] - 0.009) < 0.002
    assert abs(sub_sw["max"] - 0.040) < 0.002

    # Required correction parameters per architecture §7.5 — EXPECTED TO FAIL
    assert "near_mono_threshold" in sub_sw, (
        "stereo_width.sub missing 'near_mono_threshold' (DEF-604)"
    )
    assert sub_sw["near_mono_threshold"] == 0.15
    assert "correction_aim_point" in sub_sw, "stereo_width.sub missing 'correction_aim_point'"
    assert sub_sw["correction_aim_point"] == 0.15
    assert "correction_floor" in sub_sw, "stereo_width.sub missing 'correction_floor'"
    assert sub_sw["correction_floor"] == 0.10
    assert "max_correction_step" in sub_sw, "stereo_width.sub missing 'max_correction_step'"
    assert sub_sw["max_correction_step"] == 0.15

    # Low band width
    low_sw = sw["low"]
    assert abs(low_sw["max"] - 0.147) < 0.002, f"low width max expected ~0.147, got {low_sw['max']}"
