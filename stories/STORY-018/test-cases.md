# STORY-018 — Test cases: product packaging and release candidate

## Scope
These test cases validate the release-candidate packaging layer for the stem-aware mastering product and confirm it preserves the repo’s local-only, auditable, stem-first product contract.

## Test cases
### TC-018-01 — CLI command entry point is documented and executable
- **Preconditions**: The project environment is activated and the story implementation is importable as a Python module.
- **Action**: Invoke the documented command or module entry point with `--help`.
- **Expected result**: The CLI exits successfully and prints the usage contract including input, output, and mode arguments.
- **Covers**: requirements.md §1, §2, §3; architecture.md §1 and §3.

### TC-018-02 — Valid file processing with the end-to-end pipeline
- **Preconditions**: A valid audio file is present locally and the underlying repo pipeline is available.
- **Action**: Run the packaged CLI on the valid file and specify an explicit output directory.
- **Expected result**: A mastered output file is produced, the pipeline remains consistent with the validated end-to-end path, and the final result is written to the expected local output path.
- **Covers**: requirements.md §2, §5, §8; architecture.md §2, §6.

### TC-018-03 — Summary and audit output generation
- **Preconditions**: A valid run has completed successfully.
- **Action**: Inspect the terminal summary and the produced audit/summary artifact.
- **Expected result**: The output indicates the input, output path, chosen mode, and final verdict; the audit output preserves the run metadata and product decision clearly.
- **Covers**: requirements.md §4, §5; architecture.md §4.

### TC-018-04 — Invalid input rejection and safe failure path
- **Preconditions**: A missing path or invalid waveform input is provided.
- **Action**: Run the packaged CLI with the bad input path or an unsupported file.
- **Expected result**: The product exits non-zero with a clear error and does not continue into the mastering pipeline silently.
- **Covers**: requirements.md §2, §6, §8; architecture.md §5.

### TC-018-05 — Reproducibility across repeated runs
- **Preconditions**: The same valid input and same configuration, run twice in the same environment.
- **Action**: Execute the CLI twice on the same file and compare the final output contract and produced summary metadata.
- **Expected result**: The product reports the same mode, output conventions, and final verdict across runs; the output remains deterministic within the project’s repeatability bar.
- **Covers**: requirements.md §3, §5; architecture.md §3 and §6.

### TC-018-06 — No hidden fallback in release mode
- **Preconditions**: Release mode is selected and the input does not clearly support the stem-aware branch.
- **Action**: Run the release candidate and inspect the report and mode metadata.
- **Expected result**: The product either stays in the documented stem-aware mode or clearly states an explicit fallback; it must never silently switch to a different mode without recording it.
- **Covers**: requirements.md §6; architecture.md §3 and §6.

## Reject conditions
- Missing command contract or non-documented CLI entry point.
- Silent mode switching or hidden fallback behavior in release mode.
- Missing summary or missing audit output.
- Cloud, GUI, or plugin-hosted execution in the release path.
- Product output that cannot be traced back to the validated end-to-end pipeline.

## Revision history
- 2026-08-16: Story 018 test cases written for packaged CLI execution, reporting, validation, and guardrail enforcement.
