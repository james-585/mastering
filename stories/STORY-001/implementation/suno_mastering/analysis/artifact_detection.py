"""analysis/artifact_detection.py

Detect Suno-generation artifacts. Pure analysis stage: the input audio array
is returned byte-identical to the call site (SHA-256 hash invariant, arch §4.1).

Four detectors:
  1. SMEARED_TRANSIENT  — slow HF onset rise-time (> 25 ms), gate on HF energy presence
  2. DIGITAL_HAZE       — stationary HF temporal modulation + LF decoupling (arch §5.2)
  3. STATIONARY_WHISTLE — narrow persistent spectral peak (Q ≥ 8, ≥ 1.5 s)
  4. PHASE_SWISH        — inter-channel HF phase decorrelation (stereo only)

Deviation notes (see defects.md):
  DEF-701: AudioBuffer dataclass does not exist in the codebase; this module
           accepts plain numpy arrays matching the measure_all() convention.
           Architecture §4.1 updated to reflect plain-array contract.
  DEF-702: arch §6 originally specified FFT_SCALE_FACTOR=4 (4× zero-padding);
           using nfft=nperseg (no zero-padding) for memory reasons. Bin spacing
           at 44.1 kHz is 2 Hz — sufficient for all detectors. Architecture
           confirmed nfft=nperseg acceptable. Closed per arch §11.
  DEF-703: arch §3 originally specified pandas.Series.rolling() for persistence
           tracking; pandas is not a project dependency. Persistence is tracked
           via numpy run-length encoding (equivalent semantics). Closed per arch §3.
  DEF-712: SFM-based DIGITAL_HAZE replaced with temporal method (TMI_HF + CC_HF_LF)
           per architecture §5.2 method change. SFM was fundamentally broken for
           genuine bandlimited noise (Rayleigh asymptote ≈ 0.8455 ≈ 0.85 threshold).
  DEF-715: §5.1 LCF gate replaced with HF energy-level gate (arch §11 rev 2026-08-14).
           Crest factor is scale-invariant and cannot detect absence of HF energy.
           New gate uses self-normalising RMS tiling: HF_RMS_window / local_hf_floor
           >= _ONSET_HF_PRESENCE_RATIO (3.0 = 9.5 dB). Method change.
  DEF-715: §5.2 DIGITAL_HAZE now requires _HAZE_MIN_CONSECUTIVE_WINDOWS = 4
           consecutive qualifying sliding-window positions (~2.75 s of sustained HF).
           Prevents single-window false positives. Method change.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

import numpy as np
from scipy.signal import butter, find_peaks, hilbert, medfilt, peak_widths, sosfilt, stft

from .types import ArtifactDetectionResult, ArtifactFlag

log = logging.getLogger(__name__)

# ── STFT parameters (arch §6) ────────────────────────────────────────────────
WINDOW_DURATION_S = 0.5   # 500 ms analysis window
HOP_SIZE_S = 0.25          # 50% overlap; resolves STFT window-boundary blocker (arch §11)
# nfft = nperseg (no zero-padding) — see DEF-702 / arch §6.

CONFIDENCE_THRESHOLD_TO_WARN = 0.8  # floor for plausibility_warnings forwarding

# ── SMEARED_TRANSIENT (arch §5.1) ───────────────────────────────────────────
# 25 ms threshold: normal acoustic transients 5–15 ms; Suno decoder blur 25–50 ms.
ONSET_RISETIME_THRESHOLD_MS = 25.0
# 6 dB prominence in spectral flux to declare an onset candidate (arch §5.1 step 1).
ONSET_FLUX_PROMINENCE_DB = 6.0
ONSET_ANALYSIS_WINDOW_MS = 150.0   # window centred on HF anchor for rise-time measurement
ONSET_HF_BAND_LO_HZ = 6000.0      # HF band lower bound (arch §5.1)
ONSET_HF_BAND_HI_HZ = 16000.0     # HF band upper bound

# HF energy-level gate (§5.1 Step 2a — arch §11 rev 2026-08-14; replaces LCF gate).
# Gate criterion: HF_RMS_window / local_hf_floor > _ONSET_HF_PRESENCE_RATIO
# where both quantities are time-domain RMS of the 6–16 kHz bandpassed signal.
# Derivation: N ≈ 2·BW·T = 2×10000×0.030 = 600 independent samples in tile_0;
#   relative std of floor estimate ≈ 1/sqrt(1200) ≈ 3%. A kick drum's
#   HF_RMS_window ≈ local_hf_floor (ratio ≈ 1.0 ± 3%); threshold 3.0 = +9.5 dB
#   is >10 standard deviations above the kick-drum class → robust separation.
#   HF-bearing onsets (cymbals, sibilants, synth) produce ratio >> 3.0.
# Self-normalising: adapts to the track's actual HF noise floor per onset.
# Does NOT discriminate percussive from vocal — rise-time carries that burden.
# PROVISIONAL — REQUIRES MEASUREMENT on reference tracks, including HF-dense passages
# (§5.1, §10.1 item 8). If HF-bearing onsets in dense passages fall below 3.0,
# lower ratio or widen floor-estimation window; do not adjust rise-time threshold.
_ONSET_HF_PRESENCE_RATIO = 3.0   # Gate: HF_RMS_window must exceed local floor by this factor
ONSET_HF_WINDOW_MS = 30.0        # 30 ms tile size: tile-0 is anchor window; floor from ±16 tiles

# ── DIGITAL_HAZE (arch §5.2) ────────────────────────────────────────────────
# SFM method removed (DEF-712 — method change). Replaced with temporal approach:
# HF Temporal Modulation Index (TMI_HF) + HF-LF temporal decoupling (CC_HF_LF).
# Physical justification: Suno HF noise is stationary and decoupled from musical
# events below it; natural HF (cymbal, reverb) is modulated and time-locked to source.
#
# PROVISIONAL — REQUIRES MEASUREMENT (§5.2):
_HAZE_TMI_THRESHOLD = 0.07   # Calibrated from real reference tracks: clean commercial masters have isolated windows around 0.08–0.09 TMI_HF, so the provisional 0.10 threshold was too loose. This still leaves a margin above the synthetic stationary-noise floor (~0.01–0.02).
_HAZE_CC_THRESHOLD = 0.30    # Pearson r(E_HF, E_LF); below = decoupled from music
_HAZE_MIN_HF_ENERGY = 5.0e-4  # require a materially non-trivial HF band; tiny leakage windows are not haze
# The HF/LF ratio is intentionally not used as a gate here. It is not a stable discriminator
# for real mixes and rejects valid stationary-HF haze when the LF bed is stronger than the HF
# artifact itself; the operative signal is sustained stationarity + local HF-floor exceedance.
_HAZE_MIN_HF_LF_RATIO = 0.0
_HAZE_MIN_HF_RELATIVE_FACTOR = 1.50  # Calibrated on clean reference tracks: raise the local HF-floor gate enough to suppress natural HF-rich passages while still passing the synthetic haze positive control.
_HAZE_FLOOR_PERCENTILE = 10.0  # Revised local-floor estimator: use a low percentile rather than the median, which can be contaminated by the haze itself.
# Window size: 2 s = 8 frames at 250 ms hop.
HAZE_DURATION_THRESHOLD_S = 2.0   # metric computation window size (§5.2)
# Consecutive qualifying windows required to trigger (~2.75 s of sustained HF stationarity).
# With one-frame stride (250 ms), 4 consecutive positions span frames i..i+10 = 11 frames.
# Prevents single-window false positives (reverb tail over sustained bass, etc.)
# Use _find_consecutive_runs() to identify qualifying runs (arch §5.2, §3).
_HAZE_MIN_CONSECUTIVE_WINDOWS = 4  # consecutive qualifying 8-frame windows required (~2.75 s sustained) (§5.2)
HAZE_HF_BAND_HZ = (8000.0, 16000.0)   # high-frequency analysis band
HAZE_LF_BAND_HZ = (200.0, 2000.0)    # low-frequency reference band

# ── STATIONARY_WHISTLE (arch §5.3) ──────────────────────────────────────────
# Q ≥ 8: Suno whines show Q 10–30; normal harmonic content Q 2–5.
# Prominence ≥ 6 dB: Suno 8–18 dB; normal harmonics 3–6 dB. Thresholds with margin.
Q_THRESHOLD = 8.0
PROMINENCE_THRESHOLD_DB = 6.0
# 1.5 s persistence: artifacts last 1–3 s; shorter ≈ legitimate harmonic content.
PERSISTENCE_THRESHOLD_S = 1.5
# ±50 Hz tolerance: measured drift on stationary Suno whines (arch §5.3).
FREQUENCY_TOLERANCE_HZ = 50.0
# Background subtraction: 100 Hz median-filter kernel estimates local spectral envelope.
# Kernel and distance are specified in Hz and converted to bins at runtime (DEF-702 fix).
_WHISTLE_BACKGROUND_KERNEL_HZ = 100.0  # smoothing bandwidth for spectral background
_WHISTLE_MIN_PEAK_DISTANCE_HZ = 50.0   # minimum Hz between distinct candidate peaks
# Harmonic stack suppression (DEF-705 Issue B — method change; see arch §5.3):
# A persistent peak is suppressed if >= 2 harmonic positions {2f, 3f, f/2, f/3}
# show matching persistent peaks with >= 3 dB prominence over the same time range.
_HARMONIC_MATCH_PROMINENCE_DB = 3.0   # minimum prominence for a harmonic match (§5.3)
_HARMONIC_MATCH_MIN_COUNT = 2          # minimum matched positions to suppress flag (§5.3)

# ── PHASE_SWISH (arch §5.4) ─────────────────────────────────────────────────
HF_CUTOFF_HZ = 8000.0
HF_PHASE_VARIANCE_THRESHOLD = 0.5   # rad²; Suno 0.6–2.0, normal 0.1–0.3
HF_CORRELATION_THRESHOLD = 0.4
LF_CORRELATION_MINIMUM = 0.7

# ── Edge-case guards (arch §8) ───────────────────────────────────────────────
MIN_SAMPLE_RATE_HZ = 32000          # detectors need ≥ 16 kHz Nyquist
MIN_DURATION_FOR_PERSISTENCE_S = 1.0  # skip persistence detectors on very short audio


# ── Internal helpers ─────────────────────────────────────────────────────────

def _sha256(audio: np.ndarray) -> str:
    """SHA-256 of raw audio bytes for hash-invariance assertion."""
    return hashlib.sha256(audio.tobytes()).hexdigest()


def _to_stereo_float64(audio: np.ndarray) -> np.ndarray:
    """Return (n_samples, 2) float64 array regardless of input shape.

    Mono input (1-D or shape (N, 1)) is expanded to 2 identical channels.

    Raises ValueError for >2-channel inputs (arch §7.1 channel validation).
    """
    if audio.ndim > 2:
        raise ValueError(
            f"detect_artifacts: input array has {audio.ndim} dimensions; "
            f"expected 1-D (mono) or 2-D (n_samples, channels)."
        )
    if audio.ndim == 2 and audio.shape[1] > 2:
        raise ValueError(
            f"detect_artifacts: input has {audio.shape[1]} channels; "
            f"only mono (1) or stereo (2) inputs are supported (arch §7.1)."
        )
    a = audio.astype(np.float64, copy=False)
    if a.ndim == 1:
        return np.stack([a, a], axis=1)
    if a.shape[1] == 1:
        return np.concatenate([a, a], axis=1)
    return a


def _hf_envelope(segment: np.ndarray, sr: int, sos: np.ndarray | None) -> np.ndarray:
    """Hilbert-transform amplitude envelope of the HF-bandpassed signal.

    Returns per-sample envelope (same length as segment). Returns zeros when
    sos is None (band not representable at this sample rate) or on failure.
    """
    if sos is None or len(segment) < 64:
        return np.zeros(len(segment))
    try:
        filtered = sosfilt(sos, segment.astype(np.float64))
        env = np.abs(hilbert(filtered))
        # Smooth with a ~5 ms window to reduce carrier-frequency ripple
        smooth_n = max(1, int(0.005 * sr))
        if smooth_n > 1:
            kernel = np.ones(smooth_n) / smooth_n
            env = np.convolve(env, kernel, mode='same')
        return env
    except Exception as exc:  # pragma: no cover
        log.debug("HF envelope computation failed: %s", exc)
        return np.zeros(len(segment))


def _measure_risetime(envelope: np.ndarray, sr: int) -> float | None:
    """10%–90% onset rise-time from amplitude envelope, in milliseconds.

    Method: find peak energy; going backward from peak, locate the last
    crossing below 90% of peak (→ idx_90) then below 10% (→ idx_10).
    Rise-time = (idx_90 − idx_10) / sr * 1000. Returns None if the onset
    start or end is not clearly resolved within the window.
    """
    if envelope.max() < 1e-10:
        return None

    peak_idx = int(np.argmax(envelope))
    peak_val = float(envelope[peak_idx])
    thresh_90 = 0.90 * peak_val
    thresh_10 = 0.10 * peak_val

    idx_90 = None
    for i in range(peak_idx, -1, -1):
        if envelope[i] < thresh_90:
            idx_90 = i
            break
    if idx_90 is None:
        return None

    idx_10 = None
    for i in range(idx_90, -1, -1):
        if envelope[i] < thresh_10:
            idx_10 = i
            break
    if idx_10 is None:
        return None

    rise_ms = (idx_90 - idx_10) * 1000.0 / sr
    return float(rise_ms)


def _risetime_confidence(rise_ms: float) -> float:
    """Map rise-time to confidence score (arch §5.1 confidence table)."""
    if rise_ms > 40.0:
        return 0.95
    if rise_ms > 30.0:
        return 0.85
    return 0.75


def _find_consecutive_runs(
    frames: list[int], min_length: int
) -> list[tuple[int, int]]:
    """Return (start_frame, end_frame) for consecutive runs of ≥ min_length.

    Frames need not be sorted; duplicates are dropped.
    """
    if not frames:
        return []
    sorted_f = sorted(set(frames))
    runs: list[tuple[int, int]] = []
    run_start = sorted_f[0]
    run_end = sorted_f[0]
    for f in sorted_f[1:]:
        if f == run_end + 1:
            run_end = f
        else:
            if run_end - run_start + 1 >= min_length:
                runs.append((run_start, run_end))
            run_start = f
            run_end = f
    if run_end - run_start + 1 >= min_length:
        runs.append((run_start, run_end))
    return runs


def _flags_freq_compatible(a: ArtifactFlag, b: ArtifactFlag) -> bool:
    """Return True if two same-type flags are frequency-compatible for merging.

    Flags that carry 'frequency_hz' in their details (STATIONARY_WHISTLE) are only
    compatible if their frequencies are within FREQUENCY_TOLERANCE_HZ of each other.
    Flags without 'frequency_hz' (SMEARED_TRANSIENT, PHASE_SWISH, DIGITAL_HAZE) are
    always frequency-compatible — only timestamp proximity controls merging.
    """
    fa = a.details.get("frequency_hz")
    fb = b.details.get("frequency_hz")
    if fa is None or fb is None:
        return True
    return abs(float(fa) - float(fb)) <= FREQUENCY_TOLERANCE_HZ


def _merge_adjacent_flags(flags: list[ArtifactFlag]) -> list[ArtifactFlag]:
    """Merge same-type flags whose time ranges are adjacent or overlapping (within
    one hop of each other) AND whose frequencies are compatible.

    DEF-714 fix: two STATIONARY_WHISTLE flags at different frequencies (> 50 Hz
    apart) are not merged even if their timestamps overlap. Flags without a
    'frequency_hz' in details are frequency-blind (same behaviour as before).

    Uses a scan-all approach: each new flag is compared against every existing
    merged entry, not just the last, so that non-consecutive same-frequency groups
    are correctly merged regardless of sort order.
    """
    if not flags:
        return []
    sorted_f = sorted(flags, key=lambda x: (x.artifact_type, x.timestamp_start_s))
    merged: list[ArtifactFlag] = []
    gap_threshold = HOP_SIZE_S * 1.5

    for flag in sorted_f:
        placed = False
        for i, prev in enumerate(merged):
            if (flag.artifact_type == prev.artifact_type
                    and flag.timestamp_start_s <= prev.timestamp_end_s + gap_threshold
                    and _flags_freq_compatible(flag, prev)):
                merged[i] = ArtifactFlag(
                    timestamp_start_s=prev.timestamp_start_s,
                    timestamp_end_s=max(prev.timestamp_end_s, flag.timestamp_end_s),
                    artifact_type=prev.artifact_type,
                    confidence_score=max(prev.confidence_score, flag.confidence_score),
                    details=prev.details,
                )
                placed = True
                break
        if not placed:
            merged.append(flag)
    return merged


# ── Individual detectors ─────────────────────────────────────────────────────

def _detect_smeared_transient(
    audio_mono: np.ndarray,
    sr: int,
    Zxx_mono: np.ndarray,
    freqs: np.ndarray,
    t_frames: np.ndarray,
) -> list[ArtifactFlag]:
    """SMEARED_TRANSIENT: flag HF-bearing onsets with rise-time > 25 ms.

    Method (arch §5.1 — arch §11 rev 2026-08-14):
      1. Spectral flux on STFT to locate onset candidates.
      2. HF energy-level gate: apply 6–16 kHz bandpass to the time-domain signal.
         Localise the onset anchor (sample of maximum HF Hilbert envelope amplitude
         within the STFT frame). Tile non-overlapping 30 ms windows outward from the
         anchor (tile 0 = anchor window). Compute:
           HF_RMS_window = rms(hf_audio[tile_0])
           local_hf_floor = median(rms(hf_audio[tile_k]) for k != 0)
         If HF_RMS_window <= local_hf_floor * _ONSET_HF_PRESENCE_RATIO: skip.
         Gate is self-normalising — adapts to the track's HF noise floor. Excludes
         events with near-zero HF energy (kicks) but NOT by onset type — all HF-bearing
         events (percussive, vocal, synth) pass if RMS exceeds local floor by ratio.
         Rise-time is the sole discriminator between normal and smeared onsets (§5.1).
      3. For passing onsets: extract 150 ms window centred on the anchor sample,
         compute HF Hilbert envelope, measure 10%-90% rise-time. Flag if > 25 ms.
         Effective max measurable rise-time ≈ 75 ms (window backward runway limit).
    """
    n_frames = Zxx_mono.shape[1]
    if n_frames < 3:
        return []

    lo_norm = ONSET_HF_BAND_LO_HZ / (sr / 2.0)
    hi_norm = min(ONSET_HF_BAND_HI_HZ / (sr / 2.0), 0.99)
    sos_hf: np.ndarray | None = None
    if lo_norm < hi_norm:
        try:
            sos_hf = butter(4, [lo_norm, hi_norm], btype='band', output='sos')
        except Exception as exc:
            log.warning("SMEARED_TRANSIENT: bandpass filter failed: %s", exc)

    # Spectral flux (arch §5.1 step 1)
    mag_mono = np.abs(Zxx_mono)
    flux = np.sum(np.maximum(np.diff(mag_mono, axis=1), 0.0), axis=0)

    if flux.max() < 1e-10:
        return []

    flux_db = 20.0 * np.log10(np.maximum(flux, 1e-12))
    try:
        # DEF-711: prepend sentinel so find_peaks can evaluate prominence at index 0.
        # DEF-713: append matching sentinel at the tail so find_peaks can evaluate
        # prominence at index len(flux_db)-1 (symmetric fix). Both sentinels are
        # -300 dB, below the minimum possible flux_db value (20*log10(1e-12) = -240 dB),
        # so they are always the global minimum and can never be returned as peaks.
        # Returned indices are shifted back by 1 for the head sentinel; the tail sentinel
        # at padded index len(flux_db_padded)-1 is excluded by the upper-bound filter.
        flux_db_padded = np.concatenate([[-300.0], flux_db, [-300.0]])
        onset_peaks_padded, _ = find_peaks(flux_db_padded, prominence=ONSET_FLUX_PROMINENCE_DB)
        valid_mask = (onset_peaks_padded > 0) & (onset_peaks_padded < len(flux_db_padded) - 1)
        onset_peaks = onset_peaks_padded[valid_mask] - 1
    except Exception:
        return []

    flags: list[ArtifactFlag] = []
    half_window_samples = int(ONSET_ANALYSIS_WINDOW_MS * sr / 1000.0 / 2.0)
    half_frame_samples = int(WINDOW_DURATION_S * sr / 2.0)
    # Tile parameters for HF energy-level gate (§5.1 Step 2a):
    tile_s = max(1, int(ONSET_HF_WINDOW_MS * sr / 1000.0))  # 30 ms in samples
    half_tile_s = max(1, tile_s // 2)
    n_floor_tiles = 16   # ≈ ±480 ms radius; ~32 floor tiles total
    floor_extent_s = (n_floor_tiles + 1) * tile_s  # samples needed around anchor
    smooth_n_pad = max(1, int(0.005 * sr))  # same kernel length as _hf_envelope
    n_samples = len(audio_mono)

    for flux_idx in onset_peaks:
        onset_frame = int(flux_idx) + 1
        if onset_frame >= len(t_frames):
            continue
        onset_sample = int(float(t_frames[onset_frame]) * sr)

        # ── Step 2a: HF energy-level gate — localise anchor, then tile for floor ──
        # Extract the STFT frame region to localise the HF envelope peak (anchor).
        frame_lo = max(0, onset_sample - half_frame_samples)
        frame_hi = min(n_samples, onset_sample + half_frame_samples)
        if frame_hi - frame_lo < 64:
            continue

        if sos_hf is None:
            continue  # HF band not constructable at this sample rate

        frame_lo_padded = max(0, frame_lo - smooth_n_pad)
        frame_actual_pad = frame_lo - frame_lo_padded
        seg_frame = audio_mono[frame_lo_padded:frame_hi].astype(np.float64)

        # HF bandpassed signal for anchor localisation (carrier oscillations removed
        # via Hilbert envelope smoothing so the slow amplitude envelope is visible).
        raw_padded = sosfilt(sos_hf, seg_frame)
        if len(raw_padded) <= frame_actual_pad:
            continue
        raw_frame = raw_padded[frame_actual_pad:]  # aligned to [frame_lo, frame_hi]

        env_unsmoothed_padded = np.abs(hilbert(raw_padded))
        env_unsmoothed = env_unsmoothed_padded[frame_actual_pad:]
        if smooth_n_pad > 1:
            _k = np.ones(smooth_n_pad) / smooth_n_pad
            env_frame = np.convolve(env_unsmoothed, _k, mode='same')
        else:
            env_frame = env_unsmoothed

        if env_frame.max() < 1e-10:
            continue  # no HF content in this frame

        # Localisation anchor: sample of maximum HF envelope amplitude in frame
        anchor_in_frame = int(np.argmax(env_frame))
        anchor_sample = frame_lo + anchor_in_frame

        # ── HF energy-level gate (arch §5.1 Step 2a, arch §11 rev 2026-08-14) ──
        # Tile non-overlapping 30 ms windows outward from the anchor.
        # Tile 0 = anchor window (numerator); ±16 tiles form the floor (denominator).
        # Both numerator and denominator are time-domain RMS of 6–16 kHz bandpassed
        # signal — same estimator type, same granularity (§5.1 estimator compatibility).
        # Band reuse prohibition: DO NOT use §5.2 E_HF (8–16 kHz, STFT-magnitude
        # domain, 250 ms granularity) — band and domain differ from this gate (§5.1).

        wide_lo_s = max(0, anchor_sample - floor_extent_s)
        wide_hi_s = min(n_samples, anchor_sample + floor_extent_s)

        # Filter a wider segment (±~495 ms) for the floor tiles; include settling pad.
        gate_seg_lo = max(0, wide_lo_s - smooth_n_pad)
        gate_seg_pad = wide_lo_s - gate_seg_lo
        gate_seg = audio_mono[gate_seg_lo:wide_hi_s].astype(np.float64)
        gate_filt_padded = sosfilt(sos_hf, gate_seg)
        gate_filt = gate_filt_padded[gate_seg_pad:]  # aligned to [wide_lo_s, wide_hi_s]

        anchor_in_gate = anchor_sample - wide_lo_s

        # Tile 0 (anchor window): [anchor − half_tile, anchor + half_tile]
        t0_lo = max(0, anchor_in_gate - half_tile_s)
        t0_hi = min(len(gate_filt), t0_lo + tile_s)
        tile0 = gate_filt[t0_lo:t0_hi]
        hf_rms_window = (float(np.sqrt(np.mean(tile0 ** 2))) if len(tile0) > 1
                         else 0.0)

        # Floor tiles: non-overlapping tiles at positions ±k * tile_s from anchor
        # (k = 1..n_floor_tiles, both directions). Tile 0 excluded (arch §5.1).
        floor_rms_list: list[float] = []
        for k in range(1, n_floor_tiles + 1):
            for direction in (-1, 1):
                tk_lo = anchor_in_gate + direction * k * tile_s - half_tile_s
                tk_hi = tk_lo + tile_s
                tk_lo = max(0, tk_lo)
                tk_hi = min(len(gate_filt), tk_hi)
                if tk_hi - tk_lo < 4:
                    continue
                floor_rms_list.append(
                    float(np.sqrt(np.mean(gate_filt[tk_lo:tk_hi] ** 2)))
                )

        if len(floor_rms_list) == 0:
            continue  # no floor tiles (e.g., onset within first tile of a very short track)

        # Epsilon guard prevents division by zero on digital silence (§5.1)
        local_hf_floor = max(
            float(np.median(floor_rms_list)), float(np.finfo(np.float64).tiny)
        )

        if hf_rms_window <= local_hf_floor * _ONSET_HF_PRESENCE_RATIO:
            continue  # HF energy indistinguishable from local noise floor — skip onset

        # ── Step 3: Rise-time measurement centred on anchor_sample ──────────
        lo = max(0, anchor_sample - half_window_samples)
        hi = min(n_samples, anchor_sample + half_window_samples)
        if hi - lo < 64:
            continue

        # Pre-pad for DEF-707: prevents boxcar edge suppression at window start.
        lo_padded = max(0, lo - smooth_n_pad)
        actual_pad = lo - lo_padded
        segment_padded = audio_mono[lo_padded:hi]
        envelope_padded = _hf_envelope(segment_padded, sr, sos_hf)
        if len(envelope_padded) <= actual_pad:
            continue
        envelope = envelope_padded[actual_pad:]
        rise_ms = _measure_risetime(envelope, sr)

        if rise_ms is None or rise_ms <= ONSET_RISETIME_THRESHOLD_MS:
            continue

        confidence = _risetime_confidence(rise_ms)
        anchor_time_s = anchor_sample / sr
        flag_start = max(0.0, anchor_time_s - ONSET_ANALYSIS_WINDOW_MS / 1000.0 / 2.0)
        flag_end = anchor_time_s + ONSET_ANALYSIS_WINDOW_MS / 1000.0 / 2.0

        flags.append(ArtifactFlag(
            timestamp_start_s=round(flag_start, 3),
            timestamp_end_s=round(flag_end, 3),
            artifact_type="SMEARED_TRANSIENT",
            confidence_score=confidence,
            details={"rise_time_ms": round(rise_ms, 2)},
        ))

    return flags


def _detect_digital_haze(
    Zxx_mono: np.ndarray,
    freqs: np.ndarray,
    t_frames: np.ndarray,
) -> list[ArtifactFlag]:
    """DIGITAL_HAZE: flag stationary HF energy decoupled from LF musical content.

    Method (arch §5.2 — DEF-712 method change, SFM replaced; arch §11 rev 2026-08-14
    consecutive-window trigger added):
      1. Per-frame HF RMS: E_HF[t] = sqrt(mean(|X_k|²)) for k in 8–16 kHz.
      2. Per-frame LF RMS: E_LF[t] = sqrt(mean(|X_k|²)) for k in 200–2000 Hz.
      3. Sliding 8-frame (2 s) window:
           TMI_HF = std(E_HF) / mean(E_HF)   [HF temporal modulation index]
           CC_HF_LF = pearsonr(E_HF, E_LF)   [HF-LF temporal correlation]
      4. Collect positions where BOTH conditions are met (qualifying positions).
         Use _find_consecutive_runs() to find runs of >= _HAZE_MIN_CONSECUTIVE_WINDOWS
         consecutive qualifying positions. Emit one flag per run; time span covers
         start of first qualifying window to end of last (arch §5.2).

    Thresholds are PROVISIONAL — REQUIRES MEASUREMENT on reference tracks (§5.2).
    """
    n_frames = Zxx_mono.shape[1]
    window_frames = max(2, int(round(HAZE_DURATION_THRESHOLD_S / HOP_SIZE_S)))

    if n_frames < window_frames:
        return []

    hf_lo, hf_hi = HAZE_HF_BAND_HZ
    lf_lo, lf_hi = HAZE_LF_BAND_HZ
    hf_mask = (freqs >= hf_lo) & (freqs <= hf_hi)
    lf_mask = (freqs >= lf_lo) & (freqs <= lf_hi)

    if not hf_mask.any() or not lf_mask.any():
        log.debug("DIGITAL_HAZE: HF or LF band has no bins (sr may be low)")
        return []

    # Per-frame RMS energy (root-mean-square of STFT magnitudes in each band)
    mag = np.abs(Zxx_mono)
    E_HF = np.sqrt(np.mean(mag[hf_mask, :] ** 2, axis=0))  # shape (n_frames,)
    E_LF = np.sqrt(np.mean(mag[lf_mask, :] ** 2, axis=0))

    # Collect qualifying window positions. The temporal TMI/CC checks alone are not
    # sufficient on real commercial masters: tiny low-energy HF leakage on natural
    # music can still satisfy the provisional thresholds. Require the HF band to be
    # both materially present and meaningfully above the track's HF floor.
    qualifying_positions: list[int] = []
    tmi_per_pos: dict[int, float] = {}
    cc_per_pos: dict[int, float] = {}
    track_hf_floor = float(np.percentile(E_HF, _HAZE_FLOOR_PERCENTILE))
    for i in range(n_frames - window_frames + 1):
        hf_win = E_HF[i:i + window_frames]
        lf_win = E_LF[i:i + window_frames]

        mean_hf = float(np.mean(hf_win))
        mean_lf = float(np.mean(lf_win))
        if mean_hf < 1e-10:
            continue  # silence window: skip (§5.2 edge case)

        tmi_hf = float(np.std(hf_win) / mean_hf)

        # Pearson correlation: treat constant series (std ≈ 0) as CC = 0 (no correlation).
        std_hf = float(np.std(hf_win))
        std_lf = float(np.std(lf_win))
        if std_hf < 1e-10 or std_lf < 1e-10:
            cc_hf_lf = 0.0
        else:
            cc_hf_lf = float(np.corrcoef(hf_win, lf_win)[0, 1])
            if not np.isfinite(cc_hf_lf):
                cc_hf_lf = 0.0

        # Revised design: estimate the local HF background using a lower percentile of the
        # surrounding frames rather than the median. The median can be pulled upward by the
        # haze itself, which makes the floor too high and removes valid detections.
        local_start = max(0, i - window_frames)
        local_end = min(n_frames, i + 2 * window_frames)
        local_candidates = np.concatenate((E_HF[local_start:i], E_HF[i + window_frames:local_end]))
        local_hf_floor = (
            float(np.percentile(local_candidates, _HAZE_FLOOR_PERCENTILE))
            if local_candidates.size > 0
            else track_hf_floor
        )
        min_hf_gate = max(_HAZE_MIN_HF_ENERGY, _HAZE_MIN_HF_RELATIVE_FACTOR * local_hf_floor)

        if (
            tmi_hf < _HAZE_TMI_THRESHOLD
            and cc_hf_lf < _HAZE_CC_THRESHOLD
            and mean_hf > min_hf_gate
        ):
            qualifying_positions.append(i)
            tmi_per_pos[i] = tmi_hf
            cc_per_pos[i] = cc_hf_lf

    # Require _HAZE_MIN_CONSECUTIVE_WINDOWS consecutive qualifying positions (arch §5.2).
    # Each position advances by one frame (250 ms stride); 4 consecutive positions
    # cover frames i through i+10 ≈ 2.75 s of continuously stationary decoupled HF.
    runs = _find_consecutive_runs(qualifying_positions, min_length=_HAZE_MIN_CONSECUTIVE_WINDOWS)

    flags: list[ArtifactFlag] = []
    for (run_start, run_end) in runs:
        # run_start, run_end are the actual window-position values (i indices).
        # Use minimum TMI and minimum CC over the run as the representative values
        # (most stationary / most decoupled window in the run).
        run_tmi = min(
            (tmi_per_pos[pos] for pos in range(run_start, run_end + 1) if pos in tmi_per_pos),
            default=_HAZE_TMI_THRESHOLD,
        )
        run_cc = min(
            (cc_per_pos[pos] for pos in range(run_start, run_end + 1) if pos in cc_per_pos),
            default=_HAZE_CC_THRESHOLD,
        )

        confidence = 0.70
        if run_tmi < 0.05:
            confidence += 0.10
        if run_cc < 0.10:
            confidence += 0.10
        confidence = min(confidence, 0.90)

        # Flag spans from the start of the first qualifying window to the end of the last.
        last_frame_in_run = run_end + window_frames - 1
        ts_start = float(t_frames[run_start])
        ts_end = (float(t_frames[last_frame_in_run]) + WINDOW_DURATION_S
                  if last_frame_in_run < len(t_frames)
                  else float(t_frames[-1]) + WINDOW_DURATION_S)

        flags.append(ArtifactFlag(
            timestamp_start_s=round(ts_start, 3),
            timestamp_end_s=round(ts_end, 3),
            artifact_type="DIGITAL_HAZE",
            confidence_score=round(confidence, 3),
            details={
                "tmi_hf": round(run_tmi, 4),
                "cc_hf_lf": round(run_cc, 4),
            },
        ))

    return flags


def _detect_stationary_whistle(
    Zxx_mono: np.ndarray,
    freqs: np.ndarray,
    t_frames: np.ndarray,
) -> list[ArtifactFlag]:
    """STATIONARY_WHISTLE: flag narrow persistent spectral peaks.

    Trigger: Q >= 8 AND prominence >= 6 dB above background, sustained >= 1.5 s
    within +-50 Hz frequency tolerance (arch §5.3).

    Algorithm:
      Step 1: Background-subtracted peak finding per frame.
      Step 2: Build binary occupancy matrix peak_present[bin, frame].
      Step 3: Collect ALL qualifying consecutive runs per bin (DEF-706 fix).
      Step 4a: Independent per-flag harmonic stack check (DEF-705 Issue B):
              suppress proto-flags whose frequency has >= 2 matching harmonic
              positions at {2f, 3f, f/2, f/3}, indicating a musical tone.
      Step 4b: Cascade suppression — overtones of a 4a-suppressed fundamental
              that remain retained are also suppressed (single iteration).
      Step 5: Merge adjacent retained proto-flags within +-50 Hz in frequency.
    """
    n_frames = Zxx_mono.shape[1]
    min_persistence_frames = max(2, int(np.ceil(PERSISTENCE_THRESHOLD_S / HOP_SIZE_S)))

    if n_frames < min_persistence_frames:
        return []

    mag_db = 20.0 * np.log10(np.maximum(np.abs(Zxx_mono), 1e-12))
    n_bins = mag_db.shape[0]
    bin_spacing_hz = float(freqs[1] - freqs[0]) if len(freqs) > 1 else 1.0

    # Background subtraction parameters — Hz→bins at runtime (DEF-702 resolution).
    bg_kernel = max(3, int(_WHISTLE_BACKGROUND_KERNEL_HZ / bin_spacing_hz))
    if bg_kernel % 2 == 0:
        bg_kernel += 1
    min_peak_dist = max(1, int(_WHISTLE_MIN_PEAK_DISTANCE_HZ / bin_spacing_hz))
    tolerance_bins = max(1, int(FREQUENCY_TOLERANCE_HZ / bin_spacing_hz))

    # Steps 1 + 2: Build per-bin occupancy matrix.
    peak_present = np.zeros((n_bins, n_frames), dtype=bool)
    peak_prom_db = np.zeros((n_bins, n_frames), dtype=np.float32)
    peak_q = np.zeros((n_bins, n_frames), dtype=np.float32)

    for fi in range(n_frames):
        mag_frame = mag_db[:, fi]
        if np.max(mag_frame) < -60.0:
            continue
        try:
            background = medfilt(mag_frame, kernel_size=bg_kernel)
            residual = mag_frame - background

            peaks, props = find_peaks(
                residual,
                height=PROMINENCE_THRESHOLD_DB,
                distance=min_peak_dist,
            )
            if len(peaks) == 0:
                continue

            widths_arr, _, _, _ = peak_widths(residual, peaks, rel_height=0.5)
            for pi, peak_bin in enumerate(peaks):
                freq_hz = float(freqs[peak_bin])
                if freq_hz <= 0.0:
                    continue
                prom_db = float(props['peak_heights'][pi])
                width_hz = max(float(widths_arr[pi]) * bin_spacing_hz, bin_spacing_hz * 0.5)
                q_factor = freq_hz / width_hz
                if q_factor >= Q_THRESHOLD:
                    peak_present[peak_bin, fi] = True
                    peak_prom_db[peak_bin, fi] = prom_db
                    peak_q[peak_bin, fi] = q_factor
        except Exception as exc:
            log.debug("STATIONARY_WHISTLE: frame %d failed: %s", fi, exc)

    # Step 3: Collect ALL qualifying consecutive runs per bin (DEF-706 fix).
    proto_flags: list[tuple[int, int, int, float, float]] = []

    for b in range(n_bins):
        run_len = 0
        cur_start = 0
        for fi in range(n_frames):
            if peak_present[b, fi]:
                if run_len == 0:
                    cur_start = fi
                run_len += 1
            else:
                if run_len >= min_persistence_frames:
                    mp = float(np.max(peak_prom_db[b, cur_start:fi]))
                    mq = float(np.max(peak_q[b, cur_start:fi]))
                    proto_flags.append((b, cur_start, fi - 1, mp, mq))
                run_len = 0
        if run_len >= min_persistence_frames:
            mp = float(np.max(peak_prom_db[b, cur_start:n_frames]))
            mq = float(np.max(peak_q[b, cur_start:n_frames]))
            proto_flags.append((b, cur_start, n_frames - 1, mp, mq))

    if not proto_flags:
        return []

    # Step 4: Harmonic stack suppression (arch §5.3, DEF-705 Issue B).
    # 4a: independent per-flag check. 4b: cascade suppression of overtones whose
    # fundamental was suppressed in 4a.
    # AC3 invariant: 6.4 kHz pure sine → 0 matches in 4a → not suppressed → cascade
    #               finds no suppressed fundamental → 0 cascade suppressions.
    nyquist_hz = float(freqs[-1])

    kept_proto_flags: list[tuple[int, int, int, float, float]] = []
    suppressed_proto_flags: list[tuple[int, int, int, float, float]] = []
    for (pb, p_start, p_end, mp, mq) in proto_flags:
        f_0 = float(freqs[pb])
        primary_frame_count = p_end - p_start + 1
        min_overlap_frames = int(np.ceil(0.5 * primary_frame_count))

        harmonic_freqs = [2.0 * f_0, 3.0 * f_0, f_0 / 2.0, f_0 / 3.0]

        n_matched = 0
        for h_freq in harmonic_freqs:
            # Out-of-range positions are "not evaluated" (excluded from count)
            if h_freq < bin_spacing_hz or h_freq > nyquist_hz:
                continue  # not evaluated

            # Target bin; search within ±tolerance_bins
            h_bin_center = int(round(h_freq / bin_spacing_hz))
            h_bin_center = max(0, min(n_bins - 1, h_bin_center))
            search_lo = max(0, h_bin_center - tolerance_bins)
            search_hi = min(n_bins - 1, h_bin_center + tolerance_bins)

            # Find the bin with maximum prominence during the primary's time range
            best_hbin = -1
            best_hprom = 0.0
            for cb in range(search_lo, search_hi + 1):
                prom_slice = peak_prom_db[cb, p_start:p_end + 1]
                max_p = float(prom_slice.max()) if prom_slice.size > 0 else 0.0
                if max_p > best_hprom:
                    best_hprom = max_p
                    best_hbin = cb

            if best_hbin < 0 or best_hprom < _HARMONIC_MATCH_PROMINENCE_DB:
                continue  # no bin with sufficient prominence near this harmonic

            # Check whether best_hbin has a consecutive run overlapping the primary
            # by >= 50% of the primary's frame count AND prominence >= threshold.
            h_occ = peak_present[best_hbin, :]
            matched_this_harmonic = False
            run_l = 0
            run_s = 0
            for fi in range(n_frames + 1):
                is_p = fi < n_frames and bool(h_occ[fi])
                if is_p:
                    if run_l == 0:
                        run_s = fi
                    run_l += 1
                else:
                    if run_l > 0:
                        run_e = fi - 1
                        ov_s = max(run_s, p_start)
                        ov_e = min(run_e, p_end)
                        ov_len = max(0, ov_e - ov_s + 1)
                        if ov_len >= min_overlap_frames:
                            prom_in_ov = float(
                                np.max(peak_prom_db[best_hbin, ov_s:ov_e + 1])
                            )
                            if prom_in_ov >= _HARMONIC_MATCH_PROMINENCE_DB:
                                matched_this_harmonic = True
                                break
                    run_l = 0

            if matched_this_harmonic:
                n_matched += 1

        if n_matched >= _HARMONIC_MATCH_MIN_COUNT:
            log.debug(
                "STATIONARY_WHISTLE: suppressing proto-flag at %.0f Hz "
                "(harmonic stack, n_matched=%d)", f_0, n_matched
            )
            suppressed_proto_flags.append((pb, p_start, p_end, mp, mq))
            continue  # suppress: musical tone

        kept_proto_flags.append((pb, p_start, p_end, mp, mq))

    # Step 4b: Cascade suppression pass (DEF-705 Issue B fix — method change).
    # A fundamental suppressed in 4a carries its overtones. Any retained proto-flag
    # lying within ±FREQUENCY_TOLERANCE_HZ of a cascade position {2f, 3f, f/2, f/3}
    # of a suppressed flag, AND overlapping it by >= 50% of the retained flag's frame
    # count, is also suppressed. One iteration suffices: the fundamental (lowest partial)
    # always accumulates the most harmonic matches and is suppressed first; all overtones
    # lie at {2f, 3f, ...} of the fundamental and are caught in this single pass.
    if suppressed_proto_flags and kept_proto_flags:
        cascade_suppressed_indices: set[int] = set()
        for (sb, s_start, s_end, _, _) in suppressed_proto_flags:
            f_supp = float(freqs[sb])
            cascade_targets = [
                2.0 * f_supp,
                3.0 * f_supp,
                f_supp / 2.0,
                f_supp / 3.0,
            ]
            for ri, (rb, r_start, r_end, _, _) in enumerate(kept_proto_flags):
                if ri in cascade_suppressed_indices:
                    continue
                f_r = float(freqs[rb])
                if not any(
                    abs(f_r - ct) <= FREQUENCY_TOLERANCE_HZ
                    for ct in cascade_targets
                ):
                    continue
                retained_frame_count = r_end - r_start + 1
                min_ov = int(np.ceil(0.5 * retained_frame_count))
                ov_len = max(0, min(r_end, s_end) - max(r_start, s_start) + 1)
                if ov_len >= min_ov:
                    log.debug(
                        "STATIONARY_WHISTLE: cascade-suppressing proto-flag at %.0f Hz "
                        "(harmonic of suppressed %.0f Hz)", f_r, f_supp
                    )
                    cascade_suppressed_indices.add(ri)

        if cascade_suppressed_indices:
            kept_proto_flags = [
                pf for i, pf in enumerate(kept_proto_flags)
                if i not in cascade_suppressed_indices
            ]

    if not kept_proto_flags:
        return []

    # Step 5: Merge adjacent retained proto-flags that overlap in time AND
    # are within tolerance_bins in frequency.
    kept_proto_flags.sort(key=lambda p: (p[1], p[0]))

    clusters: list[list[int]] = []
    for pi, (pb, p_start, p_end, _, _) in enumerate(kept_proto_flags):
        placed = False
        for cluster in clusters:
            for ci in cluster:
                cb, c_start, c_end, _, _ = kept_proto_flags[ci]
                if (abs(pb - cb) <= tolerance_bins
                        and p_start <= c_end + 1
                        and p_end >= c_start - 1):
                    cluster.append(pi)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            clusters.append([pi])

    flags: list[ArtifactFlag] = []
    for cluster in clusters:
        pf_list = [kept_proto_flags[i] for i in cluster]
        frame_start = min(p[1] for p in pf_list)
        frame_end = max(p[2] for p in pf_list)
        max_prom = max(p[3] for p in pf_list)
        max_q = max(p[4] for p in pf_list)
        best_b = max(pf_list, key=lambda p: p[3])[0]
        center_freq_hz = float(freqs[best_b])

        prom_above_threshold = max_prom - PROMINENCE_THRESHOLD_DB
        confidence = 0.75 + 0.05 * min(prom_above_threshold, 4.0)
        if max_q >= 15.0:
            confidence += 0.05
        confidence = float(min(confidence, 1.0))

        ts_start = (float(t_frames[frame_start]) if frame_start < len(t_frames)
                    else frame_start * HOP_SIZE_S)
        ts_end = ((float(t_frames[frame_end]) + WINDOW_DURATION_S)
                  if frame_end < len(t_frames)
                  else frame_end * HOP_SIZE_S + WINDOW_DURATION_S)

        flags.append(ArtifactFlag(
            timestamp_start_s=round(ts_start, 3),
            timestamp_end_s=round(ts_end, 3),
            artifact_type="STATIONARY_WHISTLE",
            confidence_score=round(confidence, 3),
            details={
                "frequency_hz": round(center_freq_hz, 1),
                "prominence_db": round(max_prom, 2),
                "q_factor": round(max_q, 2),
            },
        ))

    return flags


def _detect_phase_swish(
    Zxx_L: np.ndarray,
    Zxx_R: np.ndarray,
    freqs: np.ndarray,
    t_frames: np.ndarray,
) -> list[ArtifactFlag]:
    """PHASE_SWISH: flag per-frame HF inter-channel phase decorrelation.

    Trigger (arch §5.4):
      - HF (≥ 8 kHz) phase variance > 0.5 rad²
      - HF cross-correlation < 0.4
      - LF (< 8 kHz) cross-correlation ≥ 0.7

    Phase variance uses wrapped phase difference to constrain to (−π, π].
    """
    hf_mask = freqs >= HF_CUTOFF_HZ
    lf_mask = freqs < HF_CUTOFF_HZ
    n_frames = Zxx_L.shape[1]

    if not hf_mask.any() or not lf_mask.any():
        log.debug("PHASE_SWISH: insufficient frequency bands")
        return []

    flags: list[ArtifactFlag] = []

    for fi in range(n_frames):
        z_L = Zxx_L[:, fi]
        z_R = Zxx_R[:, fi]

        phase_diff_hf = np.angle(
            np.exp(1j * (np.angle(z_L[hf_mask]) - np.angle(z_R[hf_mask])))
        )
        hf_phase_var = float(np.var(phase_diff_hf))

        mag_L_hf = np.abs(z_L[hf_mask])
        mag_R_hf = np.abs(z_R[hf_mask])
        if mag_L_hf.std() < 1e-10 or mag_R_hf.std() < 1e-10:
            continue
        hf_corr = float(np.corrcoef(mag_L_hf, mag_R_hf)[0, 1])

        mag_L_lf = np.abs(z_L[lf_mask])
        mag_R_lf = np.abs(z_R[lf_mask])
        if mag_L_lf.std() < 1e-10 or mag_R_lf.std() < 1e-10:
            continue
        lf_corr = float(np.corrcoef(mag_L_lf, mag_R_lf)[0, 1])

        if not (
            hf_phase_var > HF_PHASE_VARIANCE_THRESHOLD
            and hf_corr < HF_CORRELATION_THRESHOLD
            and lf_corr >= LF_CORRELATION_MINIMUM
        ):
            continue

        confidence = 0.70
        if hf_phase_var > 1.0:
            confidence += 0.10
        if hf_corr < 0.2:
            confidence += 0.10
        if lf_corr < 0.8:
            confidence -= 0.10
        confidence = float(np.clip(confidence, 0.0, 1.0))

        ts_start = float(t_frames[fi])
        ts_end = ts_start + WINDOW_DURATION_S

        flags.append(ArtifactFlag(
            timestamp_start_s=round(ts_start, 3),
            timestamp_end_s=round(ts_end, 3),
            artifact_type="PHASE_SWISH",
            confidence_score=round(confidence, 3),
            details={
                "hf_phase_variance_rad2": round(hf_phase_var, 4),
                "hf_cross_correlation": round(hf_corr, 4),
                "lf_cross_correlation": round(lf_corr, 4),
            },
        ))

    return flags


# ── Public API ───────────────────────────────────────────────────────────────

def detect_artifacts(
    audio: np.ndarray,
    sr: int,
    detect_stationary_whistles: bool = True,
) -> tuple[np.ndarray, ArtifactDetectionResult]:
    """Detect Suno generation artifacts in audio.

    Args:
        audio: Float32 or float64 array, shape (n_samples,) for mono or
               (n_samples, n_channels) for multichannel. Not modified.
        sr:    Sample rate in Hz. Raises ValueError if < 32000.

    Returns:
        (audio_unmodified, ArtifactDetectionResult)
        The returned audio array is byte-identical to the input (SHA-256 checked).

    Raises:
        ValueError: sample rate below minimum or more than 2 channels.
        AssertionError: audio array was modified during processing.

    Notes:
        - Mono input: PHASE_SWISH is skipped (no inter-channel information).
        - Very short audio (< 1 s): persistence detectors skipped (arch §8).
        - All-zero audio: returns zero flags (silence has no artifacts).
    """
    if sr < MIN_SAMPLE_RATE_HZ:
        raise ValueError(
            f"Sample rate {sr} Hz is below the minimum {MIN_SAMPLE_RATE_HZ} Hz required "
            f"for 8–16 kHz artifact detection (arch §8)."
        )

    audio_hash_in = _sha256(audio)

    audio_f64 = audio.astype(np.float64, copy=False)
    duration_s = audio_f64.shape[0] / sr

    is_originally_mono = audio_f64.ndim == 1 or (audio_f64.ndim == 2 and audio_f64.shape[1] == 1)
    stereo = _to_stereo_float64(audio_f64)
    n_samples = stereo.shape[0]

    audio_mono = (stereo[:, 0] + stereo[:, 1]) / 2.0

    if np.max(np.abs(audio_mono)) < 1e-10:
        result = ArtifactDetectionResult(
            total_artifacts_found=0,
            artifact_flags=[],
            overall_artifact_density_score=0.0,
            detected_at=datetime.now(timezone.utc),
        )
        assert _sha256(audio) == audio_hash_in
        return audio, result

    # STFT parameters
    window_samples = int(WINDOW_DURATION_S * sr)
    hop_samples = int(HOP_SIZE_S * sr)
    noverlap = window_samples - hop_samples

    try:
        f, t_mono, Zxx_mono = stft(
            audio_mono,
            fs=sr,
            window='hann',
            nperseg=window_samples,
            noverlap=noverlap,
            nfft=window_samples,  # no zero-padding — arch §6 / DEF-702
        )
    except Exception as exc:
        log.error("STFT computation failed: %s", exc)
        result = ArtifactDetectionResult(
            total_artifacts_found=0,
            artifact_flags=[],
            overall_artifact_density_score=0.0,
            detected_at=datetime.now(timezone.utc),
        )
        assert _sha256(audio) == audio_hash_in
        return audio, result

    if not np.all(np.isfinite(Zxx_mono)):
        n_bad = np.sum(~np.isfinite(Zxx_mono))
        log.warning("STFT produced %d non-finite values; zeroing", n_bad)
        Zxx_mono = np.nan_to_num(Zxx_mono, nan=0.0, posinf=0.0, neginf=0.0)

    all_flags: list[ArtifactFlag] = []

    smeared_flags = _detect_smeared_transient(audio_mono, sr, Zxx_mono, f, t_mono)
    all_flags.extend(smeared_flags)

    if duration_s >= MIN_DURATION_FOR_PERSISTENCE_S:
        haze_flags = _detect_digital_haze(Zxx_mono, f, t_mono)
        all_flags.extend(haze_flags)

        if detect_stationary_whistles:
            whistle_flags = _detect_stationary_whistle(Zxx_mono, f, t_mono)
            all_flags.extend(whistle_flags)

    if not is_originally_mono:
        try:
            _, t_L, Zxx_L = stft(
                stereo[:, 0],
                fs=sr, window='hann', nperseg=window_samples,
                noverlap=noverlap, nfft=window_samples,
            )
            _, _, Zxx_R = stft(
                stereo[:, 1],
                fs=sr, window='hann', nperseg=window_samples,
                noverlap=noverlap, nfft=window_samples,
            )
            Zxx_L = np.nan_to_num(Zxx_L, nan=0.0, posinf=0.0, neginf=0.0)
            Zxx_R = np.nan_to_num(Zxx_R, nan=0.0, posinf=0.0, neginf=0.0)
            swish_flags = _detect_phase_swish(Zxx_L, Zxx_R, f, t_L)
            all_flags.extend(swish_flags)
        except Exception as exc:
            log.warning("PHASE_SWISH STFT failed: %s", exc)

    merged_flags = _merge_adjacent_flags(all_flags)

    total_flagged_s = sum(
        max(0.0, flag.timestamp_end_s - flag.timestamp_start_s) for flag in merged_flags
    )
    density = float(np.clip(total_flagged_s / max(duration_s, 1.0), 0.0, 1.0))

    result = ArtifactDetectionResult(
        total_artifacts_found=len(merged_flags),
        artifact_flags=merged_flags,
        overall_artifact_density_score=round(density, 4),
        detected_at=datetime.now(timezone.utc),
    )

    assert _sha256(audio) == audio_hash_in, (
        "Audio array was mutated during artifact detection — internal bug"
    )

    return audio, result


def summarize_artifacts_for_display(result: ArtifactDetectionResult) -> list[str]:
    """Return a concise, user-facing artifact summary for live console output.

    The product workflow should not dump every raw detector hit to the end-user
    terminal. Limit output to the most informative few flags and collapse the rest
    into a single "N more" line.
    """
    lines: list[str] = []
    if result is None or not result.artifact_flags:
        return lines

    flags = list(result.artifact_flags)
    display_flags = flags[:5]
    hidden_count = max(0, len(flags) - len(display_flags))

    for flag in display_flags:
        mm_s = int(flag.timestamp_start_s // 60)
        ss_s = flag.timestamp_start_s % 60.0
        time_str = f"{mm_s:02d}:{ss_s:05.2f}"
        atype = flag.artifact_type

        if atype == "STATIONARY_WHISTLE":
            freq = flag.details.get("frequency_hz", "?")
            conf = flag.confidence_score
            lines.append(f"{atype} @ {time_str} ({freq} Hz, conf={conf:.2f})")
        elif atype == "SMEARED_TRANSIENT":
            rt = flag.details.get("rise_time_ms", "?")
            lines.append(f"{atype} @ {time_str} (rise-time {rt} ms, conf={flag.confidence_score:.2f})")
        elif atype == "DIGITAL_HAZE":
            tmi = flag.details.get("tmi_hf", "?")
            cc = flag.details.get("cc_hf_lf", "?")
            lines.append(f"{atype} @ {time_str} (TMI_HF={tmi}, CC_HF_LF={cc}, conf={flag.confidence_score:.2f})")
        elif atype == "PHASE_SWISH":
            lines.append(f"{atype} @ {time_str} (conf={flag.confidence_score:.2f})")
        else:
            lines.append(f"{atype} @ {time_str} (conf={flag.confidence_score:.2f})")

    if hidden_count:
        lines.append(f"... and {hidden_count} more detected issue(s) not shown")

    return lines


def plausibility_warnings_for(result: ArtifactDetectionResult) -> list[str]:
    """Format high-confidence flags as human-readable plausibility warnings.

    Returns strings for flags with confidence ≥ CONFIDENCE_THRESHOLD_TO_WARN
    (arch §4.2, §7.3).
    """
    warnings: list[str] = []
    for flag in result.artifact_flags:
        if flag.confidence_score < CONFIDENCE_THRESHOLD_TO_WARN:
            continue
        mm_s = int(flag.timestamp_start_s // 60)
        ss_s = flag.timestamp_start_s % 60.0
        time_str = f"{mm_s:02d}:{ss_s:05.2f}"
        atype = flag.artifact_type

        if atype == "STATIONARY_WHISTLE":
            freq = flag.details.get("frequency_hz", "?")
            conf = flag.confidence_score
            warnings.append(
                f"STATIONARY_WHISTLE detected at {time_str} ({freq} Hz, "
                f"confidence {conf:.2f}) — consider re-generating track"
            )
        elif atype == "SMEARED_TRANSIENT":
            rt = flag.details.get("rise_time_ms", "?")
            warnings.append(
                f"SMEARED_TRANSIENT detected at {time_str} (rise-time {rt} ms, "
                f"confidence {flag.confidence_score:.2f}) — transient blur artifact"
            )
        elif atype == "DIGITAL_HAZE":
            tmi = flag.details.get("tmi_hf", "?")
            cc = flag.details.get("cc_hf_lf", "?")
            warnings.append(
                f"DIGITAL_HAZE detected at {time_str} "
                f"(TMI_HF={tmi}, CC_HF_LF={cc}, "
                f"confidence {flag.confidence_score:.2f}) — stationary HF generation noise"
            )
        elif atype == "PHASE_SWISH":
            warnings.append(
                f"PHASE_SWISH detected at {time_str} "
                f"(confidence {flag.confidence_score:.2f}) — HF phase decorrelation; "
                f"may be intentional stereo width"
            )
        else:
            warnings.append(
                f"{atype} detected at {time_str} "
                f"(confidence {flag.confidence_score:.2f})"
            )
    return warnings
