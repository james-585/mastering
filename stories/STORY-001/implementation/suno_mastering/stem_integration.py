"""Integration example: Stem-separated pre-mastering in pipeline.py (STORY-008).

This file demonstrates how to integrate the stem separation stage into the
existing pipeline. It should be inserted BEFORE Stage 1 (measure_all) when
config.stem_config.enabled is True.

Usage pattern in pipeline.py master() function:

    # --- STORY-008: Optional stem separation pre-processing ---
    stem_result = None
    if config.stem_config.enabled:
        from .stem_integration import run_stem_preprocessing
        audio, stem_result = run_stem_preprocessing(
            audio=ingested.audio,
            sample_rate=ingested.sample_rate,
            stem_config=config.stem_config,
        )
        # audio is now the re-summed stems; continue with Stage 1
    
    # --- Stage 1: Ingest & Validate ---
    # ingested = ingest_mod.ingest(input_path)  # Already done above
    
    # --- Stage 2: Pre-Master Analysis ---
    before = analysis.measure_all(audio, ingested.sample_rate, config, targets_doc)
    # ... rest of pipeline ...

The stem_result (StemSeparationResult) should be added to MasteringResult
for inclusion in the final report.
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Tuple, Optional

import numpy as np

from .config import StemConfig
from .analysis.types import StemSeparationResult
from .io.stem_separation import split_stems
from .mastering.stem_processing import process_stems, sum_stems
from .mastering.stem_whistle_repair import attribute_and_repair_whistles

# STORY-019: deterministic Mid/Side boundary for the `other` stem lives in the
# story implementation folder (same cross-story pattern as pipeline.py).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_STORY_019_IMPL = _REPO_ROOT / "stories" / "STORY-019" / "implementation"
_STORY_023_IMPL = _REPO_ROOT / "stories" / "STORY-023" / "implementation"
for _story_impl in (_STORY_019_IMPL, _STORY_023_IMPL):
    if str(_story_impl) not in sys.path:
        sys.path.insert(0, str(_story_impl))

from stem_ms_dsp import process_other_stem
from audio_forensics import run_forensics

logger = logging.getLogger(__name__)


def run_stem_preprocessing(
    audio: np.ndarray,
    sample_rate: int,
    stem_config: StemConfig,
    identified_issues: Optional[list[dict]] = None,
    artifact_flags: Optional[list] = None,
) -> Tuple[np.ndarray, StemSeparationResult]:
    """Execute the complete stem separation and processing pipeline.
    
    This is the entry point for STORY-008's three-phase pre-mastering block:
        Phase A: AI separation (Demucs)
        Phase A2: attributed STATIONARY_WHISTLE repair (per-stem, surgical)
        Phase B: Targeted stem DSP only for issues previously identified on stems
        Phase C: Re-summation with sanity checks
    
    Args:
        audio: float64, shape (samples, 2) stereo input array
        sample_rate: int, sample rate in Hz
        stem_config: StemConfig instance with processing parameters
        artifact_flags: optional raw mix-level ArtifactFlag list, used to
            attribute and repair STATIONARY_WHISTLE flags per-stem
    
    Returns:
        (processed_audio, stem_result)
        - processed_audio: re-summed stereo array, ready for Stage 1
        - stem_result: StemSeparationResult for reporting
    
    Raises:
        DependencyError: if demucs/torch not installed
        ValueError: if stems have shape mismatches or contain NaN/Inf
    
    Post-condition:
        The returned audio array is guaranteed to:
        - Have shape (samples, 2), dtype float64
        - Contain no NaN or Inf values
        - Be ready to pass into analysis.measure_all() as if it were the
          original decoded audio
    """
    logger.info("=" * 70)
    logger.info("STEM SEPARATION PRE-PROCESSING (STORY-008)")
    logger.info("=" * 70)
    
    # ── Phase A: Separation ───────────────────────────────────────────────────
    logger.info(f"Phase A: Separating stems with model '{stem_config.model_name}'")
    t_start = time.perf_counter()
    
    stems = split_stems(
        audio_array=audio,
        sample_rate=sample_rate,
        stem_config=stem_config,
    )
    
    t_separation = time.perf_counter() - t_start
    logger.info(f"Separation complete in {t_separation:.2f}s")

    # ── STORY-019: deterministic M/S boundary on the `other` stem ─────────────
    # Runs immediately after extraction and before any per-stem repair, per the
    # STORY-019 architecture. The active path is a verified lossless round-trip
    # (encode/decode with a 1e-12 residual guard); diagnostics are retained in
    # the separation result metadata for the final report.
    runtime_metadata = dict(getattr(stems, "runtime_metadata", {}))
    ms_diagnostics: dict = {}
    stems = process_other_stem(dict(stems), bypass=False, diagnostics=ms_diagnostics)
    logger.info(
        "M/S other-stem stage: status=%s residual=%s safety=%s",
        ms_diagnostics.get("status"),
        ms_diagnostics.get("residual"),
        ms_diagnostics.get("safety"),
    )
    runtime_metadata["ms_other_stem"] = ms_diagnostics

    # ── Phase A2: attributed whistle repair ───────────────────────────────────
    # Mix-level detection can't know which stem a tone lives in; now that
    # stems exist, attribute each STATIONARY_WHISTLE flag by measured
    # per-stem energy and notch only the dominant stem. Other artifact types
    # have no honest per-stem attribution and are left untouched here.
    whistle_actions = []
    if artifact_flags:
        stems, whistle_actions = attribute_and_repair_whistles(
            stems=stems,
            sample_rate=sample_rate,
            artifact_flags=artifact_flags,
        )

    # ── Phase B: Targeted DSP ─────────────────────────────────────────────────
    logger.info("Phase B: Applying targeted DSP to stems")
    
    processed_stems, actions = process_stems(
        stems=stems,
        sample_rate=sample_rate,
        identified_issues=identified_issues,
    )
    actions = whistle_actions + actions
    
    for action in actions:
        logger.info(
            f"  {action.stem_name:8s}: {action.action_type:15s} {action.parameters}"
        )
    
    # ── Phase C: Re-summation ─────────────────────────────────────────────────
    logger.info("Phase C: Re-summing processed stems")
    
    summed_audio = sum_stems(processed_stems)
    
    # Verify output shape and dtype match input
    if summed_audio.shape != audio.shape:
        raise RuntimeError(
            f"Stem re-summation changed audio shape: "
            f"{audio.shape} -> {summed_audio.shape}"
        )
    
    if summed_audio.dtype != np.float64:
        summed_audio = summed_audio.astype(np.float64)
        logger.warning(
            f"Converted re-summed audio from {summed_audio.dtype} to float64"
        )

    # ── Peak-normalise stem sum before forensics gate ─────────────────────────
    # The forensics gate checks BOTH the sample peak (> 0.999999) and the 8x
    # oversampled true peak (> 1.000001). A sample-peak normalisation to 0.9999
    # is not sufficient — inter-sample peaks can still exceed 1.0 and fail the
    # true-peak guard. Compute both and normalise based on the larger value.
    # Guard: only fire on minor overloads (< 3 dB). Real gain bugs ≥ 1.414 are
    # left for the forensics hard-fail.
    _stem_sum_sample_peak = float(np.max(np.abs(summed_audio)))
    _flat = summed_audio.reshape(-1).astype(np.float64)
    _n = _flat.size
    if _n >= 2:
        _idx = np.linspace(0.0, _n - 1.0, _n * 8, endpoint=False)
        _lo = np.floor(_idx).astype(np.int64)
        _hi = np.clip(_lo + 1, 0, _n - 1)
        _frac = _idx - _lo
        _stem_sum_true_peak = float(np.max(np.abs(_flat[_lo] + (_flat[_hi] - _flat[_lo]) * _frac)))
    else:
        _stem_sum_true_peak = _stem_sum_sample_peak
    _stem_sum_peak = max(_stem_sum_sample_peak, _stem_sum_true_peak)
    if _stem_sum_peak > 0.999999 and _stem_sum_peak < 1.414:
        _scale = 0.9990 / _stem_sum_peak
        summed_audio = summed_audio * _scale
        # Scale individual stems by the same factor so Phase D processing
        # (transient restoration) receives consistent, in-range arrays.
        processed_stems = {name: stem * _scale for name, stem in processed_stems.items()}
        logger.warning(
            "Stem re-summation: sample peak %.4f / true peak %.4f exceeds guard; "
            "normalised by %.6f — inaudible.",
            _stem_sum_sample_peak, _stem_sum_true_peak, _scale,
        )

    # ── STORY-023: mandatory forensics gate after split/re-summation ──────────
    # Clipping and phase-mismatch verdicts hard-fail the run. The reconstruction
    # residual is retained as loud telemetry (STORY-022 disposition: residual is
    # expected on real separated material once targeted stem DSP has acted, so a
    # breach is reported, not fabricated into a pass).
    forensics = run_forensics(audio, summed_audio, processed_stems, sample_rate)
    logger.info("Forensics gate (STORY-023):\n%s", forensics.to_text())
    runtime_metadata["forensics"] = forensics.to_dict()
    if forensics.clipping_detected or forensics.phase_mismatch_detected:
        raise ValueError(
            "Stem forensics gate failed: " + "; ".join(forensics.reasons)
        )
    if forensics.reconstruction_artifact_detected:
        logger.warning(
            "Reconstruction residual %.6e exceeds %.1e telemetry threshold "
            "(residual_dbfs=%.2f). Continuing with the residual recorded in the "
            "report; this measures stem DSP divergence, not a lossless bypass.",
            forensics.residual_error_max,
            1e-6,
            forensics.residual_error_dbfs,
        )
        print(
            f"[Forensics] reconstruction residual "
            f"{forensics.residual_error_max:.3e} "
            f"({forensics.residual_error_dbfs:.2f} dBFS) recorded as telemetry"
        )
    else:
        print("[Forensics] split/re-summation path clean (clipping/phase/residual all pass)")

    # ── Build result object ───────────────────────────────────────────────────
    result = StemSeparationResult(
        model_used=stem_config.model_name,
        separation_time_s=t_separation,
        actions_applied=actions,
        stems={name: np.asarray(stem, dtype=np.float64) for name, stem in processed_stems.items()},
        runtime_metadata=runtime_metadata,
    )
    
    logger.info("=" * 70)
    logger.info(
        f"Stem pre-processing complete. "
        f"Processed audio peak: {np.abs(summed_audio).max():.6f}"
    )
    logger.info("=" * 70)
    
    return summed_audio, result


def verify_null_sum(
    original_audio: np.ndarray,
    processed_audio: np.ndarray,
    tolerance_dbfs: float = -80.0,
) -> bool:
    """Acceptance test: verify stems re-sum to original when DSP is bypassed.
    
    STORY-008 AC "Null Sum Test": If Phase B (Targeted DSP) is bypassed,
    the Phase C re-summed audio array must phase-cancel with the original
    input audio array to within -80 dBFS tolerance.
    
    This is a unit test helper, not part of the main pipeline flow.
    
    Args:
        original_audio: original input array
        processed_audio: re-summed stems (with DSP bypassed)
        tolerance_dbfs: acceptable difference in dB FS (default -80 dBFS)
    
    Returns:
        True if null test passes, False otherwise.
    
    Example usage in test:
        stems = split_stems(audio, sr, model="htdemucs")
        # Skip process_stems(), just sum directly
        summed = sum_stems(stems)
        assert verify_null_sum(audio, summed, tolerance_dbfs=-80.0)
    """
    if original_audio.shape != processed_audio.shape:
        logger.error(
            f"Null sum test failed: shape mismatch "
            f"{original_audio.shape} vs {processed_audio.shape}"
        )
        return False
    
    difference = original_audio - processed_audio
    peak_diff = np.abs(difference).max()
    original_peak = np.abs(original_audio).max()

    # Compare the reconstruction error against the original signal's actual peak,
    # not against 0 dBFS. This is the contract for a null-sum test on quiet or
    # non-full-scale content: the residual should be tiny relative to the source
    # itself, even when the input is well below unity peak.
    if peak_diff > 0 and original_peak > 0:
        peak_diff_dbfs = 20 * np.log10(peak_diff / original_peak)
    elif peak_diff > 0:
        peak_diff_dbfs = 20 * np.log10(peak_diff)
    else:
        peak_diff_dbfs = -np.inf

    passed = peak_diff_dbfs <= tolerance_dbfs
    
    logger.info(
        f"Null sum test: peak difference = {peak_diff_dbfs:.2f} dB FS "
        f"(tolerance: {tolerance_dbfs:.2f} dB FS) -> {'PASS' if passed else 'FAIL'}"
    )
    
    return passed
