"""STORY-002 non-functional requirements. TC-380-TC-385.

TC-380/381/382 genuinely need full-length (7-minute) material -- the NFR
itself is duration-scoped, and the per-track cost profile (8x-oversampled
true-peak FIR convolution, LRA short-term windowing) scales with duration;
a short fixture would not exercise the real cost. Marked slow; run
deliberately and once, per this suite's own run-budget discipline.
TC-383 (reproducibility) does not need full-length material and runs fast.
TC-384 is explicitly N/A (no processing stage in this story to bypass).
"""
from __future__ import annotations

import time

import pytest

from suno_mastering.reference_analysis import pipeline as ref_pipeline

from .ref_helpers import pink_noise_stereo, write_wav, ref_config


@pytest.mark.slow
def test_tc380_per_track_analysis_completes_in_seconds_not_minutes(tmp_path):
    sr = 44100
    audio = pink_noise_stereo(sr, 7 * 60.0, amplitude=0.15)
    p = write_wav(tmp_path / "seven_min.wav", audio, sr)
    start = time.perf_counter()
    ref_pipeline.analyze_track(p, ref_config())
    elapsed = time.perf_counter() - start
    print(f"TC-380: single 7-minute track analyze_track() took {elapsed:.1f}s")
    assert elapsed < 120.0  # "materially under minutes" -- generous ceiling, records actual time


@pytest.mark.slow
@pytest.mark.isolated
def test_tc381_whole_set_budget_under_5_minutes_worst_case(tmp_path):
    """Asserts against architecture.md v2's revised budget (DEF-102
    resolution: under 5 minutes for a 7-track/7-minute-average-track worst
    case), NOT test-cases.md TC-381's literal v1 '120 seconds' figure --
    that figure was superseded by DEF-102 before this suite was written.
    See defects.md for the corresponding test-spec-staleness entry.

    DEF-110 (defects.md; architecture.md v3 Section 16): this test showed
    the same session-position sensitivity as STORY-001's test_tc150 far
    more dramatically (1129.6s at the tail of an oversized combined run vs.
    a clean pass well under budget when test_ref_*.py runs as its own
    isolated suite). MUST be run in its own dedicated, isolated pytest
    invocation (see `@pytest.mark.isolated`), never at the tail of a large
    combined-suite run."""
    d = tmp_path / "refs"
    d.mkdir()
    sr = 44100
    for i in range(6):
        write_wav(d / f"r{i}.wav", pink_noise_stereo(sr, 7 * 60.0, seed=i, amplitude=0.15), sr)
    export_path = write_wav(tmp_path / "export.wav", pink_noise_stereo(sr, 7 * 60.0, seed=99, amplitude=0.2), sr)

    start = time.perf_counter()
    ref_pipeline.analyze_set(str(d), suno_export_path=export_path, config=ref_config())
    elapsed = time.perf_counter() - start
    print(f"TC-381: 7 x 7-minute tracks (6 reference + 1 comparison) took {elapsed:.1f}s")
    assert elapsed < 300.0  # architecture.md v2 Section 7.2's revised 5-minute worst-case budget


@pytest.mark.slow
def test_tc382_memory_does_not_grow_per_track(tmp_path):
    import tracemalloc

    d = tmp_path / "refs"
    d.mkdir()
    sr = 44100
    for i in range(6):
        write_wav(d / f"r{i}.wav", pink_noise_stereo(sr, 7 * 60.0, seed=i, amplitude=0.15), sr)

    tracemalloc.start()
    peaks = []
    config = ref_config()
    files = sorted(d.iterdir())
    for f in files:
        ref_pipeline.analyze_track(str(f), config)
        _, peak = tracemalloc.get_traced_memory()
        peaks.append(peak)
    tracemalloc.stop()

    print(f"TC-382: per-track cumulative tracemalloc peaks (bytes): {peaks}")
    # No unbounded per-track accumulation pattern (~2.4GB/track growth would
    # indicate a retained TruePeakResult.oversampled buffer, per architecture.md
    # Section 7's memory-discipline requirement). Peak should not grow
    # anywhere near linearly with track count.
    growth_last_vs_first = peaks[-1] - peaks[0]
    assert growth_last_vs_first < 1_000_000_000, (
        f"peak memory grew by {growth_last_vs_first / 1e9:.2f} GB across 6 tracks -- "
        f"consistent with a retained per-track buffer, not released between tracks"
    )


def test_tc383_reproducibility_identical_output_across_runs(tmp_path):
    d = tmp_path / "refs"
    d.mkdir()
    sr = 44100
    for i in range(5):
        write_wav(d / f"r{i}.wav", pink_noise_stereo(sr, 6.0, seed=i, amplitude=0.15), sr)

    config = ref_config(hf_min_duration_s=2.0)
    result1 = ref_pipeline.analyze_set(str(d), config=config)
    result2 = ref_pipeline.analyze_set(str(d), config=config)

    assert result1.aggregates == result2.aggregates
    assert result1.failures == result2.failures
    for m1, m2 in zip(result1.per_track, result2.per_track):
        assert m1 == m2


def test_tc384_bypass_disabled_stage_not_applicable():
    """N/A, per test-cases.md's own explicit statement: this story performs
    no audio processing or mastering of any kind, so there is no processing
    stage that could be bypassed or disabled, and therefore no
    bit-identical-output case to write."""
    pass
