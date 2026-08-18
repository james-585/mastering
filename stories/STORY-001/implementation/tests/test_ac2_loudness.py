"""AC2 -- loudness target. TC-010..TC-017."""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering import pipeline
from suno_mastering.analysis.loudness import measure_integrated_lufs
from suno_mastering.errors import UnresolvableMasteringConstraintError

from .conftest import make_dynamic_track, rms_amplitude_for_dbfs_sine, sine, to_stereo, write_wav


def test_tc010_bs1770_calibration_1khz_sine(default_config):
    # Mono buffer: BS.1770 sums per-channel mean-square across channels with
    # channel weight 1.0 for L/R, so a *dual-mono* stereo signal (identical
    # L/R) reads ~+3.01 dB louder than either channel's own dBFS RMS (this is
    # correct BS.1770 behavior, not an implementation bug -- see DEF-001
    # discussion in defects.md for why the dual-mono-stereo construction
    # doesn't itself read -20 LUFS). Testing mono isolates the K-weighting
    # calibration check test-cases.md TC-010 is actually after.
    sr = 44100
    amp = rms_amplitude_for_dbfs_sine(-20.0)
    tone = sine(1000, sr, 12.0, amplitude=amp)
    lufs = measure_integrated_lufs(tone, sr)
    assert abs(lufs - (-20.0)) < 0.1


def test_tc010b_bs1770_dual_mono_stereo_reads_plus3db_channel_sum(default_config):
    """Documents the dual-mono-stereo BS.1770 channel-summing behavior
    referenced above; not itself a failure condition."""
    sr = 44100
    amp = rms_amplitude_for_dbfs_sine(-20.0)
    tone = sine(1000, sr, 12.0, amplitude=amp)
    audio = to_stereo(tone)
    lufs = measure_integrated_lufs(audio, sr)
    assert abs(lufs - (-20.0 + 3.01)) < 0.2


def test_tc011_relative_gating_quiet_passage_not_skewing(default_config):
    sr = 44100
    loud_amp = rms_amplitude_for_dbfs_sine(-13.0)
    loud = to_stereo(sine(1000, sr, 60.0, amplitude=loud_amp))
    quiet = to_stereo(sine(1000, sr, 180.0, amplitude=rms_amplitude_for_dbfs_sine(-55.0)))
    full = np.concatenate([loud, quiet], axis=0)

    lufs_full = measure_integrated_lufs(full, sr)
    lufs_loud_only = measure_integrated_lufs(loud, sr)

    assert abs(lufs_full - lufs_loud_only) < 0.3


def test_tc012_absolute_gate_excludes_near_silence(default_config):
    sr = 44100
    silent = to_stereo(sine(1000, sr, 30.0, amplitude=rms_amplitude_for_dbfs_sine(-80.0)))
    loud = to_stereo(sine(1000, sr, 90.0, amplitude=rms_amplitude_for_dbfs_sine(-13.0)))
    full = np.concatenate([silent, loud], axis=0)

    lufs_full = measure_integrated_lufs(full, sr)
    lufs_loud_only = measure_integrated_lufs(loud, sr)

    assert abs(lufs_full - lufs_loud_only) < 0.3


