"""Assembles a ReferenceSetResult (reference_analysis/pipeline.py) into
ReferenceSetReport, the machine-readable schema owner (STORY-002
architecture.md Section 9). A separate module from report/builder.py --
STORY-001's builder.py/render.py are UNCHANGED (NFR: no regression to
STORY-001's report shape).

`AggregateStat` is defined in reference_analysis/aggregate.py (the module
that actually computes it, per architecture.md Section 1's [R3] ownership)
and re-exported here for the ReferenceSetReport schema -- a deliberate,
minor deviation from architecture.md Section 9's literal module-layout
table (which shows AggregateStat defined directly in this file): defining
it in aggregate.py avoids a circular import (reference_analysis would
otherwise need to import from report, inverting the intended dependency
direction where report consumes reference_analysis, not vice versa) without
changing the resulting JSON/schema shape at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from ..analysis.reference_types import ReferenceMeasurements
from ..reference_analysis.aggregate import AggregateStat
from ..reference_analysis.pipeline import ReferenceSetResult

SCHEMA_VERSION = "2.2"
# v1.1 (DEF-101 resolution): additive `BandCancellation.excess_delta_db`
# field, plus config field rename mono_cancellation_threshold_db ->
# mono_band_cancellation_excess_db reflected in config_summary below.
# v1.2 (STORY-003, AC13): additive `ReferenceMeasurements.sanity_warnings`
# field (list of analysis.sanity.SanityWarning) -- see architecture.md
# Section 4.4.
# v2.0 (STORY-004, DEF-201/DEF-203 -- architecture.md Section 8): MAJOR
# bump, per this file's own convention ("bump MAJOR for anything that
# removes or reshapes an existing field"). Removes
# `HfExtensionResult.rolloff_hz` (replaced by `hf_band_limit_hz`, a
# different nullability meaning, not an additive rename); removes
# `MonoSumResult.excess_cancellation_db` (replaced by a boolean,
# `mono_sum_excess_cancellation`, a different type, not a rename); removes
# two config fields (`hf_rolloff_threshold_db`,
# `transcode_suspect_slope_db_per_octave`) from config_summary().
# v2.1 (STORY-004, DEF-206 -- architecture.md §11): additive
# `HfExtensionResult.hf_band_limit_robustness_db: Optional[float]`
# (minimum two-sided per-segment j* margin). MINOR bump.
# v2.2 (STORY-005, DEF-205 -- architecture.md §5.4): additive
# `HfExtensionResult.per_segment_reliability_caveat: Optional[str]` and
# `HfExtensionResult.hf_band_limit_whole_track_margin_db: Optional[float]`
# (two-sided minimum j* margin on the whole-track PSD). MINOR bump.
# Versioning convention (per architecture.md Section 9): bump the MINOR
# component for additive/backward-compatible field changes, the MAJOR
# component for anything that removes or reshapes an existing field. Every
# future story that changes this schema should update this constant and
# this docstring rule together.


@dataclass(kw_only=True)
class ReferenceSetReport:
    schema_version: str = SCHEMA_VERSION
    generated_at_utc: str
    decoder_identity: dict
    tool_version: str
    config_summary: dict
    per_track: List[ReferenceMeasurements] = field(default_factory=list)
    aggregates: List[AggregateStat] = field(default_factory=list)
    comparison: Optional[dict] = None
    failures: List[dict] = field(default_factory=list)


def _config_summary(config) -> dict:
    return {
        "seven_bands_hz": {k: list(v) for k, v in config.seven_bands_hz.items()},
        "lra_window_s": config.lra_window_s,
        "lra_hop_s": config.lra_hop_s,
        "lra_relative_gate_lu": config.lra_relative_gate_lu,
        "lra_tolerance_lu": config.lra_tolerance_lu,
        "hf_stability_segment_count": config.hf_stability_segment_count,
        "hf_min_duration_s": config.hf_min_duration_s,
        "hf_stability_tolerance_hz": config.hf_stability_tolerance_hz,
        "hf_cliff_log_band_octave_fraction": config.hf_cliff_log_band_octave_fraction,
        "hf_cliff_target_window_octaves": config.hf_cliff_target_window_octaves,
        "hf_cliff_required_drop_db": config.hf_cliff_required_drop_db,
        "hf_cliff_min_window_bands": config.hf_cliff_min_window_bands,
        "hf_cliff_min_floor_bands": config.hf_cliff_min_floor_bands,
        "hf_cliff_slope_db_per_octave": config.hf_cliff_slope_db_per_octave,
        "hf_cliff_passband_max_slope_db_per_octave": config.hf_cliff_passband_max_slope_db_per_octave,
        "hf_cliff_floor_min_fraction": config.hf_cliff_floor_min_fraction,
        "hf_cliff_floor_noise_margin_db": config.hf_cliff_floor_noise_margin_db,
        "hf_cliff_search_min_hz": config.hf_cliff_search_min_hz,
        "hf_cliff_confidence_stable_floor": config.hf_cliff_confidence_stable_floor,
        "transcode_suspect_bands_hz": [list(b) for b in config.transcode_suspect_bands_hz],
        "mono_band_cancellation_excess_db": config.mono_band_cancellation_excess_db,
        "mono_sum_excess_cancellation_threshold_db": config.mono_sum_excess_cancellation_threshold_db,
        "hf_lossless_n_omit_below": config.hf_lossless_n_omit_below,
        "hf_lossless_n_low_confidence_below": config.hf_lossless_n_low_confidence_below,
        "true_peak_oversample_factor": config.true_peak_oversample_factor,
        "dr_block_seconds": config.dr_block_seconds,
        "dr_exclude_fraction": config.dr_exclude_fraction,
    }


def _comparison_dict(comparison: Optional[ReferenceMeasurements], aggregates: List[AggregateStat]) -> Optional[dict]:
    """AC3: side-by-side presentation of the Suno-export comparison track
    against the reference-set aggregate, so the gap is directly visible."""
    if comparison is None:
        return None
    agg_by_metric = {a.metric: a for a in aggregates}

    def gap(metric: str, value: Optional[float]) -> Optional[dict]:
        agg = agg_by_metric.get(metric)
        if agg is None or agg.median is None or value is None:
            return None
        return {
            "suno_export_value": value,
            "reference_median": agg.median,
            "gap": value - agg.median,
        }

    return {
        "track": comparison,
        "gaps": {
            "integrated_lufs": gap("integrated_lufs", comparison.core.integrated_lufs),
            "true_peak_dbtp": gap("true_peak_dbtp", comparison.core.true_peak_dbtp),
            "dynamic_range_db_exact": gap("dynamic_range_db_exact", comparison.dynamic_range_db_exact),
            "lra_lu": gap("lra_lu", comparison.lra.lra_lu),
        },
    }


def build_reference_set_report(result: ReferenceSetResult, config) -> ReferenceSetReport:
    return ReferenceSetReport(
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        decoder_identity=result.decoder_identity,
        tool_version=config.tool_version,
        config_summary=_config_summary(config),
        per_track=result.per_track,
        aggregates=result.aggregates,
        comparison=_comparison_dict(result.comparison, result.aggregates),
        failures=result.failures,
    )
