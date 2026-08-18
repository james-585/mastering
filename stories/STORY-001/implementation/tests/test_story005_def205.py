"""STORY-005 automated tests (DEF-205: per-segment gate false positive,
Chemical Brothers).

Test cases TC-500 through TC-521 per stories/STORY-005/test-cases.md
(TC-508 is folded into TC-500 per that document's own note; TC-520 -- full
existing-suite non-regression -- is exercised by the fast + slow runs of
test_ground_truth_hf_extension.py itself, not duplicated here).

Fast tests (no marker): TC-500, TC-501, TC-502, TC-503a, TC-503b, TC-504,
TC-505, TC-506, TC-513, TC-514, TC-515, TC-516, TC-517, TC-518, TC-519,
TC-521.
Slow tests (@pytest.mark.slow): TC-507, TC-509, TC-510, TC-511, TC-512.

Key invariants under test:
  - per_segment_reliability_caveat fires on NON-None disagreements only, never
    on None abstentions (AC5b OR-vs-AND bug guard, TC-513, TC-512 real-data
    fallback).
  - hf_band_limit_whole_track_margin_db is populated iff hf_band_limit_hz is
    not None (AC3, TC-503/TC-504).
  - Both new fields are reflected in JSON/markdown rendering (AC5c, TC-505,
    TC-506, TC-518).
  - SCHEMA_VERSION == "2.2" (NFR, TC-500).
  - Exactly one of the five reference tracks fires the caveat (Chemical
    Brothers only, gate1-review F5, TC-512).
  - 25-segment audit reproduces 20 CORRECT / 4 ABSTAIN / 1 FALSE-POSITIVE
    (AC1 under option-c scoping, TC-509).

Note on 20475 Hz spread across reference tracks: Leftfield, Chemical
Brothers, and Wavy Gravy all report WT=20475 Hz. This is NOT suspicious
narrow spread -- 20475 Hz is a 1/24-octave grid band centre near Nyquist
(44100 Hz), and full-band tracks with content to Nyquist quantise to the
same grid point. This is grid quantisation, documented in architecture
§3.2/§3.5, not a measurement artefact.
"""
from __future__ import annotations

import dataclasses
import os
from datetime import datetime, timezone
from typing import List, Optional

import numpy as np
import pytest
import soundfile as sf

from suno_mastering.analysis import _psd
from suno_mastering.analysis.hf_extension import _detect_cliff, measure_hf_extension
from suno_mastering.analysis.reference_types import HfExtensionResult
from suno_mastering.report.reference_builder import SCHEMA_VERSION, ReferenceSetReport
from suno_mastering.report.reference_render import render_markdown

from .ref_helpers import (
    brickwall_lowpass_noise_mono,
    brickwall_lowpass_noise_with_floor_mono,
    make_stub_measurements,
    ref_config,
    to_stereo,
    white_noise_mono,
)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------
SR = 44100
REF_DIR = "C:/Users/james/Documents/suno-mastering/Reference Tracks"
TRACK_NAMES = [
    "Black_Flute_Remastered.wav",
    "GusGus_-_Over_Arabian_Horse_Album.wav",
    "Leftfield_-_Melt_Audio.wav",
    "The_Chemical_Brothers_-_Live_Again_ft_Halo_Maud.wav",
    "Wavy_Gravy.wav",
]
CHEM_BROTHERS = "The_Chemical_Brothers_-_Live_Again_ft_Halo_Maud.wav"


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _drift_fixture():
    """TC-025 three-step drift fixture: brickwall at 15 kHz (1.5s),
    12 kHz (1.5s), 8 kHz (1.5s) = 4.5s total. Reused by TC-501,
    TC-514, TC-515, TC-516, TC-517."""
    p1 = brickwall_lowpass_noise_mono(SR, duration_s=1.5, cutoff_hz=15000.0, seed=1, amplitude=0.3)
    p2 = brickwall_lowpass_noise_mono(SR, duration_s=1.5, cutoff_hz=12000.0, seed=2, amplitude=0.3)
    p3 = brickwall_lowpass_noise_mono(SR, duration_s=1.5, cutoff_hz=8000.0, seed=3, amplitude=0.3)
    return to_stereo(np.concatenate([p1, p2, p3]))


def _make_report_with_hf(hf_result: HfExtensionResult) -> ReferenceSetReport:
    """Wrap a single HfExtensionResult in a minimal ReferenceSetReport for
    render_markdown / render_json tests (TC-506, TC-518)."""
    stub = make_stub_measurements("test/track.wav")
    stub_with_hf = dataclasses.replace(stub, hf_extension=hf_result)
    return ReferenceSetReport(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        decoder_identity={"lib": "test"},
        tool_version="test",
        config_summary={},
        per_track=[stub_with_hf],
    )


# ---------------------------------------------------------------------------
# Session-scoped fixture for reference track ground-truth tests
# (TC-509, TC-510, TC-511, TC-512 -- all @pytest.mark.slow)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ref_track_results():
    """Load and analyse all five reference tracks once per session.
    Skips the whole fixture (and all tests that depend on it) if any
    track file is not found on disk."""
    config = ref_config()
    results = {}
    for fname in TRACK_NAMES:
        path = os.path.join(REF_DIR, fname)
        if not os.path.exists(path):
            pytest.skip(f"Reference track not found: {path}")
        audio, sr = sf.read(path)
        results[fname] = measure_hf_extension(audio, sr, config)
    return results


# ===========================================================================
# Fast tests
# ===========================================================================

