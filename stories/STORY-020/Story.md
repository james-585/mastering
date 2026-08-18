# STORY-020 — Demucs inference parameter optimization

## User story
As a mastering engineer, I want a benchmarked Demucs inference configuration so that I can reduce separation artifacts and phase instability without paying an unreasonable runtime or memory cost.

## Scope
- In scope:
  - shifts tuning
  - overlap tuning
  - segment-size tuning
  - runtime and memory measurement
  - artifact detection and default selection
- Out of scope:
  - any changes to the mastering chain itself
  - stem content repair beyond the inference parameters

## Contract
The tool must expose a deterministic tuning harness that evaluates Demucs inference profiles and returns a measured recommendation with explicit cost/quality trade-offs for the current hardware.
