# Project layout guide

This repository contains one installable Python package plus its supporting build, docs, and history.

## Source of truth

- [src/suno_mastering](../src/suno_mastering): the installable package — pipeline, stem-level repairs, quality review, reporting, and the `tools/` subpackage (orchestration, Demucs tuning/runtime helpers, release-candidate audits).
- [tests](../tests): the pytest suite, one flat directory (`tests/story025_validation/` is its own subfolder only because it carries a dedicated `conftest.py`).
- [scripts](../scripts): standalone offline utilities that are not part of the runtime pipeline (e.g. `build_reference_curve.py`).
- [Reference Tracks](../Reference%20Tracks): reference audio and measurement reports used for validation (the `.wav` files themselves are local-only, not committed — see the README).

## History

- [docs/design-history](design-history): the original story-by-story requirements, architecture, and defect-tracking record this package was built against. Read-only historical record — do not edit path references inside it to match the current layout.

## Historical / experimental

- [legacy/CMakeLists.txt](../legacy/CMakeLists.txt) and [legacy/src_cpp](../legacy/src_cpp): historical C++ DSP experimentation (a `suno_dsp` pybind11 extension), not part of the active product path.
- Generated build folders at the repo root ([build](../build), [build-ninja](../build-ninja), [build-vs2026](../build-vs2026), [dist](../dist)): build output, not source.

## Generated / temporary output

`tmp/`, `tmp_e2e_run/`, `tmp_ref_report/`, `test_runs/`, `artifacts/` hold local experimentation and generated reports — useful for debugging, not the source tree.

## Root-level intent

The repo root stays a navigation layer and entry point (`pyproject.toml`, `README.md`, `LICENSE`, the `.bat` launchers) — not a catch-all for experiments.

## Working rule for contributors

1. Install with `pip install -e ".[test]"` from the repo root.
2. Source lives in [src/suno_mastering](../src/suno_mastering); tests in [tests](../tests).
3. Consult [docs/design-history](design-history) for the reasoning behind a given piece of behaviour, but don't treat it as a place to make new changes.
4. Treat `legacy/` as historical scaffolding unless a documented need reactivates it.
