"""Intra-track dynamics leveling stage (STORY-027 §7).

Reduces arrangement-level loudness swings via a slow, downward-only gain
envelope computed from 3-second window loudness measurements.  Sits at
Stage 3c (before the LUFS/DR/TP solver), which then receives the post-
leveler TT DR rather than the pre-leveler source DR.

Design choices (architecture §7.1-7.7):
- Operates on the stereo sum.  Arrangement-level variation is a property of
  the complete mix; per-stem leveling changes relative stem balance (mixing,
  not mastering) — consistent with Item 2's stereo-sum decision (§7.1).
- Downward-only: never boosts.  Upward gain can create new true-peak
  violations; the solver handles final loudness unconditionally.  Downward-
  only cannot create TP violations — satisfied by construction (§7.3 Step 3).
- Internal loudness target: mean of finite window values.  Architecture §7.2
  Step 2 specifies mean.  Mean is pulled upward by outlier-loud windows,
  reducing attenuation on moderately loud sections.  Choice documented here,
  not silently defaulted (Gate 1 incidental note).
- Smoothing: first-order IIR low-pass at 1.5-second time constant.  This
  converts the per-window step function into a continuous envelope.  Gate 1
  Concern 4 notes that 1.5 s TC may be audible at drop entrances; AC21
  (listening gate) must test this on real material.  TC is not changed here
  without a Gate 1 decision.

DEF-027-001 RESOLVED (architecture v1.3, 2026-08-21):
pyloudnorm.Meter.integrated_loudness() was replaced with K-weighted ungated
mean-square per architecture §7.2 v1.3.  The new path:
1. Apply BS.1770-4 K-weighting to the full buffer via scipy.signal.sosfilt
   (causal forward-pass only — zero-phase is wrong for loudness measurement).
   K-weighting filters are computed at the actual track sample rate; no
   hardcoded coefficients.
2. Compute sliding 3-second window mean-square at 100 ms hop, convert to
   LUFS without relative gating (L = -0.691 + 10*log10(ms)).
3. The 100 ms hop eliminates the step quantisation previously compensated
   by the 1.5-second IIR smoothing.  Smoothing is retained for the gain
   trajectory; its time constant remains sound at 100 ms resolution.
pyloudnorm is NOT used in the window-loudness path (may still be used
elsewhere in the pipeline — just not here).

targets.json dependency:
  leveling.no_op_threshold_db  — window-LUFS std below which the stage is a no-op.
  leveling.max_attenuation_db  — maximum downward gain ride per window (dB).

Both values require a reference-track derivation pass (§7.3).  Until that
pass runs and commits the values to targets.json, the stage skips with
reason "leveling_targets_not_derived" and still populates post_leveler_dr_db
from the unchanged buffer (required by pipeline.py — passed unconditionally
to solver).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
from scipy.signal import lfilter, sosfilt

from ..analysis.dynamic_range import measure_dynamic_range

logger = logging.getLogger(__name__)

# IIR smoothing time constant (seconds) — architecture §7.2 Step 3.
# Gate 1 Concern 4: 1.5 s may be audible at drop entrances.  Not changed
# here without a Gate 1 decision; AC21 listening gate must test this.
_SMOOTHING_TC_S: float = 1.5

# Window duration (seconds) — must match the reference-track derivation pass
# that produced no_op_threshold_db (architecture §7.3).
_WINDOW_S: float = 3.0

# Hop between successive windows (seconds) — architecture §7.2 Step 1.
_HOP_S: float = 0.10  # 100 ms; finer resolution than previous 3 s blocks

# BS.1770 absolute gate threshold.  Windows below this level are considered
# effectively silent: their LUFS is set to -inf so they are excluded from
# target_mean and std computation, and their gain is set to 0.0 (pass-through).
# Without this gate, truly silent blocks (-90 dBFS) produce finite LUFS values
# that drag target_mean down and cause large IIR-smoothed attenuation to bleed
# into adjacent silent regions.
_ABS_GATE_LUFS: float = -70.0


@dataclass
class LevelingAction:
    """Report record for the dynamics leveling stage.

    Always produced (applied=False on no-op paths).  post_leveler_dr_db is
    always populated — pipeline.py passes it to the solver unconditionally
    (Gate 1 v1.2 follow-up: must not be 0.0 or None on the no-op path).
    """
    applied: bool
    reason: str                      # "leveling_applied" | "loudness_range_below_threshold"
                                     # | "leveling_targets_not_derived"
    std_lufs_before: float           # std of finite window LUFS before leveling
    std_lufs_after: Optional[float]  # None if not applied
    max_gain_db_applied: float       # most negative value applied; 0.0 if not applied
    window_count: int
    gated_windows: int               # windows with -inf integrated LUFS (gated out)
    post_leveler_dr_db: float        # TT DR from the leveled (or unchanged) buffer;
                                     # always populated; pipeline passes to solver


def _kw_prefilter_sos(sr: int) -> np.ndarray:
    """BS.1770-4 Stage 1 pre-filter (high-shelf, head acoustics) at sr.

    Implements the bilinear-transform high-shelf design with K = tan(pi*f/sr)
    prewarping.  This is sample-rate-correct — no hardcoded coefficients.
    Reference: ITU-R BS.1770-4 Annex 1, Table 1; standard bilinear-transform
    shelving filter (cf. Audio EQ Cookbook; scipy bilinear_zpk convention).

    Parameters at 48 kHz produce coefficients matching the BS.1770-4 reference
    values within floating-point precision.
    """
    f0 = 1681.97          # shelf transition frequency (Hz), BS.1770-4
    shelf_gain_db = 4.0   # +4 dB shelf gain, BS.1770-4
    Q = 0.7071            # ~1/sqrt(2), Butterworth Q

    K = np.tan(np.pi * f0 / sr)
    Vh = 10.0 ** (shelf_gain_db / 20.0)
    # Vb matched to Vh per pyloudnorm convention for this specific filter:
    Vb = Vh ** 0.4996667741545416

    a0 = 1.0 + K / Q + K * K
    b0 = (Vh + Vb * K / Q + K * K) / a0
    b1 = 2.0 * (K * K - Vh) / a0
    b2 = (Vh - Vb * K / Q + K * K) / a0
    a1 = 2.0 * (K * K - 1.0) / a0
    a2 = (1.0 - K / Q + K * K) / a0
    # Return as SOS section: [b0, b1, b2, 1.0, a1, a2]
    return np.array([[b0, b1, b2, 1.0, a1, a2]], dtype=np.float64)


def _kw_highpass_sos(sr: int) -> np.ndarray:
    """BS.1770-4 Stage 2 highpass (2nd-order Butterworth at 38.135 Hz) at sr.

    Bilinear-transform Butterworth highpass; sample-rate-correct.
    """
    f_hp = 38.135  # Hz, BS.1770-4
    Q = 0.7071

    K = np.tan(np.pi * f_hp / sr)
    a0 = K * K + K / Q + 1.0
    b0 = 1.0 / a0
    b1 = -2.0 / a0
    b2 = 1.0 / a0
    a1 = 2.0 * (K * K - 1.0) / a0
    a2 = (K * K - K / Q + 1.0) / a0
    return np.array([[b0, b1, b2, 1.0, a1, a2]], dtype=np.float64)


def _apply_k_weighting(audio: np.ndarray, sr: int) -> np.ndarray:
    """Apply BS.1770-4 K-weighting to audio using scipy.signal.sosfilt.

    Forward-pass only (causal) — sosfiltfilt is wrong for loudness measurement
    (architecture §7.2).  Returns float64 K-weighted buffer, same shape as input.
    """
    prefilter_sos = _kw_prefilter_sos(sr)
    highpass_sos = _kw_highpass_sos(sr)
    kw = sosfilt(prefilter_sos, audio.astype(np.float64), axis=0)
    kw = sosfilt(highpass_sos, kw, axis=0)
    return kw


def _lufs_from_ms(ms: float) -> float:
    """Convert K-weighted mean-square to LUFS, applying the absolute gate."""
    if ms <= 0.0:
        return float("-inf")
    lufs = -0.691 + 10.0 * np.log10(ms)
    return lufs if lufs >= _ABS_GATE_LUFS else float("-inf")


def _compute_block_lufs(audio: np.ndarray, sr: int) -> list[float]:
    """Non-overlapping 3-second block LUFS for reporting and gate check.

    Each block is K-weighted independently (fresh filter state) so that IIR
    transients from a loud block do not contaminate the measured LUFS of an
    adjacent silent block.  If K-weighting were applied to the full track
    and the block sliced from the result, a loud-to-silent transition would
    leave -35 dBFS IIR transient energy in the first ~54 ms of the silent
    block, raising its mean-square above the -70 LUFS absolute gate and
    preventing correct gating.

    Used for: window_count, gated_windows, std_lufs_before/after, no-op
    gate, and target_mean_l.  Non-overlapping blocks are consistent with the
    reference-track derivation pass (§7.3) and with what the tests expect.

    Returns one LUFS value per non-overlapping 3-second block.  Silent blocks
    (LUFS < _ABS_GATE_LUFS) return -inf.
    """
    window_samples = int(round(_WINDOW_S * sr))
    n_blocks = audio.shape[0] // window_samples
    block_lufs: list[float] = []
    for i in range(n_blocks):
        start = i * window_samples
        chunk_audio = audio[start : start + window_samples]
        kw_chunk = _apply_k_weighting(chunk_audio, sr)
        ms = float(np.mean(kw_chunk ** 2))
        block_lufs.append(_lufs_from_ms(ms))
    return block_lufs


def _compute_window_lufs(kw: np.ndarray, sr: int) -> list[float]:
    """100 ms hop K-weighted LUFS for gain envelope computation.

    DEF-027-001 resolution (architecture §7.2 v1.3):
    Uses K-weighted mean-square without intra-window relative gating.
    Window = 3 s; hop = 100 ms.  Silent/near-silent windows (below the
    BS.1770 absolute gate of -70 LUFS) return -inf and receive gain_db = 0.0
    (pass-through) in the gain envelope — they do not influence the
    gain computation.

    Note: accepts the already-K-weighted buffer (kw) to avoid redundant
    K-weighting when both block and hop LUFS are needed in the same call.
    """
    window_samples = int(round(_WINDOW_S * sr))
    hop_samples = int(round(_HOP_S * sr))
    n_samples = kw.shape[0]

    window_lufs: list[float] = []
    for start in range(0, n_samples - window_samples + 1, hop_samples):
        chunk = kw[start : start + window_samples]
        ms = float(np.mean(chunk ** 2))
        window_lufs.append(_lufs_from_ms(ms))
    return window_lufs


def _iir_smooth_envelope(
    gain_db_per_window: list[float], sr: int, n_audio_samples: int
) -> np.ndarray:
    """Up-sample per-hop gain_db to sample rate, then smooth with a
    first-order IIR low-pass at _SMOOTHING_TC_S time constant.

    Each element of gain_db_per_window corresponds to one 100 ms hop
    (architecture §7.2 v1.3 — hop resolution replaces the old 3-second step).

    n_audio_samples: total samples in the audio buffer.  gain_db_samples is
    padded to this length (holding the last hop's gain) before the IIR pass so
    the gain envelope covers the full buffer.  Without this, the last 3-second
    window (which starts at n_audio_samples - window_samples) only contributes
    gain for the following 100 ms hop period rather than the full trailing
    duration.

    Returns a float64 linear-scale gain array of shape (n_audio_samples,).

    Uses scipy.signal.lfilter for the IIR pass (vectorized, not a Python loop).
    Transfer function: y[n] = alpha*x[n] + (1-alpha)*y[n-1]
      b = [alpha], a = [1, -(1-alpha)]
    """
    hop_len = int(round(_HOP_S * sr))   # samples per 100 ms hop
    n_hops = len(gain_db_per_window)
    hop_covered = n_hops * hop_len

    # Nearest-neighbour up-sample: each gain value held for one hop period,
    # then held at the last value until n_audio_samples.
    total_samples = max(hop_covered, n_audio_samples)
    gain_db_samples = np.empty(total_samples, dtype=np.float64)
    for i, g in enumerate(gain_db_per_window):
        gain_db_samples[i * hop_len : (i + 1) * hop_len] = g
    # Pad trailing audio not covered by any hop period with last hop's gain.
    last_gain = gain_db_per_window[-1] if gain_db_per_window else 0.0
    if hop_covered < total_samples:
        gain_db_samples[hop_covered:] = last_gain

    # First-order IIR low-pass via scipy.signal.lfilter (causal, vectorized)
    alpha = float(1.0 - np.exp(-1.0 / (_SMOOTHING_TC_S * sr)))
    b_iir = np.array([alpha], dtype=np.float64)
    a_iir = np.array([1.0, -(1.0 - alpha)], dtype=np.float64)
    smoothed_db = lfilter(b_iir, a_iir, gain_db_samples).astype(np.float64)

    # Truncate to exactly n_audio_samples and convert dB to linear gain
    return 10.0 ** (smoothed_db[:n_audio_samples] / 20.0)


def apply_dynamics_leveler(
    audio: np.ndarray,
    sr: int,
    targets: dict,
    config,
) -> tuple[np.ndarray, LevelingAction]:
    """Apply slow downward-only gain envelope to reduce arrangement-level loudness swings.

    audio: float64, shape (N, 2) stereo.  Mono is accepted but this stage
           targets the stereo sum (architecture §7.1).
    sr:    sample rate in Hz.
    targets: parsed targets.json dict.
    config:  MasteringConfig (used for TT DR re-measurement).

    Returns (audio_out, LevelingAction).  audio_out is the unchanged buffer
    when the gate fires or targets are not yet derived.  LevelingAction is
    always populated including post_leveler_dr_db.
    """
    if sr <= 0:
        raise ValueError(f"dynamics_leveler: invalid sample rate {sr}")
    if audio.ndim not in (1, 2):
        raise ValueError(f"dynamics_leveler: expected 1-D or 2-D audio, got shape {audio.shape}")

    def _measure_dr(buf: np.ndarray) -> float:
        return float(measure_dynamic_range(buf, sr, config))

    # --- Read targets.json leveling block ---
    leveling_targets = targets.get("leveling")
    if leveling_targets is None or "no_op_threshold_db" not in leveling_targets or "max_attenuation_db" not in leveling_targets:
        # Targets not yet derived — skip with an explicit reason.
        logger.info("dynamics_leveler: leveling targets not yet derived in targets.json; stage skipped")
        post_dr = _measure_dr(audio)
        return audio, LevelingAction(
            applied=False,
            reason="leveling_targets_not_derived",
            std_lufs_before=0.0,
            std_lufs_after=None,
            max_gain_db_applied=0.0,
            window_count=0,
            gated_windows=0,
            post_leveler_dr_db=post_dr,
        )

    no_op_threshold_db = float(leveling_targets["no_op_threshold_db"])
    max_attenuation_db = float(leveling_targets["max_attenuation_db"])

    # K-weight once; both block and hop computations share the result.
    kw = _apply_k_weighting(audio, sr)

    # --- Step 1a: block LUFS (non-overlapping 3 s) for reporting + gate ---
    # window_count, gated_windows, std_lufs_before/after, and the no-op gate
    # are all reported from non-overlapping 3-second blocks.  Each block is
    # K-weighted independently (fresh filter state) — see _compute_block_lufs
    # docstring for why this is required for correct gating.
    block_lufs = _compute_block_lufs(audio, sr)
    n_blocks = len(block_lufs)

    if n_blocks == 0:
        # Track too short for even one 3-second block — skip.
        post_dr = _measure_dr(audio)
        return audio, LevelingAction(
            applied=False,
            reason="loudness_range_below_threshold",
            std_lufs_before=0.0,
            std_lufs_after=None,
            max_gain_db_applied=0.0,
            window_count=0,
            gated_windows=0,
            post_leveler_dr_db=post_dr,
        )

    finite_block_lufs = [v for v in block_lufs if np.isfinite(v)]
    gated_block_count = n_blocks - len(finite_block_lufs)

    # --- Step 5 gate (BEFORE envelope computation — Gate 1 correctness note) ---
    if len(finite_block_lufs) < 2:
        post_dr = _measure_dr(audio)
        return audio, LevelingAction(
            applied=False,
            reason="loudness_range_below_threshold",
            std_lufs_before=0.0,
            std_lufs_after=None,
            max_gain_db_applied=0.0,
            window_count=n_blocks,
            gated_windows=gated_block_count,
            post_leveler_dr_db=post_dr,
        )

    std_l = float(np.std(finite_block_lufs))

    if std_l < no_op_threshold_db:
        post_dr = _measure_dr(audio)
        return audio, LevelingAction(
            applied=False,
            reason="loudness_range_below_threshold",
            std_lufs_before=std_l,
            std_lufs_after=None,
            max_gain_db_applied=0.0,
            window_count=n_blocks,
            gated_windows=gated_block_count,
            post_leveler_dr_db=post_dr,
        )

    # --- Step 2: target = mean of finite block LUFS (consistent with derivation) ---
    target_mean_l = float(np.mean(finite_block_lufs))

    # --- Step 1b: hop LUFS (100 ms) for fine-grained gain envelope (DEF-027-001) ---
    # The 100 ms hop eliminates the 3-second step quantisation: gain changes
    # smoothly at section boundaries rather than in 3-second steps.
    hop_lufs = _compute_window_lufs(kw, sr)

    # --- Step 3: gain envelope (downward-only, capped, per 100 ms hop) ---
    gain_db_per_hop: list[float] = []
    for lufs in hop_lufs:
        if not np.isfinite(lufs):
            # Gated hop (silent/near-silent): pass-through
            gain_db_per_hop.append(0.0)
        else:
            g = target_mean_l - lufs
            g = min(g, 0.0)                   # downward-only
            g = max(g, -max_attenuation_db)   # attenuation cap
            gain_db_per_hop.append(g)

    # --- Smooth and up-sample (hop resolution) ---
    envelope = _iir_smooth_envelope(gain_db_per_hop, sr, audio.shape[0])

    # --- Step 4: apply ---
    # envelope is exactly audio.shape[0] samples (padded in _iir_smooth_envelope)
    out = audio.copy()
    if out.ndim == 2:
        out *= envelope[:, np.newaxis]
    else:
        out *= envelope

    max_gain_applied = float(np.min(envelope))
    max_gain_db_applied = 20.0 * np.log10(max(max_gain_applied, 1e-12))

    # Measure block std after leveling (for reporting)
    after_block_lufs = _compute_block_lufs(out, sr)
    finite_after = [v for v in after_block_lufs if np.isfinite(v)]
    std_l_after = float(np.std(finite_after)) if len(finite_after) >= 2 else 0.0

    post_dr = _measure_dr(out)

    return out, LevelingAction(
        applied=True,
        reason="leveling_applied",
        std_lufs_before=std_l,
        std_lufs_after=std_l_after,
        max_gain_db_applied=max_gain_db_applied,
        window_count=n_blocks,
        gated_windows=gated_block_count,
        post_leveler_dr_db=post_dr,
    )
