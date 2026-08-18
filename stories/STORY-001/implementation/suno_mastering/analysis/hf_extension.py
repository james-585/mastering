"""HF band-limit cliff detection (STORY-004 architecture.md Section 3 --
DEF-201 METHOD change, not a parameter retune).

Superseded design (defects.md DEF-201, CLAUDE.md Section 5's own named
"known-wrong pattern"): threshold-crossing against an absolute relative-dB
line, per-segment re-anchored. Music has a naturally declining spectrum, so
a fixed relative-dB threshold is always crossed SOMEWHERE, regardless of
whether a real cliff exists -- this produced physically impossible output
(a 1979 Hz "cutoff" on a commercial CD master) and reported every reference
track as UNSTABLE, even though a band limit is a fixed property of a file.

Corrected design (architecture.md Section 3.2-3.7 v1.5a): a two-stage cliff
detector operating on a log-frequency (1/24-octave) grid, not the raw
linear Welch grid (the literal "adjacent bins" reading of DOMAIN.md Section
2 is not implementable at this codebase's Welch resolution -- see
architecture.md Section 3.1). The decision is made ONCE on the whole-track
(silence-gated) active-audio PSD; per-segment analysis independently
corroborates (never re-decides) it, producing `hf_band_limit_confidence`.

Three tests must ALL pass for a candidate window to qualify as a cliff
(existence gate, architecture.md Section 3.3/3.4 -- UNCHANGED since v1.3):
  1. Slope: sustained >= hf_cliff_required_drop_db (8.0 dB, FIXED regardless
     of near-Nyquist window truncation -- Gate 1 resolution, architecture.md
     Section 3.3) drop across the candidate window, monotonic within a
     +1 dB/band wiggle tolerance.
  2. Passband precondition (Section 3.4): the LOCAL slope immediately below
     the candidate must not already exceed hf_cliff_passband_max_slope_db_per_octave
     (12 dB/octave) -- this is what distinguishes "the top of a real wall"
     from "partway down an ordinary declining-spectrum slope," and is
     derived directly from the drop bar's own numbers to make continuing an
     admitted ordinary slope through the candidate window mathematically
     unable to satisfy test 1, at any window size.
  3. Floor (Section 3.3 test 3): the region after the candidate window must
     stay down near the post-drop level (coverage + no-recovery checks).

v1.5a localization (architecture.md Section 3.5, METHOD change -- supersedes
v1.4's candidate-list + argmax selection):
  - _gate_scan: runs the full Section 3.3/3.4 scan and returns i_max --
    the highest gate-qualifying candidate start index -- or None (no cliff).
  - _floor_onset_index: given i_max as freeze_index, finds j* -- the unique
    minimum index j >= freeze_index where suffix_max[j] <= L. Tie-free by
    construction (suffix_max is non-increasing; its sublevel set is an up-set
    with exactly one minimum). No candidate list. No argmax. No tie-break.
  - hf_band_limit_hz = centers[j*], not centers[i+w] of any particular
    gate candidate's window.

No cliff found anywhere in the search range -> `hf_band_limit_hz = None`.
Never Nyquist, never a fallback value, never a mid-band threshold-crossing
point (ARCHITECTURE.md Section 3.2, binding).
"""
from __future__ import annotations

import logging
from typing import List, Optional

import numpy as np

from . import _psd
from .reference_types import HfExtensionResult
from .silence import extract_active_audio

log = logging.getLogger(__name__)


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=1)


