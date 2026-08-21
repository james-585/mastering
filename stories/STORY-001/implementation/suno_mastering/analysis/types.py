"""Shared dataclasses describing analysis output. One shape, used for both
the pre-master and post-master Measurements (architecture.md Section 6:
"types.py -- Measurements dataclass(es) -- shared pre/post shape").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from .sanity import SanityWarning


# ── Shared measurement result types (also re-exported by reference_types.py) ──

@dataclass
class LraResult:
    lra_lu: float
    n_gated_blocks: int
    self_consistency_delta_lu: float  # |reconstructed integrated LUFS - measure_integrated_lufs|


@dataclass
class PerBandWidthMeasurement:
    band: str
    range_hz: tuple
    width: float  # 0 = mono/correlated, 1 = fully decorrelated (clamped to [0,1])


@dataclass
class PerBandWidthResult:
    bands: List[PerBandWidthMeasurement] = field(default_factory=list)


# ── STORY-007: Artifact detection types ──────────────────────────────────────

@dataclass
class ArtifactFlag:
    """A single detected artifact with time window and diagnostic."""
    timestamp_start_s: float
    timestamp_end_s: float
    artifact_type: str        # "SMEARED_TRANSIENT"|"DIGITAL_HAZE"|"STATIONARY_WHISTLE"|"PHASE_SWISH"
    confidence_score: float   # 0.0 to 1.0
    details: dict             # type-specific: frequency_hz, prominence_db, q_factor, …


@dataclass(eq=False)
class ArtifactDetectionResult:
    """Summary and list of detected artifacts (STORY-007 arch §4.2).

    Equality intentionally ignores `detected_at` so that repeated runs on the
    same input produce identical measurement objects while still preserving the
    diagnostic timestamp for reporting purposes.
    """
    total_artifacts_found: int
    artifact_flags: List[ArtifactFlag]
    overall_artifact_density_score: float  # 0.0 (clean) to 1.0 (heavily degraded)
    detected_at: datetime

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ArtifactDetectionResult):
            return NotImplemented
        return (
            self.total_artifacts_found == other.total_artifacts_found
            and self.artifact_flags == other.artifact_flags
            and self.overall_artifact_density_score == other.overall_artifact_density_score
        )


@dataclass
class ClippingResult:
    sample_peak_clipped_count: int
    sample_peak_clip_events: int
    inter_sample_over_count: int
    inter_sample_peak_dbtp: float
    severity: str  # "none" | "minor" | "moderate" | "severe"

    @property
    def has_clipping(self) -> bool:
        return self.sample_peak_clipped_count > 0 or self.inter_sample_over_count > 0


@dataclass
class BandMeasurement:
    range_hz: tuple
    relative_db: float          # measured energy, dB relative to the reference band
    reference_db: float         # genre-reference expected value for this band
    deviation_db: float         # relative_db - reference_db
    flagged: bool
    flag_name: Optional[str] = None


@dataclass
class FrequencyBalanceResult:
    low_end: BandMeasurement
    low_mid_mud: BandMeasurement
    presence_harsh: BandMeasurement

    @property
    def any_flagged(self) -> bool:
        return self.low_end.flagged or self.low_mid_mud.flagged or self.presence_harsh.flagged


@dataclass
class StereoWindowResult:
    start_sample: int
    end_sample: int
    start_time_s: float
    end_time_s: float
    mid_energy: float
    side_energy: float
    ratio: float
    correlation: float
    is_widened: bool


@dataclass
class StereoWidenedRegion:
    start_sample: int
    end_sample: int
    start_time_s: float
    end_time_s: float
    region_correlation: float
    mean_ratio: float
    needs_correction: bool


@dataclass
class StereoPhaseResult:
    is_mono: bool
    overall_correlation: float
    mono_compatible: bool  # overall_correlation >= config.phase_correlation_floor
    windows: list = field(default_factory=list)          # list[StereoWindowResult]
    widened_regions: list = field(default_factory=list)  # list[StereoWidenedRegion]


@dataclass
class Measurements:
    """Full six-criterion assessment for one point in the pipeline (pre- or
    post-master). Produced by analysis.* functions, consumed by
    report.builder."""

    sample_rate: int
    channels: int
    duration_seconds: float
    is_mono: bool
    integrated_lufs: float
    true_peak_dbtp: float
    dynamic_range_db: float
    frequency_balance: FrequencyBalanceResult
    stereo_phase: StereoPhaseResult
    clipping: ClippingResult
    sanity_warnings: List[SanityWarning] = field(default_factory=list)
    # STORY-007: artifact detection result (None when skipped, e.g. unsupported SR)
    artifact_detection: Optional[ArtifactDetectionResult] = None
    # Human-readable strings for high-confidence flags (confidence >= 0.8)
    plausibility_warnings: List[str] = field(default_factory=list)
    # STORY-027: HF band-limit cliff detection (hf_extension.py wired into measure_all).
    # None = no cliff detected or track too short.  Report-only per CLAUDE.md §6.2.
    hf_band_limit_hz: Optional[float] = None
    hf_band_limit_confidence: Optional[float] = None
    # Loudness Range (EBU Tech 3342 / BS.1770-4). None if audio too short for gating.
    lra: Optional[LraResult] = None
    # Per-band stereo width (frequency-domain coherence estimate). None for mono.
    per_band_stereo_width: Optional[PerBandWidthResult] = None


# ── STORY-008: Stem separation types ──────────────────────────────────────

@dataclass
class StemAction:
    """Records one DSP operation applied to a stem during pre-processing.

    Attributes:
        stem_name: "vocals" | "drums" | "bass" | "other"
        action_type: "mono_sub" | "hf_rolloff" | "lf_cut" | "passthrough"
        parameters: dict with filter-specific keys (frequency_hz, filter_type, order)
    """
    stem_name: str
    action_type: str  # e.g., "mono_sub", "hf_rolloff", "lf_cut"
    parameters: dict  # e.g., {"frequency_hz": 15000, "filter_type": "low_pass"}


@dataclass
class StemSeparationResult:
    """Summary of stem separation and processing for reporting.

    Populated when --split-stems is invoked. Included in MasteringResult
    and rendered in the Stem Pre-Processing section of output reports.

    Attributes:
        model_used: Demucs model name (e.g., "htdemucs")
        separation_time_s: Wall-clock time for AI separation (Phase A)
        actions_applied: List of StemAction records (Phase B)
        stems: Optional dict mapping stem name to float64 arrays for the later
            stem-aware mastering stages. This preserves the separated material
            until Story 11-17 has had a chance to operate on it.
        runtime_metadata: Demucs device, cache, profile, source mapping, and
            residual telemetry produced by the separation boundary.
    """
    model_used: str
    separation_time_s: float
    actions_applied: list  # list[StemAction]
    stems: dict[str, np.ndarray] = field(default_factory=dict)
    runtime_metadata: dict = field(default_factory=dict)
