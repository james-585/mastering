# STORY-010: Adaptive harshness correction for real-world material

## User Story
As a mastering engineer, I want a second-pass spectral harshness stage that can distinguish broad brightness from narrow resonant harshness and from a reference-target mismatch, so that the tool corrects the actual problem without over-dulling balanced material.

## Contract
The tool must retain the existing Stage [1]-[4] pipeline and add an optional second-pass harshness branch that classifies the distortion before choosing a corrective action.

The stage consumes the measured 2–5 kHz band result from the existing frequency-balance analysis and decides between:
- broad shelf/tilt correction for diffuse brightness
- narrow notch or resonant cut for a tight peak
- reference-target adjustment when the material is consistently above the curve for the chosen genre

The stage is optional and must remain logged and report-visible. It must never be used as a general-purpose notch engine for arbitrary user-specified frequencies.

## Scope
- In scope:
  - adaptive classification of harshness by spectral shape
  - broad-band shelf/tilt correction
  - narrow, evidence-driven corrective reduction for a single resonant peak
  - reference-target adjustment when repeated material is systematically brighter than the current curve
  - reporting which method was chosen and why
- Out of scope:
  - general surgical notching for arbitrary tones
  - source separation or per-element fixes
  - using a generic de-esser as a substitute for spectral-balance logic
  - replacing the existing first-pass corrective EQ with a more aggressive catch-all rule
