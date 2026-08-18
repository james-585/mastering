# STORY-013: Stem stereo imaging and depth control

## User Story
As a mastering engineer, I want the tool to shape stereo width per stem so the mix has believable depth and spaciousness without sounding artificially wide or phasey.

## Contract
The tool must measure width and correlate each stem separately, then apply per-stem stereo decisions that preserve kick, vocal, and bass center stability while opening ambience, synths, and pads when appropriate.

## Scope
- In scope:
  - per-stem width control
  - center stability checks
  - mono-compatibility protection
  - report visibility for each width decision
- Out of scope:
  - aggressive full-bus widening
  - fake-stereo generation from mono stems
  - phase-breaking rebalancing without evidence
