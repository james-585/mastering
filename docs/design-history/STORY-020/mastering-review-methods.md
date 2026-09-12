# STORY-020 — Mastering-Engineer Gate 1 Review (Methods)

## Finding 1

- **Severity:** Blocker
- **What is proposed:** Treat `shifts=1`, `overlap=0.25`, and `segment_seconds=None` as an upstream-compatible, stable, reproducible live default profile.
- **Why it fails, or under what conditions:** These are physically and musically reasonable compatibility defaults: one shift avoids the large runtime multiplication of multi-shift inference, 25% overlap is a normal upstream split-inference overlap, and `segment_seconds=None` correctly leaves model-specific segmentation to Demucs rather than promoting the synthetic 4096-sample harness value. They are not, however, a deterministic-output contract. Demucs shift equivariance uses a random time shift when `shifts` is nonzero, so repeated runs can differ unless the relevant RNG state is controlled and recorded. Accelerator kernels can add further variation. `segment_seconds=None` also inherits the loaded model/version default, so the effective segment is not stable across dependency or model revisions merely because the local profile string is stable. The proposed profile is safe as a compatibility baseline, but the architecture's reproducibility claim is stronger than the method supports.
- **What to do instead:** Approve these values only as an untuned compatibility profile. Define reproducibility explicitly as either bit/deterministic output or measured tolerance. For deterministic claims, control and record all relevant RNG state and deterministic-backend settings, and report the resolved model segment/default plus Demucs, Torch, model, device, and profile versions. If deterministic execution cannot be guaranteed, state that repeated output is expected to remain within a measured programme-material tolerance rather than identical.

## Finding 2

- **Severity:** Blocker
- **What is proposed:** The new active CLI section describes `StemConfig` ownership, CLI overrides, exact `apply_model` arguments, and per-run profile logging as the production path.
- **Why it fails, or under what conditions:** The current active package does not contain that path. Its `StemConfig` has no shifts, overlap, segment duration, or profile version; the CLI exposes only the older three four-stem model choices; and active inference calls `apply_model` without the proposed controls while forcing CPU. Consequently the revised architecture is a target design, not a description of current active behavior, and none of the live pass-through or provenance guarantees presently exists.
- **What to do instead:** Architect must label this section as required work rather than implemented active ownership until the production path matches it. Keep promotion of any quality-optimized default blocked until real Demucs runs on representative drums, vocals, synth-heavy, and mixed programme material measure separation artifacts, runtime, memory, reconstruction residual, and repeat-run spread.

## Verdict

**BLOCKED.** The three values are acceptable as compatibility defaults and are not inherently musically dangerous, but the architecture must narrow its reproducibility claim and acknowledge that the described active wiring is not present in the current production path.

## Second Gate 1 review

**APPROVED FOR IMPLEMENTATION: WORKFLOW WIRING ONLY. NOT YET APPROVED AS A TUNED, CROSS-DEVICE-EQUIVALENT, OR MUSICALLY VALIDATED DEMUCS RELEASE PATH.**

The revised architecture treats the defaults as an untuned compatibility
profile, records complete run provenance, and makes no deterministic-output or
performance claim. Real Demucs evidence remains required before promoting an
optimized profile or claiming repeatability, artifact, runtime, or memory results.
There is no remaining blocker to implementing the specified wiring contract.
