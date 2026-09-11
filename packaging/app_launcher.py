"""PyInstaller entry point for the packaged app.

Running this directly from source (``python packaging/app_launcher.py``)
also works -- it puts the suno_mastering package on sys.path first, exactly
like master_track_ui.bat's PYTHONPATH does, so this script behaves the same
whether frozen or not.
"""
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    _impl = Path(__file__).resolve().parent.parent / "stories" / "STORY-001" / "implementation"
    if str(_impl) not in sys.path:
        sys.path.insert(0, str(_impl))

from suno_mastering.webui import run  # noqa: E402

if __name__ == "__main__":
    run()
