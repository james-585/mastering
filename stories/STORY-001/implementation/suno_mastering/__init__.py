"""suno_mastering: automated streaming-ready mastering for Suno-generated
WAV exports. See stories/STORY-001/{requirements,architecture}.md for the
full spec this package implements against.

Primary library API: suno_mastering.pipeline.master(input_path,
output_dir=None, config=None) -> MasteringResult.
"""
from __future__ import annotations

import sys
from pathlib import Path

from ._paths import frozen_root, is_frozen


def _ensure_suno_dsp_on_path() -> None:
    """Add repo-local build directories so the compiled suno_dsp extension is
    importable. In a frozen build these candidate directories simply won't
    exist (the extension isn't bundled -- see webui.py's diagnose gating),
    so this becomes a harmless no-op rather than needing separate handling.

    Computes its own non-frozen repo root from this module's own __file__
    (rather than delegating to _paths.bundle_root(), which uses _paths.py's
    __file__) so this stays testable via
    `monkeypatch.setattr(suno_mastering, "__file__", ...)` -- see
    test_cli_progress.py::test_suno_dsp_build_dir_is_added_to_python_path.
    """
    repo_root = frozen_root() if is_frozen() else Path(__file__).resolve().parents[4]
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
