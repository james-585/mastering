# STORY-024 — Test cases: CLI workflow screen overhaul

## TC-024-01: start-of-run screen
- Given the workflow starts for a valid input
- When the command is invoked
- Then the CLI displays a stage-oriented screen with the active operation and key context

## TC-024-02: in-progress state
- Given processing is underway
- When the workflow advances through analysis or mastering stages
- Then the screen updates to show the current stage and status without losing context

## TC-024-03: failure state reporting
- Given validation or processing fails
- When the error occurs
- Then the system shows the blocking reason and the operator-facing next action

## TC-024-04: success summary
- Given all gates pass
- When the final stage completes
- Then the summary reflects the verified result instead of a generic success message

## TC-024-05: no GUI dependency
- Given the command is run in a terminal environment
- When the workflow screen renders
- Then the output remains CLI-only and does not depend on a graphical interface
