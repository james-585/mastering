"""Repo-root / bundle-root resolution shared by every module that currently
does `Path(__file__).resolve().parents[4]` to find the repo root -- config.py
(targets.json), cli.py/pipeline.py/stem_integration.py (sibling
stories/STORY-0XX/implementation folders on sys.path), webui.py (previously
the .env token file), and __init__.py (suno_dsp build directories).

In a normal source checkout, "repo root" is that parents[4] directory as
before. Frozen into a PyInstaller bundle, __file__ lives inside a temporary
extraction directory (onefile) or the app's install folder (onedir) that has
nothing to do with the source tree -- so bundle_root() switches to
sys._MEIPASS (PyInstaller's own resource root) instead. The PyInstaller spec
is responsible for placing targets.json, the story implementation folders,
etc. at the same *relative* layout inside the bundle so every existing
`bundle_root() / "stories" / "STORY-0XX" / "implementation"` expression keeps
resolving correctly without each call site needing to know it's frozen.

Writable state (currently just the HF token) is different: a frozen app's
own folder may be read-only (e.g. Program Files) or, for a onefile build, is
a fresh temp extraction wiped on every launch. user_data_dir() gives that
state a stable, writable, per-user home instead.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def frozen_root() -> Path:
    """PyInstaller's own extraction root -- only meaningful when is_frozen()
    is True. Split out from bundle_root() so call sites that need to stay
    testable via `monkeypatch.setattr(some_module, "__file__", ...)` (e.g.
    __init__.py's _ensure_suno_dsp_on_path, see test_cli_progress.py) can
    keep computing their own non-frozen repo root from their own __file__
    while still branching to this for the frozen case."""
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))


def bundle_root() -> Path:
    """Read-only resource root: the repo root in a normal checkout, or
    PyInstaller's extraction root when frozen."""
    if is_frozen():
        return frozen_root()
    return Path(__file__).resolve().parents[4]


def user_data_dir() -> Path:
    """Writable per-user directory for state that must survive across runs
    (currently: the saved Hugging Face token). Uses the repo root's .env in
    a normal checkout (matches existing dev-mode behaviour and
    master_track.bat's own .env loading); uses %LOCALAPPDATA% when frozen,
    since the install location may not be writable and a onefile build's own
    directory is a throwaway temp folder."""
    if is_frozen():
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        d = base / "SunoMastering"
        d.mkdir(parents=True, exist_ok=True)
        return d
    return Path(__file__).resolve().parents[4]
