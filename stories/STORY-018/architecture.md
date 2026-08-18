# STORY-018 — Architecture: product packaging and release candidate

## Goal
Package the validated stem-aware mastering workflow into a deterministic local CLI product that can be released as a repeatable, auditable, and product-fit release candidate.

## Product architecture
1. Command entry point and execution contract
   - The packaged CLI is a thin wrapper around the existing validated end-to-end pipeline, not a new processing algorithm.
   - The primary entry point is a Python module or CLI script invoked locally: a single input file plus explicit output directory and optional mode selection.
   - The CLI should surface a stable argument contract and reject malformed inputs before running the mastering pipeline.

2. Local file I/O model
   - Inputs are read from local paths only; output is written to the chosen local directory.
   - The run must be deterministic and non-destructive: the original input file stays untouched, while the output is created in an explicit output folder or near the input path, with a clear artifact naming convention.
   - The product must create a corresponding report and audit artifact so the output remains reproducible and reviewable.

3. Product configuration and mode selection
   - Product configuration is centralized in the repo’s existing config objects rather than ad hoc CLI-only parameters.
   - The default product mode is stem-aware and must preserve the validated stem-first direction.
   - An explicit fallback mode is allowed only when the user or workflow indicates that the input is not suitable for stem-aware handling; in that case, the mode must be labeled in the summary and audit output.
   - Release mode must not contain hidden automatic fallback logic that changes the pipeline silently.

4. Summary reporting and final audit output
   - The CLI emits a human-readable summary for terminal use and a structured summary/audit artifact for repeatability.
   - The summary must include at minimum: input path, output path, chosen mode, selected processing path, final verdict, and whether the output passed the release-candidate checks.
   - The audit artifact must preserve critical metadata such as configuration summary, pipeline mode, and final quality status so it can be reviewed later without re-running the product.

5. Release-candidate validation logic
   - The packaged CLI must validate both execution and correctness: the file exists, the pipeline can run, the output is created, and the product reports its result clearly.
   - A release candidate is considered valid only when the wrapper and the underlying end-to-end pipeline are both demonstrably working together.
   - The validation layer must check for clear failure modes, including invalid input, missing output path, and unsafe or mismatched configuration without masking the cause.

6. Compatibility with the validated end-to-end pipeline
   - The release-candidate path must reuse the proven pipeline and report generation path rather than inventing a new wrapper-only processing chain.
   - The packaging layer is a product boundary, not a replacement for the mastering logic; it must preserve the same local-only, float64-internal, oversampled-true-peak, stem-aware behavior that the validation work already proved.
   - The release product must be auditable and explainable: if an output is weaker or more limited than the validated pipeline, the CLI should surface that instead of papering over it.

## Architecture rules
- No cloud APIs, no GUI, no plugin hosting, and no hidden external dependencies in the release path.
- Default product direction remains stem-first; stereo fallback is explicit and labeled, not silent.
- No fake source recovery or unverified “magic fix” behavior is allowed in the CLI packaging layer.
- The final CLI result must remain auditable, deterministic, and consistent with the repo’s engineering guardrails.
- Internal processing remains float64 and true-peak enforcement remains oversampled; integer conversion stays at final I/O boundaries only.

## Expected result
The story produces a stable release-candidate CLI that packages the validated mastering workflow into a consistent local product path. The tool is auditable, deterministic, and transparent about its mode and output decisions, and it does not trade away engineering integrity for a cleaner wrapper.

## Revision history
- 2026-08-16: Story 018 architecture written for the product packaging and release-candidate milestone.
