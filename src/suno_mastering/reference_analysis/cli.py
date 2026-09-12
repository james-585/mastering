"""Thin argparse wrapper around pipeline.analyze_set() (STORY-002
architecture.md Section 11, "CLI vs. library API"):

    python -m suno_mastering.reference_analysis <reference_dir> \
        [--suno-export PATH] [--output-dir DIR] [--config PATH]

Mirrors suno_mastering/cli.py's pattern -- catches the errors.py exception
hierarchy at the top level, writes both renderings to disk.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from ..config import MasteringConfig
from ..errors import MasteringError
from ..report.reference_builder import build_reference_set_report
from ..report.reference_render import render_json, render_markdown
from .config import ReferenceAnalysisConfig
from .pipeline import analyze_set


def _load_config(config_path: str) -> ReferenceAnalysisConfig:
    with open(config_path, "r", encoding="utf-8") as fh:
        overrides = json.load(fh)
    mastering_overrides = overrides.pop("mastering", {})
    return ReferenceAnalysisConfig(mastering=MasteringConfig(**mastering_overrides), **overrides)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="suno_mastering.reference_analysis",
        description="Analyse a folder of reference tracks (and optionally a Suno export) and report measurements.",
    )
    parser.add_argument("reference_dir", help="Path to a folder of reference tracks (WAV/FLAC/MP3).")
    parser.add_argument("--suno-export", default=None, help="Optional path to a Suno-export WAV for side-by-side comparison (AC3).")
    parser.add_argument("--output-dir", default=None, help="Directory to write the report into (defaults to the reference folder).")
    parser.add_argument("--config", default=None, help="Path to a JSON file of ReferenceAnalysisConfig field overrides.")
    return parser


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config = _load_config(args.config) if args.config else ReferenceAnalysisConfig()

    try:
        result = analyze_set(args.reference_dir, suno_export_path=args.suno_export, config=config)
    except MasteringError as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    report = build_reference_set_report(result, config)

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.reference_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "reference_set_report.md"
    json_path = output_dir / "reference_set_report.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(render_json(report), encoding="utf-8")

    print(f"Reference set report written to: {md_path}")
    print(f"Machine-readable report written to: {json_path}")
    print(f"Tracks analyzed: {len(result.per_track)}, failures: {len(result.failures)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
