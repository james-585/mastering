## Contract
Consumes: AudioBuffer plus the artifact report produced by the artifact-detection stage (STORY-007 / detection pass), including flagged timestamps, frequency estimates, and confidence scores.
Produces: A restoration-decision report and optional per-flag action log describing whether a detected issue is non-recoverable, should be re-rendered, or may receive a tightly scoped, non-destructive mitigation. The default output is a report-only gate before the mastering chain.
Consumed by: The mastering pipeline before corrective EQ, and terminal review when human triage is required.

## Restated intent
This story exists to bridge artifact detection and the mastering chain by giving the pipeline a clear, auditable decision point after detection. The stage must prevent known Suno-generation defects from being treated as valid programme content. It is not a general-purpose restoration engine: the project domain explicitly forbids claiming to repair smeared transients or recover content above the generation band limit. The accepted design is a gate, triage, and logging stage that documents which issues are non-recoverable and which may receive only extremely narrow, explicitly approved mitigation.

## Acceptance criteria
1. Given a stereo or mono audio buffer and an artifact report, when the restoration gate runs, then it must append a structured decision record for each flagged artifact with timestamp, artifact type, confidence, and action recommendation.
2. Given a `STATIONARY_WHISTLE` flag with a frequency estimate and confidence score, when the gate evaluates it, then it must record whether the issue is safe to ignore, requires re-generation, or may be considered for a narrowly scoped non-destructive mitigation only if architecture explicitly approves it; it must not claim a successful restoration without a defined method and measurement plan.
3. Given a `SMEARED_TRANSIENT` flag, when the gate evaluates it, then it must classify the issue as non-recoverable at mastering stage and emit a human-readable recommendation to discard or regenerate the source rather than attempting a transient repair in the mastering chain.
4. Given a clean file with no artifact flags, when the gate runs, then it must not modify the audio or emit any restoration actions.
5. Given a flagged file and a post-stage re-analysis pass, when the gate reports its result, then the output must include a before/after summary that records whether the artifact count changed, whether the issue remains, and why no further repair is expected; it must never state that a transient smear or band-limit loss was fully repaired unless the architecture defines an explicit, measurable repair method and validation threshold.
6. Given any action taken on a flagged segment, when the stage runs, then it must be constrained to the affected interval only, logged with parameter values, and reported as a non-destructive intervention rather than a general-purpose restoration step.
7. Given a file that fails because of an unsupported or invalid input contract, when the stage runs, then it must fail loudly with a clear error and must not silently continue into mastering.

## Audio quality targets
- No new loudness target is introduced by this story. It must not shift the project’s loudness or dynamic-range targets for the mastering chain unless a later story defines a specific restoration-dependent target.
- Any optional mitigation must respect the project’s existing constraints: float64 internal processing, integer conversion only at final I/O boundaries, and no silent clipping.
- A valid output must preserve source sample rate and channel layout unless a later architecture story explicitly defines a resampling or conversion step.
- The stage must be lossless with respect to clean sections: no gain change, no filter effect, and no metadata change outside the flagged region.
- If a decision requires comparison with the pre-master artifact report, the comparison must use the same detection method, same thresholds, and same timestamps to avoid reporting an artificial improvement.

## Input/output assumptions
- The input is a floating-point stereo or mono audio buffer produced by the render or analysis pipeline, with a valid sample-rate value and channel count.
- The source is expected to be Suno-generated audio, which may contain generation artifacts that are not necessarily audible in every section but are detected by the artifact-analysis stage.
- The primary output is a machine-readable report plus human-readable decision log, not a permanently altered audio file.
- If a direct DSP action is allowed by architecture, it must operate on the same sample rate and channel layout as the input and must leave the original audio unchanged unless an explicit safe-apply path is defined.
- The stage is meant to sit between artifact detection and the broad corrective EQ / dynamics / limiting chain, not to replace it.

## Explicit out-of-scope
- Repairing or de-noising smeared transients in a way that claims to restore the original attack envelope.
- Removing or “recovering” content above the generation band limit.
- Baked-in ambience or reverb removal.
- Per-element restoration or source separation from a stereo sum.
- Broad EQ or limiter tuning used as a substitute for actual restoration of missing content.
- Any requirement that implies the mastering stage can fix a transitory artifact that was never rendered in the source.

## Rejected as out of scope
- The draft requirement to apply “targeted spectral repair and transient shaping” to `SMEARED_TRANSIENT` is rejected. The repository’s domain definition states that transient smearing and other missing-content problems are not fixable at master stage because the information is absent and cannot be recovered from a stereo sum.
- The draft requirement to dynamically notch a whistle at a measured frequency is only acceptable if a later architecture story explicitly defines a narrow, safe, reversible, and validated mitigation path. As written, it promises restoration beyond the project’s domain and is therefore out of scope for this requirements stage.
- Any claim that a master-stage process can recover content above the generation band limit, re-create a missing transient, or correct a source problem requiring per-element access is rejected with the reason that the relevant information is not present in the stereo sum.

## Non-functional requirements
- Determinism: With identical input audio and detection report, identical decisions and logs must be produced across repeated runs.
- Reliability: The stage must fail clearly and explicitly on invalid metadata or impossible operations rather than silently passing a bad result into the mastering chain.
- Reproducibility: Any action taken must be logged with frequency, time range, threshold, and method name so that a second run can replicate the decision.
- Batch suitability: The stage must support file-by-file processing in a CLI workflow without requiring a GUI or real-time processing.
- Reporting: The result must be suitable for both programmatic consumption and human review in a report summary.

## Open questions
- Is the intended output of this story purely a report-only gate, or is there a future architecture-approved exception for non-destructive narrow-band mitigation of a stationary whistle?
- What exact artifact report schema is consumed by the stage, and which story/producer emits it?
- What is the minimum supported sample rate and the behaviour for files below the project’s standard analysis window?
- Should the stage treat `STATIONARY_WHISTLE` as a “review required” artifact by default rather than an auto-correct event?
- What is the exact threshold for a whistle to be considered eligible for any non-destructive action, if the architecture later permits it?
- For the “secondary detection pass” requirement, what delta metric is considered valid evidence of reduction without creating a false claim that the source has been repaired?

## Notes for downstream architecture and implementation
- This story should be implemented as a gate and decision layer between artifact detection and standard mastering, not as a replacement for the existing mastering pipeline.
- The architect must define any allowed, narrowly scoped mitigation logic separately from this requirements document.
- The final implementation must be able to explain, in plain language, why a detected defect is non-recoverable and why no action was taken rather than claiming a silent fix.
