# STORY-019 — Requirements: Deterministic Mid/Side processing for the “other” stem

## Contract
Consumes: a Demucs-separated stem bundle containing an `other` stem and the current stereo signal metadata.
Produces: a deterministic Mid/Side processing path that can be bypassed without introducing loss or phase error.
Consumed by: the optional pre-mastering stem-processing layer before final summation.

## Product requirements
1. Mid/Side encoding and decoding must be implemented as an explicit, auditable signal transform using SciPy, not as an implicit channel swap or ad hoc reordering.
2. The transformed path must operate only on the `other` stem so the feature remains constrained to the correct signal domain and does not silently touch vocals, bass, or drums.
3. The implementation must use float64 internally and convert to integer only at final I/O boundaries.
4. The DSP path must be bypassable in a mathematically exact identity mode to allow phase-cancellation and null-sum testing.
5. The pipeline must fail loudly on non-finite values, clipping risk, or invalid stereo layout instead of silently continuing.
6. When the DSP is disabled, the re-summed output must be numerically indistinguishable from the original input signal under deterministic test conditions.

## Functional requirements
- The stage must expose a pure encoding/decoding function pair that is easy to unit test.
- The transform must preserve stereo geometry in both endpoints: left/right input and mid/side intermediate representation.
- A no-op branch must return the original `other` stem exactly without resampling, normalization, or dtype conversion.
- The final re-summation logic must validate that every stem is present and that the signal dimensions match the input contract.

## Acceptance criteria
- Given a valid stereo input, when `encode_ms` runs, then `decode_ms(encode_ms(x))` matches the original within `1e-12` maximum absolute error.
- Given the DSP is bypassed, when the process runs, then the `other` stem is exactly unchanged and the final recombined signal matches the source within `1e-12` at every sample.
- Given a phase-cancellation null test is executed, when the DSP is bypassed, then the residual after inverse processing must be effectively zero and not exceed the explicit tolerance threshold.
- Given a non-finite or invalid input, when validation executes, then the pipeline raises an error before any output is written.
- Given clipping risk is detected, when the output amplitude exceeds the safety limit, then the stage logs a hard failure or explicit warning instead of silently proceeding.

## Validation plan
- Use deterministic synthetic stereo fixtures with known sample values.
- Run null-sum tests using the identity branch and inverse transform.
- Validate both `float64` exactness and sample-level reproducibility on repeated runs.
- Confirm all output is mathematically lossless when the stage is disabled.

## Revision history
- 2026-08-17: Initial requirements artifact for the M/S processing story.
