# STORY-021 — Requirements: GPU acceleration and singleton model caching

## Contract
Consumes: the Demucs separation runtime and device capability information.
Produces: a hardware-aware execution layer that prefers CUDA/MPS when available while falling back gracefully to CPU and reusing cached models.
Consumed by: the optional Demucs stage before stem processing.

## Product requirements
1. Detect and select the best available execution device: CUDA, then MPS, then CPU.
2. Cache model instances per model name, device, and config version to prevent redundant loading.
3. Ensure CPU fallback is explicit and graceful when the preferred backend is unavailable.
4. Provide a clear report of model cache status and device selection.
5. Fail cleanly with clear diagnostics if dependencies are missing or the model cannot initialize.

## Active workflow integration contract
- Model cache identity includes only model-loading state: model name, selected device, and model-load configuration.
- Per-run inference controls (`shifts`, `overlap`, and `segment_seconds`) are supplied on every inference call and must not become stale through model reuse.
- Every run reports model name, selected device, fallback reason, cache hit or miss, effective inference profile, and available Demucs/Torch versions.
- Backend initialization or inference failures preserve the original exception context; any CPU fallback is explicit and logged.

## Acceptance criteria
- Given a CUDA-capable environment, when Demucs initializes, then the pipeline selects CUDA when available.
- Given CUDA is unavailable, when the runtime executes, then it falls back to MPS or CPU without crashing.
- Given the same model and config are reused, when the second call executes, then the cache returns the existing instance instead of reloading.
- Given an initialization failure occurs, when the pipeline diagnoses it, then the user receives a clear remediation message and the root cause is preserved.

## Validation plan
- Run device-selection tests for CUDA, MPS, and CPU-only environments.
- Validate cache hit behavior and stale-key rejection.
- Confirm the runtime emits a reliable explanatory report on the chosen device and fallback path.

## Revision history
- 2026-08-17: Initial requirements artifact for GPU and cache support.
- 2026-08-17: Defined model-cache identity separately from per-run inference controls and required live workflow reporting.
