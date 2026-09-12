# STORY-020 — Test cases: Demucs configuration tuning

## TC-020-01: benchmark profile output
- Given a valid input fixture
- When a tuning profile is benchmarked
- Then the result includes runtime, memory, and artifact score

## TC-020-02: reject unstable profile
- Given a profile that creates non-finite output or phase mismatch
- When the safety gate runs
- Then the profile is rejected and logged as invalid

## TC-020-03: deterministic repeated runs
- Given the same input and profile
- When repeated runs execute
- Then the output quality and metrics stay within the configured tolerance

## TC-020-04: default profile selection
- Given multiple valid configurations
- When `select_default_demucs_profile()` runs
- Then it chooses the lowest-risk profile with acceptable cost

## TC-020-05: active profile pass-through
- Given a versioned `StemConfig` with explicit shifts, overlap, and segment duration
- When the active separation boundary invokes Demucs
- Then the exact values are supplied as run-only `apply_model` keyword arguments and recorded in runtime metadata

## TC-020-06: invalid profile fails before loading
- Given invalid shifts, overlap, segment duration, or an empty profile version
- When configuration is constructed
- Then validation fails before any model loader or inference function is called

## TC-020-07: JSON and CLI precedence
- Given nested JSON stem configuration and a subset of explicit CLI overrides
- When CLI configuration is resolved
- Then unspecified JSON and stem-DSP values are preserved, explicit CLI values win, and modified run controls require a non-empty profile version

## Evidence limit
- Fake dependencies prove configuration and invocation contracts only.
- Real Demucs repeatability, runtime, memory, and artifact measurements remain release evidence and are not inferred from these cases.
