"""suno_mastering: automated streaming-ready mastering for Suno-generated
WAV exports. See stories/STORY-001/{requirements,architecture}.md for the
full spec this package implements against.

Primary library API: suno_mastering.pipeline.master(input_path,
output_dir=None, config=None) -> MasteringResult.
"""
from __future__ import annotations

import sys
from pathlib import Path


def _ensure_suno_dsp_on_path() -> None:
    """Add repo-local build directories so the compiled suno_dsp extension is importable."""
    repo_root = Path(__file__).resolve().parents[4]
    candidate_dirs = [
        repo_root / "artifacts" / "build" / "build" / "Release",
        repo_root / "artifacts" / "build" / "build" / "Debug",
        repo_root / "build" / "Release",
        repo_root / "build" / "Debug",
        repo_root / "build-vs2026" / "Release",
        repo_root / "build-vs2026" / "Debug",
        repo_root / "build-ninja" / "Release",
        repo_root / "build-ninja" / "Debug",
        repo_root / "build",
        repo_root / "build-vs2026",
        repo_root / "build-ninja",
    ]
    for candidate in candidate_dirs:
        if candidate.exists() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))


_ensure_suno_dsp_on_path()

from .config import MasteringConfig
from .pipeline import MasteringResult, master

__all__ = ["master", "MasteringResult", "MasteringConfig"]

__version__ = "0.1.0"