def test_tc500_schema_version_constant_and_report_field():
    """TC-500 (NFR Schema version bump; TC-508 folded in per test-cases.md):
    SCHEMA_VERSION constant == "2.2", and a ReferenceSetReport's own
    schema_version field (defaulting from the module constant) also reads
    "2.2". test_ref_ac9_output.py::test_tc292 is updated separately (step 4
    of this TC, per test-cases.md) to assert "2.2" instead of "2.1"."""
    assert SCHEMA_VERSION == "2.2", (
        f"Expected SCHEMA_VERSION='2.2' (STORY-005 additive fields); "
        f"got {SCHEMA_VERSION!r}"
    )
    report = ReferenceSetReport(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        decoder_identity={"lib": "test"},
        tool_version="test",
        config_summary={},
        per_track=[],
    )
    assert report.schema_version == "2.2", (
        f"ReferenceSetReport.schema_version should default to SCHEMA_VERSION='2.2'; "
        f"got {report.schema_version!r}"
    )


def test_tc501_caveat_fires_on_drift_fixture():
    """TC-501 (AC5a, AC6c): the TC-025 three-step drift fixture (15k→12k→8k)
    triggers per_segment_reliability_caveat. Segments 2-4 return non-None
    values (12 kHz and 8 kHz) disagreeing with WT (~15 kHz) by 3000 Hz and
    7000 Hz respectively -- both exceed hf_stability_tolerance_hz (2000 Hz).

    Precondition check: asserts that at least one segment's deviation
    actually exceeds the tolerance before checking the caveat, so a
    shifted WT gives a diagnostic rather than a silent caveat failure
    (test-cases.md TC-501 preconditions: proof by construction from TC-025's
    own assertions).

    Steps 3-6 per test-cases.md: caveat not None, non-empty, contains
    'false positive' (AC5a), and contains a reference to the actual
    tolerance value from config ('2000', the default -- not a hardcoded
    literal; TC-516 proves this is genuine interpolation, not coincidence,
    using a non-default tolerance)."""
    audio = _drift_fixture()
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is not None, \
        f"Precondition: whole-track must find a cliff near 15 kHz; got None. " \
        f"per_segment={result.per_segment_hf_band_limit_hz}"

    non_none = [s for s in result.per_segment_hf_band_limit_hz if s is not None]
    d = max((abs(s - result.hf_band_limit_hz) for s in non_none), default=0.0)
    assert d > config.hf_stability_tolerance_hz, (
        f"Precondition: max per-segment deviation {d:.0f} Hz must exceed "
        f"tolerance {config.hf_stability_tolerance_hz:.0f} Hz. "
        f"Segs: {result.per_segment_hf_band_limit_hz}"
    )

    caveat = result.per_segment_reliability_caveat
    assert caveat is not None, (
        f"Caveat must fire on drift fixture. "
        f"WT={result.hf_band_limit_hz:.0f} Hz, "
        f"segs={result.per_segment_hf_band_limit_hz}"
    )
    assert len(caveat) > 0, "Caveat string must be non-empty"
    assert "false positive" in caveat, (
        f"AC5(a): 'false positive' not found in caveat: {caveat!r}"
    )
    assert "2000" in caveat, (
        f"Caveat must reference the actual tolerance value from config "
        f"(default 2000 Hz), not omit it: {caveat!r}"
    )


def test_tc502_caveat_none_for_clean_detection():
    """TC-502 (AC5, AC6c, negative control -- non-regression): a stationary
    brickwall at 15 kHz (TC-020's signal) produces the same cliff in every
    segment. All per-segment values agree with the whole-track value within
    hf_stability_tolerance_hz -- no disagreement exists to trigger the
    caveat. Any non-None caveat here is an over-fire defect (architecture
    §11 R2 risk)."""
    mono = brickwall_lowpass_noise_mono(SR, duration_s=3.0, cutoff_hz=15000.0, seed=1, amplitude=0.3)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is not None, \
        "Precondition: stationary 15 kHz brickwall must produce a cliff"
    assert result.per_segment_reliability_caveat is None, (
        f"Over-fire defect (architecture §11 R2): caveat fired on a clean, "
        f"stationary detection with no genuine per-segment disagreement. "
        f"WT={result.hf_band_limit_hz}, "
        f"per_segment={result.per_segment_hf_band_limit_hz}, "
        f"caveat={result.per_segment_reliability_caveat!r}"
    )


def test_tc503a_whole_track_margin_equals_robustness_when_one_segment():
    """TC-503a (AC3, test-cases.md TC-503 Sub-case A -- digital-zero
    brickwall, leftward-dominated, TC-431 fixture): when
    hf_stability_segment_count=1 the single segment is exactly the active
    audio. Both _detect_cliff calls (whole-track and segment) receive the
    same PSD from the same data, so hf_band_limit_whole_track_margin_db ==
    hf_band_limit_robustness_db exactly (same j*, same L, same suffix_max)
    -- a wiring check (architecture R3 risk).

    Fixture: brickwall_lowpass_noise_mono(SR=44100, duration_s=3.0,
    cutoff_hz=16000.0, seed=1, amplitude=0.3), exactly per test-cases.md
    TC-503 Sub-case A preconditions. Digital-zero stopband:
    j* = i_max + 1; leftward margin = levels_db[i_max] - L =
    hf_cliff_required_drop_db = 8.0 dB exactly; rightward margin >> 8 dB.
    Two-sided minimum = 8.0 dB (empirically confirmed 8.0 dB exactly at
    this seed/duration). Expected ≈ 8.0 ± 1.0 dB per test-cases.md."""
    mono = brickwall_lowpass_noise_mono(SR, duration_s=3.0, cutoff_hz=16000.0,
                                        seed=1, amplitude=0.3)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0, hf_stability_segment_count=1)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is not None, \
        "Precondition: brickwall at 16 kHz must produce a cliff"
    assert result.hf_band_limit_robustness_db is not None, \
        "hf_band_limit_robustness_db must be populated for n_segments=1"
    assert result.hf_band_limit_whole_track_margin_db is not None, \
        "hf_band_limit_whole_track_margin_db must be populated when cliff found"

    # Wiring assertion (test-cases.md TC-503, "Wiring assertion (Sub-case A
    # only)"): a large difference indicates the developer assigned the
    # wrong variable to one of the two fields.
    delta = abs(result.hf_band_limit_whole_track_margin_db - result.hf_band_limit_robustness_db)
    assert delta < 1.0, (
        f"n_segments=1: whole_track_margin={result.hf_band_limit_whole_track_margin_db:.6f} dB "
        f"and robustness={result.hf_band_limit_robustness_db:.6f} dB must be nearly equal "
        f"(same PSD, same computation). Delta={delta:.4f} dB"
    )
    # Plausibility: near 8 dB (leftward margin = required_drop_db)
    assert result.hf_band_limit_whole_track_margin_db == pytest.approx(8.0, abs=1.0), (
        f"Digital-zero brickwall: whole_track_margin expected ~8 dB; "
        f"got {result.hf_band_limit_whole_track_margin_db:.3f} dB"
    )
    assert result.hf_band_limit_whole_track_margin_db > 0.0, \
        "Sanity bound: margin must be positive"


