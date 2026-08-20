"""Orchestrates the stem-first mastering workflow described by the product story.

The operator-facing stage narration follows the product's six macro-phases:

    1. Stem Split          - ingest, validate, Demucs stem separation, stem analysis
    2. Tighten Low End      - stem mastering: transient restoration, harshness control,
                               stereo imaging, and controlled bus glue re-summation
    3. Lochness EQ          - targets-based per-stem corrective EQ, adaptive harshness
    4. Reintegrate Lows     - stereo width, detector-driven sub-bass / vocal repair
    5. Loudness Normalize   - two-pass measured LUFS/true-peak solver + dither
    6. Ready for Release    - export, integrity check, before/after reporting

Each macro-phase keeps the existing reference-derived targets and detector-driven
DSP methods underneath; only the operator-facing grouping/order changed to match
the product workflow narrative. The implementation still keeps the underlying
helper modules separate so each stage remains testable, but the runtime sequence now reflects the intended
product workflow instead of the older legacy corrective pass.
"""
from __future__ import annotations

import dataclasses
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from .progress import NullReporter, render_stage_bar

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FOR_STORY_11_17 = [
    _REPO_ROOT / "stories" / "STORY-011" / "implementation",
    _REPO_ROOT / "stories" / "STORY-012" / "implementation",
    _REPO_ROOT / "stories" / "STORY-013" / "implementation",
    _REPO_ROOT / "stories" / "STORY-014" / "implementation",
    _REPO_ROOT / "stories" / "STORY-015" / "implementation",
    _REPO_ROOT / "stories" / "STORY-025" / "implementation",
]
for _story_path in _FOR_STORY_11_17:
    if str(_story_path) not in sys.path:
        sys.path.insert(0, str(_story_path))

from final_bus_glue import apply_final_bus_glue
from grounded_quality_review import evaluate_quality_review
from harshness_control import apply_stem_harshness_control
from stem_stereo_imaging import apply_stem_stereo_imaging
from transient_restoration import apply_stem_transient_restoration

from . import analysis
from .analysis import seven_band_balance as seven_band_balance_mod
from .analysis import summarize_artifacts_for_display
from .analysis.types import Measurements, StemSeparationResult
from .analysis.stereo_phase import StereoWidenedRegion
from .config import MasteringConfig
from .errors import DependencyError, NonDestructiveIntegrityError, TargetsLoadError
from .io import export as export_mod
from .io import ingest as ingest_mod
from .mastering import adaptive_harshness as adaptive_harshness_mod
from .mastering import corrective_eq as corrective_eq_mod
from .mastering import dither as dither_mod
from .mastering import loudness_limit
from .mastering import resample as resample_mod
from .mastering import stereo_correct as stereo_correct_mod
from .mastering import stereo_width_corrector as width_corrector_mod
from .mastering import swish_collapse as collapse_swish_mod
from .mastering import transient_shaping as transient_shaping_mod
from .mastering import whistle_repair as whistle_repair_mod
from .targets.loader import load_targets
from .analysis import per_band_stereo_width as per_band_width_mod
from .reference_analysis.config import ReferenceAnalysisConfig
from .report import builder as report_builder

logger = logging.getLogger(__name__)


def _print_artifact_fix_summary(before_lines: list[str], after_lines: list[str]) -> None:
    """Show whether artifact detection improved after corrective processing.

    Generation artifacts detected from a stereo sum are not generally fixable in
    the mastering stage. If the count is unchanged, report that fact clearly and
    explain that no repair was attempted rather than implying a successful fix.
    """
    before_count = len(before_lines)
    after_count = len(after_lines)

    print("Artifact fix status:")
    print(f"  before: {before_count} artifact(s)")
    print(f"  after: {after_count} artifact(s)")

    if after_count < before_count:
        print(f"  result: reduced ({before_count} -> {after_count})")
    elif after_count == before_count:
        print(
            "  result: unchanged (non-recoverable; no repair attempted at mastering stage)"
        )
    else:
        print("  result: increased (new artifacts detected after processing)")


def _announce_progress(stage: int, label: str, detail: str | None = None, *, reporter=None) -> None:
    """Emit a concise user-visible progress bar for a pipeline stage.

    The pipeline has a single canonical progress source: the reporter path. When no
    reporter is supplied, this falls back to a direct console print for library-only
    callers that do not participate in the CLI screen flow.
    """
    total = 6
    message = render_stage_bar(stage, label, stage, total, detail)
    if reporter is not None:
        reporter.emit(stage, label, detail, total=total)
    else:
        print(message)
    # logger.debug, not .info: the reporter/print above is the single console
    # output path -- .info would duplicate every line via the CLI's own handler.
    logger.debug(message)