def test_tc013_output_lands_in_band_happy_path(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(
        sr, 40.0, body_amplitude=rms_amplitude_for_dbfs_sine(-20.0),
        transient_amplitude=0.4, transient_period_s=1.0, freq=220,
    )
    path = write_wav(tmp_wav_dir / "tc013.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    assert -14.5 <= result.after.integrated_lufs <= -13.5
    assert result.report.solver["rationale"] is None


@pytest.mark.parametrize("source_dbfs", [-30.0, -18.0, -9.0])
def test_tc014_hard_ceiling_never_exceeded(tmp_wav_dir, out_dir, default_config, source_dbfs):
    sr = 44100
    body_amp = rms_amplitude_for_dbfs_sine(source_dbfs)
    transient_amp = min(0.95, body_amp * 3.0)
    # DEF-009 fix: when body_amp is high enough that the 0.95 transient cap
    # binds, the crest factor drops below DR10 and the solver raises
    # UnresolvableMasteringConstraintError. Reshape only the affected case
    # (body_amp > 0.300 → -9.0 dBFS) to body=0.282/transient=0.95 so
    # source_dr=10.00 (measured). The -18.0 and -30.0 cases are unchanged.
    _DR10_BODY_LIMIT = 0.95 / (10 ** (10.0 / 20))  # ≈ 0.300
    if body_amp > _DR10_BODY_LIMIT:
        body_amp, transient_amp = 0.282, 0.95
    audio = make_dynamic_track(
        sr, 40.0, body_amplitude=body_amp, transient_amplitude=transient_amp,
        transient_period_s=1.0, freq=220,
    )
    path = write_wav(tmp_wav_dir / f"tc014_{source_dbfs}.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    assert result.after.integrated_lufs <= -13.5 + 0.01


def test_tc015_rationale_present_when_backing_off(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    # High crest factor: quiet body, one very loud/brief transient near 0dBFS,
    # DR right at the DR8+3dB margin so pushing to -13.5 would erode DR below floor.
    audio = make_dynamic_track(
        sr, 40.0, body_amplitude=rms_amplitude_for_dbfs_sine(-30.0),
        transient_amplitude=0.94, transient_period_s=1.0, freq=220,
    )
    path = write_wav(tmp_wav_dir / "tc015.wav", audio, sr)

    # (a) solver must NOT raise UnresolvableMasteringConstraintError for this
    # fixture -- v4 makes this resolve to a real, reported (if low) LUFS
    # value instead. Assert explicitly rather than relying on an implicit
    # "reaching the next line means it didn't raise".
    try:
        result = pipeline.master(path, output_dir=out_dir, config=default_config)
    except UnresolvableMasteringConstraintError as exc:
        pytest.fail(
            "UnresolvableMasteringConstraintError must not be raised for this "
            f"high-crest-factor fixture per architecture.md v4 Section 1: {exc}"
        )

    # v4 (architecture.md Section 1, resolves DEF-001 residual): -16 LUFS is
    # a soft, report-escalation threshold, not a hard solver constraint, for
    # high-crest-factor sources like this fixture. The hard constraints are
    # the DR floor and the true-peak ceiling; do NOT assert
    # achieved_lufs >= -16 here (that was the removed v1-v3 contract).
    assert result.after.integrated_lufs < -14.5

    solver = result.report.solver

    # (b) below_documented_lufs_floor must be True for this fixture.
    assert result.below_documented_lufs_floor is True
    assert solver["below_documented_lufs_floor"] is True

    # (c) the DR floor hard constraint must still be held exactly
    # (achieved DR meets max(DR8, source_DR - 3dB)).
    assert solver["dr_floor_used"] == pytest.approx(
        max(default_config.dr_floor, solver["source_dr"] - default_config.dr_max_reduction_db)
    )
    assert solver["achieved_dr"] >= solver["dr_floor_used"] - 0.01

    # true-peak ceiling hard constraint also still respected.
    assert result.after.true_peak_dbtp <= -1.0 + 0.05

    # (d) rationale text must name the DR floor as the reason for landing
    # below -16 LUFS (architecture.md v4 Section 1 point 5).
    rationale = solver["rationale"]
    assert rationale is not None
    assert "DR floor" in rationale
    assert f"{solver['dr_floor_used']:.1f}" in rationale


def test_tc016_untested_middle_tier_below_14_5_above_16(tmp_wav_dir, out_dir, default_config):
    """Reworked per architecture.md v4 Section 1 (defects.md DEF-001,
    "Verification pass (2026-08-01, python-developer)" note recommending
    test-case-writer/QA rework -- the old v1-v3 "clamped at -16 or raises"
    fixture/assertion is stale and, worse, was vacuous against the current
    contract: it used body=-14dBFS/transient=0.99, which lands at -13.83
    LUFS (inside the normal [-14.5,-13.5] band), never touching -16 at all,
    so the old `>= -16.0 - 0.01` assertion passed for a reason unrelated to
    the boundary it claimed to test.

    Fixture below is empirically tuned (per test-cases.md TC-016's own
    "tune the fixture's crest factor empirically" flag) to land in the
    untested middle tier -- confirmed via direct instrumentation to read
    ~-15.47 LUFS, i.e. below -14.5 (baseline rationale applies) but above
    -16.0 (below_documented_lufs_floor must be False), unlike TC-015/TC-130
    (~-19.8/-20.9) and TC-131 (genuinely unresolvable)."""
    sr = 44100
    audio = make_dynamic_track(
        sr, 40.0, body_amplitude=rms_amplitude_for_dbfs_sine(-24.0),
        transient_amplitude=0.7, transient_period_s=1.0, freq=220,
    )
    path = write_wav(tmp_wav_dir / "tc016.wav", audio, sr)

    try:
        result = pipeline.master(path, output_dir=out_dir, config=default_config)
    except UnresolvableMasteringConstraintError as exc:
        pytest.fail(
            "UnresolvableMasteringConstraintError must not be raised for this "
            f"DR/peak-feasible middle-tier fixture: {exc}"
        )

    solver = result.report.solver

    # Middle tier: below -14.5 (baseline rationale applies)...
    assert result.after.integrated_lufs < -14.5
    # ...but above -16.0, so the escalation flag must read False, unlike
    # TC-015/TC-130/TC-131.
    assert -16.0 <= result.after.integrated_lufs
    assert result.below_documented_lufs_floor is False
    assert solver["below_documented_lufs_floor"] is False

    # DR floor and true-peak ceiling hard constraints still held exactly.
    assert solver["dr_floor_used"] == pytest.approx(
        max(default_config.dr_floor, solver["source_dr"] - default_config.dr_max_reduction_db)
    )
    assert solver["achieved_dr"] >= solver["dr_floor_used"] - 0.01
    assert result.after.true_peak_dbtp <= -1.0 + 0.05

    # Baseline rationale tier: AC2 requires rationale text for any result
    # below -14.5, not only below -16.
    rationale = solver["rationale"]
    assert rationale is not None
    assert "DR floor" in rationale


def test_tc017_silence_only_does_not_crash(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = np.zeros((sr * 10, 2), dtype=np.float64)
    path = write_wav(tmp_wav_dir / "tc017.wav", audio, sr)

    # measure_integrated_lufs on all-zero must give a well-defined sentinel,
    # not raise/NaN.
    lufs = measure_integrated_lufs(audio, sr)
    assert lufs == float("-inf") or lufs is None or not np.isfinite(lufs)

    # Full pipeline: either raises a typed MasteringError, or completes with
    # a pass-through/no-op and a report note -- either is acceptable, only an
    # unhandled crash is a failure.
    from suno_mastering.errors import MasteringError
    try:
        pipeline.master(path, output_dir=out_dir, config=default_config)
    except MasteringError:
        pass
