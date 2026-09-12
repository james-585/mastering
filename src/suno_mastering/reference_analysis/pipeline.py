"""[R1]-[R5] orchestration (STORY-002 architecture.md Section 1). A
deliberately separate top-level pipeline (reference_analysis.pipeline), not
an insertion into suno_mastering/pipeline.py -- STORY-001's pipeline.master()
entry point is untouched.

    [R1] Discover & Ingest (per file in the reference folder)
    [R2] Per-Track Analysis   -> ReferenceMeasurements (per track)
    [R3] Set Aggregation      -> aggregates (median/min/max, N, exclusions)
    [R4] Suno-Export Comparison (optional, single track, same [R2] path)
    [R5] Report Generation (per-track + aggregate + comparison, MD + JSON)
    (report generation itself lives in report/reference_builder.py /
    report/reference_render.py -- this module builds the ReferenceSetReport
    data, callers render it.)

Sequential, single-track-in-memory-at-a-time (architecture.md Section 7):
`analyze_track()` never retains the previous track's audio buffer or
TruePeakResult.oversampled buffer past that track's own analysis call --
`analysis.measure_all()` never returns the oversampled buffer at all (it is
a local variable inside measure_all/detect_clipping), so this is satisfied
by construction, not by an explicit `del`.

One unreadable file must not abort the set: [R1]'s per-file try/except
records a failure entry and the loop continues (architecture.md Section 7).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .. import analysis
from ..analysis import hf_extension as hf_extension_mod
from ..analysis import loudness_range as loudness_range_mod
from ..analysis import mono_sum as mono_sum_mod
from ..analysis import summarize_artifacts_for_display
from ..analysis import per_band_stereo_width as per_band_stereo_width_mod
from ..analysis import seven_band_balance as seven_band_balance_mod
from ..analysis.dynamic_range import _measure_dynamic_range_unrounded
from ..analysis.reference_types import ReferenceMeasurements
from ..analysis.sanity import check_hf_rolloff_vs_air_band, check_seven_band_adjacent_deltas
from ..errors import EmptyReferenceSetError, MasteringError, NonDestructiveIntegrityError
from ..io import reference_ingest
from .aggregate import AggregateStat, build_aggregates
from .config import ReferenceAnalysisConfig

logger = logging.getLogger(__name__)

_REFERENCE_EXTENSIONS = {".wav", ".flac", ".mp3"}


@dataclass
class ReferenceSetResult:
    per_track: List[ReferenceMeasurements]
    aggregates: List[AggregateStat]
    failures: List[dict]
    comparison: Optional[ReferenceMeasurements]
    decoder_identity: dict


def _discover_files(reference_dir: str) -> List[Path]:
    p = Path(reference_dir)
    if not p.exists() or not p.is_dir():
        raise MasteringError(f"Reference directory does not exist: {reference_dir}")
    # sorted() for deterministic, filesystem-order-independent traversal
    # (reproducibility NFR -- architecture.md Section 10).
    return sorted(
        f for f in p.iterdir() if f.is_file() and f.suffix.lower() in _REFERENCE_EXTENSIONS
    )


def analyze_track(path: str, config: ReferenceAnalysisConfig) -> ReferenceMeasurements:
    """[R2]: full AC1 per-track measurement. Calls STORY-001's existing
    analysis.measure_all() UNMODIFIED (architecture.md Section 8, item 1) so
    `core` is produced by literally the same call STORY-001's stage [2]
    makes -- this is what makes AC11's code-path-identity claim true by
    construction rather than by convention."""
    ingest_result = reference_ingest.ingest_reference_track(path, config)
    audio = ingest_result.audio
    sr = ingest_result.sample_rate

    core = analysis.measure_all(audio, sr, config.mastering)
    if core.artifact_detection is not None and core.artifact_detection.artifact_flags:
        print(f"Artifact summary for {path}:")
        for line in summarize_artifacts_for_display(core.artifact_detection):
            print(f"  - {line}")
    dynamic_range_db_exact = _measure_dynamic_range_unrounded(audio, sr, config.mastering)
    lra = loudness_range_mod.measure_loudness_range(audio, sr, config)
    seven_band = seven_band_balance_mod.measure_seven_band_balance(audio, sr, config)
    hf_ext = hf_extension_mod.measure_hf_extension(audio, sr, config)

    is_mono = core.is_mono
    per_band_width = None
    mono_sum_result = None
    if not is_mono:
        per_band_width = per_band_stereo_width_mod.measure_per_band_stereo_width(audio, sr, config)
        mono_sum_result = mono_sum_mod.measure_mono_sum(audio, sr, config)

    provenance = ingest_result.provenance
    provenance.suspected_transcode = hf_ext.suspected_transcode
    provenance.suspected_transcode_reason = hf_ext.suspected_transcode_reason

    # STORY-003 sanity assertions (architecture.md Section 4.3):
    # reference-analysis-only checks, layered on top of core's own
    # sanity_warnings (never duplicated -- superset, not a second list).
    air_relative_db = next(
        (b.relative_db for b in seven_band.bands if b.band == "air"), None
    )
    reference_warnings = list(core.sanity_warnings) + [
        w
        for w in (
            check_hf_rolloff_vs_air_band(
                hf_ext.hf_band_limit_hz, hf_ext.insufficient_duration, air_relative_db
            ),
        )
        if w is not None
    ] + check_seven_band_adjacent_deltas(seven_band.bands)

    return ReferenceMeasurements(
        core=core,
        dynamic_range_db_exact=dynamic_range_db_exact,
        lra=lra,
        seven_band=seven_band,
        hf_extension=hf_ext,
        per_band_stereo_width=per_band_width,
        mono_sum=mono_sum_result,
        provenance=provenance,
        track_path=str(path),
        label=None,
        sanity_warnings=reference_warnings,
    )


def analyze_set(
    reference_dir: str,
    suno_export_path: Optional[str] = None,
    config: Optional[ReferenceAnalysisConfig] = None,
) -> ReferenceSetResult:
    """Library API entry point (architecture.md Section 11). Per-file
    ingest/decode exceptions are caught internally and recorded in
    `failures` (a deliberate, narrow exception to "exceptions propagate" --
    scoped exactly to the per-file ingest/decode boundary; a bug inside
    [R2]'s measurement logic still propagates as a real exception)."""
    config = config or ReferenceAnalysisConfig()

    files = _discover_files(reference_dir)
    per_track: List[ReferenceMeasurements] = []
    failures: List[dict] = []
    decoders_seen: dict = {}
    # Hash taken immediately before each file's [R1]/[R2] pass, so [R5]'s
    # run-completion re-hash below (architecture.md Section 10) can detect
    # any mutation of a successfully-ingested file for the remainder of the
    # run -- STORY-001's own suno_mastering/pipeline.py equivalent hashes
    # once at the very start of the run for the same purpose.
    input_hashes: dict = {}

    for f in files:
        try:
            logger.info("Analyzing reference track: %s", f)
            pre_hash = reference_ingest.compute_file_hash(str(f))
            measurement = analyze_track(str(f), config)
        except MasteringError as exc:
            logger.warning("Failed to analyze %s: %s", f, exc)
            failures.append({"path": str(f), "reason": str(exc)})
            continue
        per_track.append(measurement)
        decoders_seen[measurement.provenance.container] = measurement.provenance.decoder
        input_hashes[str(f)] = pre_hash

    if not per_track:
        raise EmptyReferenceSetError(
            f"No reference tracks could be analyzed from {reference_dir} "
            f"(failures: {failures})"
        )

    # [R5] non-destructive integrity re-verification (architecture.md
    # Section 10 / AC8): re-hash every successfully-ingested file and
    # assert the set matches the hash taken before that file's own
    # analysis pass. Reused exception type (not duplicated) matches
    # STORY-001's own suno_mastering/pipeline.py::master() equivalent.
    for path, before_hash in input_hashes.items():
        after_hash = reference_ingest.compute_file_hash(path)
        if after_hash != before_hash:
            raise NonDestructiveIntegrityError(
                f"Input file hash changed during processing: started with "
                f"{before_hash}, ended with {after_hash}. "
                f"The original input must never be modified."
            )

    aggregates = build_aggregates(per_track, config)

    comparison = None
    if suno_export_path:
        # [R4]: identical [R2] path, no format asymmetry on this side
        # (Input/output assumptions section: lossy handling is
        # reference-side only) -- suno_export_path is WAV-scope per
        # STORY-001, but analyze_track()'s reference_ingest path handles
        # WAV identically to STORY-001's own ingest.py (AC11-verified).
        comparison = analyze_track(suno_export_path, config)

    return ReferenceSetResult(
        per_track=per_track,
        aggregates=aggregates,
        failures=failures,
        comparison=comparison,
        decoder_identity=decoders_seen,
    )
