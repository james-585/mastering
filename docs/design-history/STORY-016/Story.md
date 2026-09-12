# STORY-016: End-to-end pipeline integration and acceptance

## User Story
As a product owner, I want the full mastering pipeline wired end-to-end so that the tool can run a complete stem-aware master in one pass and prove the result is real, safe, and audibly improved.

## Contract
The complete mastering flow must be connected end-to-end: ingest → analysis → stem separation or fallback → stem corrections → bus glue → final safety → final quality review → export or reject.

## Scope
- In scope:
  - end-to-end orchestration of the whole pipeline
  - integrated stem-aware processing order
  - pass / reject / refine decision flow
  - end-to-end audit trail for each stage
- Out of scope:
  - introducing new DSP algorithms beyond the proven stage chain
  - feature work unrelated to pipeline closure
  - hidden fallback behavior that bypasses the required stage review

## Product goal
Make the full pipeline run as a coherent product path and prove the assembled flow delivers a better result than the original, while remaining auditable and safe.

## Revision history
- 2026-08-16: Story 016 created to close the gap between individual stage stories and a real end-to-end product.