def _gate_scan(
    levels_db: np.ndarray,
    n_bands: int,
    search_start_idx: int,
    one_octave_bands: int,
    config,
) -> Optional[int]:
    """Run the existence gate (architecture.md Section 3.3/3.4) across the
    full admissible candidate range and return i_max -- the highest `i` among
    all qualifying (i, w) pairs -- or None if the qualifying set is empty.

    The three per-candidate tests (slope, passband precondition, floor
    criterion) are identical to v1.4's. Only the return value changes: v1.5a
    no longer collects a candidate list or performs any argmax; it returns the
    single scalar i_max directly, so the caller gets both the gate boolean
    (None -> no cliff) and the freeze index in one pass.

    Args:
        levels_db:        1/24-octave log-grid power levels (dB), full array.
        n_bands:          len(levels_db).
        search_start_idx: first grid index at or above hf_cliff_search_min_hz.
        one_octave_bands: number of grid bands per octave (= 1/octave_fraction).
        config:           ReferenceAnalysisConfig instance.

    Returns:
        Highest qualifying candidate start index i, or None.
    """
    min_window = config.hf_cliff_min_window_bands
    min_floor = config.hf_cliff_min_floor_bands
    required_drop_db = config.hf_cliff_required_drop_db
    target_window_bands = int(round(
        config.hf_cliff_target_window_octaves / config.hf_cliff_log_band_octave_fraction
    ))
    last_candidate_idx = n_bands - (min_window + min_floor)

    i_max: Optional[int] = None

    for i in range(search_start_idx, last_candidate_idx + 1):
        if i - one_octave_bands < 0:
            continue  # not expected given f_min derivation; safety net

        bands_remaining = n_bands - i
        w = min(target_window_bands, bands_remaining - min_floor)
        w = max(w, min_window)
        if i + w >= n_bands:
            continue  # need at least one floor band beyond the window

        # --- Passband precondition (Section 3.4) ---
        local_pre_slope_db_per_octave = (levels_db[i - one_octave_bands] - levels_db[i]) / 1.0
        if local_pre_slope_db_per_octave > config.hf_cliff_passband_max_slope_db_per_octave:
            continue

        # --- Slope test (Section 3.3 tests 1 and 2) ---
        window = levels_db[i:i + w]
        steps = window[1:] - window[:-1]
        if np.any(steps > 1.0):  # +1 dB/band wiggle tolerance
            continue

        total_drop = levels_db[i] - levels_db[i + w]
        if total_drop < required_drop_db:
            continue

        # --- Floor criterion (Section 3.3 test 3) ---
        floor_region = levels_db[i + w:]
        if floor_region.size < min_floor:
            continue  # guaranteed by last_candidate_idx bound; safety net
        floor_ref = levels_db[i + w]
        coverage = float(np.mean(floor_region <= floor_ref + config.hf_cliff_floor_noise_margin_db))
        if coverage < config.hf_cliff_floor_min_fraction:
            continue
        no_recovery_bound = levels_db[i] - required_drop_db + config.hf_cliff_floor_noise_margin_db
        if float(np.max(floor_region)) > no_recovery_bound:
            continue

        # Qualifying candidate -- track the highest i seen (i_max).
        # No candidate list; no collection of (i, w, drop) tuples.
        i_max = i

    return i_max


def _floor_onset_index(
    centers: np.ndarray,
    levels_db: np.ndarray,
    passband_level: float,
    freeze_index: int,
    nyquist_hz: float,
    config,
) -> Optional[tuple[int, float]]:
    """Find j* -- the unique minimum index j >= freeze_index such that
    suffix_max[j] <= L (architecture.md Section 3.5 Step 2).

    suffix_max[j] = max(levels_db[j:]) computed over the full array; then
    the Nyquist clamp (centers <= nyquist_hz) and the freeze constraint
    (j >= freeze_index) are applied jointly to the candidate set.
    suffix_max is non-increasing by construction, so {j : suffix_max[j] <= L}
    is an up-set with exactly one minimum -- tie-free by structure, not
    empirically.

    L = passband_level - hf_cliff_required_drop_db. The noise margin
    (hf_cliff_floor_noise_margin_db) is NOT added here -- it is confined to
    the gate's own floor-coverage/no-recovery tests (Section 3.3 test 3).
    Adding it would pull j* down in frequency on every fixture.

    Args:
        centers:         band center frequencies (Hz), full grid.
        levels_db:       1/24-octave log-grid power levels (dB), full grid.
        passband_level:  levels_db[freeze_index] -- the frozen passband anchor.
        freeze_index:    i_max from _gate_scan; j* must be >= this index.
        nyquist_hz:      sr / 2.0 -- Nyquist clamp (Section 3.2 grid-geometry note).
        config:          ReferenceAnalysisConfig instance.

    Returns:
        (j_star, margin_db) tuple or None if no qualifying index exists.
        margin_db is the two-sided j* margin (architecture.md Section 11):
        min(L - suffix_max[j*], levels_db[j*-1] - L). j*-1 >= 23 always
        (Section 11.3.1); no boundary guard needed.
    """
    L = passband_level - config.hf_cliff_required_drop_db

    # Right-to-left running max over the FULL array (architecture.md Section 3.5 Step 2).
    # suffix_max[j] = max(levels_db[j:]) -- non-increasing in j.
    suffix_max = np.maximum.accumulate(levels_db[::-1])[::-1]

    # Apply Nyquist clamp (Section 3.2's grid-geometry note: the last band's
    # center can exceed Nyquist at 44.1 kHz) and freeze constraint jointly.
    valid = centers <= nyquist_hz
    qualifying_mask = valid & (suffix_max <= L)
    candidates = np.where(qualifying_mask)[0]
    candidates = candidates[candidates >= freeze_index]

    if candidates.size == 0:
        return None

    j_star = int(candidates[0])  # min() -- the unique minimum of an up-set
    rightward_margin = float(L - suffix_max[j_star])          # suffix_max already computed
    leftward_margin  = float(levels_db[j_star - 1] - L)       # single look-up; j_star-1 >= 23
    margin_db = min(rightward_margin, leftward_margin)
    return (j_star, margin_db)


