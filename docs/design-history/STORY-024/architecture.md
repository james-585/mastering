# STORY-024 — Architecture: CLI workflow screen overhaul

## Pipeline placement
Insert at the operator-facing CLI boundary, immediately above the command execution and validation logic. This is not a DSP change; it is a workflow-reporting and state-display layer that explains what the engine is doing and whether it passed or failed.

## Business analyst confirmation
- Story intent: present a clear, trustworthy CLI workflow screen that communicates stage, status, and blocking conditions.
- Scope limit: this story is intentionally limited to workflow reporting and the operator interaction layer; it does not redesign the mastering DSP pipeline or add GUI features.
- Acceptance criteria: readable status transitions, deterministic text output, and failure-specific operator guidance remain the central requirement.
- Ambiguity check: no open question remains about whether this is a GUI task or a CLI-only task; the product remains terminal-first and local-only.

## Design decisions
- The CLI workflow screen is a thin reporting layer that summarizes the underlying execution state.
- It must expose the active stage and relevant metadata without exposing unnecessary low-level implementation details.
- Success should only be presented after the relevant validation gate has passed; otherwise the screen must clearly indicate the blocked or failed state.
- Terminal output must be intentionally plain and machine-readable enough to support logs, QA review, and operator debugging.

## Module boundaries
- Module: cli/workflow_screen.py
- Public API:
  - render_screen(stage, context)
  - render_summary(result)
  - render_error(error)
- Helper functions:
  - _format_stage_label()
  - _format_context_values()
  - _render_status_line()

## Data contract
- Input: current workflow stage, status, file metadata, model/profile selection, and validation result.
- Output: operator-facing terminal screen with stage name, current state, and actionable detail.
- Failure mode: error reports must include the real reason and any next-step guidance.

## Library choices
- Standard library formatting for terminal output
- Existing CLI argument and status data structures
- No GUI libraries or cloud services

## Implementation constraints
- Must not fake completion before the signal or validation path is confirmed.
- Must not add hidden state or silently alter execution behavior.
- Must remain consistent with the project’s local-only, CLI-first constraints.

## Gate 1 review (mastering engineer)

**Verdict:** PASS-ON-SCOPE

- The story is correctly scoped to operator-facing workflow reporting rather than DSP or plugin behavior.
- A deterministic screen layer is a practical improvement because accurate process visibility materially reduces operator confusion and prevents false confidence in a partially completed run.
- The architecture preserves the no-GUI, local-only requirement and keeps all operational logic in the CLI path.
- Explicit success/failure state handling is the correct safeguard: it prevents the workflow from appearing complete before validation has actually passed.

## Review disposition (mastering engineer)
- Accepted as-is: the workflow screen is a reporting layer and should not own mastering logic.
- Accepted as-is: stage-oriented progress and failure states are valuable for operator clarity and QA review.
- Action item: maintain a single source of truth for workflow state and ensure any screen display reflects that exact state.
- Action item: every terminal screen must clearly expose whether the run is in progress, blocked, or complete.

## Revision history
- 2026-08-17: Initial architecture for the CLI workflow screen overhaul.