def _announce_story_step(stage: int, label: str, detail: str | None = None, *, reporter=None) -> None:
    """Emit the stage label in the product story vocabulary."""
    _announce_progress(stage, label, detail, reporter=reporter)


@dataclass
class MasteringResult:
    output_path: str
    before: Measurements
    after: Measurements
    actions: dict
    report: report_builder.ReportData
    input_hash: str
    output_hash: str
    integrity_verified: bool
    # v4 (architecture.md Section 1, resolves DEF-001 residual): True iff the
    # solver's selected candidate landed below config.lufs_floor (-16.0
    # default), which is now a soft, report-escalation threshold rather than
    # a hard solver constraint -- see mastering.loudness_limit.SolverOutcome.
    below_documented_lufs_floor: bool
    stem_separation: Optional[StemSeparationResult] = None  # STORY-008
    quality_review: object | None = None


def _rescale_regions_to_sample_rate(regions, new_sr: int) -> list:
    """Widened-element regions are detected once, in stage [2], against the
    original sample rate. If stage [3] resamples, sample-index boundaries
    must be remapped to the new sample rate before stage [5b] uses them --
    time boundaries (start_time_s/end_time_s) are sample-rate independent
    and are the source of truth for the remap."""
    rescaled = []
    for r in regions:
        rescaled.append(
            StereoWidenedRegion(
                start_sample=int(round(r.start_time_s * new_sr)),
                end_sample=int(round(r.end_time_s * new_sr)),
                start_time_s=r.start_time_s,
                end_time_s=r.end_time_s,
                region_correlation=r.region_correlation,
                mean_ratio=r.mean_ratio,
                needs_correction=r.needs_correction,
            )
        )
    return rescaled


def _apply_story_11_17_stem_mastering(audio: np.ndarray, sample_rate: int, stem_result=None) -> tuple[np.ndarray, dict[str, list]]:
    """Activate the validated Story 11-14 mastering stages in the live product path."""
    stems: dict[str, np.ndarray]
    if stem_result is not None and getattr(stem_result, "stems", None):
        stems = {name: np.asarray(value, dtype=np.float64) for name, value in stem_result.stems.items()}
    else:
        stems = {"mix": np.asarray(audio, dtype=np.float64).copy()}

    transient_processed, transient_actions = apply_stem_transient_restoration(stems, sample_rate)
    harsh_processed, harsh_actions = apply_stem_harshness_control(transient_processed, sample_rate)
    stereo_processed, stereo_actions = apply_stem_stereo_imaging(harsh_processed, sample_rate)
    bus_processed, bus_actions = apply_final_bus_glue(stereo_processed, sample_rate)
    processed = bus_processed.get("mix", np.asarray(audio, dtype=np.float64).copy())
    if processed.shape != np.asarray(audio, dtype=np.float64).shape:
        processed = np.asarray(audio, dtype=np.float64).copy()

    return processed, {
        "transient_restoration": transient_actions,
        "harshness_control": harsh_actions,
        "stereo_imaging": stereo_actions,
        "bus_glue": bus_actions,
    }


