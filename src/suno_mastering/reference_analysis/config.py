"""ReferenceAnalysisConfig (STORY-002 architecture.md Section 3): wraps a
MasteringConfig instance (reusing its existing frequency-band constants,
silence-gate threshold, true-peak/DR/stereo parameters, etc. where they
overlap) and adds this story's new config surface. `MasteringConfig` itself
gains zero new fields (config.py is UNCHANGED).

Attribute access falls through to the wrapped `mastering` config for any
name not defined directly on this dataclass, so the five new
`analysis/*` functions (and the reused ones) can be called with a single
config object using STORY-001's own attribute names for shared thresholds
-- this is what makes AC11's "same config values" guarantee (architecture.md
Section 8, item 1) hold without STORY-002 re-specifying/duplicating any
STORY-001 constant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..config import MasteringConfig

SEVEN_BANDS_HZ = {
    "sub":       (20.0, 60.0),
    "low":       (60.0, 120.0),
    "low_mid":   (120.0, 500.0),
    "mid":       (500.0, 2000.0),
    "high_mid":  (2000.0, 5000.0),
    "high":      (5000.0, 10000.0),
    "air":       (10000.0, None),   # None = Nyquist, resolved per-track at call time
}


@dataclass
class ReferenceAnalysisConfig:
    mastering: MasteringConfig = field(default_factory=MasteringConfig)

    # --- Seven-band scheme (resolved open question #3) ---
    seven_bands_hz: dict = field(default_factory=lambda: dict(SEVEN_BANDS_HZ))

    # --- LRA (architecture.md Section 4.1) ---
    lra_window_s: float = 3.0
    lra_hop_s: float = 0.1
    lra_relative_gate_lu: float = -20.0   # deliberately -20, NOT -10 (integrated's own gate)
    bs1770_block_s: float = 0.4           # self-consistency check windowing
    bs1770_hop_s: float = 0.1
    lra_tolerance_lu: float = 1.0          # AC10 external-reference tolerance
    lra_self_consistency_tolerance_lu: float = 0.1

    # --- HF band-limit cliff detection (STORY-004 architecture.md Section
    # 3 -- DEF-201 METHOD change: replaces the superseded threshold-crossing
    # `hf_rolloff_threshold_db` mechanism entirely, not a parameter retune
    # of it. See architecture.md Section 3.3's table for the derivation of
    # each field below; "judgment call" fields are flagged as such there,
    # not asserted as derived -- matching this codebase's own precedent in
    # analysis/sanity.py's seven-band adjacent-delta thresholds.) ---
    hf_stability_segment_count: int = 5
    hf_min_duration_s: float = 30.0
    hf_stability_tolerance_hz: float = 2000.0  # kept, repurposed (architecture.md
    # Section 3.3/3.7): per-segment/whole-track Hz-agreement tolerance feeding
    # hf_band_limit_confidence, not a raw spread-of-crossings figure.
    # Adjacent-band uncertainty smaller than this tolerance is not captured by
    # `confidence` but is reported in `HfExtensionResult.hf_band_limit_robustness_db`
    # (architecture.md §11).
    hf_rolloff_test_tolerance_hz: float = 500.0

    hf_cliff_log_band_octave_fraction: float = 1.0 / 24.0  # judgment call -- grid resolution
    hf_cliff_target_window_octaves: float = 1.0 / 3.0  # derived: 8 bands at 1/24-octave
    # resolution; the TARGET (interior) window size against which
    # hf_cliff_required_drop_db is derived. The window itself still shrinks
    # near Nyquist (near-Nyquist truncation logic); the drop bar derived
    # from it does not -- Gate 1 fix, architecture.md Section 3.3/v1.3.
    hf_cliff_required_drop_db: float = 8.0  # derived, FIXED (Gate 1 resolution):
    # hf_cliff_target_window_octaves * hf_cliff_slope_db_per_octave = 1/3 * 24 = 8.0 dB.
    # Applied identically to every candidate window regardless of its (possibly
    # truncated) size -- supersedes an earlier w-scaled bar that shrank to as
    # little as 3.0 dB near Nyquist, which the mastering-engineer's Gate 1
    # review correctly identified as near-vacuous (satisfied by ordinary
    # 48kHz top-end roll-off with no real filter present). See
    # architecture.md Section 3.3 for the full derivation.
    hf_cliff_min_window_bands: int = 3  # derived-with-margin -- smallest window (1/8
    # octave) admitted as a candidate near Nyquist; the required drop across it is
    # still the full hf_cliff_required_drop_db (8 dB over 1/8 octave = 64 dB/octave).
    hf_cliff_min_floor_bands: int = 2  # derived-with-margin -- smallest floor region
    # (1/12 octave) still treated as confirming a floor (architecture.md Section 3.5).
    hf_cliff_slope_db_per_octave: float = 24.0  # derived -- DOMAIN.md Section 2
    # (renamed from transcode_suspect_slope_db_per_octave: same value, now the
    # primary cliff-detection mechanism, not a secondary corroborator --
    # architecture.md Section 3.6).
    hf_cliff_passband_max_slope_db_per_octave: float = 12.0  # derived with stated
    # margin -- 2x DOMAIN.md Section 2's ~6 dB/octave "heavily filtered" ordinary-
    # tilt ceiling, and exactly half of hf_cliff_slope_db_per_octave, giving a
    # clean separation band between "ordinary tilt" and "a wall" (architecture.md
    # Section 3.4).
    hf_cliff_floor_min_fraction: float = 0.8  # judgment call
    hf_cliff_floor_noise_margin_db: float = 3.0  # judgment call
    hf_cliff_search_min_hz: float = 3000.0  # judgment call -- search-range floor,
    # not a plausibility floor (architecture.md Section 3.7/Section 6 risk 3).
    hf_cliff_confidence_stable_floor: float = 0.6  # judgment call -- bar for the
    # derived `stable` boolean.

    # --- Transcode suspicion (resolved open question #10) ---
    transcode_suspect_bands_hz: Tuple[Tuple[float, float], ...] = (
        (15500.0, 16500.0), (18500.0, 19500.0), (19500.0, 20500.0),
    )

    # --- Per-band stereo width (architecture.md Section 4.4) ---
    per_band_width_test_tolerance: float = 0.1

    # --- Mono-sum cancellation (architecture.md Section 4.5, DEF-101) ---
    # Compared against BandCancellation.excess_delta_db (delta_db already
    # referenced to the rho=0 per-band floor), NOT a raw dB reading -- at the
    # default -3.0, a band flags when delta_db < -6.0103 dB (rho <~ -0.5).
    mono_band_cancellation_excess_db: float = -3.0

    # --- Mono-sum broadband excess-cancellation trigger (STORY-004
    # architecture.md Section 2.3, DEF-203) --- one-sided: flags only when
    # mono_sum_level_change_db falls BELOW this bar (DOMAIN.md Section 3:
    # "excess cancellation... only... below roughly -4.5 dB"). This is an
    # analysis-time plausibility threshold, not a mastering target
    # (ARCHITECTURE.md Section 1 principle 2's "no target constants in
    # code" applies to the MASTERING CHAIN stage, not analysis-side
    # detection thresholds like this one).
    mono_sum_excess_cancellation_threshold_db: float = -4.5

    # --- Lossless-confidence-N thresholds for HF aggregate (resolved q #7) ---
    hf_lossless_n_omit_below: int = 1    # N=0 -> omit entirely
    hf_lossless_n_low_confidence_below: int = 3  # N=1-2 -> low-confidence flag

    def __getattr__(self, name: str):
        # Delegate to the wrapped MasteringConfig for any shared attribute
        # not defined on this dataclass -- e.g. freq_reference_band_hz,
        # silence_gate_threshold_db, true_peak_oversample_factor,
        # dr_block_seconds, dr_exclude_fraction, stereo_window_ms,
        # bs1770_relative_gate_lu, phase_correlation_floor, tool_version.
        # __getattr__ (not __getattribute__) is only invoked when normal
        # attribute lookup fails, so this never shadows a real
        # ReferenceAnalysisConfig field.
        return getattr(self.mastering, name)
