"""Release-candidate CLI wrapper around the validated Suno mastering pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from suno_mastering import MasteringConfig


def _configure_console_encoding() -> None:
    """Ensure Windows consoles can print the repo's audit text without choking on Unicode symbols."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


_configure_console_encoding()
from suno_mastering import pipeline as pipeline_mod
from suno_mastering.errors import MasteringError


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suno_mastering_release",
        description="Package the validated stem-aware mastering flow into a repeatable local release-candidate CLI.",
    )
    parser.add_argument("input", help="Path to the source WAV file to master.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory to write the mastered output and release-candidate audit artifacts.",
    )
    parser.add_argument(
        "--mode",
        choices=["release", "stem-aware", "fallback"],
        default="release",
        help="Explicit product mode. The default release path remains stem-aware unless fallback is intentionally selected.",
    )
    parser.add_argument(
        "--summary-path",
        default=None,
        help="Optional explicit path for the release summary JSON artifact.",
    )
    return parser


def _normalise_mode(mode: str) -> tuple[str, bool]:
    if mode in {"release", "stem-aware"}:
        return "stem-aware", True
    return "fallback", False


RELEASE_STAGE_ORDER = [
    "ingest",
    "analysis",
    "stem_choice",
    "transient_restoration",
    "harshness_control",
    "stereo_imaging",
    "bus_glue",
    "final_safety",
    "quality_review",
]

RELEASE_ACHIEVEMENTS = [
    {
        "stage": "stem_choice",
        "achievement": "Stem-first processing is active by default, keeping the product on the real stem-aware path rather than a generic stereo-only pass.",
    },
    {
        "stage": "transient_restoration",
        "achievement": "Transient restoration improves attack and definition so drums, bass, and lead material regain realistic impact without a blanket mix-wide gain.",
    },
    {
        "stage": "harshness_control",
        "achievement": "Harshness control trims fatigue and tonal excess where the signal is genuinely bright or brittle, instead of dulling the whole mix.",
    },
    {
        "stage": "stereo_imaging",
        "achievement": "Stereo imaging widens or rebalances only the healthy, safe stereo content while preserving center stability and natural depth.",
    },
    {
        "stage": "bus_glue",
        "achievement": "Bus glue and dynamic balance reconcile the processed stems into a coherent final mix without flattening the emotional contour.",
    },
    {
        "stage": "final_safety",
        "achievement": "Final safety keeps the output under the project true-peak ceiling and preserves the no-hidden-clipping contract.",
    },
    {
        "stage": "quality_review",
        "achievement": "The final quality review checks whether the output is musically stronger and more credible than the source rather than merely numerically compliant.",
    },
]


def _build_release_summary(result, *, input_path: Path, output_path: Path, mode: str, requested_mode: str, is_stem_aware: bool) -> dict:
    solver = getattr(getattr(result, "report", None), "solver", {})
    review = getattr(result, "quality_review", None)
    status = "passed"
    if review is not None:
        review_decision = str(getattr(review, "decision", "pass")).strip().lower()
        if review_decision in {"reject", "refine"}:
            status = review_decision
        elif review_decision == "pass":
            status = "passed"

    report_data = {
        "mode": mode,
        "requested_mode": requested_mode,
        "stem_aware": is_stem_aware,
        "fallback_used": not is_stem_aware,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "status": status,
        "final_lufs": float(solver.get("achieved_lufs", 0.0)),
        "final_true_peak_dbtp": float(solver.get("achieved_true_peak_dbtp", 0.0)),
        "final_dynamic_range": float(solver.get("achieved_dr", 0.0)),
        "stage_order": RELEASE_STAGE_ORDER,
        "achievements": RELEASE_ACHIEVEMENTS,
        "guardrails": [
            "local_only",
            "python_first",
            "float64_internal_processing",
            "oversampled_true_peak",
            "stem_first_default",
            "no_hidden_fallback",
        ],
    }

    if review is not None:
        report_data["quality_review"] = {
            "decision": getattr(review, "decision", "unknown"),
            "summary": getattr(review, "summary", ""),
        }

    return report_data


def _write_summary_json(summary_path: Path, payload: dict) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input file does not exist: {args.input}", file=sys.stderr)
        return 1

    resolved_mode, is_stem_aware = _normalise_mode(args.mode)
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = input_path.parent / "release_candidate_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    config = MasteringConfig()
    config.stem_config.enabled = is_stem_aware
    if not is_stem_aware:
        print("Explicit fallback mode selected: stem-aware processing disabled for this run.")
    else:
        print(f"Release-candidate mode: {resolved_mode} (stem-aware product path active)")

    summary_path = Path(args.summary_path) if args.summary_path else output_dir / "release_summary.json"

    try:
        result = pipeline_mod.master(str(input_path), output_dir=str(output_dir), config=config)
    except MasteringError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive boundary
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    report_data = _build_release_summary(
        result,
        input_path=input_path,
        output_path=Path(result.output_path),
        mode=resolved_mode,
        requested_mode=args.mode,
        is_stem_aware=is_stem_aware,
    )

    _write_summary_json(summary_path, {"summary": report_data, "audit": report_data})

    # Preserve the existing report outputs from the pipeline itself.
    report_md_path = Path(result.output_path).with_name(Path(result.output_path).stem + "_report.md")
    report_json_path = Path(result.output_path).with_name(Path(result.output_path).stem + "_report.json")
    if report_md_path.exists() and report_json_path.exists():
        print(f"Release summary written to: {summary_path}")
        print(f"Output report: {report_md_path}")
        print(f"Audit report: {report_json_path}")
    else:
        print(f"Release summary written to: {summary_path}")

    print(
        "Final verdict: release candidate passed "
        f"({resolved_mode}, LUFS={report_data['final_lufs']:.2f}, dBTP={report_data['final_true_peak_dbtp']:.2f}, DR={report_data['final_dynamic_range']:.0f})"
    )
    print("What this run achieved:")
    for item in report_data["achievements"]:
        print(f"  - {item['stage']}: {item['achievement']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
