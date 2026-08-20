"""Single source of truth for all thresholds/targets used across the
pipeline (architecture.md Section 6, "Config as single source of truth").

Every magic number referenced anywhere in requirements.md/architecture.md
lives here, as one overridable dataclass, so tests can construct
boundary-condition configs (e.g. a signal crafted to sit exactly at the
DR8 boundary) without touching pipeline code.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from .mastering.adaptive_harshness import AdaptiveHarshnessConfig

_DEFAULT_REFERENCE_CURVE = str(
    Path(__file__).resolve().parent / "reference" / "progressive_house_124bpm.json"
)
_DEFAULT_TARGETS_JSON = str(Path(__file__).resolve().parents[4] / "targets.json")


@dataclass
class StemConfig:
    """Configuration for stem-separated pre-mastering (STORY-008).

    Controls the optional AI stem-separation pipeline stage that runs before
    Stage 1 (measure_all). When enabled via --split-stems, the input audio is
    split into four stems (vocals, drums, bass, other), targeted DSP is applied,
    then stems are re-summed before entering the main pipeline.
    """
    enabled: bool = False
    # Default is the 6-stem model so piano/guitar are always separated
    # (STORY-022); four-stem models remain explicit opt-in overrides.
    model_name: str = "htdemucs_6s"
    shifts: int = 1
    overlap: float = 0.25
    segment_seconds: float | None = None
    profile_version: str = "demucs-default-v1"
    allow_device_fallback: bool = True
    # Disk cache for separated stems. Set to None to disable. Keyed by
    # audio SHA-256 + model + profile so re-runs of the same file skip Demucs.
    stem_cache_dir: str | None = str(Path.home() / ".cache" / "suno-mastering" / "stems")

    # Bass stem processing
    bass_mono_cutoff_hz: float = 90.0  # Mono summing below this frequency

    # Vocal stem processing
    vocal_lpf_hz: float = 15000.0      # Low-pass to remove AI sizzle
    vocal_hpf_hz: float = 80.0         # High-pass to remove rumble/DC

    def __post_init__(self) -> None:
        supported_models = {"htdemucs", "htdemucs_ft", "mdx_extra", "htdemucs_6s"}
        if self.model_name not in supported_models:
            raise ValueError(
                f"Unsupported stem model {self.model_name!r}; expected one of "
                f"{sorted(supported_models)}"
            )
        if isinstance(self.shifts, bool) or not isinstance(self.shifts, int) or self.shifts < 1:
            raise ValueError("StemConfig.shifts must be an integer greater than or equal to 1")
        if isinstance(self.overlap, bool) or not isinstance(self.overlap, (int, float)):
            raise ValueError("StemConfig.overlap must be a finite number in [0.0, 1.0)")
        if not math.isfinite(float(self.overlap)) or not 0.0 <= float(self.overlap) < 1.0:
            raise ValueError("StemConfig.overlap must be a finite number in [0.0, 1.0)")
        if self.segment_seconds is not None:
            if isinstance(self.segment_seconds, bool) or not isinstance(
                self.segment_seconds, (int, float)
            ):
                raise ValueError("StemConfig.segment_seconds must be None or a positive finite number")
            if not math.isfinite(float(self.segment_seconds)) or self.segment_seconds <= 0.0:
                raise ValueError("StemConfig.segment_seconds must be None or a positive finite number")
        if not isinstance(self.profile_version, str) or not self.profile_version.strip():
            raise ValueError("StemConfig.profile_version must be a non-empty string")
        if not isinstance(self.allow_device_fallback, bool):
            raise ValueError("StemConfig.allow_device_fallback must be a boolean")


@dataclass
class RepairWhistlesConfig:
    """STORY-009 (architecture.md Section 9). Default-off until explicitly enabled.

    Deliberately carries NO frequency field -- the only way a frequency
    reaches `suno_dsp.repair_whistles` is via `ArtifactDetectionResult`
    flags read inside `mastering.whistle_repair.apply_whistle_repair`
    (architecture.md Section 6, structural enforcement of CLAUDE.md §4.2a).
    """
    # Default-off until explicitly enabled; the repair stage must never ship
    # on by default, even when detector output exists. See architecture.md
    # Section 1/6 and the no-op gating requirements.
    enabled: bool = False
    # Reuses STORY-007's CONFIDENCE_THRESHOLD_TO_WARN (0.8) -- unchanged
    # per Gate 1 review (architecture.md Section 6, Blocker 2).
    confidence_threshold: float = 0.8
    # Explicit prominence gate for auto-notching; must be > 6 dB to have any
    # effect. This project's documented validation value is 10.0 dB.
    prominence_floor_db: float | None = 10.0
    # Reuses config.stereo_crossfade_ms's value as a starting point
    # (architecture.md Section 4).
    crossfade_ms: float = 50.0
    # When False, _detect_stationary_whistle is skipped entirely so whistle
    # flags never appear in the artifact summary or repair pipeline.
    detect_stationary_whistles: bool = True


@dataclass
class ShapeTransientsConfig:
    """STORY-009 (architecture.md Section 9). Default-off until explicitly enabled.

    The detector-sidechain highpass cutoff (150 Hz) and the slow-envelope
    time constant (100-500 ms range) are NOT config fields in this
    revision -- they are internal `suno_dsp` C++ constants, consistent with
    the other hardcoded envelope constants (architecture.md Section 9).
    """
    enabled: bool = False
    attack_boost_db: float = 3.0
    sustain_cut_db: float = -3.0


@dataclass
class CollapseSwishConfig:
    """STORY-009 (architecture.md Section 9). Default-off until explicitly enabled.

    Use the documented validation value from the architecture/test cases:
    a 5 kHz cutoff for the deployed RBJ biquad.
    """
    enabled: bool = False
    cutoff_freq_hz: float = 5000.0


@dataclass
class MasteringConfig:
    # --- Loudness (BS.1770-4 integrated LUFS) ---
    lufs_target_low: float = -14.5       # soft target band, low end
    lufs_ceiling: float = -13.5          # hard ceiling, never exceed
    lufs_floor: float = -16.0            # solver may back off no further than this
    bs1770_absolute_gate_lufs: float = -70.0
    bs1770_relative_gate_lu: float = -10.0

    # --- True peak (BS.1770-4 Annex 2) ---
    true_peak_ceiling_dbtp: float = -1.0
    true_peak_oversample_factor: int = 8   # >= 4x floor per spec; 8x for safety margin
    # v4 (DEF-002 resolution): tolerance for TC-022-style cross-oversampling-
    # factor self-consistency test assertions ONLY (architecture.md Section 2,
    # "Accepted tolerance for TC-022's cross-factor monotonicity check") --
    # never used to relax the true-peak ceiling enforcement itself, which
    # remains exact.
    true_peak_monotonicity_tolerance_db: float = 0.05

    # --- Dynamic range (TT DR-meter scale) ---
    dr_floor: float = 8.0                 # DR8, hard floor
    dr_max_reduction_db: float = 3.0      # never reduce more than this vs. source DR
    dr_block_seconds: float = 3.0
    dr_exclude_fraction: float = 0.2      # exclude loudest 20% of blocks

    # --- Frequency balance (genre-referenced, melodic prog house/techno 124bpm) ---
    freq_low_band_hz: tuple = (20.0, 120.0)
    freq_mud_band_hz: tuple = (200.0, 500.0)
    freq_presence_band_hz: tuple = (2000.0, 5000.0)
    freq_reference_band_hz: tuple = (500.0, 2000.0)   # 0 dB baseline band
    thin_low_end_threshold_db: float = 4.0     # trigger when measured < ref - 4dB
    muddiness_threshold_db: float = 3.0        # trigger when measured > ref + 3dB
    harshness_threshold_db: float = 3.0        # trigger when measured > ref + 3dB
    reference_curve_path: str = _DEFAULT_REFERENCE_CURVE
    silence_gate_threshold_db: float = -60.0   # near-silence gate for spectral analysis
    silence_block_ms: float = 400.0
    eq_max_gain_db: float = 2.0              # max gain per band in old genre-curve EQ (mastering/eq.py)

    # --- Stereo phase / mono compatibility ---
    phase_correlation_floor: float = 0.0
    phase_correlation_widened_target: float = 0.3
    stereo_window_ms: float = 500.0
    stereo_hop_ms: float = 500.0          # v3 (DEF-003): no overlap -- window tiles contiguously
    stereo_side_mid_ratio_threshold: float = 0.6
    stereo_debounce_windows: int = 2
    stereo_crossfade_ms: float = 50.0

    # --- Clipping detection ---
    clip_sample_threshold: float = 0.999    # |x| >= this counts as a full-scale sample
    clip_minor_fraction: float = 1e-4       # < this fraction of samples => "minor"
    clip_moderate_fraction: float = 1e-3    # < this fraction of samples => "moderate"; else "severe"

    # --- Output format ---
    output_bit_depth: int = 24
    supported_sample_rates: tuple = (44100, 48000)
    default_sample_rate: int = 44100

    # --- Dither ---
    dither_seed: int = 42

    # --- Targets ---
    targets_json_path: str | None = _DEFAULT_TARGETS_JSON

    # --- Solver (loudness_limit.py / stereo_correct.py) ---
    solver_max_iterations: int = 32
    solver_lufs_tolerance: float = 0.05
    limiter_lookahead_ms: float = 5.0
    limiter_release_ms: float = 60.0

    # --- Stem separation (STORY-008) ---
    stem_config: StemConfig = field(default_factory=StemConfig)

    # --- Adaptive harshness (STORY-010) --- default off until explicitly enabled
    adaptive_harshness: AdaptiveHarshnessConfig = field(default_factory=AdaptiveHarshnessConfig)

    # --- suno_dsp pipeline stages (STORY-009) --- all default off (AC5) ---
    repair_whistles: RepairWhistlesConfig = field(default_factory=RepairWhistlesConfig)
    shape_transients: ShapeTransientsConfig = field(default_factory=ShapeTransientsConfig)
    collapse_swish: CollapseSwishConfig = field(default_factory=CollapseSwishConfig)

    # --- Misc ---
    tool_version: str = "0.1.0"

    def reference_curve(self) -> dict:
        import json

        with open(self.reference_curve_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
