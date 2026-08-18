# STORY-020 — Requirements: Demucs inference parameter optimization

## Contract
Consumes: the current Demucs separation workflow and a fixed set of representative audio fixtures.
Produces: a reproducible inference tuning profile that reduces separation artifacts while reporting the quality-time-memory trade-off.
Consumed by: the Demucs pre-processing stage before final mastering.

## Product requirements
1. Benchmark Demucs inference settings including shifts, overlap, and segment size.
2. Record runtime, memory, and artifact metrics for each candidate configuration.
3. Keep a stable default configuration that is explicitly logged and versioned.
4. Reject configurations that introduce non-finite output, phase instability, or clipping risk.
5. Make the trade-offs visible in the CLI report or JSON artifact.

## Active workflow integration contract
- The live configuration uses `shifts`, `overlap`, and `segment_seconds`; `segment_seconds` is either a positive duration or `None` to retain the model default.
- The harness value `segment_length=4096` is sample-domain test data and must never be passed directly to Demucs as a duration.
- Until a real Demucs benchmark validates a segment override, the active default is `segment_seconds=None`. Synthetic runtime, memory, or artifact formulas are not evidence for a production default.
- The effective values and non-empty profile version pass unchanged through `StemConfig`, stem preprocessing, and the inference call, and are logged for every separation run.

## Acceptance criteria
- Given a parameter sweep is executed, then each configuration records run time, memory usage, and output integrity metrics.
- Given a candidate configuration causes phase mismatch or reconstruction artifact above threshold, then it is rejected before becoming default.
- Given the default configuration is repeated across runs, then it remains stable and reproducible on the same fixture.
- Given no valid configuration passes safety checks, then the process fails clearly instead of proceeding with hidden degradation.

## Validation plan
- Measure performance across representative fixtures: drums, vocals, synth-heavy, and mixed music.
- Benchmark quality and cost for multiple shift/segment combinations.
- Require QA reporting of runtime + memory + artifact score for every scenario.

## Revision history
- 2026-08-17: Initial requirements artifact for Demucs inference tuning.
- 2026-08-17: Clarified live parameter names and units; prohibited promotion of synthetic harness values into the active Demucs workflow.
