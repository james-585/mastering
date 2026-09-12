"""Assembles pre/post Measurements + the corrective-action log into one
report data structure (pipeline stage [10]).

Owns AC8 (before/after report covering all six criteria) and AC10
(traceability: tool version, settings, input/output hashes).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..analysis.types import Measurements


@dataclass
class ReportData:
    tool_version: str
    generated_at_utc: str
    input_path: str
    output_path: str
    input_hash: str
    output_hash: str
    config_summary: dict
    before: Measurements
    after: Measurements
    resample_action: Optional[dict]
    eq_actions: list
    stereo_actions: list
    solver: dict
    dither_seed: int
    integrity_verified: bool
    repair_whistles_actions: list = field(default_factory=list)
    collapse_swish_actions: list = field(default_factory=list)
    shape_transients_actions: list = field(default_factory=list)
    adaptive_harshness_actions: list = field(default_factory=list)
    transient_restoration_actions: list = field(default_factory=list)
    harshness_control_actions: list = field(default_factory=list)
    stereo_imaging_actions: list = field(default_factory=list)
    bus_glue_actions: list = field(default_factory=list)
    stem_runtime: Optional[dict] = None
    quality_review: object | None = None
    # STORY-027: seven-band balance (before/after), leveling, and hf_band_limit.
    # Disambiguation: seven-band band names do NOT correspond to three-band
    # frequency_balance names by frequency range (requirements.md Finding 0):
    #   three-band low_mid_mud:  200-500 Hz
    #   seven-band low_mid:      120-500 Hz
    # Never substitute one for the other in AC3 / residual_gap_db logic.
    seven_band_balance: Optional[dict] = None  # {"before": {...}, "after": {...}}
    leveling_action: object | None = None       # LevelingAction dataclass
    leveling_action_applied: bool = False


def _config_summary(config) -> dict:
    return {
        "lufs_target_band": [config.lufs_target_low, config.lufs_ceiling],
        "lufs_floor": config.lufs_floor,
        "true_peak_ceiling_dbtp": config.true_peak_ceiling_dbtp,
        "true_peak_oversample_factor": config.true_peak_oversample_factor,
        "dr_floor": config.dr_floor,
        "dr_max_reduction_db": config.dr_max_reduction_db,
        "eq_max_gain_db": config.eq_max_gain_db,
        "phase_correlation_floor": config.phase_correlation_floor,
        "phase_correlation_widened_target": config.phase_correlation_widened_target,
        "output_bit_depth": config.output_bit_depth,
        "supported_sample_rates": list(config.supported_sample_rates),
        "dither_seed": config.dither_seed,
        "solver_max_iterations": config.solver_max_iterations,
        # Air band: informational only — no corrective EQ applied (architecture §19).
        # Correction is applied to sub (20–60 Hz) and low_mid (120–500 Hz) only.
        # Low band (60–120 Hz): informational; receives shelf bleed from sub correction
        # (approximately ±1 dB at 120 Hz for a ±2 dB sub correction) — expected behaviour.
        "spectral_correction_scope": "sub and low_mid only; air/high/high_mid/low are informational",
    }


def _build_seven_band_entry(
    band: str,
    relative_db: Optional[float],
    targets: Optional[dict],
    de_mud_fired: bool = False,
) -> dict:
    """Build a single seven-band report entry with optional range/in_range fields."""
    entry: dict = {"relative_db": relative_db}

    # Bands with correction ranges in targets.json
    ranged_bands = {"sub", "low_mid", "high_mid", "high", "air"}
    # low and mid have degenerate/zero ranges in targets.json — omit range fields
    if band in ranged_bands and targets is not None:
        band_cfg = targets.get("spectral_bands", {}).get(band, {})
        range_cfg = band_cfg.get("range_db_re_mid", {})
        range_min = range_cfg.get("min")
        range_max = range_cfg.get("max")
        if range_min is not None and range_max is not None:
            entry["range_min"] = range_min
            entry["range_max"] = range_max
            if relative_db is not None:
                entry["in_range"] = bool(range_min <= relative_db <= range_max)

    if band == "low_mid":
        entry["de_mud_triggered"] = de_mud_fired

    return entry


def _build_seven_band_block(
    band_map: Dict[str, float],
    targets: Optional[dict],
    de_mud_fired: bool = False,
) -> dict:
    """Build the seven_band_balance.before or .after sub-dict."""
    all_bands = ["sub", "low", "low_mid", "mid", "high_mid", "high", "air"]
    return {
        band: _build_seven_band_entry(
            band,
            band_map.get(band),
            targets,
            de_mud_fired=(band == "low_mid" and de_mud_fired),
        )
        for band in all_bands
    }


def build_report(
    *,
    config,
    input_path: str,
    output_path: str,
    input_hash: str,
    output_hash: str,
    before: Measurements,
    after: Measurements,
    resample_action: Optional[dict],
    eq_actions: list,
    stereo_actions: list,
    repair_whistles_actions: Optional[list] = None,
    collapse_swish_actions: Optional[list] = None,
    shape_transients_actions: Optional[list] = None,
    adaptive_harshness_actions: Optional[list] = None,
    transient_restoration_actions: Optional[list] = None,
    harshness_control_actions: Optional[list] = None,
    stereo_imaging_actions: Optional[list] = None,
    bus_glue_actions: Optional[list] = None,
    solver_outcome,
    integrity_verified: bool,
    stem_runtime: Optional[dict] = None,
    quality_review: object | None = None,
    # STORY-027 new params (all optional for backward compatibility)
    leveling_action: object | None = None,
    pre_seven_band_balance: Optional[Dict[str, float]] = None,
    post_seven_band_balance: Optional[Dict[str, float]] = None,
    de_mud_fired: bool = False,
    targets: Optional[dict] = None,
) -> ReportData:
    solver_dict = {
        "target_lufs": solver_outcome.target_lufs,
        "achieved_lufs": solver_outcome.achieved_lufs,
        "achieved_true_peak_dbtp": solver_outcome.achieved_true_peak_dbtp,
        "achieved_dr": solver_outcome.achieved_dr,
        "source_dr": solver_outcome.source_dr,
        "dr_floor_used": solver_outcome.dr_floor_used,
        "gain_db_applied": solver_outcome.gain_db_applied,
        "outer_iterations": solver_outcome.outer_iterations,
        "peak_convergence_iterations": solver_outcome.peak_convergence_iterations,
        "below_soft_band": solver_outcome.below_soft_band,
        "below_documented_lufs_floor": solver_outcome.below_documented_lufs_floor,
        "rationale": solver_outcome.rationale,
    }

    # STORY-027 §5.3: compute residual_gap_db for each eq_action using
    # post-master seven-band measurement.  Populated here (not at EQ time)
    # because the post-master band levels are not available until after the
    # full processing chain and post-master measure_all have run.
    updated_eq_actions = list(eq_actions)
    if post_seven_band_balance:
        updated_eq_actions = []
        for action in eq_actions:
            post_db = post_seven_band_balance.get(getattr(action, "band", None))
            aim = getattr(action, "aim_point_db", None)
            if post_db is not None and aim is not None:
                try:
                    action = dataclasses.replace(action, residual_gap_db=aim - post_db)
                except (TypeError, ValueError):
                    pass  # action type does not support residual_gap_db; leave unchanged
            updated_eq_actions.append(action)

    # STORY-027 §5.2: seven_band_balance block for the report.
    seven_band_balance_report: Optional[dict] = None
    if pre_seven_band_balance is not None:
        before_block = _build_seven_band_block(pre_seven_band_balance, targets, de_mud_fired)
        after_block = (
            _build_seven_band_block(post_seven_band_balance, targets, de_mud_fired)
            if post_seven_band_balance is not None
            else None
        )
        seven_band_balance_report = {
            "_note": (
                "Seven-band band names do NOT correspond to three-band frequency_balance "
                "names by frequency range (requirements.md Finding 0). "
                "three-band low_mid_mud=200-500 Hz; seven-band low_mid=120-500 Hz. "
                "Do not substitute one for the other."
            ),
            "before": before_block,
            "after": after_block,
        }

    return ReportData(
        tool_version=config.tool_version,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        input_path=input_path,
        output_path=output_path,
        input_hash=input_hash,
        output_hash=output_hash,
        config_summary=_config_summary(config),
        before=before,
        after=after,
        resample_action=resample_action,
        eq_actions=updated_eq_actions,
        stereo_actions=list(stereo_actions),
        solver=solver_dict,
        dither_seed=config.dither_seed,
        integrity_verified=integrity_verified,
        repair_whistles_actions=list(repair_whistles_actions or []),
        collapse_swish_actions=list(collapse_swish_actions or []),
        shape_transients_actions=list(shape_transients_actions or []),
        adaptive_harshness_actions=list(adaptive_harshness_actions or []),
        transient_restoration_actions=list(transient_restoration_actions or []),
        harshness_control_actions=list(harshness_control_actions or []),
        stereo_imaging_actions=list(stereo_imaging_actions or []),
        bus_glue_actions=list(bus_glue_actions or []),
        stem_runtime=stem_runtime,
        quality_review=quality_review,
        seven_band_balance=seven_band_balance_report,
        leveling_action=leveling_action,
        leveling_action_applied=getattr(leveling_action, "applied", False),
    )
