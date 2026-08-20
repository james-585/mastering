# STORY-026: Spectral de-noise pre-processor for stationary tonal infestation

## User Story
As the product owner, I want a spectral de-noise pre-processing stage that learns the noise profile of stationary tones from quiet sections of a track and subtracts them via Wiener filtering before the rest of the mastering chain runs, so that tracks with dense, sustained tonal/whistle infestation get cleaned up properly instead of relying on the current notch-based spot repair.

## Background
- `stories/STORY-001/implementation/suno_mastering/mastering/whistle_repair.py` (STORY-009) attempted narrowband notch repair of stationary tones and is **currently disabled in production**. [DEF-009-001](../STORY-009/defects.md) (open) documents that the notch approach was found destructive on real programme material: the listening gate failed with the output "characterised as 'highly destructive to the track'" even after fixing an OLA bug, because the detector cannot distinguish AI-generation tonal artifacts from musical content (sustained synth tones, pad harmonics) at the arithmetic level.
- Even after STORY-009 added a harmonic guard (§6b) that suppressed 95.7% of flags as likely-musical, only 19 of 439 flags were judged safe enough to forward to the notch stage — leaving 428 of 452 `STATIONARY_WHISTLE` flags on the "Sunday Club" reference track untouched. The notch method does not scale to dense, sustained tonal infestation; it can only safely handle a small number of clearly isolated, non-harmonic whistles.
- Commit `900f9bd` made `--no-detect-whistles --no-repair-whistles` the default in `master_track.bat`, because running detection without an actionable repair only inflated the artifact count in reports (202 → 476) with no benefit. `RepairWhistlesConfig.enabled` and the whistle-detection flag both default to `False` in `config.py` today.
- `stories/STORY-001/implementation/suno_mastering/analysis/artifact_detection.py` already scores tonal/artifact density (`overall_artifact_density_score`) and its `_detect_stationary_whistle` step (with its own Step 4a/4b harmonic checks) is the existing source of confirmed whistle evidence to build on.
- The harmonic-preservation problem that defeated whistle_repair.py — distinguishing genuine AI-encoder tonal artifacts from musical fundamentals/harmonics at the same frequency — applies equally here and must be designed in from the start, not patched on afterward. This story does not get a free pass just because Wiener subtraction is a different method; it must clear the same evidentiary bar that sank the notch approach.
- This is a pre-processing stage: it must run *before* the rest of the mastering/repair chain. Whether whistle_repair.py stays as a disabled/no-op fallback, is re-enabled for residual isolated whistles this stage misses, or is retired entirely is an open question for the architect — it should not be assumed to remain an active downstream layer.

## Contract
```
Consumes:  raw input audio, STORY-001 artifact_detection output (quiet-section / stationary-tone
           localization), existing seven-band spectral analysis for harmonic-content awareness
Produces:  a spectral de-noise module producing a de-noised audio buffer plus a noise-profile
           report (bands/frequencies subtracted, magnitude of reduction, sections used for
           profile learning), inserted as the first stage of the mastering pipeline
Consumed by: whistle_repair.py (STORY-001) and the rest of the mastering chain (post-denoise
           input), STORY-025 grounded quality review (artifact-density delta before/after)
```

## Scope
- In scope:
  - Noise profile estimation from quiet/low-energy sections of the track (leveraging existing quiet-section or low-activity detection where available)
  - Wiener filtering (or comparable spectral-subtraction approach) to remove the learned stationary noise profile from the full track
  - A guard against removing wanted harmonic/musical content overlapping the noise profile's frequencies (consistent with the STORY-009 harmonic guard precedent)
  - Producing a report of what was removed (bands, magnitude, source sections) for QA and the grounded quality review in STORY-025
  - Insertion point: runs before whistle_repair.py and the rest of the mastering chain
- Out of scope:
  - Removing or replacing the existing notch-based whistle_repair.py (it remains as spot-repair fallback)
  - Non-stationary noise (transient artifacts, clicks, dropouts) — this story targets stationary tonal/noise beds only
  - Changing loudness/DR/EQ targets or correction caps (STORY-006 territory)
  - Real-time/streaming processing — this is an offline pre-processing pass like the rest of the pipeline

## Product goal
Give the pipeline a de-noise stage capable of handling dense, sustained tonal noise infestation that the current spot-repair notch filtering cannot adequately address, without degrading wanted musical/harmonic content.

## Revision history
- 2026-08-20: Story created — targeting the dense stationary tonal infestation observed on "Sunday Club".
- 2026-08-20: Background corrected — whistle_repair.py (STORY-009) is disabled in production per open defect DEF-009-001 (notch repair judged destructive on real material; scales to only 19/439 flags even with harmonic guard), not an active fallback layer as originally assumed.
