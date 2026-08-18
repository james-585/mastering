# STORY-018 — Requirements: Product packaging and release candidate

## Contract
Consumes: the validated stem-aware mastering pipeline, the repo’s product guardrails, and a local audio input.
Produces: a deterministic, release-candidate CLI product that can be run consistently on a local workstation and emits auditable output without hidden fallback behavior.

## Product requirements
1. Release-candidate CLI contract
   - The product must expose a clear local command entry point for a single input file and an explicit output destination.
   - The CLI must accept file paths and mode selection without ambiguous defaults or silent fallback injection.
   - The command contract must be documented in the story and reflected in the implementation so a developer can reproduce the run without ad hoc assembly.

2. Input and output handling
   - The CLI must validate the input audio file before any mastering work begins.
   - The output directory must be created deterministically, and the output file path must be explicit and non-destructive.
   - Production output must include the mastered WAV and a companion summary/audit artifact, with no silent omission of result metadata.

3. Local execution and reproducibility
   - The release flow must run only with project-local dependencies and the repository’s supported Python environment.
   - The workflow must be reproducible across repeated local runs with the same input, same configuration, and same code revision.
   - The release path must avoid cloud services, external APIs, GUI wrappers, or plugin-hosted execution.

4. User-facing reporting and audit output
   - The tool must emit a clear human-readable summary of the run, including the input path, selected mode, processing choices, and final output verdict.
   - The tool must also produce an audit record sufficient to explain the decision path, the selected product mode, and whether it stayed in the stem-aware product contract or used an explicit fallback.
   - The summary and audit output must be generated in a way that is auditable without reverse-engineering the code.

5. Release-candidate validation workflow
   - The project must define a release-validation path that executes the end-to-end pipeline against a valid input and checks the output contract end-to-end.
   - The validation flow must confirm the CLI path executes correctly, produces a valid result, and maintains the repo’s safety rules.
   - A release candidate is not considered valid if the wrapper works but the underlying pipeline cannot be shown to run with the expected product intent.

6. No hidden fallback behavior in release mode
   - In release mode, the product must not silently switch from stem-aware processing to a generic stereo-only pass.
   - Any fallback must be explicit, explained, and recorded in the summary/audit output.
   - If the product does not have the information required for stem-aware processing, it must fail clearly or continue only under a documented explicit fallback mode, never a hidden one.

7. Product guardrails and no fake recovery
   - The package must preserve the stem-first product direction as the default operating mode.
   - The release flow must not claim to recover information that was never present in the source.
   - It must remain local-only, Python-first, and consistent with the repo’s real-source product goal rather than a fake “magic fix” path.

8. Audio and engineering safety constraints
   - The internal pipeline must continue to use float64 processing; integer conversion must happen only at final I/O boundaries.
   - True peak must use oversampled metering, not sample peak.
   - No silent clipping or hidden safety bypass may be permitted in the release flow.
   - Any final-output risk or validation failure must be exposed in the summary/audit output instead of hidden behind a neat CLI wrapper.

## Acceptance criteria
- A developer can run the product from a single documented local command.
- The CLI accepts clear input and output paths and a defined mode selection without hidden fallback behavior.
- The configured product flow remains stem-aware by default and only uses an explicit fallback when deliberately requested.
- The run emits summary and audit output that explains what happened and the final verdict.
- The product remains reproducible, local-only, and consistent with the repository’s product guardrails.
- The release path is compatible with the validated end-to-end mastering pipeline and can be used as a release-candidate path rather than an ad hoc experiment.

## Validation plan
- Run the packaged CLI on a representative valid input to confirm the end-to-end path executes successfully.
- Check the generated summary/audit files and confirm they describe the mode and the product decision clearly.
- Reject invalid input and missing configuration with clear, non-ambiguous errors.
- Verify repeated runs are deterministic and report the same final verdict and output conventions.

## Revision history
- 2026-08-16: Story 018 requirements written for the packaging and release-candidate milestone.
