## Findings

1. **Severity**: Note
   - **What is proposed**: Stem-local transient restoration that only runs when a real local attack deficit exists, with conservative onset-gain shaping, per-stem operation, and hard peak protection.
   - **Why it fails, or under what conditions**: It does not fail under the repo’s constraints or the known-wrong patterns, as long as the implementation stays on the local onset metric and remains default-off. The real danger is overreach on naturally soft or dark programme material, but the story explicitly rejects global thresholds, whole-stem broad boosts, and “repair missing source” claims.
   - **What to do instead**: Keep the method exactly as designed: evidence-driven, stem-specific, local to the transient region, and no-op when the stem is already good. This is a physically and musically plausible approach for real programme material.

2. **Severity**: Note
   - **What is proposed**: The architecture avoids the classic failure modes by using per-stem detection, no broad stereo-sum correction, and true-peak oversampling safety.
   - **Why it fails, or under what conditions**: It would be a problem only if the detector regressed into a fixed dB threshold, a global crest-factor rule, or a blanket gain stage. The requirements and architecture explicitly forbid those patterns.
   - **What to do instead**: Preserve the guardrails: local onset evidence, no-op default, explicit peak guard, and report-visible action logs. No blockers.
