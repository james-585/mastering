# Suno Mastering

A stem-aware mastering pipeline purpose-built for AI-generated (Suno) tracks. It separates a mix into stems, repairs generation-specific artifacts (transient smearing, digital haze, spurious whistles, phase swish) at the stem level, then re-integrates, EQs, and loudness-normalizes to a streaming-safe LUFS/true-peak target — producing a mastered WAV plus a quality report.

Unlike generic "AI mastering" services, this doesn't pretend to fix everything: it works from a documented model of what's actually fixable from a stereo mixdown (see [docs/design-history/STORY-001/architecture.md](docs/design-history/STORY-001/architecture.md)) and reports honestly when it can't.

## Requirements

- Python 3.10+ (developed and tested on 3.14)
- Windows (the packaged `.exe` and `.bat` launchers are Windows-specific; the Python pipeline itself has no Windows-only dependencies)
- ~2 GB free disk for the PyTorch/Demucs stem-separation stack

## Install

**Easiest — no Python needed:** build (or download, if a release is provided) the standalone folder and run the `.exe` directly. See [packaging](packaging) for how to build it yourself.

**From source:**

```bash
pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
pip install -e ".[test]"
```

The first line installs the CPU-only PyTorch build — installing `torch` straight from PyPI via `requirements.txt` alone pulls a much larger CUDA-bundled wheel you don't need for this project.

## Usage

```bash
python -m suno_mastering path/to/track.wav --output-dir out/
```

Or use the drag-and-drop launchers from the repo root:

- **`master_track.bat`** — drag a WAV onto it (or double-click) to master from the command line.
- **`master_track_ui.bat`** — double-click to open a local browser UI for customising every mastering setting before running.

Stem separation (Demucs) needs a Hugging Face access token the first time it downloads model weights — both the CLI and the web UI prompt for this.

## Repo layout

- Package source: [src/suno_mastering](src/suno_mastering) — start here for any product work.
- Tests: [tests](tests)
- Design history (requirements/architecture/defect records the package was built against): [docs/design-history](docs/design-history)
- Reference audio fixtures (local-only, see below): [Reference Tracks](Reference%20Tracks)
- Packaging (PyInstaller build): [packaging](packaging)
- Historical experimental C++ scaffolding (not the active product path): [legacy](legacy)

## Reference Tracks

`Reference Tracks/` holds commercial audio  used as real-world test fixtures. These `.wav` files are never committed to this repo (`.gitignore` excludes all `*.wav`) and are not bundled into the packaged `.exe` — only you having a personal, legally-obtained copy of a track locally makes those files present.

## Development

1. Work in [src/suno_mastering](src/suno_mastering); [docs/design-history](docs/design-history) documents the requirements/architecture/defects behind each part of it.
2. Run the test suite from the repo root: `pytest -m "not slow" -n auto` (matches CI exactly).
3. The historical C++/CMake scaffolding under [legacy](legacy) is experimental, not the active product strategy — see [.claude/docs/CLAUDE.md](.claude/docs/CLAUDE.md).
4. Keep generated build/test scratch output out of the source tree where possible.

## License

[MIT](LICENSE) — see the LICENSE file. Note this covers the code in this repository only: it does not extend to any commercial reference audio you place in `Reference Tracks/` (see above) or to the third-party dependencies pulled in via `requirements.txt`, each of which keeps its own license.
