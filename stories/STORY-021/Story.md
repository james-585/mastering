# STORY-021 — GPU acceleration and singleton model caching

## User story
As a local mastering operator, I want Demucs to use the fastest available hardware while reusing a cached model instance so that the pipeline is faster without repeatedly reinitializing large models.

## Scope
- In scope:
  - CUDA/MPS detection
  - CPU fallback
  - singleton model cache
  - runtime reporting
- Out of scope:
  - cloud execution
  - GUI-based model management
  - non-local hardware acceleration

## Contract
The system must resolve an execution device deterministically, reuse a cached model when the config matches, and present clear fallback behavior when the preferred backend is unavailable or fails.
