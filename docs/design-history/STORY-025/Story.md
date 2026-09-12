# STORY-025: Grounded quality validation — proving the master actually sounds better

## User Story
As the product owner, I want the mastering pipeline's pass/reject verdict to be based on grounded, musically meaningful evidence and real listening review — not proxy metrics and auto-generated report prose — so that a "PASS" actually means the output sounds better than the source.

## Background
A review of the current implementation found:
- `stories/STORY-015/implementation/final_quality_review.py` computes a "musical" verdict from crude proxies: `clarity_delta` is a mean-absolute-amplitude difference (a loudness proxy, not clarity), and `_spectral_tilt` is a coarse 2-bin FFT ratio, not the project's existing seven-band spectral analysis.
- `stories/STORY-017/implementation/real_world_validation.py` (the real-world validation pass) produces auditable report text describing what a review *should* find, without an actual human listening step occurring by default. `human_decision`/`human_note` fields exist but are unpopulated in the default path.
- The mandatory loudness-matching step (`.claude/docs/CLAUDE.md` §6.3 — "level-matching is mandatory before comparing a mastered result to a reference") is not enforced in code before before/after deltas are computed.
- The stem-first default path is untested with real models: Demucs/Torch are absent from the current working environment (per repo memory), so the core product strategy has never been run end-to-end on real audio.

## Contract
```
Consumes:  existing STORY-015 final_quality_review.py, STORY-017 real_world_validation.py,
           STORY-007 artifact_detection output (overall_artifact_density_score),
           STORY-006 seven-band spectral analysis, real Suno validation set
Produces:  a grounded quality-review module with LUFS-matched before/after comparison,
           artifact-density delta check, and a real (non-simulated) human-listening capture step
Consumed by: STORY-017 real-world validation re-run; release gate
```

## Scope
- In scope:
  - Replacing proxy metrics in the quality-review stage with grounded, already-existing project measurements (seven-band spectral balance, artifact density, DR/crest factor)
  - Enforcing LUFS-matched comparison before any before/after delta is computed
  - Wiring a real human-listening capture step (no auto-generated stand-in verdicts)
  - Verifying the Demucs/Torch stem-separation path runs on real audio before validation results are trusted
- Out of scope:
  - Adding new corrective DSP processing stages
  - Changing loudness/DR/EQ targets or correction caps (STORY-006 territory)
  - Cloud-based or automated perceptual-quality models (PEAQ/ViSQOL etc.) unless a later story justifies the dependency

## Product goal
Turn the pipeline's pass/reject decision into one backed by real evidence: grounded metrics plus an actual listen, not proxy math and auto-generated prose.

## Revision history
- 2026-08-17: Story created from orchestrator review of STORY-015/017 gaps.
