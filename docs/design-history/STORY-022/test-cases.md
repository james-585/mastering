# STORY-022 — Test cases: 6-stem extraction and recombination

## TC-022-01: model registry supports 6-stem path
- Given the user selects `htdemucs_6s`
- When the model is resolved
- Then the pipeline exposes the six expected outputs

## TC-022-02: piano/guitar mapping
- Given a valid inference run
- When stem names are checked
- Then piano and guitar appear as their own explicit channels rather than as `other`

## TC-022-03: partial bundle rejection
- Given a 6-stem run returns fewer than six valid stems
- When validation executes
- Then the run fails with a clear contract error

## TC-022-04: source-order-safe mapping
- Given a model reports the exact valid source set in a non-canonical order
- When inference output is mapped
- Then tensor indices follow `model.sources` and the returned bundle uses canonical registry order without label swaps

## TC-022-05: exhaustive structural rejection
- Given missing, extra, duplicate, mono, wrong-length, wrong-count, or non-finite output
- When validation executes
- Then the run fails before stem DSP and does not trigger device fallback

## TC-022-06: uncorrected residual telemetry
- Given a structurally valid four- or six-stem bundle whose sum differs from the input
- When separation completes
- Then residual peak and energy ratio are reported from the original model output and no stem is modified to force identity

## TC-022-07: complete six-stem provenance
- Given a valid `htdemucs_6s` result
- When runtime metadata and reports are produced
- Then model-reported order, canonical order, piano, guitar, and per-stem peaks are retained

## Evidence limit
- Fake-model tests establish structural mapping and validation only.
- Installed-model source compatibility, leakage, transient damage, phase behavior, residual acceptability, and listening quality remain release gates.
