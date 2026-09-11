# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the packaged Suno Mastering app.

Build with (from the repo root, inside the project .venv):

    .venv\\Scripts\\pyinstaller.exe packaging\\suno_mastering.spec

Produces a onedir build under dist/SunoMastering/ -- zip that whole folder
to distribute it. SunoMastering.exe inside it launches the same local web UI
webui.py serves in dev mode; opens the browser automatically.

Deliberately onedir, not onefile: onefile re-extracts the ~1 GB torch/demucs
payload into a fresh temp directory on every launch, which is both slow and
was one of two things that coincided with this machine locking up during
testing (see packaging notes). onedir extracts once, at build time.
"""
from pathlib import Path

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_data_files

REPO_ROOT = Path(SPECPATH).resolve().parent
IMPL = REPO_ROOT / "stories" / "STORY-001" / "implementation"

# Sibling story-implementation folders suno_mastering imports from at
# runtime (pipeline.py, stem_integration.py, cli.py -- see _paths.py's
# docstring). Mirrored into the bundle at the same relative path so the
# existing `bundle_root() / "stories" / "STORY-0XX" / "implementation"`
# sys.path.insert calls keep resolving unchanged.
RUNTIME_STORY_DIRS = [
    "STORY-011", "STORY-012", "STORY-013", "STORY-014", "STORY-015",
    "STORY-019", "STORY-023", "STORY-024", "STORY-025",
]
_TREE_EXCLUDES = ["__pycache__", "*.pyc", "tests", "test_*.py"]

story_trees = []
for _story in RUNTIME_STORY_DIRS:
    _src = REPO_ROOT / "stories" / _story / "implementation"
    if _src.exists():
        story_trees.append(
            Tree(str(_src), prefix=f"stories/{_story}/implementation", excludes=_TREE_EXCLUDES)
        )

datas = [
    (str(REPO_ROOT / "targets.json"), "."),
    (
        str(IMPL / "suno_mastering" / "reference" / "progressive_house_124bpm.json"),
        "suno_mastering/reference",
    ),
]
# demucs.pretrained reads these remote/*.yaml files at runtime to know which
# Hugging Face repo each model name maps to -- without them bundled, stem
# separation fails to find any model.
datas += collect_data_files("demucs")

a = Analysis(
    [str(REPO_ROOT / "packaging" / "app_launcher.py")],
    pathex=[str(IMPL)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SunoMastering",
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    *story_trees,
    name="SunoMastering",
)
