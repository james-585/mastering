"""Section 15 -- non-functional requirements. TC-150..TC-152."""
from __future__ import annotations

import time

import pytest

from suno_mastering import pipeline

from .conftest import make_dynamic_track, write_wav


@pytest.mark.slow
@pytest.mark.isolated
def test_tc150_processing_time_budget(tmp_wav_dir, out_dir, default_config):
    """Full 8-minute, 48kHz/24-bit track under 5 minutes wall-clock, per
    requirements.md's NFR. The developer's own smoke test reported ~1m42s
    for a comparable 8.5min fixture; this test uses the same order of
    magnitude to keep CI runtime reasonable while still exercising the
    real budget-relevant code paths (not a scaled-down proxy).

    DEF-110 (defects.md; architecture.md v3 Section 16): this test's true
    isolated margin against its 300s budget is thin (~2-3%, ~290-294s
    measured). Session-level resource pressure (memory/page-cache,
    scheduler contention, thermal throttling) accumulated from 20-45+
    minutes of prior heavy numeric test work in the same process is enough
    to push it over budget when run at the tail of a large combined
    session, even though no production code is at fault. This is a
    test-execution-process issue, not a flaky test to be retried or a
    budget to be silently loosened -- it MUST be run in its own dedicated,
    isolated pytest invocation (see `@pytest.mark.isolated` and
    stories/STORY-001/automation/README.md / stories/STORY-002/automation/
    README.md for the exact command). Never fold it into a large combined
    suite run."""
    sr = 48000
    dur = 8 * 60.0
    audio = make_dynamic_track(sr, dur, body_amplitude=0.1, transient_amplitude=0.4,
                                transient_period_s=1.0, freq=220)
    path = write_wav(tmp_wav_dir / "tc150.wav", audio, sr)

    start = time.monotonic()
    pipeline.master(path, output_dir=out_dir, config=default_config)
    elapsed = time.monotonic() - start

    assert elapsed < 5 * 60, f"Pipeline took {elapsed:.1f}s, exceeding the 5-minute NFR budget"


@pytest.mark.slow
def test_tc151_vectorization_regression_guard(tmp_wav_dir, out_dir, default_config):
    """Runtime sanity check on a shorter fixture as a fast proxy for the
    full TC-150 fixture: if a stage were accidentally reimplemented as a
    sample-by-sample Python loop (e.g. the DR-meter block loop or the
    limiter's envelope follower), a 60s/48kHz stereo track would take
    dramatically longer than this generous ceiling."""
    sr = 48000
    dur = 60.0
    audio = make_dynamic_track(sr, dur, body_amplitude=0.1, transient_amplitude=0.4,
                                transient_period_s=1.0, freq=220)
    path = write_wav(tmp_wav_dir / "tc151.wav", audio, sr)

    start = time.monotonic()
    pipeline.master(path, output_dir=out_dir, config=default_config)
    elapsed = time.monotonic() - start

    # Generous ceiling (order of magnitude above expected ~5-15s) so this is
    # a regression guard against accidental O(n) Python loops, not a tight
    # performance gate that flakes on slower CI hardware.
    assert elapsed < 60.0, (
        f"60s fixture took {elapsed:.1f}s to process -- possible vectorization "
        f"regression (per-sample Python loop) in a DSP stage."
    )


@pytest.mark.skip(reason="TC-152: fidelity-vs-manual-baseline comparison requires a real "
                          "manually-mastered reference track (Audacity/bx_mastering workflow) "
                          "that does not exist in-repo -- flagged residual validation gap in "
                          "defects.md, same category as TC-024/TC-067, not a code failure.")
def test_tc152_fidelity_vs_manual_baseline():
    pass
