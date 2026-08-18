"""Analysis stage modules: each primary function takes plain numpy arrays +
sample rate (+ config where relevant), not file paths (architecture.md
Section 7, testability notes)."""
from __future__ import annotations

import numpy as np

from .artifact_detection import (
    MIN_SAMPLE_RATE_HZ as _ARTIFACT_MIN_SR,
    detect_artifacts,
    plausibility_warnings_for,
    summarize_artifacts_for_display,
)
from .clipping import detect_clipping
from .dynamic_range import measure_dynamic_range
from .frequency_balance import measure_frequency_balance
from .loudness import measure_integrated_lufs
from .sanity import check_correlation_range, check_lufs_plausible
from .stereo_phase import analyze_stereo_phase
from .true_peak import measure_true_peak
from .types import Measurements


def measure_all(audio: np.ndarray, sr: int, config) -> Measurements:
    """Run all six assessment criteria against `audio` (plain numpy array,
    mono (samples,) or stereo (samples, channels)) at sample rate `sr`.
    Used identically for pre-master (stage 2) and post-master (stage 9)
    analysis, per architecture.md Section 1 -- same analysis code, called
    twice, against different buffers."""
    channels = 1 if audio.ndim == 1 else audio.shape[1]
    is_mono = channels == 1
    duration_seconds = audio.shape[0] / sr if sr else 0.0

    integrated_lufs = measure_integrated_lufs(audio, sr)
    true_peak_result = measure_true_peak(audio, sr, config)
    dynamic_range_db = measure_dynamic_range(audio, sr, config)
    frequency_balance = measure_frequency_balance(audio, sr, config)
    stereo_phase = analyze_stereo_phase(audio, sr, config)
    clipping = detect_clipping(audio, sr, config, true_peak_result=true_peak_result)

    # STORY-003 sanity assertions (architecture.md Section 4.3): run on
    # every measure_all() call, mastering pipeline and reference pipeline
    # alike, since both call this same function. Never raises -- collects
    # advisory SanityWarning entries onto the result (module docstring's
    # hard rule, analysis/sanity.py).
    sanity_warnings = [
        w
        for w in (
            check_lufs_plausible(integrated_lufs),
            check_correlation_range(stereo_phase.overall_correlation),
        )
        if w is not None
    ]

    # STORY-007: artifact detection (arch §7.2). Runs after all standard
    # measures; returns audio byte-identical.
    # Explicit SR check avoids masking genuine ValueError bugs inside the
    # detector (CLAUDE.md: "fail loudly on invalid input").
    if sr >= _ARTIFACT_MIN_SR:
        _, artifact_result = detect_artifacts(audio, sr)
    else:
        artifact_result = None  # unsupported SR (< 32 kHz): skip silently

    artifact_warnings = (
        plausibility_warnings_for(artifact_result)
        if artifact_result is not None
        else []
    )

    return Measurements(
        sample_rate=sr,
        channels=channels,
        duration_seconds=duration_seconds,
        is_mono=is_mono,
        integrated_lufs=integrated_lufs,
        true_peak_dbtp=true_peak_result.dbtp,
        dynamic_range_db=dynamic_range_db,
        frequency_balance=frequency_balance,
        stereo_phase=stereo_phase,
        clipping=clipping,
        sanity_warnings=sanity_warnings,
        artifact_detection=artifact_result,
        plausibility_warnings=artifact_warnings,
    )
