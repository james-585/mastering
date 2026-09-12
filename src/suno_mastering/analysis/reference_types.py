"""Dataclasses for STORY-002's reference-track measurements (architecture.md
Section 3: "compose, don't extend Measurements"). `Measurements`
(analysis/types.py) is imported and wrapped, never modified.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .sanity import SanityWarning
from .types import LraResult, Measurements, PerBandWidthMeasurement, PerBandWidthResult


@dataclass
class SevenBandMeasurement:
    band: str
    range_hz: tuple
    relative_db: float  # dB relative to the shared 500Hz-2kHz reference band


@dataclass
class SevenBandResult:
    bands: List[SevenBandMeasurement] = field(default_factory=list)


@dataclass
class HfExtensionResult:
    """STORY-004 architecture.md Section 3.8 return contract. Replaces the
    superseded threshold-crossing `rolloff_hz`/`stable`-from-raw-Hz-spread
    fields (DEF-201) with the two-stage log-frequency-grid cliff detector's
    output. `hf_band_limit_hz` is nullable and NEVER a fallback value --
    `None` means either a confirmed absence of a cliff, or (near Nyquist)
    "not measurable in the remaining bandwidth" (architecture.md Section
    3.5/Section 6 risk 4); both states report identically today, by design."""
    hf_band_limit_hz: Optional[float]  # None: no cliff found, or insufficient duration
    hf_band_limit_confidence: float     # [0,1] -- fraction of segments corroborating
                                          # the whole-track decision (architecture.md
                                          # Section 3.7), defined for both the
                                          # found-cliff and no-cliff branches
    stable: bool                         # hf_band_limit_confidence >= config.hf_cliff_confidence_stable_floor
    method: str = "cliff_detection"     # explicit method contract for JSON/report output
    per_segment_hf_band_limit_hz: List[Optional[float]] = field(default_factory=list)
    insufficient_duration: bool = False
    suspected_transcode: bool = False
    suspected_transcode_reason: Optional[str] = None
    hf_band_limit_robustness_db: Optional[float] = None
    # Minimum two-sided j* margin (dB) across all per-segment _detect_cliff calls
    # that returned a non-None result.
    # margin_db = min(L_seg - suffix_max_seg[j*_seg],   <- rightward: noise moving j* higher
    #                 levels_db_seg[j*_seg - 1] - L_seg) <- leftward: noise moving j* lower
    # where L_seg = passband_level_seg - hf_cliff_required_drop_db.
    # None when hf_band_limit_hz is None, or when no segment found a cliff.
    # Bounds two-sided localization quantization GIVEN the anchor (i_max from _gate_scan).
    # Does NOT validate the anchor itself -- see DEF-205 (open) and architecture.md §11.3.2.
    # <0.5 dB: within Welch estimator noise; j* could shift one 1/24-oct grid band.
    # ~8 dB (= hf_cliff_required_drop_db): passband close to L, typical of gradual cliff.
    # No config threshold -- see architecture.md §11.3.3.
    # When per_segment_reliability_caveat is non-None, this minimum may incorporate a
    # false-positive segment's j* margin rather than the true-wall localization robustness.

    per_segment_reliability_caveat: Optional[str] = None
    # Populated when a per-segment false positive is detected: a non-None segment value
    # disagrees with the whole-track result by more than hf_stability_tolerance_hz.
    # When non-None, per-segment values MUST NOT be used as alternative band-limit estimates:
    # the non-None disagreeing value is a wrong number (gate fired on programme-content
    # spectral decline, not a band-limit wall), not an honest abstention.
    # None means no per-segment false positive was detected on this track; the field is
    # unrelated to whether any segment returned None (an honest abstention is a distinct,
    # safe state -- see AC5(b)).
    # Machine-readable check: `if result.per_segment_reliability_caveat is not None`.

    hf_band_limit_whole_track_margin_db: Optional[float] = None
    # Two-sided minimum j* margin (dB) on the whole-track PSD.
    # Same definition as hf_band_limit_robustness_db but for the whole-track _detect_cliff
    # call: min(L - suffix_max[j*], levels_db[j*-1] - L) where L = passband_level -
    # hf_cliff_required_drop_db. Populated when hf_band_limit_hz is not None.
    # Unlike hf_band_limit_robustness_db, this field is never contaminated by a per-segment
    # false-positive margin -- it is derived from the whole-track PSD only.
    # Use this field together with per_segment_reliability_caveat to understand whether
    # stable=False reflects genuine whole-track uncertainty or merely insufficient
    # per-segment corroboration (STORY-005 architecture.md §5.1).


@dataclass
class BandCancellation:
    band: str
    range_hz: tuple
    delta_db: float  # mono-sum band power vs. channel-mean band power, dB
    excess_delta_db: float  # delta_db - (-3.0103 dB, the shared rho=0/
                              # fully-decorrelated channel-mean floor --
                              # STORY-004 architecture.md Section 2.1/2.3.
                              # 0 => an ordinary, healthy decorrelated band;
                              # large negative => genuine anti-correlation/
                              # cancellation in this band.
    cancellation: bool  # excess_delta_db < config.mono_band_cancellation_excess_db


@dataclass
class MonoSumResult:
    """STORY-004 architecture.md Section 2 (DEF-203 method change): mono sum
    compared against the CHANNEL-MEAN reference (not BS.1770's channel-
    summed stereo LUFS), giving a rho=0 floor of -3.0103 dB (not the
    superseded -6.0206 dB). See architecture.md Section 2.1 for the full
    derivation and Section 2.3 for the field-contract rationale."""
    mono_sum_level_change_db: float  # LUFS(mono_sum) - channel_mean_lufs(L, R),
                                        # architecture.md Section 2.1/2.2. rho=1.0 (L=R)
                                        # -> 0 dB; rho=0.0 (independent, equal power)
                                        # -> -3.0103 dB; rho=-1.0 (fully inverted) -> -inf.
    mono_sum_excess_cancellation: bool  # True iff mono_sum_level_change_db <
                                           # config.mono_sum_excess_cancellation_threshold_db
                                           # (-4.5 dB, DOMAIN.md Section 3). One-sided.
    mono_sum_both_channels_silent: bool = False  # True iff both L and R independently
                                                    # measured -inf LUFS (Gate 1 advisory,
                                                    # architecture.md Section 2.2). When
                                                    # True, mono_sum_level_change_db is the
                                                    # defined 0.0 dB rho=1 limit, not a
                                                    # measured comparison.
    band_cancellations: List[BandCancellation] = field(default_factory=list)

    @property
    def any_cancellation(self) -> bool:
        return any(b.cancellation for b in self.band_cancellations)


@dataclass
class ProvenanceResult:
    container: str              # "wav" | "flac" | "mp3"
    lossless: bool               # container-declared, not corroborated
    bitrate_kbps: Optional[int]  # None => "bitrate unknown"
    decoder: str                 # e.g. "libsndfile-<version>" | "ffmpeg-<version>"
    suspected_transcode: bool = False
    suspected_transcode_reason: Optional[str] = None


@dataclass
class ReferenceMeasurements:
    core: Measurements              # STORY-001's exact shape, unmodified
    dynamic_range_db_exact: float   # unrounded DR (architecture.md Section 5)
    lra: LraResult
    seven_band: SevenBandResult
    hf_extension: HfExtensionResult
    per_band_stereo_width: Optional[PerBandWidthResult]   # None if mono
    mono_sum: Optional[MonoSumResult]                     # None if mono
    provenance: ProvenanceResult
    track_path: str
    label: Optional[str] = None      # forward-compat free-text tag (open q #2)
    # STORY-003 sanity assertions (architecture.md Section 4.3): superset of
    # core.sanity_warnings -- includes the reference-analysis-only checks
    # (HF-rolloff-vs-air-band, seven-band adjacent deltas) alongside every
    # warning core's own measure_all() already produced. One field, one
    # list: gives report/reference_render.py exactly one place to read
    # from, avoiding a renderer bug where only one of two scattered lists
    # gets rendered.
    sanity_warnings: List[SanityWarning] = field(default_factory=list)
