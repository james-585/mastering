# STORY-022 — Advanced stem extraction with 6-stem HTDemucs model

## User story
As a mastering engineer, I want the pipeline to support `htdemucs_6s` so that piano and guitar can be isolated individually and processed with the correct semantic mapping instead of being folded into the generic `other` stem.

## Scope
- In scope:
  - 6-stem model selection
  - piano and guitar mapping
  - recombination validation
  - report visibility
- Out of scope:
  - per-element repair beyond the chosen stem set
  - cloud-hosted model inference

## Contract
The system must support a distinct 6-stem extraction path that preserves the original semantic structure and can validate and recombine the complete stem bundle without silent information loss.
