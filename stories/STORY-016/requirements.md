# STORY-016 — Requirements: End-to-end pipeline integration and acceptance

## Contract
Consumes: the original source audio, validated stage outputs from Stories 011–015, and the repo’s product guardrails.
Produces: a single end-to-end mastering workflow that runs the full stem-first chain, records a clear pass / reject / refine verdict, and either exports the result or rejects it with a documented reason.

## Product requirements
1. Stage ordering and execution
   - The orchestrator must run the pipeline in the required order: ingest → analysis → stem selection / fallback → transient restoration → harshness control → stereo imaging → bus glue → final safety → quality review.
   - No stage may be silently skipped. A missing or invalid stage result must be recorded in the audit trail and must fail or reject the output when the product contract requires it.

2. Stem-first default, stereo fallback only when explicit
   - The default workflow must prefer real stem data when a valid stem set exists.
   - Stereo-only operation is valid only as an explicit fallback mode and must be marked as limited in the audit output.
   - The pipeline must not imply that it recovered source information that was never present in the source.

3. Stage-level auditability
   - Each stage must log: stage name, status, and a summary of what changed or why it did not change.
   - The audit trail is part of the product path and must remain human-readable and traceable.
   - A stage result that is safe but unchanged is still recorded; no silent no-op is allowed.

4. Decision logic: pass / reject / refine
   - The final quality review must produce an explicit product decision.
   - A pass requires meaningful improvement with acceptable safety and no unresolved quality risks.
   - A reject requires evidence of degraded, dull, fatigued, artificial, or otherwise unconvincing output.
   - A refine result is acceptable only when the issue type is clear and the product can point to the next corrective action.

5. Safety and robustness
   - The pipeline must remain in float64 throughout processing and convert to integer only at the final I/O boundary.
   - True-peak safety checks must use oversampling, not sample peak.
   - The output must fail loudly if it violates the project’s transients or clipping guardrails.
   - Final export requires a real pass result or a documented override reason.

6. No hidden bypass or false claim
   - The workflow must not bypass required quality review or safety checks under the hood.
   - The pipeline must not claim to reconstruct missing source detail, remove information that was never present, or produce a full stem-aware master from a stereo-only fallback without saying so.

## Acceptance criteria
- End-to-end orchestration runs without manual stage stitching.
- The stage ordering is stable and auditable across repeated runs.
- The output explicitly records stem-first operation or explicit stereo fallback.
- Final review returns pass, reject, or refine with reasons.
- Export is blocked unless the result is passed or explicitly overridden with a reason.
- Safety checks and oversampled true-peak validation remain active.

## Validation plan
- Run a real Suno track through the orchestration path.
- Confirm that stage ordering remains stable and that audit output contains all required stages.
- Validate that explicit fallback is logged and not silently hidden.
- Confirm that pass / reject / refine logic reflects quality evidence, not only metric compliance.
- Confirm no clipping or unsafe true-peak condition is shipped without recorded handling.
