# Project layout guide

This repository contains multiple kinds of content. The goal is to make the active developer path clear without hiding the design history.

## Source of truth

- [stories](../stories): story archive, architecture, requirements, and implementation work
- [stories/STORY-001/implementation](../stories/STORY-001/implementation): current active Python implementation area
- [Reference Tracks](../Reference%20Tracks): reference audio and measurement reports used for validation

## Historical / experimental

- [CMakeLists.txt](../CMakeLists.txt): legacy CMake scaffolding
- [src_cpp](../src_cpp): historical C++ DSP experimentation
- older build folders at the repo root: [build](../build), [build-ninja](../build-ninja), [build-vs2026](../build-vs2026)

These artifacts are not the active product shape and should be treated as historical or generated context unless a specific story explicitly reactivates them.

## Generated / temporary output

The following areas are for local experimentation and should not be treated as primary code:

- [tmp](../tmp)
- [tmp_e2e_run](../tmp_e2e_run)
- [tmp_ref_report](../tmp_ref_report)
- [test_runs](../test_runs)

These folders are useful for debugging and verification, but they should not be the main place a contributor expects to find the source tree.

## Root-level intent

The repo root should remain a navigation layer and project entry point, not a catch-all for experiments. Keep only documents, metadata, and short-lived launch scripts here.

## Working rule for contributors

1. Start in [stories](../stories).
2. Use [stories/STORY-001/implementation](../stories/STORY-001/implementation) for active product work.
3. Leave generated outputs in temporary directories or ignore them in the source tree.
4. Treat C++ and CMake directories as historical scaffolding unless a documented story requires them.