def test_tc503b_whole_track_margin_finite_floor():
    """TC-503b (AC3, test-cases.md TC-503 Sub-case B -- finite-floor
    brickwall, rightward-dominated, TC-430 fixture): brickwall with a
    finite stopband floor (floor_below_db=10) constrains the rightward
    j* margin.

    Fixture: brickwall_lowpass_noise_with_floor_mono(SR=44100,
    duration_s=3.0, cutoff_hz=16000.0, floor_below_db=10.0, seed=1,
    passband_sigma=0.15), exactly per test-cases.md TC-503 Sub-case B
    preconditions. By construction, rightward margin =
    floor_below_db - hf_cliff_required_drop_db = 10 - 8 = 2.0 dB nominally;
    leftward margin ≈ 8.0 dB; two-sided min = rightward ≈ 2.0 dB.
    Empirically confirmed 1.878 dB at this seed/duration -- inside the
    test-cases.md 2.0 ± 0.5 dB tolerance band (the small deviation from the
    nominal 2.0 dB reflects ordinary Welch-PSD/log-band-averaging noise
    over a 3s window, not a defect)."""
    mono = brickwall_lowpass_noise_with_floor_mono(
        SR, duration_s=3.0, cutoff_hz=16000.0, floor_below_db=10.0,
        seed=1, passband_sigma=0.15)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0, hf_stability_segment_count=1)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is not None, \
        "Precondition: brickwall with 10 dB floor must produce a cliff"
    assert result.hf_band_limit_whole_track_margin_db is not None, \
        "hf_band_limit_whole_track_margin_db must be populated when cliff found"
    assert result.hf_band_limit_robustness_db is not None, \
        "hf_band_limit_robustness_db must be populated for n_segments=1"

    assert result.hf_band_limit_whole_track_margin_db == pytest.approx(2.0, abs=0.5), (
        f"10 dB floor: whole_track_margin expected ~2 dB (rightward-dominated); "
        f"got {result.hf_band_limit_whole_track_margin_db:.3f} dB. "
        f"A value near 8.0 dB would indicate the implementation returned the "
        f"leftward margin rather than the two-sided minimum."
    )
    assert result.hf_band_limit_whole_track_margin_db > 0.0, \
        "Sanity bound: margin must be positive"


def test_tc504_whole_track_margin_none_when_no_cliff():
    """TC-504 (AC5 None-branch coverage, AC6c): hf_band_limit_whole_track_margin_db
    is None when whole-track finds no cliff (white noise, 3s). The field is
    only populated when whole_track_result is not None in hf_extension.py
    lines 323-326 -- this test exercises that guard."""
    mono = white_noise_mono(SR, duration_s=3.0, seed=2, amplitude=0.2)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is None, (
        f"Precondition: white noise must produce no cliff; "
        f"got {result.hf_band_limit_hz}"
    )
    assert result.hf_band_limit_whole_track_margin_db is None, (
        "hf_band_limit_whole_track_margin_db must be None when no cliff found"
    )


def test_tc505_caveat_propagates_to_json_via_asdict():
    """TC-505 (AC5, AC6c): dataclasses.asdict(result) (the same mechanism
    render_json uses at reference_render.py line 25) propagates both new
    fields, using the TC-025 drift fixture's genuine non-None caveat (no
    hand-built fixture needed -- this test verifies the automatic
    dataclass-serialisation path actually carries the field, not just that
    a dict CAN hold it)."""
    audio = _drift_fixture()
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    assert result.per_segment_reliability_caveat is not None, \
        "Precondition: drift fixture must fire caveat"

    d = dataclasses.asdict(result)

    assert "per_segment_reliability_caveat" in d, \
        "per_segment_reliability_caveat key missing from asdict() output"
    assert d["per_segment_reliability_caveat"] is not None
    assert d["per_segment_reliability_caveat"] == result.per_segment_reliability_caveat

    assert "hf_band_limit_whole_track_margin_db" in d, \
        "hf_band_limit_whole_track_margin_db key missing from asdict() output"
    assert d["hf_band_limit_whole_track_margin_db"] is not None
    assert d["hf_band_limit_whole_track_margin_db"] == result.hf_band_limit_whole_track_margin_db


def test_tc506_caveat_appears_in_markdown_rendering():
    """TC-506 (AC5, AC6c, R4 closure): render_markdown emits the literal
    prefix "  - Per-segment reliability caveat: {caveat_string}"
    (reference_render.py lines 116-117), using the TC-025 drift fixture's
    genuine result wrapped in a minimal ReferenceSetReport."""
    audio = _drift_fixture()
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    assert result.per_segment_reliability_caveat is not None, \
        "Precondition: drift fixture must fire caveat"

    report = _make_report_with_hf(result)
    md = render_markdown(report)

    assert result.per_segment_reliability_caveat in md, (
        f"Caveat string not found verbatim in markdown. "
        f"Caveat: {result.per_segment_reliability_caveat!r}"
    )