def master(
    input_path: str,
    output_dir: Optional[str] = None,
    config: Optional[MasteringConfig] = None,
    *,
    reporter=None,
) -> MasteringResult:
    """Library API entry point. Exceptions propagate to the caller -- no
    swallowed errors at this layer (architecture.md Section 6)."""
    config = config or MasteringConfig()
    reporter = reporter or NullReporter()

    # Resolve (and hard-fail-guard) the output path early, before doing any
    # heavy processing, so a doomed run fails fast.
    output_path = export_mod.resolve_output_path(input_path, output_dir)

    # --- Load targets.json before Stage [1] --- (DEF-606)
    # Raises TargetsLoadError immediately if absent, malformed, or path is None.
    # No audio processing occurs when targets.json is unavailable.
    targets_doc = load_targets(getattr(config, "targets_json_path", None))
    targets = targets_doc.to_dict()

    # ReferenceAnalysisConfig is used for both per-band width measurement (after [2])
    # and seven-band balance measurement (before [4]).
    ref_cfg = ReferenceAnalysisConfig(mastering=config)

    any_dsp_stage_enabled = (
        config.repair_whistles.enabled
        or config.shape_transients.enabled
        or config.collapse_swish.enabled
    )
    if any_dsp_stage_enabled:
        try:
            import suno_dsp  # noqa: F401
        except ImportError as exc:
            raise DependencyError(
                "suno_dsp extension is required because at least one of "
                "repair_whistles/shape_transients/collapse_swish is enabled, "
                "but the module could not be imported. Build it via "
                "CMakeLists.txt before enabling these stages."
            ) from exc

    # --- [1] Ingest & Validate ---
    _announce_story_step(1, "Stem Split", input_path, reporter=reporter)
    ingest_result = ingest_mod.ingest(input_path, config)

    audio = ingest_result.audio

    # --- [2] TDemucs stem separation ---
    if config.stem_config.enabled:
        _announce_story_step(1, "Stem Split", f"model={config.stem_config.model_name}", reporter=reporter)
    else:
        _announce_story_step(1, "Stem Split", "stereo path", reporter=reporter)

    # --- [3] Stem analysis ---
    _announce_story_step(1, "Stem Split", "stem analysis", reporter=reporter)
    before = analysis.measure_all(audio, ingest_result.sample_rate, config)
    artifact_detection = getattr(before, "artifact_detection", None)
    before_artifact_lines: list[str] = []
    if artifact_detection is not None:
        before_artifact_lines = summarize_artifacts_for_display(artifact_detection)
        if before_artifact_lines:
            print("Artifact summary (pre-master):")
            for line in before_artifact_lines:
                print(f"  - {line}")
            if len(before_artifact_lines) >= 6:
                print("  - Summary intentionally limited to the most relevant findings.")

    # --- STORY-008: Optional stem issue identification + repair ---
    # Requirement: artifact fixes happen after identification and within Stage [2].
    stem_result = None
    if config.stem_config.enabled:
        _announce_story_step(2, "Tighten Low End", f"detector-driven sub-bass/vocal repair, model={config.stem_config.model_name}", reporter=reporter)
        logger.info("=" * 70)
        logger.info("STAGE 2: STEM ISSUE IDENTIFICATION + REPAIR (STORY-008)")
        logger.info("=" * 70)
        from .stem_integration import run_stem_preprocessing

        # ArtifactFlag carries no stem_name -- mix-level flags are attributed
        # to a stem only inside run_stem_preprocessing, once stems exist.
        artifact_flags = getattr(artifact_detection, "artifact_flags", None)

        audio, stem_result = run_stem_preprocessing(
            audio=audio,
            sample_rate=ingest_result.sample_rate,
            stem_config=config.stem_config,
            artifact_flags=artifact_flags,
        )
        logger.info("Stem repair complete within Stage [2].")
        print("[Stage 2] Stem issue identification and repair complete; continuing to resampling")

    # --- Story 11-15: active stem-aware mastering path ---
    # Runs here (Stage 2), right after stem separation/repair, so its output
    # becomes the audio buffer that EQ/width/loudness act on. It previously ran
    # last and re-derived the mix from the stale pre-EQ stems, silently throwing
    # away every later corrective stage.
    _announce_story_step(2, "Tighten Low End", "stem attack and clarity upgrade", reporter=reporter)
    audio, story_11_17_actions = _apply_story_11_17_stem_mastering(
        audio, ingest_result.sample_rate, stem_result
    )
    _announce_story_step(2, "Tighten Low End", "local de-haze and control", reporter=reporter)
    _announce_story_step(2, "Tighten Low End", "widens only safe, stereo-healthy stems", reporter=reporter)
    _announce_story_step(2, "Tighten Low End", "cohesive final mix balance", reporter=reporter)

    # Per-band stereo widths (Stage [2] measurement used as pre_widths for Stage [5a]).
    # Uses the current working audio so stem-preprocessed material is consistent
    # with the signal that continues through the pipeline.
    per_band_widths = {}
    if before.channels == 2:
        pw = per_band_width_mod.measure_per_band_stereo_width(
            audio, ingest_result.sample_rate, ref_cfg
        )
        for b in pw.bands:
            per_band_widths[b.band] = b.width

    sr = ingest_result.sample_rate

    # --- [4] tonal balance / transient density / harshness / width behavior / dynamic range ---
    _announce_story_step(3, "Lochness EQ", "analysis and corrective targets", reporter=reporter)
    resample_outcome = resample_mod.resample_if_needed(audio, sr, config)
    audio = resample_outcome.audio
    sr = resample_outcome.sample_rate
    resample_action = None
    if resample_outcome.was_resampled:
        resample_action = {
            "source_sample_rate": resample_outcome.source_sample_rate,
            "sample_rate": resample_outcome.sample_rate,
        }

    # --- [4a] repair_whistles (detector-driven only, config-gated) ---
    repair_whistle_actions: list = []
    if config.repair_whistles.enabled:
        _announce_story_step(3, "Lochness EQ", "detector-driven cleanup", reporter=reporter)
        audio, repair_whistle_actions = whistle_repair_mod.apply_whistle_repair(
            audio,
            sr,
            before.artifact_detection,
            config.repair_whistles,
        )

    # --- [4b] Corrective EQ (targets-based) ---
    # Old genre-curve EQ (mastering/eq.py apply_corrective_eq) is retired — DEF-605.
    # Seven-band measurement is taken fresh here for pre_band_levels (DEF-607):
    # uses correct band bounds (sub=20–60 Hz, low_mid=120–500 Hz) from the
    # seven-band scheme, rather than the three-band frequency_balance bands which
    # map different frequency ranges (20–120 Hz and 200–500 Hz respectively).
    _announce_story_step(3, "Lochness EQ", "targets-based corrective EQ", reporter=reporter)
    seven_band = seven_band_balance_mod.measure_seven_band_balance(audio, sr, ref_cfg)
    seven_band_map = {b.band: b.relative_db for b in seven_band.bands}
    pre_band_levels = {
        "sub":     seven_band_map.get("sub", 0.0),
        "low_mid": seven_band_map.get("low_mid", 0.0),
        "mid":     seven_band_map.get("mid", 0.0),
    }
    eq_actions: list = []
    audio, eq_actions = corrective_eq_mod.apply_corrective_eq(
        audio, sr, targets, pre_band_levels
    )

    adaptive_harshness_actions: list = []
    if config.adaptive_harshness.enabled:
        _announce_story_step(3, "Lochness EQ", "evidence-based stem-aware reduction", reporter=reporter)
        audio, adaptive_harshness_actions = adaptive_harshness_mod.apply_adaptive_harshness(
            audio,
            sr,
            before.frequency_balance,
            config.adaptive_harshness,
        )

    # --- [5a] Per-Band Stereo Width Correction ---
    _announce_story_step(4, "Reintegrate Lows", "local stereo shaping", reporter=reporter)
    if before.channels == 2:
        audio, width_actions = width_corrector_mod.apply_stereo_width_correction(
            audio, sr, targets, per_band_widths
        )
    else:
        width_actions = []

    # --- [5b] Broadband Stereo/Mono Correction ---
    _announce_story_step(4, "Reintegrate Lows", "broadband stereo/mono correction", reporter=reporter)
    widened_regions = _rescale_regions_to_sample_rate(
        before.stereo_phase.widened_regions, sr
    )
    audio, stereo_actions = stereo_correct_mod.correct_stereo_widened_elements(
        audio, sr, widened_regions, config
    )
    stereo_actions = list(stereo_actions) + list(width_actions)

    # --- [5c] collapse_swish (default off, not detector-driven) ---
    collapse_swish_actions: list = []
    if config.collapse_swish.enabled:
        _announce_story_step(4, "Reintegrate Lows", f"swish collapse cutoff={config.collapse_swish.cutoff_freq_hz:.0f} Hz", reporter=reporter)
        audio, collapse_swish_actions = collapse_swish_mod.apply_collapse_swish(
            audio,
            sr,
            config.collapse_swish,
            artifact_detection=before.artifact_detection,
        )

    # --- [5d] shape_transients (default off, not detector-driven) ---
    transient_actions: list = []
    if config.shape_transients.enabled:
        _announce_story_step(4, "Reintegrate Lows", "transient shaping", reporter=reporter)
        audio, transient_actions = transient_shaping_mod.apply_transient_shaping(
            audio,
            sr,
            config.shape_transients,
        )

    # --- [7] dynamic range + final safety ---
    _announce_story_step(5, "Loudness Normalize", "loudness and true-peak safety", reporter=reporter)
    # source_dr_db is the TRUE original pre-processing DR from stage [2] --
    # deliberately not recomputed here (architecture.md Section 1 note).
    solver_outcome = loudness_limit.solve_loudness_and_limit(
        audio, sr, source_dr_db=before.dynamic_range_db, config=config
    )
    audio = solver_outcome.audio

    # --- [7] Dither & Bit-Depth Conversion ---
    _announce_story_step(5, "Loudness Normalize", "dither and bit-depth conversion", reporter=reporter)
    dither_outcome = dither_mod.tpdf_dither_and_quantize(
        audio, config.output_bit_depth, config.dither_seed
    )

    # --- [9] Export ---
    _announce_story_step(6, "Ready for Release", output_path, reporter=reporter)
    export_mod.export_wav(
        dither_outcome.audio,
        sr,
        output_path,
        config,
        preserved_chunks=ingest_result.preserved_chunks,
    )

    # --- [10] Before/after stem-by-stem reporting ---
    _announce_story_step(6, "Ready for Release", "before/after stem-by-stem reporting", reporter=reporter)
    post_ingest_result = ingest_mod.ingest(output_path, config)
    after = analysis.measure_all(
        post_ingest_result.audio, post_ingest_result.sample_rate, config
    )
    post_artifact_detection = getattr(after, "artifact_detection", None)
    after_artifact_lines: list[str] = []
    if post_artifact_detection is not None:
        after_artifact_lines = summarize_artifacts_for_display(post_artifact_detection)
        if after_artifact_lines:
            print("Artifact summary (post-master):")
            for line in after_artifact_lines:
                print(f"  - {line}")
    if before_artifact_lines or after_artifact_lines:
        _print_artifact_fix_summary(before_artifact_lines, after_artifact_lines)
    output_hash = post_ingest_result.input_hash

    # Non-destructive integrity check (architecture.md Section 4): re-hash
    # the ORIGINAL input at the very end of the run and assert it matches
    # the hash taken at the start.
    final_input_hash = ingest_mod.compute_file_hash(input_path)
    integrity_verified = final_input_hash == ingest_result.input_hash
    if not integrity_verified:
        raise NonDestructiveIntegrityError(
            f"Input file hash changed during processing: started with "
            f"{ingest_result.input_hash}, ended with {final_input_hash}. "
            f"The original input must never be modified."
        )

    # STORY-025: grounded quality review runs after before/after measurement so
    # post_ingest_result is available; placed before build_report so the result
    # can be embedded in the report and MasteringResult together.
    quality_review = evaluate_quality_review(
        ingest_result.audio, post_ingest_result.audio, ingest_result.sample_rate
    )

    # --- [11] Report generation ---
    _announce_story_step(6, "Ready for Release", "report generation", reporter=reporter)
    report = report_builder.build_report(
        config=config,
        input_path=input_path,
        output_path=output_path,
        input_hash=ingest_result.input_hash,
        output_hash=output_hash,
        before=before,
        after=after,
        resample_action=resample_action,
        eq_actions=eq_actions,
        stereo_actions=stereo_actions,
        repair_whistles_actions=repair_whistle_actions,
        collapse_swish_actions=collapse_swish_actions,
        shape_transients_actions=transient_actions,
        adaptive_harshness_actions=adaptive_harshness_actions,
        transient_restoration_actions=story_11_17_actions.get("transient_restoration"),
        harshness_control_actions=story_11_17_actions.get("harshness_control"),
        stereo_imaging_actions=story_11_17_actions.get("stereo_imaging"),
        bus_glue_actions=story_11_17_actions.get("bus_glue"),
        solver_outcome=solver_outcome,
        integrity_verified=integrity_verified,
        stem_runtime=getattr(stem_result, "runtime_metadata", None),
        quality_review=quality_review,
    )

    # Built manually (not via dataclasses.asdict) to avoid deep-copying the
    # full mastered-audio numpy buffer just to discard it from the log.
    loudness_limit_action = {
        f.name: getattr(solver_outcome, f.name)
        for f in dataclasses.fields(solver_outcome)
        if f.name != "audio"
    }
    actions = {
        "resample": resample_action,
        "eq": eq_actions,
        "stereo_correct": stereo_actions,
        "loudness_limit": loudness_limit_action,
    }
    if config.adaptive_harshness.enabled:
        actions["adaptive_harshness"] = adaptive_harshness_actions
    if config.repair_whistles.enabled:
        actions["repair_whistles"] = repair_whistle_actions
    if config.collapse_swish.enabled:
        actions["collapse_swish"] = collapse_swish_actions
    if config.shape_transients.enabled:
        actions["shape_transients"] = transient_actions
    actions.update(story_11_17_actions)

    return MasteringResult(
        output_path=output_path,
        before=before,
        after=after,
        actions=actions,
        report=report,
        input_hash=ingest_result.input_hash,
        output_hash=output_hash,
        integrity_verified=integrity_verified,
        below_documented_lufs_floor=solver_outcome.below_documented_lufs_floor,
        stem_separation=stem_result,  # STORY-008
        quality_review=quality_review,
    )
