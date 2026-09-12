# STORY-024 — Requirements: CLI workflow screen overhaul

## Contract
Consumes: the current local CLI mastering workflow and operator-facing status output.
Produces: a clearer, screen-oriented workflow display for validation, execution, and failure states.
Consumed by: developer, QA, and operator execution scenarios.

## Product requirements
1. Replace opaque or inconsistent terminal output with a clear workflow screen that reflects the active stage.
2. Show the current operation, input file, selected profile or model, and key measurements in plain text.
3. Distinguish between progress, waiting, success, and failure states without implying a completed operation before it has actually passed validation.
4. Surface operator guidance when required inputs are missing or when a stage is blocked by a real issue.
5. Preserve the repo’s local-only, CLI-first, reproducible workflow constraints.

## Active workflow integration contract
- The CLI screen is part of the operator interaction layer, not a separate product surface.
- The workflow must remain deterministic across runs for a given input and configuration.
- Output should be concise, legible, and structured enough for both manual operation and automated log capture.
- Any failure message must identify the real blocking condition instead of returning a generic status.

## Acceptance criteria
- Given the workflow begins, when the operator starts the mastering command, then a clear stage-oriented screen is displayed.
- Given a valid run is in progress, when analysis or processing steps execute, then the current stage and state remain visible.
- Given a failing condition occurs, when the validation gate rejects the file or output, then the system reports the specific failure and halts.
- Given a successful pass occurs, when the final stage is reached, then the displayed summary reflects the verified result and not an assumed outcome.

## Validation plan
- Review the terminal output against a reference CLI run.
- Validate consistent screen state transitions across success and failure paths.
- Check that the output is readable, concise, and suitable for logs and operator review.

## Revision history
- 2026-08-17: Initial requirements artifact for the CLI workflow screen overhaul.
