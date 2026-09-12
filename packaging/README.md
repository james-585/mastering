# Packaging

Builds a standalone, no-install version of the app using PyInstaller.

## Build

```
packaging\build.bat
```

(or directly: `.venv\Scripts\pyinstaller.exe packaging\suno_mastering.spec`)

Takes 2-3 minutes. Output is `dist\SunoMastering\` — an entire self-contained
folder (~550 MB, mostly `torch`). Zip that folder to hand it to someone; they
unzip it and double-click `SunoMastering.exe` inside. No Python install, no
`pip install`, nothing else needed. It opens the same local web UI
`master_track_ui.bat` does, in their default browser.

## What's bundled vs. not

- **Bundled**: the full Python + dependency environment (torch, demucs,
  scipy, numpy, soundfile), `targets.json`, the genre reference curve, and
  the `suno_mastering` package under `src/` (PyInstaller's Analysis() scan
  picks up every submodule automatically).
- **Not bundled**: Demucs's own model weights (~340 MB per model) — those
  still download from Hugging Face the first time stem separation is used,
  same as in dev mode. That's why the web UI's Hugging Face token box
  exists; a packaged user needs one token, entered once, same as a dev
  checkout needs `.env`.
- **Not bundled**: the `suno_dsp` C++ extension (whistle repair / transient
  shaping / swish collapse). It's built for a very specific Python ABI
  (`cp314-win_amd64` at time of writing) and isn't portable the way the rest
  of the stack is. The app already handles this gracefully: the diagnose
  panel checks whether `suno_dsp` is importable before suggesting those
  settings, so a packaged build without it just doesn't offer them rather
  than suggesting a setting that fails on submit. If you want those stages
  in a specific distributed build, build `suno_dsp` for that exact frozen
  Python's ABI and drop the resulting `.pyd` next to `SunoMastering.exe`
  (`_ensure_suno_dsp_on_path` in `__init__.py` also checks the app's own
  directory... currently it doesn't — extend the candidate list there if
  you need this).

## Why onedir, not onefile

`suno_mastering.spec` builds `COLLECT` (onedir), not a single `.exe`
(onefile). A onefile build re-extracts its entire ~550 MB payload to a fresh
temp directory on *every launch* — slow, and repeated heavy disk I/O across
a huge file tree is one of two things that coincided with this machine
freezing entirely during testing (see below). onedir extracts once, at
build time; launching is just running an .exe that's already on disk.

## A note on antivirus

Real-time antivirus scanning every file PyInstaller touches while it
analyzes/copies `torch`'s ~500 MB tree is a common, well-documented cause of
severe slowdowns or full system freezes on Windows. During development,
building with AVG's real-time protection active reliably froze the whole
machine (unrelated to Python 3.14 or this dependency set specifically —
`pip install`, Demucs inference, and PyInstaller's build all touch the same
huge file tree and can each trigger it under a scanner). Exclude the repo
folder (and `%LOCALAPPDATA%\Temp` if you build from a temp checkout) from
real-time scanning before building. This affects *building* the package, not
running the already-built `dist\SunoMastering\SunoMastering.exe` — that's a
normal, much lighter workload.

## Requirements.txt (resolved)

`requirements.txt` previously omitted `torch`/`demucs` (imported directly by
the stem-separation path) and `mutagen` (needed by the MP3-decode/provenance
path) despite the code depending on them, and had no `pytest-xdist` for CI.
All four are now declared and pinned, and `pip install -r requirements.txt`
installs cleanly on Python 3.14 (verified locally and in CI) — the earlier
concern about `numba` lacking a 3.14 wheel no longer applies with the
versions currently pinned. `torch` should still be installed from the
CPU-only wheel index first; see the comment at the top of
`requirements.txt`.
