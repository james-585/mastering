# STORY-012: Stem-local harshness control and de-haze

## User Story
As a mastering engineer, I want the tool to reduce harshness and de-haze on the actual offending stems so that the mix feels cleaner and less fatiguing without becoming dull, flattened, or globally over-processed.

## Contract
The tool must detect and reduce harsh upper-mid/high energy only on stems that show real evidence of brittleness, glare, or haze. It must leave clean or low-energy stems unchanged and keep every correction auditable, conservative, and signal-bound.

## Scope
- In scope:
  - stem-aware harshness detection
  - local de-haze for harsh vocals, bright synths, cymbals, and bright percussion
  - audit log for stem name, reason, band, and gain
  - conservative correction with oversampling safety and true-peak checks
  - no-op behavior on clean or silent stems
- Out of scope:
  - blanket global EQ for the full mix
  - source recovery beyond the actual signal in hand
  - dulling the entire track to “fix” a few offending stems
  - broad stereo-sum harshness correction as the primary path

## Product goal
Reduce listener fatigue and brittleness on the actual offending stems while preserving texture, detail, and transient attack. The output must remain musically alive and truthful to the source instead of becoming a generic dulling pass.

## Revision history
- 2026-08-16: Story 012 aligned to stem-first product direction and the repo requirement to avoid blanket global dulling across the full mix.