def test_tc513_none_abstentions_do_not_trigger_caveat():
    """TC-513 (AC5b): fixture where some segments abstain (return None) but
    no non-None segment disagrees with WT. Caveat must remain None.

    This is the OR-vs-AND bug detector. The correct implementation fires
    only when `s is not None AND abs(s - WT) > tolerance`. An OR bug
    (firing on None abstentions) would fail this test.

    Confirmed real (not vacuous) coverage: empirically verified this fixture
    produces per_segment_hf_band_limit_hz = [16251.1, None, 16251.1, None,
    16251.1] -- segments 1 and 3 (the LOW_AMP white-noise segments) genuinely
    abstain (flat PSD -> _gate_scan finds no qualifying window), while
    extract_active_audio does NOT gate out the LOW_AMP segments (verified:
    active audio retains the full 50s -- LOW_AMP=0.002 sits comfortably above
    the -60 dB silence_gate_threshold_db). The pytest.skip fallback path
    (TC-512 coverage) is present but does not fire on this construction.

    Fixture (5 × 10s = 50s): segments 0,2,4 brickwall at 16 kHz (find cliff);
    segments 1,3 white noise at very low amplitude (flat PSD → None abstention).

    Preconditions asserted before the main assertion:
      - whole-track finds a cliff (otherwise caveat trivially None)
      - at least one segment returns None (proves we test the right branch)
    If the fixture fails to produce abstentions, pytest.skip names TC-512 as
    the ground-truth fallback per test-cases.md scope note."""
    F_REAL = 16000.0
    SEG_DUR = 10.0
    HIGH_AMP = 0.2
    # ~40 dB below HIGH_AMP in power (-40 dB PSD density ratio): flat spectrum
    # guarantees no 8 dB drop window → _gate_scan returns None on these segments
    LOW_AMP = 0.002

    segs = []
    for i in range(5):
        if i in (1, 3):
            segs.append(white_noise_mono(SR, SEG_DUR, seed=200 + i, amplitude=LOW_AMP))
        else:
            segs.append(brickwall_lowpass_noise_mono(
                SR, SEG_DUR, cutoff_hz=F_REAL, seed=300 + i, amplitude=HIGH_AMP))

    audio = to_stereo(np.concatenate(segs))
    config = ref_config()  # default hf_min_duration_s=30.0; 50s total passes

    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is not None, (
        f"Precondition: whole-track must find a cliff near {F_REAL:.0f} Hz; got None. "
        f"per_segment={result.per_segment_hf_band_limit_hz}. "
        "TC-512 (slow, ground-truth) covers the fallback case."
    )

    if not any(s is None for s in result.per_segment_hf_band_limit_hz):
        pytest.skip(
            "TC-513 fixture produced no None abstentions -- all segments found a cliff. "
            "Coverage fallback: TC-512 (slow, ground-truth on reference tracks). "
            f"per_segment={result.per_segment_hf_band_limit_hz}"
        )

    # Main assertion: None abstentions must NOT trigger caveat
    assert result.per_segment_reliability_caveat is None, (
        f"None abstentions must not trigger caveat (AC5b OR-vs-AND check). "
        f"WT={result.hf_band_limit_hz:.0f} Hz, "
        f"segs={result.per_segment_hf_band_limit_hz}, "
        f"caveat={result.per_segment_reliability_caveat!r}"
    )


def test_tc514_caveat_none_when_whole_track_result_is_none():
    """TC-514 (AC5, AC6c, edge case): both `result.hf_band_limit_hz` and
    `result.per_segment_reliability_caveat` are None for a signal with no
    whole-track cliff (white noise -- already verified None by TC-022/024).
    The population condition has an explicit `whole_track_hz is not None`
    guard (architecture §5.1); this test exercises that guard directly."""
    mono = white_noise_mono(SR, duration_s=3.0, seed=3, amplitude=0.2)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is None, (
        f"Precondition: white noise must produce no whole-track cliff; "
        f"got {result.hf_band_limit_hz}"
    )
    assert result.per_segment_reliability_caveat is None, (
        f"Caveat must be None when whole-track result is None "
        f"(architecture §5.1 guard); got {result.per_segment_reliability_caveat!r}"
    )


def test_tc515_both_new_fields_none_when_insufficient_duration():
    """TC-515 (AC5, AC6c, edge case -- very short file): a 0.5s noise burst
    is shorter than hf_min_duration_s=2.0, so measure_hf_extension
    short-circuits at the insufficient-duration path (architecture §9.3)
    before the cliff detector runs at all. Both new fields must be None."""
    mono = white_noise_mono(SR, duration_s=0.5, seed=4, amplitude=0.2)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)

    assert result.insufficient_duration is True, (
        f"Precondition: 0.5s audio with hf_min_duration_s=2.0 must short-circuit; "
        f"got insufficient_duration={result.insufficient_duration}"
    )
    assert result.per_segment_reliability_caveat is None, (
        f"per_segment_reliability_caveat must be None on the insufficient-duration "
        f"path; got {result.per_segment_reliability_caveat!r}"
    )
    assert result.hf_band_limit_whole_track_margin_db is None, (
        f"hf_band_limit_whole_track_margin_db must be None on the insufficient-duration "
        f"path; got {result.hf_band_limit_whole_track_margin_db}"
    )


def test_tc516_non_default_tolerance_interpolated_in_caveat():
    """TC-516 (AC5a): with hf_stability_tolerance_hz=1500 Hz, caveat must
    interpolate '1500' and must NOT contain '2000' (the default). The drift
    fixture has max disagreement ~7000 Hz >> 1500 Hz, so the caveat fires."""
    audio = _drift_fixture()
    config = ref_config(hf_min_duration_s=2.0, hf_stability_tolerance_hz=1500.0)
    result = measure_hf_extension(audio, SR, config)

    assert result.per_segment_reliability_caveat is not None, (
        "Drift fixture with tolerance=1500 Hz must fire caveat "
        "(max disagreement ~7000 Hz >> 1500 Hz)"
    )
    caveat = result.per_segment_reliability_caveat
    assert "1500" in caveat, (
        f"AC5a: tolerance value '1500' not interpolated in caveat: {caveat!r}"
    )
    assert "2000" not in caveat, (
        f"AC5a: default '2000' must not appear when tolerance=1500: {caveat!r}"
    )


