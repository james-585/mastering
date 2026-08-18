# Suno Mastering

This repository is a local, Python-first mastering workflow for Suno-generated audio. The active product direction is the stem-aware, CLI-oriented pipeline defined in the project documentation and story artifacts under [stories](stories).

## Active product path

The current active implementation lives under:

- [stories/STORY-001/implementation](stories/STORY-001/implementation)

This is the codebase to open first when working on the product itself.

## Repo layout

The repository intentionally mixes a few different categories:

- Source and historical workflow docs: [stories](stories)
- Reference material: [Reference Tracks](Reference%20Tracks)
- Root-level project entry points and metadata: this folder
- Generated build and temporary output: [build](build), [build-ninja](build-ninja), [build-vs2026](build-vs2026), [tmp](tmp), [tmp_e2e_run](tmp_e2e_run), [test_runs](test_runs)
- Historical experimental C++ scaffolding: [CMakeLists.txt](CMakeLists.txt), [src_cpp](src_cpp)

## Important rule

The historical C++ and CMake scaffolding is not the active product strategy. The project guidance in [.claude/docs/CLAUDE.md](.claude/docs/CLAUDE.md) explicitly treats that work as legacy/experimental and keeps the active product in the Python-first story pipeline.

## Expected developer flow

1. Start with the story docs in [stories](stories).
2. Work in the active implementation under [stories/STORY-001/implementation](stories/STORY-001/implementation).
3. Keep generated build/test scratch output out of the source tree when possible.
4. Treat the root directory as the project entry point, not as a dumping ground for experiments.

## Common commands

- Run the project tests from the repo root using the configured pytest path setup.
- Use the story implementation directories for targeted work and verification.

## Notes

This repository is still in flux while story-based work is being completed. The layout is intentionally organized around the active product, the historical story archive, and the generated/temporary artifacts that support local debugging and experimentation.
