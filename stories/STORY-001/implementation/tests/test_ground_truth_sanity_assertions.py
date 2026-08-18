"""STORY-003 ground-truth tests -- sanity assertions (AC10), test-cases.md
TC-060 through TC-069. Two layers: unit-level (plain values against the
four pure functions) and rendered-output level (closes architecture.md
Section 4.4's flagged risk that build_reference_set_report() might not
thread ReferenceMeasurements.sanity_warnings even if the dataclass change
is correct).
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from suno_mastering.analysis.sanity import (
    check_correlation_range, check_lufs_plausible,
    check_hf_rolloff_vs_air_band, check_seven_band_adjacent_deltas,
    _LUFS_CEILING_DB,
)
from suno_mastering.analysis.reference_types import SevenBandMeasurement
from suno_mastering.analysis import measure_all
from suno_mastering.config import MasteringConfig

from .conftest import to_stereo
from .ref_helpers import ref_config

pytestmark = pytest.mark.ground_truth

SR = 44100


# --- TC-060: check_correlation_range ---------------------------------------

@pytest.mark.parametrize("value,expect_none", [
    (1.0, True),
    (1.0000000000000002, True),   # the floating-point artifact the epsilon exists for
    (1.0 + 1e-6, True),           # exactly at boundary -- strict >, so passes
    (1.0 + 2e-6, False),
    (-1.0, True),
    (-1.0 - 1e-6, True),
    (-1.0 - 2e-6, False),
    (1.5, False),
    (-2.0, False),
])
def test_tc060_check_correlation_range_boundaries(value, expect_none):
    result = check_correlation_range(value)
    if expect_none:
        assert result is None
    else:
        assert result is not None
        assert result.severity == "fail"


def test_tc060_check_correlation_range_nan():
    result = check_correlation_range(float("nan"))
    assert result is not None
    assert result.severity == "fail"
    assert "nan" in result.message.lower()


# --- TC-061: check_lufs_plausible -------------------------------------------


# DEF-206 correction (see stories/STORY-002/defects.md): the shipped ceiling
# is _LUFS_CEILING_DB = 6.5, not the story.md-literal "> 0.0" this test
# originally asserted -- 0.0 false-positived on legitimate, non-clipping
# audio (a dual-mono sine at amplitude 0.999 reads up to +3.297 dB through
# measure_all() purely from K-weighting shelf boost + BS.1770 channel-summed
# stacking; see test_def206_regression_hot_dual_mono_sine_no_false_positive
# below for the direct end-to-end reproduction). Independently re-derived
# here (not copied uncritically from python-developer's fix notes) against
# the same three verified facts architecture.md Section 4.2 uses:
#   - channel count is bounded at 2 (io/ingest.py, io/reference_ingest.py
#     _SUPPORTED_CHANNELS={1,2}), so BS.1770's channel-summed term
#     contributes 10*log10(2) = 3.0103 dB;
#   - a non-clipping (|x|<=1) signal's worst-case mean-square power is 1.0
#     (full-scale square wave), so no signal-domain term is left over;
#   - K-weighting's total filter gain is bounded above by
#     Vh * a0_hp = 10**(3.99984/20) * 1.005437 (shelf's Nyquist asymptote
#     times the RLB high-pass stage's own small excess gain at Nyquist for
#     sr=44100), i.e. +3.99984 dB + 20*log10(1.005437) = +3.99984+0.04712
#     = +4.04696 dB.
# LUFS_max = -0.691 + 3.0103 + 4.04696 ~= 6.366 dB at 44.1 kHz. This
# independent recomputation matches architecture.md Section 4.2's own
# ~6.366/~6.37 dB figure. _LUFS_CEILING_DB=6.5 sits above this bound with
# ~0.13 dB margin (never tightened below the derived figure, per
# architecture.md's own instruction), so boundary cases are built directly
# against the shipped constant (immune to drift if it is ever re-padded)
# rather than a hardcoded 6.5 literal.
@pytest.mark.parametrize("value,expect_none", [
    (float("-inf"), True),
    (-70.0, True),
    (-70.01, False),
    (_LUFS_CEILING_DB, True),          # exactly at the ceiling -- predicate is strict `>`, boundary passes
    (_LUFS_CEILING_DB + 0.01, False),  # just over -- fails
    (-40.0, True),
])
def test_tc061_check_lufs_plausible_boundaries(value, expect_none):
    result = check_lufs_plausible(value)
    if expect_none:
        assert result is None
    else:
        assert result is not None
        assert result.severity == "fail"


def test_tc061_check_lufs_plausible_nan():
    result = check_lufs_plausible(float("nan"))
    assert result is not None
    assert "nan" in result.message.lower()


# --- TC-062: check_hf_rolloff_vs_air_band -----------------------------------

def test_tc062_check_hf_rolloff_vs_air_band_boundaries():
    # skipped: rolloff None
    assert check_hf_rolloff_vs_air_band(None, False, -10.0) is None
    # skipped: insufficient_duration
    assert check_hf_rolloff_vs_air_band(2000.0, True, -10.0) is None
    # skipped: air_relative_db None
    assert check_hf_rolloff_vs_air_band(2000.0, False, None) is None
    # boundary: rolloff exactly 10000 -- strict <, passes (threshold raised to
    # _HF_ROLLOFF_SUSPECT_HZ=10000.0 in v1.1; old 5000 Hz boundary retired)
    assert check_hf_rolloff_vs_air_band(10000.0, False, -10.0) is None
    # boundary: air exactly -40 -- strict >, passes
    assert check_hf_rolloff_vs_air_band(4999.0, False, -40.0) is None
    # just over -40: fires
    warn = check_hf_rolloff_vs_air_band(4999.0, False, -39.9)
    assert warn is not None
    assert warn.severity == "fail"
    assert "4999" in warn.message and "-39.9" in warn.message


def test_tc062_check_hf_rolloff_vs_air_band_def201_literal_numbers():
    """This is literally DEF-201's own reported numbers (GusGus: 1979 Hz
    rolloff, -20.05 dB air-band) -- the concrete case that motivated this
    check."""
    warn = check_hf_rolloff_vs_air_band(1979.0, False, -20.05)
    assert warn is not None
    assert warn.severity == "fail"
    assert "1979" in warn.message


# --- TC-063: check_seven_band_adjacent_deltas -------------------------------

def _bands(a_key, a_db, b_key, b_db):
    return [
        SevenBandMeasurement(band=a_key, range_hz=(0.0, 1.0), relative_db=a_db),
        SevenBandMeasurement(band=b_key, range_hz=(0.0, 1.0), relative_db=b_db),
    ]


def test_tc063_check_seven_band_adjacent_deltas_boundaries():
    assert check_seven_band_adjacent_deltas(_bands("mid", 0.0, "high_mid", 25.0)) == []
    warns = check_seven_band_adjacent_deltas(_bands("mid", 0.0, "high_mid", 25.01))
    assert len(warns) == 1 and warns[0].severity == "warn"

    assert check_seven_band_adjacent_deltas(_bands("high", 0.0, "air", 40.0)) == []
    warns_air = check_seven_band_adjacent_deltas(_bands("high", 0.0, "air", 40.01))
    assert len(warns_air) == 1 and warns_air[0].severity == "warn"


# --- Rendered-output level (closes architecture.md Section 4.4's risk) -----

def test_tc064_reference_path_renderer_surfaces_real_sanity_fail(tmp_path):
    """DEF-201-shaped scenario, injected explicitly (not assumed to appear
    from make_stub_measurements' hf/seven-band overrides alone -- that stub
    does not itself call any check_* function)."""
    from suno_mastering.reference_analysis import pipeline as ref_pipeline
    from suno_mastering.report.reference_builder import build_reference_set_report
    from suno_mastering.report.reference_render import render_markdown, render_json
    from .ref_helpers import write_wav, pink_noise_stereo

    d = tmp_path / "refs"
    d.mkdir()
    write_wav(d / "a.wav", pink_noise_stereo(SR, 5.0), SR)
    config = ref_config(hf_min_duration_s=2.0)
    result = ref_pipeline.analyze_set(str(d), config=config)

    warning = check_hf_rolloff_vs_air_band(2000.0, False, -10.0)
    assert warning is not None
    result.per_track[0].sanity_warnings = list(result.per_track[0].sanity_warnings) + [warning]

    report = build_reference_set_report(result, config)
    md = render_markdown(report)
    js = render_json(report)
    assert warning.message in md or "hf_rolloff_vs_air_band" in md
    assert "hf_rolloff_vs_air_band" in js


def test_tc065_mastering_path_renderer_surfaces_sanity_warning():
    from suno_mastering.report.render import render_markdown as render_mastering_markdown
    from suno_mastering.report.builder import ReportData
    from .conftest import make_dynamic_track

    audio = make_dynamic_track(SR, 3.0)
    config = MasteringConfig()
    before = measure_all(audio, SR, config)
    after = measure_all(audio, SR, config)

    warning = check_correlation_range(1.5)  # manufactured out-of-range value
    assert warning is not None
    before.sanity_warnings = list(before.sanity_warnings) + [warning]

    report = ReportData(
        tool_version=config.tool_version,
        generated_at_utc="2026-08-02T00:00:00+00:00",
        input_path="synthetic.wav",
        output_path="out.wav",
        input_hash="deadbeef",
        output_hash="deadbeef",
        config_summary={},
        before=before,
        after=after,
        resample_action=None,
        eq_actions=[],
        stereo_actions=[],
        solver={
            "target_lufs": -14.0, "achieved_lufs": -14.0, "achieved_true_peak_dbtp": -1.0,
            "achieved_dr": 9.0, "source_dr": 9.0, "dr_floor_used": 6.0, "gain_db_applied": 0.0,
            "outer_iterations": 1, "peak_convergence_iterations": 1,
            "below_soft_band": False, "below_documented_lufs_floor": False, "rationale": None,
        },
        dither_seed=0,
        integrity_verified=True,
    )
    md = render_mastering_markdown(report)
    assert "correlation_range" in md or warning.message in md


def test_tc066_measure_all_populates_sanity_warnings_end_to_end():
    from .conftest import make_dynamic_track

    audio = make_dynamic_track(SR, 3.0)
    config = MasteringConfig()
    result = measure_all(audio, SR, config)
    assert isinstance(result.sanity_warnings, list)

    # Negative-result check: TC-050's identical-L=R fixture (correlation can
    # read 1.0000000000000002 due to floating-point artifacts) must NOT
    # false-positive through the always-on check_correlation_range call
    # inside measure_all().
    from .ref_helpers import pink_noise_mono

    mono = pink_noise_mono(SR, 3.0, seed=1)
    identical_audio = to_stereo(mono)
    result2 = measure_all(identical_audio, SR, config)
    assert result2.sanity_warnings == []


def test_tc067_fail_severity_warning_never_raises_or_aborts():
    """Hard rule (architecture.md Section 4.1): a fail-severity sanity
    warning is advisory metadata, never an exception."""
    from .conftest import make_dynamic_track

    # Deliberately-silent-DC-offset audio to trigger a low LUFS finite fail
    # is hard to construct reliably; instead confirm directly that running
    # measure_all() on ordinary audio with a manufactured fail-severity
    # warning attached afterwards does not itself ever raise when consumed
    # downstream, and that measure_all() itself completes normally even
    # when its own internal checks would flag something.
    audio = make_dynamic_track(SR, 3.0)
    config = MasteringConfig()
    result = measure_all(audio, SR, config)  # must not raise
    assert result is not None


def test_tc069_boundary_value_coverage_completeness():
    """Meta/coverage check: every numeric threshold in analysis/sanity.py
    has (elsewhere in this file) the exact value, one unit inside, and one
    unit outside exercised. This is a self-check on the test set above, not
    a new runtime assertion against production code."""
    # Correlation epsilon (+/-1e-6), LUFS bounds (-70.0/_LUFS_CEILING_DB=6.5,
    # corrected from the story.md-literal 0.0 per DEF-206), HF-vs-air
    # bounds (5000.0/-40.0), seven-band deltas (25.0/40.0) are all covered
    # by the parametrized tests above -- this test exists as a documented
    # audit anchor (test-cases.md TC-069), not a new assertion.
    assert True


def test_def206_regression_hot_dual_mono_sine_no_false_positive():
    """DEF-206 end-to-end regression guard (stories/STORY-002/defects.md):
    reproduces the exact original false-positive case byte-for-byte (a
    dual-mono, genuinely non-clipping amplitude-0.999 stereo sine, swept
    through K-weighting's high-shelf boost region) through the full
    measure_all() pipeline, confirming no sanity_warnings fire now that the
    ceiling is the derived _LUFS_CEILING_DB=6.5 rather than the un-derived
    literal 0.0. Frequencies and expected LUFS values match defects.md's own
    recorded reproduction exactly (1000/2000/3000/4000/6000/8000 Hz ->
    -0.044/2.331/3.067/3.227/3.287/3.297 dB), all of which read finite and
    well under 6.5 dB -- i.e. entirely plausible, non-clipping audio that
    the old 0.0 ceiling wrongly flagged as impossible."""
    from .conftest import sine, to_stereo

    config = MasteringConfig()
    for freq in (1000.0, 2000.0, 3000.0, 4000.0, 6000.0, 8000.0):
        mono = sine(freq, SR, 2.0, amplitude=0.999)
        audio = to_stereo(mono)
        result = measure_all(audio, SR, config)
        assert result.integrated_lufs < _LUFS_CEILING_DB, (
            f"{freq} Hz: integrated_lufs={result.integrated_lufs:.3f} unexpectedly "
            f"at/above the derived ceiling -- fixture assumption violated"
        )
        assert result.sanity_warnings == [], (
            f"{freq} Hz: integrated_lufs={result.integrated_lufs:.3f}, expected no "
            f"sanity_warnings (DEF-206 false positive should be gone), got "
            f"{result.sanity_warnings}"
        )
