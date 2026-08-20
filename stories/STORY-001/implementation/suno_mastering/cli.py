"""Thin argparse wrapper around pipeline.master() (architecture.md Section
6, "CLI vs. library API").

    python -m suno_mastering <input.wav> [--output-dir DIR] [--config PATH]

Catches the errors.py exception hierarchy at the top level to print a clear
message and exit non-zero, and writes the rendered report alongside the
output WAV.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from pathlib import Path

from .config import MasteringConfig, StemConfig
from .errors import MasteringError
from .pipeline import master
from .progress import ConsoleReporter, NullReporter, render_stage_bar
from .report.render import render_json, render_markdown

# STORY-024: operator-facing workflow screen lives in the story implementation
# folder (same cross-story pattern as pipeline.py uses for stories 11-15).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_STORY_024_IMPL = _REPO_ROOT / "stories" / "STORY-024" / "implementation"
if str(_STORY_024_IMPL) not in sys.path:
    sys.path.insert(0, str(_STORY_024_IMPL))

from workflow_screen import render_error, render_run_header, render_summary


def _load_config(config_path: str) -> MasteringConfig:
    with open(config_path, "r", encoding="utf-8") as fh:
        overrides = json.load(fh)
    stem_overrides = overrides.get("stem_config")
    if isinstance(stem_overrides, dict):
        changed_profile_controls = {"shifts", "overlap", "segment_seconds"} & stem_overrides.keys()
        if changed_profile_controls and not str(stem_overrides.get("profile_version", "")).strip():
            raise ValueError(
                "JSON stem_config changes to shifts, overlap, or segment_seconds "
                "require an explicit non-empty profile_version"
            )
        overrides["stem_config"] = StemConfig(**stem_overrides)
    return MasteringConfig(**overrides)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suno_mastering",
        description="Analyse and master a raw Suno WAV export to streaming-ready targets.",
    )
    parser.add_argument("input", help="Path to the input WAV file (raw Suno export).")
    parser.add_argument(
        "--output-dir", default=None,
        help="Directory to write the mastered WAV + report into (defaults to the input file's directory).",
    )
    parser.add_argument(
        "--config", default=None,
        help="Path to a JSON file of MasteringConfig field overrides.",
    )
    parser.add_argument(
        "--split-stems",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable AI stem separation pre-processing (requires demucs/torch)",
    )
    parser.add_argument(
        "--stem-model",
        type=str,
        default=None,
        choices=["htdemucs", "htdemucs_ft", "mdx_extra", "htdemucs_6s"],
        help="Demucs model to use for stem separation",
    )
    parser.add_argument(
        "--stem-shifts", "--shifts",
        dest="stem_shifts",
        type=int,
        default=None,
        help="Number of Demucs equivariant shifts",
    )
    parser.add_argument(
        "--stem-overlap", "--overlap",
        dest="stem_overlap",
        type=float,
        default=None,
        help="Demucs split overlap in [0.0, 1.0)",
    )
    parser.add_argument(
        "--stem-segment-seconds", "--segment-seconds",
        dest="stem_segment_seconds",
        type=float,
        default=None,
        help="Optional Demucs segment duration in seconds",
    )
    parser.add_argument(
        "--stem-profile-version", "--profile-version",
        dest="stem_profile_version",
        default=None,
        help="Non-empty version label for the effective Demucs profile",
    )
    parser.add_argument(
        "--stem-device-fallback",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Allow one explicit accelerator-to-CPU retry",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging and fuller terminal progress output.",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        default=True,
        help="Print explicit stage-by-stage progress messages during the run (default: on).",
    )
    parser.add_argument(
        "--no-progress",
        dest="progress",
        action="store_false",
        help="Disable the terminal stage progress bars.",
    )
    parser.add_argument(
        "--json-summary",
        action="store_true",
        help="Print a JSON summary of the final mastering result to stdout.",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Skip writing the Markdown/JSON report files to disk.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the input and configuration without running the full mastering pipeline.",
    )
    parser.add_argument(
        "--stem-cache",
        dest="stem_cache",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable the disk cache for Demucs stem separation (default: on). "
             "Use --no-stem-cache to force a fresh Demucs run.",
    )
    parser.add_argument(
        "--detect-whistles",
        dest="detect_whistles",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable stationary-whistle detection (default: on). Use --no-detect-whistles to suppress whistle flags entirely.",
    )
    parser.add_argument(
        "--repair-whistles",
        dest="repair_whistles",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable the detector-driven whistle repair C++ stage.",
    )
    parser.add_argument(
        "--shape-transients",
        dest="shape_transients",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable the transient shaping C++ stage.",
    )
    parser.add_argument(
        "--collapse-swish",
        dest="collapse_swish",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable or disable the stereo swish collapse C++ stage.",
    )
    return parser


def _emit_progress(stage: int, label: str, detail: str | None = None) -> None:
    suffix = f" - {detail}" if detail else ""
    print(f"[Stage {stage}] {label}{suffix}")


def _emit_stage_bar(stage: int, label: str, done: int, total: int, detail: str | None = None) -> None:
    print(render_stage_bar(stage, label, done, total, detail))


def _render_summary_json(result) -> str:
    solver = getattr(result.report, "solver", {})
    summary = {
        "output_path": getattr(result, "output_path", None),
        "achieved_lufs": solver.get("achieved_lufs"),
        "achieved_true_peak_dbtp": solver.get("achieved_true_peak_dbtp"),
        "achieved_dr": solver.get("achieved_dr"),
    }
    return json.dumps({"Summary": summary}, indent=2)


def _print_active_workflow() -> None:
    workflow = [
        "Stem Split (Isolate Tracks) - Demucs stem separation + stem analysis",
        "Lochness EQ (Surgical EQ) - targets-based corrective EQ, adaptive harshness reduction",
        "Tighten Low End (Clean Sub-Bass) - detector-driven bass/vocal stem repair",
        "Reintegrate Lows (Controlled Low Boost) - stereo width, transient restoration, "
        "harshness control, stereo imaging, controlled bus glue re-summation",
        "Loudness Normalize (Two-Pass LUFS & True Peak) - measured solver + dither",
        "Ready for Release (Mastered Output) - export, integrity check, before/after reporting",
    ]
    print("Mastering workflow:")
    for index, step in enumerate(workflow, start=1):
        print(f"  {index}. {step}")


def _build_reporter(args) -> ConsoleReporter | NullReporter:
    if not getattr(args, "progress", False):
        return NullReporter()
    return ConsoleReporter()


def _prompt_yes_no(prompt: str, default: bool = True) -> bool:
    """Prompt for a yes/no answer in an interactive terminal.

    Returns the explicit choice when user answers, otherwise uses the default.
    Accepts: y/yes/n/no/blank.
    """
    if not hasattr(sys, "stdin") or sys.stdin is None or not sys.stdin.isatty():
        return default

    choices = "Y/n" if default else "y/N"
    while True:
        response = input(f"{prompt} [{choices}]: ").strip().lower()
        if response in ("",):
            return default
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print("Please answer yes or no.")


def _prompt_artifact_toggles(args, config) -> None:
    """Legacy C++ repair stages are intentionally not part of the active product flow.

    They remain default-off in config and are not asked about in the normal CLI
    workflow. Explicit CLI flags still parse correctly for compatibility, but the
    interactive prompt path does not expose them in the user-facing product flow.
    """
    return


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        force=True,
    )

    reporter = _build_reporter(args)
    if args.progress:
        print("Live stage-progress will be shown during the mastering run.")
        print("The workflow is driven by the active reporter and reflects the current")
        print("product pipeline rather than the old static checklist.")
        reporter.emit(0, "Stem Split", args.input, total=6)

    if args.verbose:
        print(f"Verbose logging enabled; log level={logging.getLevelName(log_level)}")

    config = _load_config(args.config) if args.config else MasteringConfig()
    profile_controls_changed = any(
        value is not None
        for value in (args.stem_shifts, args.stem_overlap, args.stem_segment_seconds)
    )
    if profile_controls_changed and not str(args.stem_profile_version or "").strip():
        parser.error(
            "changing --shifts, --overlap, or --segment-seconds requires "
            "--profile-version"
        )
    stem_updates = {
        name: value
        for name, value in {
            "enabled": args.split_stems,
            "model_name": args.stem_model,
            "shifts": args.stem_shifts,
            "overlap": args.stem_overlap,
            "segment_seconds": args.stem_segment_seconds,
            "profile_version": args.stem_profile_version,
            "allow_device_fallback": args.stem_device_fallback,
        }.items()
        if value is not None
    }
    config.stem_config = dataclasses.replace(config.stem_config, **stem_updates)
    if config.stem_config.enabled:
        print(
            "Stem separation enabled: "
            f"model={config.stem_config.model_name} "
            f"profile={config.stem_config.profile_version}"
        )
    else:
        print("Stem separation disabled; using standard stereo master path")

    # STORY-024: stage-oriented start-of-run screen (TC-024-01).
    print(
        render_run_header(
            input_file=args.input,
            model=config.stem_config.model_name,
            profile=config.stem_config.profile_version,
            stem_enabled=config.stem_config.enabled,
        )
    )

    # Legacy C++ repair stages are intentionally default-off and not exposed to
    # the normal product flow. Explicit CLI flags still work when provided, but
    # the interactive prompt path stays silent to avoid resurfacing old build-era
    # features in the customer workflow.
    if args.repair_whistles is None:
        args.repair_whistles = False
    if args.shape_transients is None:
        args.shape_transients = False
    if args.collapse_swish is None:
        args.collapse_swish = False

    _prompt_artifact_toggles(args, config)
    if args.stem_cache is not None and not args.stem_cache:
        config.stem_config.stem_cache_dir = None
    if args.detect_whistles is not None:
        config.repair_whistles.detect_stationary_whistles = args.detect_whistles
    if args.repair_whistles is not None:
        config.repair_whistles.enabled = args.repair_whistles
    if args.shape_transients is not None:
        config.shape_transients.enabled = args.shape_transients
    if args.collapse_swish is not None:
        config.collapse_swish.enabled = args.collapse_swish

    for name, enabled in [
        ("repair_whistles", config.repair_whistles.enabled),
        ("shape_transients", config.shape_transients.enabled),
        ("collapse_swish", config.collapse_swish.enabled),
    ]:
        if enabled:
            print(f"{name} enabled via CLI toggle")

    input_path = Path(args.input)
    if not input_path.exists():
        # STORY-024 TC-024-03: failure screen names the real blocking condition.
        print(render_error(FileNotFoundError(f"input file does not exist: {args.input}")), file=sys.stderr)
        return 1

    if args.dry_run:
        if args.progress:
            reporter.emit(1, "Dry run validation", "configuration valid", total=6)
        print("DRY RUN: configuration validated; skipping mastering pipeline execution.")
        return 0

    try:
        if args.progress:
            reporter.emit(1, "Running mastering pipeline", "load + validate", total=6)
        result = master(args.input, output_dir=args.output_dir, config=config, reporter=reporter)
    except MasteringError as exc:
        print(render_error(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive top-level guard
        print(render_error(exc), file=sys.stderr)
        return 1

    if args.progress:
        reporter.emit(6, "Ready for Release", "reports + final summary", total=6)

    if not args.no_report:
        output_path = Path(result.output_path)
        report_md_path = output_path.with_name(output_path.stem + "_report.md")
        report_json_path = output_path.with_name(output_path.stem + "_report.json")
        report_md_path.write_text(render_markdown(result.report), encoding="utf-8")
        report_json_path.write_text(render_json(result.report), encoding="utf-8")
        print(f"Report written to: {report_md_path}")
    else:
        print("Report generation skipped (--no-report).")

    print(f"Mastered WAV written to: {result.output_path}")
    if args.progress:
        reporter.emit(6, "Ready for Release", "complete", total=6)
    summary_text = (
        f"Achieved: {result.report.solver['achieved_lufs']:.2f} LUFS, "
        f"{result.report.solver['achieved_true_peak_dbtp']:.2f} dBTP, "
        f"DR{result.report.solver['achieved_dr']:.0f}"
    )
    print(summary_text)

    # STORY-024 TC-024-04: the summary reflects verified result state only.
    print(render_summary(result))

    review = getattr(result, "quality_review", None)
    decision = None
    if review is not None:
        decision = str(getattr(review, "decision", "unknown")).upper()
        summary = getattr(review, "summary", "")
        print(f"Quality review: {decision} - {summary}")

    if args.json_summary:
        print("Summary:")
        json_summary = _render_summary_json(result)
        if review is not None:
            review_payload = {
                "decision": str(getattr(review, "decision", "unknown")).upper(),
                "summary": getattr(review, "summary", ""),
            }
            json_summary = json_summary[:-1] + ', "quality_review": ' + json.dumps(review_payload, indent=2) + "}"
        print(json_summary)

    # A rejected quality review is a completed run, not a crash -- exit 2 so
    # callers (e.g. master_track.bat) can tell it apart from exit 1 failures.
    if decision == "REJECT":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
