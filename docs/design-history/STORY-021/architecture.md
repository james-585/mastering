# STORY-021 — Architecture: GPU acceleration and model caching

## Pipeline placement
Insert around Demucs model loading and inference so that device selection and model reuse happen before the actual stem extraction work begins.

## Business analyst confirmation

- Story intent: provide a local-only Demucs execution layer that prefers CUDA or MPS when available and reuses a cached model instance without altering the mastering DSP path.
- Runtime contract: resolve a device once per process, reuse a model only for an identical model/device/config signature, and report fallback behavior explicitly in logs and CLI-visible output.
- Acceptance criteria: CUDA is preferred when present; MPS is used when CUDA is unavailable; CPU is used only as an explicit fallback; cache hits occur only for equivalent configuration; dependency or backend failures are not hidden.
- Scope limit: no mastering signal changes, no new DSP algorithmic behavior, no cloud execution, and no GUI handling. This is an optimization boundary only.
- Ambiguity check: none material remained after requirements review. The story remains strictly a runtime optimization and does not drift into non-local or algorithmic signal changes.

## Design decisions
- The execution layer will be singleton-based to avoid redundant model instantiation.
- Device selection happens once per process and is cached with a config fingerprint.
- CPU fallback is required to maintain a reliable local-only workflow even when hardware support is partial.
- Any backend failure must be preserved in the runtime report so the fallback path remains auditable and not silent.

## Module boundaries
- Module: `demucs_runtime.py`
- Public API:
  - `resolve_device() -> str`
  - `get_or_create_model(model_name, device, config) -> object`
  - `run_demucs_inference(...) -> StemBundle`
- Helper functions:
  - `_detect_cuda()`
  - `_detect_mps()`
  - `_cache_key()`
  - `_safe_fallback()`

## Data contract
- Each model cache entry must include model name, device, configuration fingerprint, and runtime state.
- If a backend fails, the system must preserve the original exception context and log the fallback path.
- Output still conforms to the same stem bundle contract used elsewhere in the project.

## Library choices
- `torch` device selection if available
- `numpy` for signal validation
- `demucs` runtime for inference

## Implementation constraints
- No silent fallback without a logged report.
- No model reuse across incompatible configuration hashes.
- CPU fallback must remain valid and deterministic.
- The runtime must preserve exact error context when CUDA/MPS are unavailable or fail during initialization.

## Gate 1 review (mastering engineer)

**Verdict:** PASS-ON-SCOPE

- The device-selection flow is correctly limited to runtime orchestration around Demucs loading and inference; it does not touch the mastering DSP path or alter any signal processing semantics.
- The singleton cache keyed by model name, device, and config fingerprint is the correct way to avoid redundant model instantiation without cross-device or cross-config leakage.
- CPU fallback is handled as an explicit, report-visible path rather than a hidden hardware choice, which matches the project’s local-only and no-silent-fallback guardrails.
- The reported reason chain remains auditable and reproducible, which is essential for local developer workstations where CUDA/MPS availability varies by machine.
- No blocker was identified for the story as specified; this architecture is acceptable to proceed into implementation.

## Review disposition (mastering engineer)
- Accepted as-is: the runtime optimization remains strictly outside the mastering algorithm and does not change signal behavior.
- Accepted as-is: CUDA/MPS selection is a deterministic preference order that remains safe across local hardware variations.
- Accepted as-is: the model cache is keyed on the exact model/device/config signature to avoid reuse across incompatible settings.
- Accepted as-is: CPU fallback is explicit and report-visible, and backend errors are retained alongside the fallback reason.
- Action item: keep the runtime status and fallback reason visible in the CLI or report payload for each execution path.
- Action item: only treat the cache as reusable for identical effective configuration; any config mismatch must generate a fresh model instance.

## Required production contract: runtime ownership

When implemented, `io/stem_separation.py` is the production orchestration boundary. It owns
optional dependency loading, deterministic device selection, device-bound model
caching, one-shot backend retry, inference, and runtime metadata. Story-local
prototype modules are not imported by the active CLI.

The separation API accepts the complete `StemConfig` plus optional injected
`torch_module`, `model_loader`, and `apply_model_fn` dependencies for contract
tests. When an injected dependency is absent, the production dependency loader
supplies it or raises the existing actionable `DependencyError` with original
context.

Device order is CUDA, MPS, CPU. `StemConfig.allow_device_fallback` defaults to
`True`; strict reproducibility runs set it to `False`. If fallback is allowed and
accelerator model loading or inference fails,
the original exception type/message is logged and the original input is retried
on CPU exactly once. Invalid configuration, malformed output, semantic mapping,
and non-finite stem failures are contract errors and never trigger backend
fallback. A CPU failure preserves both failure contexts and fails the requested
stem workflow rather than silently switching to stereo mastering.

Fallback preserves the validated stem-bundle contract, not identical audio.
Metadata distinguishes requested and final device and records the fallback point,
reason, deterministic settings, effective profile, and dependency/model versions.
With fallback disabled, an accelerator failure is reported without changing device.

The lock-protected cache uses schema `demucs-model-cache-v1`. Its identity
contains model name/revision, weights identity, selected device and placement,
dtype/precision, construction options, compile mode/options, dependency versions,
and every other model-mutating load option. Per-run shifts, overlap, segment duration, and profile
version are supplied on every inference call and are excluded from cache identity.
Failed loads are not cached, and CPU fallback uses a separate cache entry.

Each run produces one metadata record containing model, device, fallback reason,
backend error context, cache hit/miss, effective profile, canonical stem names,
and available Demucs/Torch versions. The stem result carries this record unchanged
for CLI and report rendering; those layers do not independently infer runtime
state.

Focused fake-based tests cover device selection, cache identity, exact inference
arguments, accelerator-to-CPU retry, no retry for malformed output, dependency
diagnostics, and exception preservation. Real hardware performance remains a
release-environment check.

## Gate 1 follow-up disposition

- Accepted with revision: device fallback is an alternate, provenance-visible
  execution that may change stem audio; it is never described as signal-neutral.
- Changed: fallback policy is explicit and a strict no-fallback mode is available.
- Changed: cache identity is schema-versioned and exhaustive for model-mutating
  state; run-only controls remain outside it only when supplied per call.
- Changed: the runtime section is a required production contract until implemented.

## Revision history
- 2026-08-17: Initial architecture for GPU and cache support.
- 2026-08-17: Added business-analyst confirmation, mastering-review gate findings, and explicit review disposition for the runtime-only hardware and cache design.
- 2026-08-17: Defined active separation ownership, cache identity, explicit one-shot CPU fallback, injected test boundaries, and shared runtime metadata.
- 2026-08-17: Dispositioned mastering review with explicit fallback policy, strict mode, output-provenance limits, exhaustive cache identity, and required-work labeling.