def _detect_cliff(freqs: np.ndarray, psd: np.ndarray, sr: int, config) -> Optional[tuple[float, float]]:
    """Two-stage cliff detector (architecture.md Section 3.3-3.5 v1.5a),
    applied identically whether called on the whole-track PSD or a single
    segment's PSD -- self-contained, no shared state between calls.

    Stage 1 -- existence gate (_gate_scan): runs Section 3.3/3.4's three-test
    candidate scan across the full admissible range. Returns i_max -- the
    highest gate-qualifying candidate start index -- or None (no cliff). The
    gate is purely boolean here; it no longer selects a report point.

    Stage 2 -- floor-onset localization (_floor_onset_index): given
    freeze_index = i_max, finds j* -- the unique minimum j >= freeze_index
    where suffix_max[j] <= L. Reports centers[j*] as hf_band_limit_hz.

    Returns None if the gate finds no qualifying window, or if the
    gate/localization disagreement branch fires (suffix_max scan finds no
    valid j* -- rare on real programme material, always logged as a warning).
    Returns (centers[j_star], margin_db) on success, where margin_db is the
    two-sided j* margin from _floor_onset_index (architecture.md Section 11).
    """
    nyquist = sr / 2.0
    f_min = config.hf_cliff_search_min_hz / 2.0  # exactly one octave below the
    # search floor (architecture.md Section 3.2/3.4) -- guarantees every
    # candidate at or above hf_cliff_search_min_hz has a full octave of
    # pre-candidate grid history for the passband precondition.
    if f_min <= 0 or nyquist <= f_min:
        return None

    octave_fraction = config.hf_cliff_log_band_octave_fraction
    centers, levels_db = _psd.log_band_levels_db(
        freqs, psd, f_min, nyquist, band_octave_fraction=octave_fraction
    )
    n_bands = centers.size

    one_octave_bands = int(round(1.0 / octave_fraction))
    search_start_idx = int(round(
        np.log2(config.hf_cliff_search_min_hz / f_min) / octave_fraction
    ))  # == one_octave_bands, by the f_min derivation above

    # Step 0/1 -- existence gate (Section 3.3/3.4) returns i_max or None.
    # If None, no qualifying window exists anywhere in the search range --
    # this branch is provably identical to v1.3/v1.4's None path: an empty
    # qualifying set is unaffected by anything downstream of it.
    i_max = _gate_scan(levels_db, n_bands, search_start_idx, one_octave_bands, config)
    if i_max is None:
        return None

    freeze_index = i_max  # highest gate-qualifying candidate start (Section 3.5 Step 1).
                           # Permanent -- never updated after this point.
    passband_level = levels_db[freeze_index]

    # Step 2 -- floor-onset localization (Section 3.5 Step 2).
    onset = _floor_onset_index(centers, levels_db, passband_level, freeze_index, nyquist, config)
    if onset is None:
        log.warning(
            "hf_cliff: gate found qualifying candidate at i=%d but floor-onset "
            "scan found no valid j* at or after freeze_index -- reporting None "
            "(gate/localization disagreement, architecture.md v1.5a Section 3.5)",
            freeze_index,
        )
        return None

    j_star, margin_db = onset
    return (float(centers[j_star]), margin_db)


def _compute_confidence(
    whole_track_hz: Optional[float], per_segment_hz: List[Optional[float]], config
) -> float:
    """architecture.md Section 3.7 (v1.5a). Both branches are defined: when the
    whole-track result is None, confidence measures how many segments ALSO
    independently found no cliff -- agreement on absence is exactly as
    meaningful a confidence signal as agreement on a frequency.

    Operates on centers[j*] values from independent Section 3.5 runs (not
    centers[i+w] of any per-candidate argmax -- that mechanism is removed)."""
    if not per_segment_hz:
        return 0.0
    if whole_track_hz is None:
        agree = sum(1 for s in per_segment_hz if s is None)
    else:
        agree = sum(
            1 for s in per_segment_hz
            if s is not None and abs(s - whole_track_hz) <= config.hf_stability_tolerance_hz
        )
    return agree / len(per_segment_hz)