def test_tc517_caveat_tolerance_boundary():
    """TC-517: caveat fires at tolerance = d − 500 but not at tolerance = d + 500,
    where d = max(|s − WT|) over non-None per-segment values from the drift fixture.
    Confirms the strict-inequality boundary is correctly implemented
    (`abs(s - WT) > tolerance`, not >=)."""
    audio = _drift_fixture()
    config_base = ref_config(hf_min_duration_s=2.0)
    result_base = measure_hf_extension(audio, SR, config_base)

    assert result_base.hf_band_limit_hz is not None, \
        "Precondition: drift fixture WT must find a cliff"
    non_none = [s for s in result_base.per_segment_hf_band_limit_hz if s is not None]
    assert non_none, "Precondition: at least one non-None segment required"
    d = float(max(abs(s - result_base.hf_band_limit_hz) for s in non_none))

    # Tolerance above d: no segment exceeds it → no caveat
    config_above = ref_config(hf_min_duration_s=2.0, hf_stability_tolerance_hz=d + 500.0)
    r_above = measure_hf_extension(audio, SR, config_above)
    assert r_above.per_segment_reliability_caveat is None, (
        f"With tolerance={d + 500.0:.0f} Hz (> d={d:.0f} Hz): caveat must be None. "
        f"Segs: {r_above.per_segment_hf_band_limit_hz}"
    )

    # Tolerance below d: the max-deviation segment fires the caveat
    tol_below = max(d - 500.0, 1.0)
    config_below = ref_config(hf_min_duration_s=2.0, hf_stability_tolerance_hz=tol_below)
    r_below = measure_hf_extension(audio, SR, config_below)
    assert r_below.per_segment_reliability_caveat is not None, (
        f"With tolerance={tol_below:.0f} Hz (< d={d:.0f} Hz): caveat must fire. "
        f"Segs: {r_below.per_segment_hf_band_limit_hz}"
    )


def test_tc518_whole_track_margin_appears_in_markdown_rendering():
    """TC-518 (AC5, R4 second-block closure): render_markdown emits the
    literal prefix "  - Whole-track j* margin: " (reference_render.py line
    119) and the formatted margin value. Uses the TC-503 Sub-case A
    digital-zero brickwall fixture, whose margin is ≈ 8.0 dB (confirmed
    exactly 8.0 dB at this seed/duration by test_tc503a) -- the rendered
    value must therefore contain "8.00 dB" (reference_render.py's `_fmt`
    formats to 2 decimal places)."""
    mono = brickwall_lowpass_noise_mono(SR, duration_s=3.0, cutoff_hz=16000.0,
                                        seed=1, amplitude=0.3)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0, hf_stability_segment_count=1)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_whole_track_margin_db is not None, \
        "Precondition: TC-503 Sub-case A fixture must produce a populated margin"
    assert result.hf_band_limit_whole_track_margin_db == pytest.approx(8.0, abs=1.0), (
        f"Precondition: expected margin ≈ 8.0 dB (TC-503a); "
        f"got {result.hf_band_limit_whole_track_margin_db:.3f} dB"
    )

    report = _make_report_with_hf(result)
    md = render_markdown(report)

    assert "Whole-track j* margin" in md, (
        f"Literal prefix 'Whole-track j* margin' not found in markdown. "
        f"First 800 chars: {md[:800]}"
    )
    assert "8.00 dB" in md, (
        f"Formatted margin value '8.00 dB' not found near the prefix. "
        f"Actual margin: {result.hf_band_limit_whole_track_margin_db:.4f} dB. "
        f"First 800 chars: {md[:800]}"
    )


def test_tc519_determinism_new_fields_bit_identical_across_runs():
    """TC-519 (NFR Reproducibility): both new fields are bit-identical
    across two runs of measure_hf_extension on the same audio buffer and
    config (the TC-025 drift fixture, which produces a non-None caveat)."""
    audio = _drift_fixture()
    config = ref_config(hf_min_duration_s=2.0)

    result1 = measure_hf_extension(audio, SR, config)
    result2 = measure_hf_extension(audio, SR, config)

    assert result1.per_segment_reliability_caveat == result2.per_segment_reliability_caveat, (
        f"Caveat not bit-identical across identical runs: "
        f"{result1.per_segment_reliability_caveat!r} != {result2.per_segment_reliability_caveat!r}"
    )
    assert result1.hf_band_limit_whole_track_margin_db == result2.hf_band_limit_whole_track_margin_db, (
        f"Whole-track margin not bit-identical across identical runs: "
        f"{result1.hf_band_limit_whole_track_margin_db} != {result2.hf_band_limit_whole_track_margin_db}"
    )


def test_tc521_ac5_caveat_string_covers_all_three_required_clauses():
    """TC-521 (AC5(a)(b)(c) content correctness): the caveat string produced
    by the TC-025 drift fixture substantively covers all three AC5 clauses:

      AC5(a): 'false positive' -- per-segment values on complex material may
              be false positives unrelated to a band-limit wall.
      AC5(b): 'alternative' (or 'estimate') and 'abstention' (or 'honest')
              -- a false-positive value must not be used as an alternative
              band-limit estimate; None is a distinct, honest abstention.
      AC5(c): 'correct' -- stable=False with low confidence and a strong
              whole-track margin is the correct report, not a detector
              failure.

    Note (test-cases.md TC-521): keyword substring checks are necessary but
    not sufficient -- a human reviewer must additionally read the caveat
    string verbatim against AC5(a)(b)(c) as part of Gate 1 sign-off. This
    test prevents silent omission; it cannot prevent technically-present-
    but-misleading phrasing."""
    audio = _drift_fixture()
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    caveat = result.per_segment_reliability_caveat
    assert caveat is not None, "Precondition: drift fixture must fire caveat"

    assert "false positive" in caveat.lower(), (
        f"AC5(a): 'false positive' not found in caveat: {caveat!r}"
    )
    assert ("alternative" in caveat or "estimate" in caveat), (
        f"AC5(b): neither 'alternative' nor 'estimate' found in caveat: {caveat!r}"
    )
    assert ("abstention" in caveat or "honest" in caveat), (
        f"AC5(b): neither 'abstention' nor 'honest' found in caveat: {caveat!r}"
    )
    assert "correct" in caveat, (
        f"AC5(c): 'correct' not found in caveat: {caveat!r}"
    )


