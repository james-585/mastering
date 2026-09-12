# STORY-019 — Test cases: M/S DSP and bypass null-sum validation

## TC-019-01: M/S round-trip exactness
- Given a stereo fixture with deterministic values
- When `decode_ms(encode_ms(x))` runs
- Then the output matches the original within `1e-12` maximum absolute error

## TC-019-02: bypass identity test
- Given a valid `other` stem and a disabled DSP flag
- When the processing stage executes
- Then the output equals the input exactly and the final recombined signal matches the original mix to within tolerance

## TC-019-03: phase null-test
- Given a bypassed M/S stage
- When the inverse transform is applied in a test harness
- Then the residual must be effectively zero and must not exceed the configured tolerance threshold

## TC-019-04: invalid input rejection
- Given NaN, Inf, or malformed stereo shape
- When validation occurs
- Then the stage raises a hard failure before writing output

## TC-019-05: clipping guard
- Given a near-full-scale signal
- When the processed output is checked
- Then the stage reports or fails loudly rather than silently clipping

## TC-019-06: report visibility
- Given the stage executes
- Then the log includes transform status, bypass state, numeric residual, and output safety verdict
