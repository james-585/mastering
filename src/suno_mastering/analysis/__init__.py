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
from .hf_extension import measure_hf_extension
from .loudness import measure_integrated_lufs
from .loudness_range import measure_loudness_range
from .per_band_stereo_width import measure_per_band_stereo_width
from .sanity import check_correlation_range, check_lufs_plausible
from .stereo_phase import analyze_stereo_phase
from .true_peak import measure_true_peak
from .types import Measurements


def measure_all(audio: np.ndarray, sr: int, config) -> Measurements:
    """Run all six assessment criteria against `audio` (plain numpy array,
    mono (samples,) or stereo (samples, channels)) at sample rate `sr`.
    Used identically for pre-master (stage 2) and post-master (stage 9)
    analysis, per architecture.md Section 1 -- same analysis code, called
    twice, against different buffers.

    STORY-027: also calls measure_hf_extension (wired into both pre- and
    post-master calls per architecture §6.2).  Result is report-only;
    no lift behaviour is applied (CLAUDE.md §6.2, Gate 1 DECISION 1).
    """
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
        _detect_whistles = getattr(getattr(config, "repair_whistles", None), "detect_stationary_whistles", True)
        _, artifact_result = detect_artifacts(audio, sr, detect_stationary_whistles=_detect_whistles)
    else:
        artifact_result = None  # unsupported SR (< 32 kHz): skip silently

    artifact_warnings = (
        plausibility_warnings_for(artifact_result)
        if artifact_result is not None
        else []
    )

    # STORY-027 §6.2: HF band-limit cliff detection.  Wired into both pre- and
    # post-master measure_all calls (ARCHITECTURE.md §2: same code path on both).
    # Gate 1 DECISION 4: per-segment PSD stays enabled (confidence assessment
    # distinguishes a real filter cutoff from a spurious detection).
    # measure_hf_extension expects a ReferenceAnalysisConfig; create one on
    # demand from the passed config (MasteringConfig).  ReferenceAnalysisConfig
    # falls through to mastering for any attribute it doesn't define itself.
    try:
        from ..reference_analysis.config import ReferenceAnalysisConfig as _RefCfg
        _ref_cfg = _RefCfg(mastering=config)
        hf_result = measure_hf_extension(audio, sr, _ref_cfg)
        hf_band_limit_hz = hf_result.hf_band_limit_hz
        hf_band_limit_confidence: float | None = hf_result.hf_band_limit_confidence
    except Exception:
        # Never let hf_extension failure abort a mastering run.
        hf_band_limit_hz = None
        hf_band_limit_confidence = None

    try:
        from ..reference_analysis.config import ReferenceAnalysisConfig as _RefCfg
        _ref_cfg_lra = _RefCfg(mastering=config)
        lra_result = measure_loudness_range(audio, sr, _ref_cfg_lra)
    except Exception:
        lra_result = None

    try:
        from ..reference_analysis.config import ReferenceAnalysisConfig as _RefCfg
        _ref_cfg_pbw = _RefCfg(mastering=config)
        per_band_width_result = (
            measure_per_band_stereo_width(audio, sr, _ref_cfg_pbw)
            if not is_mono
            else None
        )
    except Exception:
        per_band_width_result = None

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
        hf_band_limit_hz=hf_band_limit_hz,
        hf_band_limit_confidence=hf_band_limit_confidence,
        lra=lra_result,
        per_band_stereo_width=per_band_width_result,
    )