# ===========================================================================
# Slow tests
# ===========================================================================

@pytest.mark.slow
def test_tc507_false_positive_geometry_250s_fixture():
    """TC-507 (AC6(a)(c), architecture Section 9.1 geometry-faithful
    fixture): 250s mono signal designed to produce a per-segment false
    positive in segment 0 only, replicating the Chemical Brothers
    segment-1 mechanism at the same segment-Welch-window geometry
    (~73 Welch windows per 50s segment).

    Fixture geometry (44100 Hz, 5 x 50s = 250s):

      Segment 0: brickwall_lowpass_noise_with_floor_mono(cutoff_hz=F_FALSE,
      floor_below_db=10.0, passband_sigma=PASSBAND_SIGMA) -- a genuine
      cliff at F_FALSE=8000 Hz with a FULL-BAND floor (present at every
      frequency above the cutoff, all the way to Nyquist, not just above
      F_REAL). This is the calibration correction from an earlier
      iteration of this fixture (see note below): a two-region
      construction (digital-zero stopband from F_FALSE to F_REAL, then an
      injected floor only above F_REAL) fails _gate_scan's floor-coverage
      test for ANY candidate window near F_FALSE, because the deep
      digital-zero buffer between F_FALSE and F_REAL, followed by a
      "recovery" back up to the injected floor level above F_REAL, causes
      >20% of the floor region to sit above floor_ref + floor_noise_margin_db
      for every candidate window -- construction-time verification (below)
      caught this exact failure mode empirically, matching gate1-review F4's
      warning that fixture calibration must be iterated on the segment-1
      slice alone before trusting a hand-derived value. A uniform, full-band
      floor (same convention as TC-023's own finite-floor fixture) avoids
      the digital-zero buffer entirely and gives near-100% floor coverage.

      Segments 1-4: brickwall_lowpass_noise_with_floor_mono(cutoff_hz=F_REAL,
      floor_below_db=100.0, passband_sigma=PASSBAND_SIGMA) -- a genuine
      cliff at F_REAL=16000 Hz with a very deep (effectively digital-zero)
      floor, sigma-consistent with segment 0's own passband level (both
      helpers share the same passband_sigma convention, unlike an
      amplitude-normalized brickwall_lowpass_noise_mono call, which would
      not reliably match segment 0's passband reference level P).

    Whole-track PSD (empirically confirmed below, not just derived):
      - Below F_FALSE: all 5 segments contribute at level P.
      - F_FALSE..F_REAL: segments 1-4 contribute passband level P; segment 0
        contributes its floor (P-10 dB). Weighted average close to P.
      - Above F_REAL: segments 1-4 contribute their (near digital-zero,
        floor_below_db=100) floor; segment 0 contributes its floor (P-10 dB).
        Weighted average (1/5)*(P-10) dominates -- far more than 8 dB below
        the F_REAL passband level, so whole-track finds a cliff at F_REAL.

    Segment 0 in isolation shows only its own F_FALSE cliff (no F_REAL
    structure -- its floor is uniform above F_FALSE by construction), so
    its per-segment result disagrees with the whole-track F_REAL result by
    F_REAL - F_FALSE = 8000 Hz >> hf_stability_tolerance_hz (2000 Hz) --
    exactly the false-positive/whole-track disagreement this story's
    caveat mechanism exists to disclose.

    Construction-time PSD verification (before the full pipeline call, so
    a miscalibrated fixture gives a diagnostic about the signal, not a
    confusing failure downstream): confirms _detect_cliff finds a cliff on
    segment 0's own PSD near F_FALSE, not F_REAL, and that it disagrees
    with F_REAL by more than the stability tolerance.

    Note on F_REAL=16000 Hz vs the ~20000 Hz suggested in architecture
    Section 9.1: 16000 Hz leaves ~11 1/24-octave bands between F_REAL and
    Nyquist at 44100 Hz (log2(22050/16000)/(1/24) ~= 11), comfortably
    enough for the full 8-band gate window plus floor bands; 20000 Hz
    leaves only ~3, insufficient margin for a reliable gate-qualifying
    window. This is a deliberate, documented deviation from the
    architecture's illustrative value, not an unexplained parameter change."""
    F_FALSE = 8000.0    # segment 0 false cliff
    F_REAL = 16000.0    # segments 1-4 true brickwall; whole-track cliff
    SEG_DUR_S = 50.0
    PASSBAND_SIGMA = 0.15

    config = ref_config()

    seg0 = brickwall_lowpass_noise_with_floor_mono(
        SR, SEG_DUR_S, cutoff_hz=F_FALSE, floor_below_db=10.0,
        seed=42, passband_sigma=PASSBAND_SIGMA,
    )
    segs = [seg0]
    for i in range(1, 5):
        segs.append(brickwall_lowpass_noise_with_floor_mono(
            SR, SEG_DUR_S, cutoff_hz=F_REAL, floor_below_db=100.0,
            seed=100 + i, passband_sigma=PASSBAND_SIGMA,
        ))
    tc507_mono = np.concatenate(segs)

    # --- Construction-time PSD verification on segment 0 alone ---
    freqs_s0, psd_s0 = _psd.compute_psd(seg0, SR)
    false_result = _detect_cliff(freqs_s0, psd_s0, SR, config)
    assert false_result is not None, (
        f"Precondition (gate1-review F4 calibration check): _detect_cliff on "
        f"segment 0 returned None -- false cliff at F_FALSE={F_FALSE:.0f} Hz "
        f"not detected. Fixture requires recalibration before proceeding."
    )
    false_hz, _ = false_result
    assert abs(false_hz - F_FALSE) < 1000.0, (
        f"Precondition: segment-0 cliff at {false_hz:.0f} Hz is not close to "
        f"F_FALSE={F_FALSE:.0f} Hz -- fixture geometry error."
    )
    assert abs(false_hz - F_REAL) > config.hf_stability_tolerance_hz, (
        f"Precondition: segment-0 cliff at {false_hz:.0f} Hz must disagree with "
        f"F_REAL={F_REAL:.0f} Hz by more than "
        f"{config.hf_stability_tolerance_hz:.0f} Hz tolerance."
    )

    # --- Full pipeline call ---
    audio = to_stereo(tc507_mono)
    result = measure_hf_extension(audio, SR, config)

    # Whole-track cliff near F_REAL
    assert result.hf_band_limit_hz is not None, (
        f"Whole-track must find cliff near F_REAL={F_REAL:.0f} Hz; got None. "
        f"per_segment={result.per_segment_hf_band_limit_hz}"
    )
    assert result.hf_band_limit_hz == pytest.approx(F_REAL, abs=1000.0), (
        f"WT cliff at {result.hf_band_limit_hz:.0f} Hz; expected ~{F_REAL:.0f} +/- 1000 Hz"
    )

    # At least one per-segment value is non-None and disagrees with WT by
    # more than tolerance (test-cases.md TC-507 step 6, verbatim assertion).
    assert any(
        s is not None and abs(s - result.hf_band_limit_hz) > config.hf_stability_tolerance_hz
        for s in result.per_segment_hf_band_limit_hz
    ), (
        f"Expected at least one per-segment false positive disagreeing with WT "
        f"by > {config.hf_stability_tolerance_hz:.0f} Hz; "
        f"WT={result.hf_band_limit_hz:.0f}, per_segment={result.per_segment_hf_band_limit_hz}"
    )

    # Caveat fires (segment 0 is a false positive)
    caveat = result.per_segment_reliability_caveat
    assert caveat is not None, (
        f"Caveat must fire: segment 0 false cliff at ~{false_hz:.0f} Hz disagrees with "
        f"WT {result.hf_band_limit_hz:.0f} Hz. per_segment={result.per_segment_hf_band_limit_hz}"
    )
    assert len(caveat) > 0, "Caveat string must be non-empty"

    # Steps 9-10 (test-cases.md TC-507): caveat propagates to JSON (via
    # dataclasses.asdict, the mechanism render_json uses) and to markdown.
    # Deliberately no specific Hz value asserted for the false-positive
    # segment (test-cases.md TC-507 step 11): the exact value is not
    # analytically derivable and asserting it would lock in a regression
    # value rather than testing correctness.
    d = dataclasses.asdict(result)
    assert d["per_segment_reliability_caveat"] is not None, \
        "Caveat must propagate through dataclasses.asdict()"

    report = _make_report_with_hf(result)
    md = render_markdown(report)
    assert result.per_segment_reliability_caveat in md, \
        "Caveat must appear verbatim in markdown rendering"


