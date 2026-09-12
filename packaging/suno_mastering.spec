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

from PyInstaller.utils.hooks import collect_data_files

REPO_ROOT = Path(SPECPATH).resolve().parent
IMPL = REPO_ROOT / "src"

# suno_mastering is a single installable package under src/ (2026-09-12
# restructure). PyInstaller's normal Analysis() import scan picks up every
# submodule -- stem_stages/, quality_review/, tools/ included -- the same
# as any other package; no separate story-folder mirroring into the bundle
# is needed.

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
    name="SunoMastering",
)
