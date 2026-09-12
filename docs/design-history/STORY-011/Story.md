# STORY-011: Stem-aware transient restoration

## User Story
As a mastering engineer, I want the tool to restore transient realism per stem so that drums hit harder, bass has more punch, and vocals and synths feel more defined without turning the track harsh or artificial.

## Contract
The tool must use HTDemucs-separated stems as the input to a transient-aware restoration stage. It consumes stem-level analysis and outputs per-stem restoration actions, which are then recombined for the final mix bus.

## Scope
- In scope:
  - per-stem attack restoration
  - transient-shape correction for drums, bass, and melodic elements
  - mild dynamic contour correction to preserve realism
  - report-visible audit trail
- Out of scope:
  - single-file stereo-only correction as the main pathway
  - reconstructing removed source material that never existed
  - aggressive crackle or artefact removal beyond measured transient evidence