@pytest.mark.slow
def test_tc509_25_segment_audit_20_correct_4_abstain_1_false_positive(ref_track_results):
    """TC-509 (AC1, under option-c scoping per architecture §3.5): the full
    25-segment classification (5 tracks x 5 segments each) reproduces
    20 CORRECT / 4 ABSTAIN / 1 FALSE-POSITIVE, matching architecture §4's
    before/after table (before = after under option c: no gate parameters
    changed).

    Classification (per segment, WT = that track's own whole-track value):
      C (CORRECT):        non-None, within 2000 Hz of WT.
      A (ABSTAIN):        None.
      FP (FALSE-POSITIVE): non-None, outside 2000 Hz of WT.

    Note (test-cases.md TC-509): requirements.md AC1's literal "zero false
    positives" applies to options (a)/(b) only. Under option (c) -- the
    resolution actually selected for this story -- the after-state
    deliberately retains Chemical Brothers segment 1's false positive,
    disclosed via per_segment_reliability_caveat rather than eliminated.
    This test asserts the documented EXPECTED pattern (1 FP), not zero FP;
    any other count is scoped as a defect (test-cases.md TC-509 pass/fail
    criterion), but 1 FP at the specific documented location is correct,
    not a regression."""
    tolerance = 2000.0
    totals = {"C": 0, "A": 0, "FP": 0}
    fp_locations = []

    for fname, result in ref_track_results.items():
        wt = result.hf_band_limit_hz
        for idx, s in enumerate(result.per_segment_hf_band_limit_hz):
            if s is None:
                totals["A"] += 1
            elif wt is not None and abs(s - wt) <= tolerance:
                totals["C"] += 1
            else:
                totals["FP"] += 1
                fp_locations.append((fname, idx, s, wt))

    assert totals["C"] == 20, f"Expected 20 CORRECT; got {totals['C']}. Totals: {totals}"
    assert totals["A"] == 4, f"Expected 4 ABSTAIN; got {totals['A']}. Totals: {totals}"
    assert totals["FP"] == 1, f"Expected 1 FALSE-POSITIVE; got {totals['FP']}. Totals: {totals}"

    assert len(fp_locations) == 1, f"Expected exactly one FP location; got {fp_locations}"
    fp_fname, fp_idx, fp_val, fp_wt = fp_locations[0]
    assert fp_fname == CHEM_BROTHERS, (
        f"FP must be localized to Chemical Brothers; got {fp_fname} segment {fp_idx}"
    )
    assert fp_idx == 0, f"FP must be Chemical Brothers segment 1 (index 0); got index {fp_idx}"
    assert fp_val == pytest.approx(14066.0, abs=5.0), (
        f"Chemical Brothers segment 1 FP value expected ≈14066 Hz; got {fp_val}"
    )

    # Four ABSTAINs: Chemical Brothers segs 2 and 5 (indices 1, 4);
    # Wavy Gravy segs 2 and 3 (indices 1, 2).
    chem = ref_track_results[CHEM_BROTHERS]
    assert chem.per_segment_hf_band_limit_hz[1] is None, "Chemical Brothers segment 2 must abstain"
    assert chem.per_segment_hf_band_limit_hz[4] is None, "Chemical Brothers segment 5 must abstain"
    wavy = ref_track_results["Wavy_Gravy.wav"]
    assert wavy.per_segment_hf_band_limit_hz[1] is None, "Wavy Gravy segment 2 must abstain"
    assert wavy.per_segment_hf_band_limit_hz[2] is None, "Wavy Gravy segment 3 must abstain"


