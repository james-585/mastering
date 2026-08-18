"""STORY-002 AC10 -- verification bars for newly-introduced measurements.
TC-300-TC-313.

Landmine note (per this story's own defects.md DEF-101): TC-311 and TC-313
are written in test-cases.md v1 as *open questions* against architecture v1
("which channel convention?", "spec collision at the -3dB threshold?").
Both are resolved by architecture v2 / the DEF-101 fix -- see defects.md for
the corresponding test-spec-staleness entry. This file asserts the
*resolved* v2 behavior directly, not the v1 open-question framing.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from suno_mastering.analysis.loudness import measure_integrated_lufs
from suno_mastering.analysis.loudness_range import measure_loudness_range, k_weight
from suno_mastering.analysis.hf_extension import measure_hf_extension
from suno_mastering.analysis.per_band_stereo_width import measure_per_band_stereo_width
from suno_mastering.analysis.mono_sum import measure_mono_sum

from .ref_helpers import (
    sine, to_stereo, calibrated_tone_mono, lowpassed_white_noise,
    brickwall_lowpass_noise_mono,
    mono_low_decorrelated_high_stereo, independent_noise_stereo, ref_config,
)


# --- 9.1 LRA -----------------------------------------------------------

def test_tc300_lra_self_consistency_check():
    sr = 44100
    a = calibrated_tone_mono(sr, 30.0, dbfs_rms=-18.0)
    b = calibrated_tone_mono(sr, 30.0, dbfs_rms=-12.0)
    audio = to_stereo(np.concatenate([a, b]))
    config = ref_config()
    lra_result = measure_loudness_range(audio, sr, config)
    reference_lufs = measure_integrated_lufs(audio, sr)
    assert lra_result.self_consistency_delta_lu < config.lra_self_consistency_tolerance_lu + 0.05
    assert np.isfinite(reference_lufs)


def test_tc301_lra_baseline_two_level_12lu_separation():
    sr = 44100
    a = calibrated_tone_mono(sr, 30.0, dbfs_rms=-14.0)
    b = calibrated_tone_mono(sr, 30.0, dbfs_rms=-26.0)
    audio = to_stereo(np.concatenate([a, b]))
    config = ref_config()
    result = measure_loudness_range(audio, sr, config)
    assert result.lra_lu == pytest.approx(12.0, abs=config.lra_tolerance_lu)


def test_tc302_lra_gate_discriminates_correct_vs_incorrect_relative_gate():
    """Regression guard for the single most common LRA implementation bug
    (architecture.md Section 4.1): the relative gate must be -20 LU, not
    -10 LU. Uses an 18 LU separation, calibrated (see this suite's own
    empirical derivation, not test-cases.md TC-302's literal 25 LU fixture
    -- see defects.md for why 25 LU does not actually discriminate, given
    the gate's mean-of-all-passing-blocks definition with a 50/50 duration
    split: the loud cluster pulls the gated mean down by ~3 dB, so a 25 LU
    separation is excluded under EITHER gate value and does not
    discriminate)."""
    sr = 44100
    a = calibrated_tone_mono(sr, 30.0, dbfs_rms=-10.0)
    b = calibrated_tone_mono(sr, 30.0, dbfs_rms=-28.0)  # 18 LU separation
    audio = to_stereo(np.concatenate([a, b]))

    correct_config = ref_config()  # -20 LU relative gate (default)
    assert correct_config.lra_relative_gate_lu == -20.0
    result_correct = measure_loudness_range(audio, sr, correct_config)
    assert result_correct.lra_lu == pytest.approx(18.0, abs=1.0)
    assert result_correct.lra_lu > 5.0  # explicitly not collapsed toward 0

    wrong_config = ref_config(lra_relative_gate_lu=-10.0)
    result_wrong = measure_loudness_range(audio, sr, wrong_config)
    assert result_wrong.lra_lu < 1.0  # miscopied -10 LU gate collapses the quiet cluster out


@pytest.mark.skip(reason="TC-303: EBU Tech 3342 published conformance test signals not yet "
                          "sourced into the repository -- see defects.md / test-cases.md open "
                          "question #4. Synthetic fixtures TC-301/TC-302 carry primary coverage "
                          "until this material is obtained (same posture as STORY-001 TC-024).")
def test_tc303_lra_external_ebu_conformance_material():
    pass


# --- 9.2 HF extension ----------------------------------------------------

def test_tc304_hf_rolloff_recovers_known_butterworth_cutoff_16k():
    """DEF-201 blast-radius migration (STORY-003 architecture.md Section 2.5,
    test-cases.md TC-026) -- re-fixtured from lowpassed_white_noise (a
    finite-slope Butterworth+sosfiltfilt filter whose threshold-crossing
    frequency MOVES when hf_rolloff_threshold_db moves) onto
    brickwall_lowpass_noise_mono (a genuine spectral-zero edge, whose
    crossing frequency is independent of threshold depth -- both the old
    6 dB and the corrected 20 dB crossing sit at cutoff_hz, to within a few
    Welch-PSD leakage bins). Confirmed empirically (not just by the
    asymptotic sosfiltfilt formula) before this migration: the OLD
    lowpassed_white_noise fixture, left unmodified, reports rolloff_hz=
    16747.4 Hz at the current threshold_db=20.0 -- outside the 16000+/-500 Hz
    tolerance -- see defects.md DEF-201 for the recorded failing-value
    evidence. This is the required re-fixturing, not a widened tolerance."""
    sr = 44100
    mono = brickwall_lowpass_noise_mono(sr, 35.0, cutoff_hz=16000.0, amplitude=0.3)
    audio = to_stereo(mono)
    config = ref_config()
    result = measure_hf_extension(audio, sr, config)
    assert result.hf_band_limit_hz == pytest.approx(16000.0, abs=config.hf_rolloff_test_tolerance_hz)
    assert result.stable is True


def test_tc305_hf_rolloff_recovers_second_known_cutoff_12k():
    """DEF-201 blast-radius migration (test-cases.md TC-027) -- same
    re-fixturing as test_tc304, for the 12 kHz cutoff. The OLD
    lowpassed_white_noise fixture, left unmodified, reports rolloff_hz=
    13010.1 Hz at threshold_db=20.0 -- outside the 12000+/-500 Hz tolerance
    (defects.md DEF-201)."""
    sr = 44100
    mono = brickwall_lowpass_noise_mono(sr, 35.0, cutoff_hz=12000.0, amplitude=0.3)
    audio = to_stereo(mono)
    config = ref_config()
    result = measure_hf_extension(audio, sr, config)
    assert result.hf_band_limit_hz == pytest.approx(12000.0, abs=config.hf_rolloff_test_tolerance_hz)


def test_tc306_insufficient_duration_reports_defined_result_not_crash():
    sr = 44100
    mono = lowpassed_white_noise(sr, 20.0, cutoff_hz=16000.0, amplitude=0.3)  # below default 30s
    audio = to_stereo(mono)
    result = measure_hf_extension(audio, sr, ref_config())
    assert result.insufficient_duration is True
    assert result.hf_band_limit_hz is None


@pytest.mark.parametrize("duration_s,expect_insufficient", [
    (2.9, True), (3.0, False), (3.1, False),
])
def test_tc307_hf_min_duration_boundary(duration_s, expect_insufficient):
    """Resolves test-cases.md's own open question #8: the shipped
    comparison is `duration_s < config.hf_min_duration_s` (strict less-than)
    -- exactly hf_min_duration_s is INCLUDED (sufficient), confirmed here
    against the code directly rather than left ambiguous."""
    sr = 44100
    config = ref_config(hf_min_duration_s=3.0, hf_stability_segment_count=2)
    mono = lowpassed_white_noise(sr, duration_s, cutoff_hz=16000.0, amplitude=0.3)
    audio = to_stereo(mono)
    result = measure_hf_extension(audio, sr, config)
    assert result.insufficient_duration is expect_insufficient


def test_tc308_stability_flag_false_for_materially_shifting_rolloff():
    sr = 44100
    # v1.5a: i_max selects the HIGHEST qualifying candidate (whole-track value
    # lands near 16k). A 20s+20s equal split gives 3/5 segments agreeing with
    # 16k (the first pure-16k segment + the boundary mixed segment both find
    # i_max at 16k) -> confidence = 3/5 = 0.6 = stable_floor -> stable=True
    # (wrong). Fix: 5s+20s so only the first, short 16k segment agrees;
    # confidence = 1/5 = 0.2 < 0.6 -> stable=False. Same fix as TC-028 in
    # test_ground_truth_hf_extension.py.
    half1 = lowpassed_white_noise(sr, 5.0, cutoff_hz=16000.0, seed=1, amplitude=0.3)
    half2 = lowpassed_white_noise(sr, 20.0, cutoff_hz=10000.0, seed=2, amplitude=0.3)
    mono = np.concatenate([half1, half2])
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)  # 25s total; default 30s would trip insufficient_duration
    result = measure_hf_extension(audio, sr, config)
    assert result.stable is False, (
        f"16k/10k two-segment drift (5s+20s) should be unstable; "
        f"got confidence={result.hf_band_limit_confidence:.3f}, "
        f"stable={result.stable}, per_segment={result.per_segment_hf_band_limit_hz}"
    )
    assert result.hf_band_limit_hz is not None  # whole-track gate finds the 16k cliff


# --- 9.3 Per-band stereo width -------------------------------------------

def test_tc309_per_band_width_low_near_zero_high_near_one():
    sr = 44100
    audio = mono_low_decorrelated_high_stereo(sr, 12.0, low_crossover_hz=120.0, high_crossover_hz=5000.0)
    config = ref_config()
    result = measure_per_band_stereo_width(audio, sr, config)
    by_band = {b.band: b.width for b in result.bands}
    tol = config.per_band_width_test_tolerance
    assert by_band["sub"] == pytest.approx(0.0, abs=tol)
    assert by_band["low"] == pytest.approx(0.0, abs=tol)
    assert by_band["high"] == pytest.approx(1.0, abs=tol)
    assert by_band["air"] == pytest.approx(1.0, abs=tol)


def test_tc310_per_band_width_caveat_in_report(tmp_path):
    from suno_mastering.reference_analysis import pipeline as ref_pipeline
    from suno_mastering.report.reference_builder import build_reference_set_report
    from suno_mastering.report.reference_render import render_markdown
    from .ref_helpers import write_wav, pink_noise_stereo

    d = tmp_path / "refs"
    d.mkdir()
    write_wav(d / "a.wav", pink_noise_stereo(44100, 5.0), 44100)
    config = ref_config(hf_min_duration_s=2.0)
    result = ref_pipeline.analyze_set(str(d), config=config)
    report = build_reference_set_report(result, config)
    md = render_markdown(report)
    assert "Per-band stereo width" in md
    # Report distinguishes overall (broadband time-domain) correlation from
    # per-band (frequency-domain) width -- both figures present, not conflated.
    assert "Overall stereo correlation" in md


# --- 9.4 Mono-sum level change + cancellation ----------------------------

def test_tc311_monosum_level_change_correlated_lr_is_zero_db():
    """DEF-203 channel-mean comparator: for perfectly correlated L=R stereo,
    mono_sum=(L+R)/2=L, channel_mean_lufs=LUFS(L), so
    mono_sum_level_change_db = LUFS(L) - LUFS(L) = 0 dB exactly.
    This is the DOMAIN.md Section 3 / architecture.md Section 2.1 rho=+1
    prediction for the corrected channel-mean method (not the superseded
    channel-sum method that gave -3.0103 dB -- see defects.md DEF-203)."""
    sr = 44100
    mono = sine(1000, sr, 10.0, amplitude=0.2)
    audio = to_stereo(mono)
    result = measure_mono_sum(audio, sr, ref_config())
    assert result.mono_sum_level_change_db == pytest.approx(0.0, abs=0.1)
    assert result.mono_sum_excess_cancellation is False  # rho=+1: well above -4.5 dB threshold


def test_tc312_monosum_anti_phase_large_cancellation():
    sr = 44100
    n = int(10 * sr)
    rng = np.random.default_rng(2)
    tone = sine(1000, sr, 10.0, amplitude=0.2)
    noise_floor_amp = 0.2 * (10 ** (-20.0 / 20.0))
    left = tone + rng.normal(0.0, noise_floor_amp, n)
    right = -tone + rng.normal(0.0, noise_floor_amp, n)
    audio = np.stack([left, right], axis=1)
    result = measure_mono_sum(audio, sr, ref_config())
    assert result.mono_sum_level_change_db < -15.0
    mid = next(b for b in result.band_cancellations if b.band == "mid")
    assert mid.cancellation is True


def test_tc313_def101_regression_ordinary_decorrelated_stereo_no_false_positive():
    """The direct DEF-101 regression guard: ordinary, healthy, fully
    decorrelated (independent, equal-power, non-anti-phase) stereo content
    must NOT be flagged as cancellation on any band, and
    excess_cancellation_db must read close to 0 -- this is exactly the
    false-positive DEF-101 found and fixed. Uses two independent seeds/
    levels per the QA landmine note (DEF-101's own measured
    excess_delta_db spread was -0.26..+0.32 across bands -- tolerance below
    is set accordingly, not knife-edge-tight)."""
    sr = 44100
    config = ref_config()
    for seed, sigma in [(1, 0.05), (7, 0.08)]:
        audio = independent_noise_stereo(sr, 8.0, sigma=sigma, seed=seed)
        result = measure_mono_sum(audio, sr, config)
        assert result.mono_sum_level_change_db == pytest.approx(-3.0103, abs=0.5), \
            f"seed={seed}: mono_sum_level_change_db={result.mono_sum_level_change_db}"
        for b in result.band_cancellations:
            assert b.cancellation is False, \
                f"seed={seed}: false-positive cancellation on band {b.band} " \
                f"(excess_delta_db={b.excess_delta_db})"
            assert b.excess_delta_db == pytest.approx(0.0, abs=0.6)
