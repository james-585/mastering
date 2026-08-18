# STORY-021 — Mastering-Engineer Gate 1 Review (Methods)

## Finding 1

- **Severity:** Blocker
- **What is proposed:** On accelerator model-load or inference failure, retry the original input once on CPU while treating device selection and fallback as runtime-only behavior that does not alter signal-processing semantics.
- **Why it fails, or under what conditions:** CPU and accelerator execution of the same Demucs model are not guaranteed to produce identical stems. Floating-point evaluation order, backend kernels, device precision behavior, and nondeterministic operations can change low-level output and occasionally audible separation artifacts. A run that falls back therefore has different execution semantics and reproducibility provenance even when the model and inference controls are unchanged. Logging the fallback makes the change visible but does not make the CPU result equivalent to the failed accelerator result or to a successful accelerator run.
- **What to do instead:** Architect must state that fallback preserves the stem-bundle contract, not identical audio. Include requested device, final device, deterministic settings, dependency/model versions, fallback point and reason, and effective inference profile in output provenance. Define a strict reproducibility mode that fails instead of changing device, or require an explicit policy permitting CPU retry. Validate CPU-versus-accelerator output on real programme material with reconstruction, null/difference, and listening-oriented artifact criteria before describing fallback as musically transparent.

## Finding 2

- **Severity:** Concern
- **What is proposed:** Cache models by model-loading state while supplying shifts, overlap, and segment duration on every inference call.
- **Why it fails, or under what conditions:** This ownership split is sound only if every excluded setting is genuinely run-only. Any option that changes model construction, model state, precision, compile mode, or device placement must be in the cache key. Otherwise an apparently valid cache hit can change output or fail differently from a fresh load.
- **What to do instead:** Define the model-load options exhaustively and version the cache-key schema. Keep run controls out of the key only where the active Demucs API applies them without mutating cached model state. Record the final cache identity in run metadata.

## Finding 3

- **Severity:** Blocker
- **What is proposed:** `io/stem_separation.py` is described as already owning device selection, device-bound caching, one-shot retry, injected runtime dependencies, and shared metadata.
- **Why it fails, or under what conditions:** The current active separation module loads a model on every call, forces `device="cpu"`, has no accelerator detection or retry, and returns no runtime provenance. The architecture therefore describes a future implementation as current active behavior. Feasibility is reasonable, but the stated guarantees cannot be reviewed as present or relied upon by downstream reporting.
- **What to do instead:** Recast the active-runtime section as the required production contract until that ownership exists. Preserve the rule that malformed output, invalid source mapping, non-finite stems, and bundle-contract failures must never be reclassified as backend failures eligible for CPU retry.

## Verdict

**BLOCKED.** Explicit CPU fallback is operationally feasible, but it can change output and reproducibility. It is acceptable only as a provenance-visible alternate execution with an explicit fallback policy, not as signal-neutral runtime plumbing.

## Second Gate 1 review

**APPROVED FOR IMPLEMENTATION: WORKFLOW WIRING ONLY. NOT YET APPROVED AS A TUNED, CROSS-DEVICE-EQUIVALENT, OR MUSICALLY VALIDATED DEMUCS RELEASE PATH.**

The revised architecture makes fallback policy explicit, offers strict
no-fallback operation, records requested/final device provenance, and versions
an exhaustive model-cache identity. CPU/accelerator musical equivalence is not
established and must not be claimed without real-hardware evidence. There is no
remaining blocker to implementing the specified wiring contract.
