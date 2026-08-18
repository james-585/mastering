# STORY-021 — Test cases: GPU fallback and model caching

## TC-021-01: device selection
- Given a machine with CUDA available
- When the runtime resolves a device
- Then CUDA is selected as the preferred backend

## TC-021-02: MPS fallback
- Given CUDA is unavailable but MPS is available
- When initialization runs
- Then the system chooses MPS

## TC-021-03: CPU fallback
- Given no accelerator is available
- When inference starts
- Then execution continues on CPU with a logged fallback message

## TC-021-04: cache hit
- Given the same model and config are requested twice
- When the second run executes
- Then the same cached model instance is reused

## TC-021-05: invalid config mismatch
- Given a different config fingerprint
- When the cache lookup occurs
- Then the system does not reuse the wrong model instance

## TC-021-06: run-only controls reuse the model
- Given the same model, device, and model-load state with different shifts, overlap, or segment duration
- When both runs execute
- Then the model cache hits while each inference receives its own effective run controls

## TC-021-07: explicit one-shot CPU retry
- Given an accelerator inference failure and device fallback is enabled
- When separation runs
- Then CPU is attempted exactly once and requested/final device, fallback point, reason, and backend error are recorded

## TC-021-08: strict no-fallback mode
- Given an accelerator failure and device fallback is disabled
- When separation runs
- Then the original failure is preserved and CPU is not attempted

## TC-021-09: contract errors never fallback
- Given inference returns a malformed or non-finite stem bundle
- When output validation runs
- Then the run fails as a contract error without retrying another device

## TC-021-10: runtime provenance
- Given a successful run
- When metadata is emitted
- Then it includes cache schema/key/status, model, requested/final device, effective profile, deterministic settings, dependency versions, and source mapping

## Evidence limit
- Fake capability and inference objects prove orchestration contracts only.
- CPU/accelerator equivalence and real-hardware performance remain release checks.