@pytest.mark.slow
def test_tc510_whole_track_values_match_baseline(ref_track_results):
    """TC-510 (AC2, whole-track no-regression): whole-track hf_band_limit_hz
    values match the architecture §4 table exactly (within 1 Hz -- Welch
    determinism on unchanged gate code, since option (c) does not touch
    _gate_scan/_floor_onset_index/_detect_cliff).

    Note on the 20475 Hz spread across three tracks (Leftfield, Chemical
    Brothers, Wavy Gravy): this is NOT suspicious narrow spread -- 20475 Hz
    is a 1/24-octave log-band grid centre near Nyquist (44100 Hz), and
    full-band tracks with content to Nyquist quantise to the same grid
    point by construction (architecture §3.2/§3.5), not a measurement
    artefact."""
    expected = {
        "Black_Flute_Remastered.wav": 15788.0,
        "GusGus_-_Over_Arabian_Horse_Album.wav": 16251.0,
        "Leftfield_-_Melt_Audio.wav": 20475.0,
        CHEM_BROTHERS: 20475.0,
        "Wavy_Gravy.wav": 20475.0,
    }
    for fname, expected_hz in expected.items():
        result = ref_track_results[fname]
        assert result.hf_band_limit_hz is not None, f"{fname}: expected a whole-track cliff, got None"
        assert result.hf_band_limit_hz == pytest.approx(expected_hz, abs=1.0), (
            f"{fname}: expected {expected_hz} Hz (±1 Hz); got {result.hf_band_limit_hz}"
        )


@pytest.mark.slow
def test_tc511_stable_and_confidence_values_unchanged(ref_track_results):
    """TC-511 (AC3): stable and hf_band_limit_confidence values match the
    architecture §4 table on all five reference tracks. Chemical Brothers
    stable=False, confidence=0.4 is the CORRECT, expected, honest output
    (gate1-review Q1) -- requirements.md AC3 requires no flip of the four
    stable=True tracks; it does NOT require Chemical Brothers to become
    stable=True. Any option (a)/(b) successor story that changes the gate
    must re-run this test before any parameter can be committed."""
    expected = {
        "Black_Flute_Remastered.wav": (True, 1.0),
        "GusGus_-_Over_Arabian_Horse_Album.wav": (True, 1.0),
        "Leftfield_-_Melt_Audio.wav": (True, 1.0),
        CHEM_BROTHERS: (False, 0.4),
        "Wavy_Gravy.wav": (True, 0.6),
    }
    for fname, (expected_stable, expected_conf) in expected.items():
        result = ref_track_results[fname]
        assert result.stable == expected_stable, (
            f"{fname}: expected stable={expected_stable}; got {result.stable}"
        )
        assert result.hf_band_limit_confidence == pytest.approx(expected_conf, abs=0.01), (
            f"{fname}: expected confidence={expected_conf}; got {result.hf_band_limit_confidence}"
        )


@pytest.mark.slow
def test_tc512_caveat_fires_on_exactly_chemical_brothers(ref_track_results):
    """TC-512 (gate1-review F5, AC5): per_segment_reliability_caveat is
    non-None on exactly Chemical Brothers and None on the other four
    reference tracks. Any other firing pattern is a defect (gate1-review
    F5 verbatim).

    This test also provides the real-data fallback coverage for TC-513's
    OR-instead-of-AND failure mode: Wavy Gravy has two None abstentions and
    all non-None values at exactly 20475.06 Hz (|diff|=0 < tolerance). An
    OR-based implementation (firing on `s is None OR abs(s-WT) > tol`
    instead of `s is not None AND ...`) would incorrectly fire the caveat
    on Wavy Gravy's None segments and fail this test's step 4.

    Also verifies Chemical Brothers' caveat covers the AC5 keyword content
    (superset check beyond TC-521's synthetic-fixture check, confirming
    the real-data caveat string is not somehow different in content)."""
    expected_none = [
        "Black_Flute_Remastered.wav",
        "GusGus_-_Over_Arabian_Horse_Album.wav",
        "Leftfield_-_Melt_Audio.wav",
        "Wavy_Gravy.wav",
    ]
    chem = ref_track_results[CHEM_BROTHERS]
    assert chem.per_segment_reliability_caveat is not None, (
        f"Chemical Brothers must fire caveat. "
        f"WT={chem.hf_band_limit_hz}, per_segment={chem.per_segment_hf_band_limit_hz}"
    )
    for fname in expected_none:
        result = ref_track_results[fname]
        assert result.per_segment_reliability_caveat is None, (
            f"{fname}: expected no caveat (gate1-review F5: exactly 1 of 5 tracks fires); "
            f"got: {result.per_segment_reliability_caveat!r}. "
            f"WT={result.hf_band_limit_hz}, per_segment={result.per_segment_hf_band_limit_hz}"
        )

    caveat = chem.per_segment_reliability_caveat
    assert "false positive" in caveat, f"AC5a: 'false positive' not found: {caveat!r}"
    assert "alternative" in caveat, f"AC5b: 'alternative' not found: {caveat!r}"
    assert "honest abstention" in caveat, f"AC5b: 'honest abstention' not found: {caveat!r}"
    assert "correct" in caveat, f"AC5c: 'correct' not found: {caveat!r}"
    assert "2000" in caveat, f"AC5a: default tolerance '2000' not interpolated: {caveat!r}"
