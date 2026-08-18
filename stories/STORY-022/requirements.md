# STORY-022 — Requirements: Advanced stem extraction with 6-stem HTDemucs model

## Contract
Consumes: the current Demucs stem-aware workflow and the configured model registry.
Produces: a 6-stem extraction flow using `htdemucs_6s` that isolates piano and guitar while preserving deterministic summation logic.
Consumed by: the stem-processing and mastering pipeline stages.

## Product requirements
1. Add support for `htdemucs_6s` as an explicit model option.
2. Map the six stems to their correct semantic names and ensure the pipeline can report them clearly.
3. Update recombination logic so six-stem output is combined deterministically and validated before mastering.
4. Reject partial stem bundles or missing channels that would make the output ambiguous.
5. Preserve the repo’s safety guardrails for amplitude and reconstruction integrity.

## Active workflow integration contract
- `htdemucs_6s` is an explicit `StemConfig` and CLI model choice; the existing four-stem models remain distinct paths.
- Expected names are derived from the selected model contract: four-stem output is `drums`, `bass`, `other`, `vocals`; six-stem output additionally contains `piano` and `guitar`.
- Before stem DSP begins, validation rejects missing or extra names, non-stereo arrays, mismatched sample counts, non-finite values, and an output count inconsistent with the selected model.
- The resolved model name and ordered semantic mapping are logged and retained in the separation result.

## Acceptance criteria
- Given an `htdemucs_6s` model is selected, when stem separation runs, then a six-stem bundle is produced with explicit piano and guitar channels.
- Given a partial or invalid 6-stem output is received, when validation occurs, then the pipeline halts with a clear error.
- Given a no-op identity check is run, when all six stems are recombined, then the signal remains mathematically equivalent to the original under the configured tolerance.
- Given the model is logged, when a report is generated, then the exact model and stem mapping are visible.

## Validation plan
- Validate against synthetic audio fixtures that include piano and guitar content.
- Confirm the 6-stem summation is deterministic and rejects partial results.
- Inspect output contracts for sample rate, shape, and channel ordering.

## Revision history
- 2026-08-17: Initial requirements artifact for the 6-stem Demucs evolution.
- 2026-08-17: Added the active CLI/config hand-off and model-derived validation contract.
