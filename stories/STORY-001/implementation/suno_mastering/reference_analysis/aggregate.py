"""[R3] Set aggregation -- median/min/max across the reference set for every
AC1 metric, each carrying its own N and contributing-track identity (AC12),
and applying the three resolved exclusion/subsetting rules (STORY-002
architecture.md Section 1):

  - lossy tracks excluded from the HF-extension aggregate (source format
    point 2, AC5),
  - HF-extension aggregated per sample-rate subset, never blended (resolved
    open question #6),
  - mono tracks excluded from stereo-width/mono-compatibility aggregates
    specifically (Input/output assumptions, mono note).

Every exclusion is a visible, reason-coded entry (`excluded`), never a
silent drop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

from ..analysis.reference_types import ReferenceMeasurements


@dataclass
class AggregateStat:
    metric: str
    median: Optional[float]
    min: Optional[float]
    max: Optional[float]
    n: int
    contributing_tracks: List[str] = field(default_factory=list)
    excluded: List[dict] = field(default_factory=list)   # [{"track": ..., "reason": ...}]
    note: Optional[str] = None   # e.g. "low-confidence (N<3 lossless)", "no lossless references"


def _stat(metric: str, values: List[float], tracks: List[str], excluded: List[dict], note: Optional[str] = None) -> AggregateStat:
    if not values:
        return AggregateStat(metric=metric, median=None, min=None, max=None, n=0, contributing_tracks=[], excluded=excluded, note=note)
    return AggregateStat(
        metric=metric,
        median=float(np.median(values)),
        min=float(np.min(values)),
        max=float(np.max(values)),
        n=len(values),
        contributing_tracks=list(tracks),
        excluded=excluded,
        note=note,
    )


def _basic_metric_stat(metric: str, tracks: List[ReferenceMeasurements], getter: Callable[[ReferenceMeasurements], Optional[float]]) -> AggregateStat:
    values, names = [], []
    for t in tracks:
        v = getter(t)
        if v is None or not np.isfinite(v):
            continue
        values.append(float(v))
        names.append(t.track_path)
    return _stat(metric, values, names, excluded=[])


def _stereo_only_metric_stat(metric: str, tracks: List[ReferenceMeasurements], getter: Callable[[ReferenceMeasurements], Optional[float]]) -> AggregateStat:
    values, names, excluded = [], [], []
    for t in tracks:
        if t.core.is_mono:
            excluded.append({"track": t.track_path, "reason": "mono track - excluded from stereo-width/mono-compatibility aggregate"})
            continue
        v = getter(t)
        if v is None or not np.isfinite(v):
            continue
        values.append(float(v))
        names.append(t.track_path)
    return _stat(metric, values, names, excluded=excluded)


def build_aggregates(tracks: List[ReferenceMeasurements], config) -> List[AggregateStat]:
    aggregates: List[AggregateStat] = []

    # --- Metrics aggregated over the full track set, no exclusion ---
    aggregates.append(_basic_metric_stat("integrated_lufs", tracks, lambda t: t.core.integrated_lufs))
    aggregates.append(_basic_metric_stat("true_peak_dbtp", tracks, lambda t: t.core.true_peak_dbtp))
    aggregates.append(_basic_metric_stat("dynamic_range_db_exact", tracks, lambda t: t.dynamic_range_db_exact))
    aggregates.append(_basic_metric_stat("lra_lu", tracks, lambda t: t.lra.lra_lu))

    for band_key in config.seven_bands_hz.keys():
        aggregates.append(
            _basic_metric_stat(
                f"seven_band.{band_key}.relative_db", tracks,
                lambda t, bk=band_key: next((b.relative_db for b in t.seven_band.bands if b.band == bk), None),
            )
        )

    # --- Stereo-width / mono-compatibility: mono tracks excluded ---
    aggregates.append(_stereo_only_metric_stat("overall_correlation", tracks, lambda t: t.core.stereo_phase.overall_correlation))
    aggregates.append(_stereo_only_metric_stat("mono_sum.mono_sum_level_change_db", tracks, lambda t: t.mono_sum.mono_sum_level_change_db if t.mono_sum else None))
    # mono_sum.excess_cancellation_db aggregate line REMOVED (STORY-004
    # architecture.md Section 4 item 8): the corrected field,
    # mono_sum_excess_cancellation, is a boolean, not a median-appropriate
    # metric. Deliberate simplification, not a silent loss -- the per-track
    # boolean remains visible in the per-track report section
    # (report/reference_render.py).
    for band_key in config.seven_bands_hz.keys():
        aggregates.append(
            _stereo_only_metric_stat(
                f"per_band_stereo_width.{band_key}", tracks,
                lambda t, bk=band_key: next(
                    (b.width for b in t.per_band_stereo_width.bands if b.band == bk), None
                ) if t.per_band_stereo_width else None,
            )
        )

    # --- HF extension: per sample-rate subset, lossless-only (AC5, resolved q#6/q#7) ---
    aggregates.extend(_hf_extension_aggregates(tracks, config))

    return aggregates


def _hf_extension_aggregates(tracks: List[ReferenceMeasurements], config) -> List[AggregateStat]:
    sample_rates = sorted({t.core.sample_rate for t in tracks})
    results = []
    for sr in sample_rates:
        subset = [t for t in tracks if t.core.sample_rate == sr]
        values, names, excluded = [], [], []
        for t in subset:
            if not t.provenance.lossless:
                excluded.append({"track": t.track_path, "reason": "lossy source (mp3) - excluded from HF-extension aggregate (AC5)"})
                continue
            if t.hf_extension.insufficient_duration:
                excluded.append({"track": t.track_path, "reason": "insufficient duration for HF-band-limit analysis"})
                continue
            if t.hf_extension.hf_band_limit_hz is None:
                # STORY-004 architecture.md Section 4 item 8: behavior
                # change, not just a rename -- distinguishes "insufficient
                # duration" (above) from "no band limit detected", which is
                # a legitimate measurement outcome (AC2), not a defect.
                excluded.append({"track": t.track_path, "reason": "no band limit detected (confirmed absence of a cliff, or not measurable near Nyquist) - legitimate, not a defect"})
                continue
            values.append(t.hf_extension.hf_band_limit_hz)
            names.append(t.track_path)

        n = len(values)
        # Metric key renamed hf_extension_rolloff_hz -> hf_extension_hf_band_limit_hz
        # (STORY-004, schema 2.0): the old name is a machine-readable key
        # STORY-005 consumes -- leaving it as "rolloff_hz" after the field
        # itself is gone/renamed is exactly the "rename shipped incompletely"
        # pattern architecture.md Section 4 warns about (DEF-104/DEF-106).
        if n < config.hf_lossless_n_omit_below:
            note = "no lossless references available for HF extension"
            results.append(_stat(f"hf_extension_hf_band_limit_hz.{sr}hz", [], [], excluded=excluded, note=note))
            continue
        note = None
        if n < config.hf_lossless_n_low_confidence_below:
            note = f"low-confidence: only {n} lossless reference(s) contribute (below the N>=3 confidence bar)"
        results.append(_stat(f"hf_extension_hf_band_limit_hz.{sr}hz", values, names, excluded=excluded, note=note))
    return results
