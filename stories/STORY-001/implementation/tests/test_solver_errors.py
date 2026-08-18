"""Section 12 -- solver "give-up" path and typed error hierarchy.
TC-130..TC-133."""
from __future__ import annotations

import subprocess
import sys

import numpy as np
import pytest

from suno_mastering import pipeline
from suno_mastering.errors import (
    InvalidWavError,
    MasteringError,
    UnresolvableMasteringConstraintError,
    UnsupportedFormatError,
)

from .conftest import make_dynamic_track, rms_amplitude_for_dbfs_sine, write_wav


def test_tc130_peak_ceiling_wins_over_lufs_band(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    body = rms_amplitude_for_dbfs_sine(-32.0)
    transient = 10 ** (-0.9 / 20)  # near-ceiling peak, very low body loudness -> huge crest factor
    audio = make_dynamic_track(sr, 40.0, body_amplitude=body, transient_amplitude=transient,
                                transient_period_s=1.0, freq=220)
    path = write_wav(tmp_wav_dir / "tc130.wav", audio, sr)

    # This is one of the two high-crest-factor fixtures DEF-001/architecture.md
    # v4 Section 1 names explicitly (source DR=20, dr_required=17; the
    # developer's hand-bisected figures put achieved LUFS around -20.87).
    # (a) solver must NOT raise UnresolvableMasteringConstraintError -- v4
    # resolves this to a real, reported (if low) LUFS value instead. Assert
    # explicitly rather than relying on an implicit "reaching the next line
    # means it didn't raise".
    try:
        result = pipeline.master(path, output_dir=out_dir, config=default_config)
    except UnresolvableMasteringConstraintError as exc:
        pytest.fail(
            "UnresolvableMasteringConstraintError must not be raised for this "
            f"high-crest-factor fixture per architecture.md v4 Section 1: {exc}"
        )

    # v4 (architecture.md Section 1, resolves DEF-001 residual): -16 LUFS is
    # a soft, report-escalation threshold, not a hard solver constraint, for
    # high-crest-factor sources like this fixture. Do NOT assert
    # achieved_lufs >= lufs_floor here (that was the removed v1-v3 contract).
    assert result.after.true_peak_dbtp <= default_config.true_peak_ceiling_dbtp + 0.01

    solver = result.report.solver

    # (b) below_documented_lufs_floor must be True for this fixture -- this
    # fixture is engineered to be true-peak/DR-conflict-driven and is known
    # (per DEF-001's own hand-bisected figures) to land around -20.87 LUFS,
    # well below the -16 floor.
    assert result.below_documented_lufs_floor is True
    assert solver["below_documented_lufs_floor"] is True

    # (c) the DR floor hard constraint must still be held exactly
    # (achieved DR meets max(DR8, source_DR - 3dB)).
    assert solver["dr_floor_used"] == pytest.approx(
        max(default_config.dr_floor, solver["source_dr"] - default_config.dr_max_reduction_db)
    )
    assert solver["achieved_dr"] >= solver["dr_floor_used"] - 0.01

    # (d) rationale text must name the DR floor as the reason for landing
    # below -16 LUFS (architecture.md v4 Section 1 point 5).
    rationale = solver["rationale"]
    assert rationale is not None
    assert "DR floor" in rationale
    assert f"{solver['dr_floor_used']:.1f}" in rationale


def test_tc131_unresolvable_case_raises_no_partial_output(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    # DEF-009 fix: replaced the previous unreliable fixture (body=-6 dBFS,
    # transient_len_ms=200 ms) with a confirmed DR≈3 fixture that reliably
    # raises UnresolvableMasteringConstraintError. Uses old TC-023[hot] shape:
    # body=rms_amp(-6.0)≈0.708, transient=0.98, default 5 ms transient bursts.
    # Confirmed by pre-fix DEF-009 runs: Source DR=3.0, floor=8.0 → raises.
    # Non-vacuity: disabling the raise at loudness_limit.py line 204 makes
    # this test fail (pipeline.master completes without raising).
    body = rms_amplitude_for_dbfs_sine(-6.0)   # ≈ 0.708, DR≈3 with transient=0.98
    transient = 0.98
    audio = make_dynamic_track(sr, 40.0, body_amplitude=body, transient_amplitude=transient,
                                transient_period_s=1.0, freq=220)
    path = write_wav(tmp_wav_dir / "tc131.wav", audio, sr)

    import os
    with pytest.raises(UnresolvableMasteringConstraintError,
                       match=r"DR floor"):
        pipeline.master(path, output_dir=out_dir, config=default_config)

    expected_output = os.path.join(out_dir, "tc131_mastered.wav")
    assert not os.path.exists(expected_output)


def test_tc132_typed_exception_hierarchy():
    assert issubclass(InvalidWavError, MasteringError)
    assert issubclass(UnsupportedFormatError, MasteringError)
    assert issubclass(UnresolvableMasteringConstraintError, MasteringError)


def test_tc133_cli_clean_error_nonzero_exit(tmp_wav_dir):
    corrupt = tmp_wav_dir / "corrupt.wav"
    corrupt.write_bytes(b"NOTRIFFHEADERBYTES" + b"\x00" * 100)

    proc = subprocess.run(
        [sys.executable, "-m", "suno_mastering", str(corrupt)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "Traceback (most recent call last)" not in combined
    assert "ERROR" in combined or "Error" in combined
