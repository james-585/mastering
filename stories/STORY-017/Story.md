# STORY-017: Real-world tuning and validation on Suno source material

## User Story
As a product owner, I want the mastering pipeline tuned against a small set of real Suno tracks so that the product decisions are based on actual listening outcomes, not just unit tests.

## Contract
The tool must be validated against a small curated set of real files to check whether the chain actually improves clarity, control, width, depth, and emotional feel without causing fatigue or over-processing.

## Scope
- In scope:
  - real-world tuning against a small test set
  - review of before/after musical outcome
  - parameter adjustment based on listening results
  - evidence-based final tuning
- Out of scope:
  - adding more speculative processing stages
  - tuning to synthetic-only metrics without listening confirmation
  - reworking the architecture without a clear defect or product failure

## Product goal
Turn the working stage chain into a product that behaves well on actual source material rather than only on synthetic fixtures.

## Revision history
- 2026-08-16: Story 017 created to formalize the real-world validation pass.
