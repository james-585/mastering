# STORY-024 — CLI workflow screen overhaul

## User story
As a mastering operator and CLI user, I want a clearer and more deterministic workflow screen so that I can understand the current operation, expected inputs, and whether the system is progressing or blocking on a real issue.

## Scope
- In scope:
  - CLI status and progress output
  - workflow screen structure and state transitions
  - operator guidance for required inputs and safe failure modes
  - reproducible terminal reporting
- Out of scope:
  - GUI redesign
  - cloud-based orchestration
  - real-time plugin hosting
  - non-CLI workflow experiences

## Contract
The local mastering workflow must provide a readable screen-oriented CLI narrative that presents the current stage, critical values, expected actions, and failure conditions without hiding the underlying process or creating a fake success state.
