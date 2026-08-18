# STORY-010 — Architecture: adaptive harshness correction

## Pipeline placement
Insert the new stage after the existing corrective EQ and before final limiting.

The order is:
1. ingest
2. pre-master analysis
3. sample-rate check
4. corrective EQ
5. adaptive harshness correction
6. loudness and limiting
7. export/report

## Design decisions
- Keep the existing presence/harsh measurement as the trigger signal.
- Add a classification step that inspects the band shape, not only the average level.
- Choose corrective method by evidence:
  - broad brightness → shelf/tilt
  - narrow peak → notch or narrow bell
  - systematic mismatch → target curve update
- All actions remain logged and capped to preserve the project’s gentle mastering stance.
- No band-level correction may be used to hide a known artifact that should be handled elsewhere.

## Guardrails
- Stereo sum only; no element-level fixes.
- No arbitrary user frequencies.
- No default-on behavior.
- No silent broad dulling.