def measure_hf_extension(audio: np.ndarray, sr: int, config) -> HfExtensionResult:
    mono = _to_mono(audio)
    duration_s = mono.size / sr if sr else 0.0
    if duration_s < config.hf_min_duration_s:
        return HfExtensionResult(
            hf_band_limit_hz=None, hf_band_limit_confidence=0.0, stable=False,
            method="cliff_detection", insufficient_duration=True,
        )

    active = extract_active_audio(
        mono, sr, block_ms=config.silence_block_ms, threshold_db=config.silence_gate_threshold_db
    )
    if active.size < 8:
        active = mono

    # Whole-track decision (architecture.md Section 3.7): decided ONCE on
    # the whole-track (silence-gated) active-audio PSD -- this is the
    # structural fix for "the detector tracks programme material," matching
    # this codebase's own precedent of running the deleted
    # _transcode_slope_check on the whole-track PSD for the same reason.
    freqs_whole, psd_whole = _psd.compute_psd(active, sr)
    whole_track_result = _detect_cliff(freqs_whole, psd_whole, sr, config)
    # Unpack whole-track result; expose two-sided margin (STORY-005 §5.2 Step 1).
    if whole_track_result is not None:
        whole_track_hz, whole_track_margin_db = whole_track_result
    else:
        whole_track_hz, whole_track_margin_db = None, None

    n_segments = max(1, config.hf_stability_segment_count)
    seg_len = active.size // n_segments
    if seg_len < 8:
        n_segments = 1
        seg_len = active.size

    per_segment_results: List[Optional[tuple[float, float]]] = []
    for i in range(n_segments):
        start = i * seg_len
        end = active.size if i == n_segments - 1 else start + seg_len
        segment = active[start:end]
        if segment.size < 8:
            continue
        freqs_seg, psd_seg = _psd.compute_psd(segment, sr)
        # Identical, self-contained detector -- does not re-anchor to any
        # shared state between segments; corroborates, does not override,
        # the whole-track decision above.
        per_segment_results.append(_detect_cliff(freqs_seg, psd_seg, sr, config))

    per_segment_hz: List[Optional[float]] = [
        r[0] if r is not None else None for r in per_segment_results
    ]

    if not per_segment_hz:
        return HfExtensionResult(
            hf_band_limit_hz=None, hf_band_limit_confidence=0.0, stable=False,
            method="cliff_detection", insufficient_duration=True,
        )

    # Caveat: detect per-segment false positives (STORY-005 §5.2 Step 2).
    # A false positive is a non-None segment value disagreeing with the whole-track
    # result by more than hf_stability_tolerance_hz. None is an honest abstention
    # and is distinct from this condition.
    per_segment_reliability_caveat: Optional[str] = None
    if whole_track_hz is not None:
        for s in per_segment_hz:
            if s is not None and abs(s - whole_track_hz) > config.hf_stability_tolerance_hz:
                per_segment_reliability_caveat = (
                    "per-segment gate false positive detected: one or more segments returned a "
                    "non-None value disagreeing with the whole-track result by more than "
                    f"{config.hf_stability_tolerance_hz:.0f} Hz. "
                    "This indicates the per-segment gate fired on programme-content spectral "
                    "decline, not a band-limit wall. Per-segment values on complex material "
                    "must not be used as alternative band-limit estimates. "
                    "None on a segment is an honest abstention (insufficient spectral evidence) "
                    "and is distinct from this false-positive condition: None does not indicate "
                    "the gate misfired. "
                    "stable=False with low confidence and a strong whole-track margin is the "
                    "correct honest report under current gate parameters."
                )
                break

    confidence = _compute_confidence(whole_track_hz, per_segment_hz, config)
    stable = confidence >= config.hf_cliff_confidence_stable_floor

    segment_margins = [r[1] for r in per_segment_results if r is not None]
    hf_band_limit_robustness_db: Optional[float] = (
        min(segment_margins) if (segment_margins and whole_track_hz is not None) else None
    )

    # suspected_transcode (architecture.md Section 3.6): the separate
    # _transcode_slope_check is deleted -- its job (confirming a steep,
    # sustained slope at a candidate cutoff) is already performed
    # unconditionally as part of cliff confirmation above, so this is now a
    # direct, zero-extra-work classification against the confirmed value.
    suspected_transcode = (
        whole_track_hz is not None
        and any(lo <= whole_track_hz <= hi for lo, hi in config.transcode_suspect_bands_hz)
    )
    reason = None
    if suspected_transcode:
        reason = (
            f"band limit at {whole_track_hz:.0f} Hz falls within an encoder-typical "
            f"cutoff band -- suspected lossy-source transcode, review before treating "
            f"as a clean reference."
        )

    return HfExtensionResult(
        hf_band_limit_hz=whole_track_hz,
        hf_band_limit_confidence=confidence,
        stable=stable,
        method="cliff_detection",
        per_segment_hf_band_limit_hz=per_segment_hz,
        insufficient_duration=False,
        suspected_transcode=suspected_transcode,
        suspected_transcode_reason=reason,
        hf_band_limit_robustness_db=hf_band_limit_robustness_db,
        per_segment_reliability_caveat=per_segment_reliability_caveat,
        hf_band_limit_whole_track_margin_db=whole_track_margin_db,
    )
