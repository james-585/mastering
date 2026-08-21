# STORY-027: Close the spectral and dynamics correction gaps outside sub/low_mid

## Status: Draft — requirements written, not yet at architecture/Gate 1

## User Story
As the product owner, I want the mastering chain to actually address the
correction gaps that a direct review of a real mastered track exposed —
an under-delivered low-end/low-mid correction, two dormant/no-op harshness
stages, no treatment at all for high-frequency energy above 2 kHz, and no
handling of within-track loudness swings — so that "mastered" output
reflects a genuine correction pass across the bands and dynamics the
current pipeline actually measures, not just sub and low_mid.

## Background
The product owner reviewed `artifacts/Sunday Club_mastered_report.json`
(2026-08-20 run) and `targets.json` directly and diagnosed four gaps. This
business-analyst pass independently re-verified each claim against the
same files plus the pipeline source, and found the underlying gaps real
but, in two cases, differently shaped than first diagnosed. See
`requirements.md` "Source-grounding" for the full evidence trail; summary:

1. **`low_mid` de-mud correction is capped below what it's aiming for.**
   Confirmed directly in the report's `eq_actions`: `low_mid` measured
   +6.54 dB re mid, the `de_mud` trigger fired (source > mid + 4.0 dB) and
   aimed at +2.0 dB, but `correction_cap_db` (2.0, from `targets.json`)
   only allowed −2.0 dB of the needed −4.54 dB, `cap_reached: true`. The
   `sub` band shows the same capping (+6.83 dB source, aiming at the range
   edge +1.94 dB, capped at −2.0 dB of a needed −4.89 dB) — **but the two
   bands are not the same case**: `sub`'s source value is genuinely outside
   its reference range (range compliance), while `low_mid`'s +6.54 dB
   source sits *inside* `low_mid`'s reference range (`[-0.145, +8.522]`
   dB re mid) — it is the separate `de_mud` trigger, aiming at +2.0 dB,
   that is capped. +2.0 dB is below `low_mid`'s own reference median
   (+3.39 dB) and close to its range floor. Simply raising the cap number
   would push `low_mid` from a mid-range measured value toward the bottom
   edge of a band where reference tracks spread over 8.7 dB — the exact
   "correcting hard toward a value no real record occupies" failure named
   in `docs/DOMAIN.md` §6. This needs a design decision about the
   `de_mud` aim point and the cap together, not a bigger cap number.

2. **The picture for 2–8 kHz harshness is two no-op stages, not one dormant
   one.** `adaptive_harshness.py` (STORY-010) is default-off *by design*
   (STORY-010's own acceptance criteria require this) and is not reachable
   from either shipped entrypoint — no flag in `master_track.bat`, no flag
   in `cli.py` — and it only implements 2 of STORY-010's 3 required
   classification branches (no reference-target-mismatch path; STORY-010's
   own TC-0103 has no corresponding code). Separately, `harshness_control`
   (STORY-012, `apply_stem_harshness_control`) is **always on, no config
   gate**, and runs unconditionally inside the stem-mastering stage — but
   on the Sunday Club run it produced zero actions (`harshness_control_actions: []`)
   because that run had stem separation off (`stem_runtime: null`), so the
   stage fell back to a single `"mix"` pseudo-stem, whose generic 2.5–5 kHz
   band-energy ratio never crossed its 1.25 trigger threshold. Also worth
   noting: the specific 2–5 kHz measurement the pipeline does expose
   (`presence_harsh`) is **not flagged**, before or after, on this track
   (deviation −0.16 dB before, +0.27 dB after) — the motivating track does
   not itself demonstrate excess energy in that specific band; the gap
   being closed here is the structural absence of any working correction
   path for `high_mid`/`high`/`air`, not a proven audible defect on this
   one file. `docs/DOMAIN.md` §4 separately rules out "metallic" character
   (transient smearing) as a mastering-fixable problem — only broadband
   excess energy is correctable; see requirements.md "Rejected as out of
   scope."

3. **No shimmer/air enhancement stage exists** — genuinely true;
   `hf_extension.py` is analysis-only (band-limit detection) and isn't
   even wired into `measure_all`/the report today, so no per-file band-limit
   is currently available to scope an air boost against. `docs/DOMAIN.md`
   §4 explicitly rules out boosting content above a file's actual band
   limit ("Silence. A shelf boost mostly amplifies the noise floor.") and
   Suno exports typically band-limit around 13–16 kHz (§2) — inside the
   nominal 10–24 kHz "air" band. `CLAUDE.md` §6.2 additionally records a
   *standing decision* that HF extension is "report-only unless justified
   by the actual signal" — any change here touches that decision and, per
   `CLAUDE.md`'s own preamble, must be raised and cleared, not silently
   worked around. There is also a live tension the story must not let
   surface late: STORY-007's artifact detector flags stationary whistles
   in exactly this frequency territory, and STORY-009's whistle-repair
   attempt (open defect DEF-009-001) was judged "highly destructive to the
   track" at the listening gate on real material. Any HF-lift approach
   risks amplifying the same artifacts the rest of the pipeline is trying
   to suppress.

4. **No intra-track dynamics-leveling stage.** Confirmed by absence: no
   compressor, multiband leveler, RMS rider, or gain-riding module exists
   anywhere in `stories/STORY-001/implementation/suno_mastering/mastering/`.
   The pipeline's only loudness-shaping stage (`loudness_limit.py`) does a
   single global gain solve to a target integrated LUFS plus a lookahead
   true-peak limiter — nothing addresses within-track loudness variation.
   The product owner separately measured 3-second-window loudness curves
   (pyloudnorm) on the reference source and the mastered output and found
   the loudness range/std essentially unchanged (source: 9.8 dB range /
   1.59 dB std; mastered: 10.1 dB / 1.54 dB) — this business-analyst pass
   did not independently re-run that measurement; it is cited as
   product-owner-reported evidence, consistent with the code-level finding
   that no stage exists that could have changed it.

Also surfaced but explicitly **not** in this story's scope: `targets.json`'s
hard −13.5 ±0.5 LUFS target (derived from only 3 reference tracks) may
itself be conservative relative to modern club-mastering norms. The product
owner clarified "volume normalization" in their original framing meant
item 4 (intra-track swings), not the integrated-loudness target. Re-deriving
the reference/target set is a materially larger, separate undertaking and
is left as a pointer for a future story.

## Contract
```
Consumes: targets.json (hard_targets, spectral_bands, de_mud policy);
          STORY-001 corrective_eq.py, adaptive_harshness.py, harshness_control.py
          (STORY-012), loudness_limit.py, and the seven-band/three-band
          frequency-balance measurements they read from;
          STORY-007's artifact_detection output (whistle/artifact evidence
          relevant to the item-3 HF tension);
          STORY-009's DEF-009-001 (open defect, HF-artifact risk precedent).
Produces: (a) a resolved policy for the low_mid de_mud cap/aim-point pair
          (and, separately, confirmation that sub's range-compliance cap
          is the correct, simpler case to relax); (b) a decision, not
          necessarily new code, on which of the two existing harshness
          paths (or a replacement) becomes the pipeline's actual working
          2–8 kHz correction, reachable from the shipped entrypoints;
          (c) either a narrowly-scoped, evidence-gated HF-lift design
          cleared through the CLAUDE.md §6.2 standing-decision process and
          Gate 1, or an explicit rejection recorded as such; (d) a design
          for an intra-track dynamics-leveling stage compatible with the
          existing hard DR-floor/true-peak solver constraints.
Consumed by: software-architect (architecture.md); mastering-engineer
          Gate 1 review (mandatory for item 3 given the DEF-009-001
          precedent, and for item 2 given the CLAUDE.md §6.2 standing
          decision); python-developer / test-case-writer; STORY-025's
          `evaluate_quality_review` (before/after artifact-density and
          spectral-shift comparison already consumes this pipeline's
          output and must see any new stage's actions).
```

## Scope
- In scope:
  - Resolving the `low_mid` de-mud cap/aim-point interaction (and the
    simpler `sub` range-compliance cap) so a track measuring outside
    reference range or above the de-mud threshold gets corrected toward a
    justified target, not silently truncated
  - Establishing a single, reachable, working correction path for
    2–8 kHz broadband excess energy (resolving which of `adaptive_harshness`
    / `harshness_control` / a replacement is authoritative, and making it
    reachable from `master_track.bat`/`cli.py`)
  - A narrowly-scoped HF-lift (air/shimmer) design, gated on a per-file
    measured band limit and cleared through Gate 1 and the CLAUDE.md §6.2
    standing-decision process — or an explicit, recorded rejection
  - An intra-track dynamics-leveling stage design, compatible with the
    existing hard DR-floor and true-peak constraints in the loudness
    solver
- Out of scope (see requirements.md for full detail):
  - Any change to the −13.5 ±0.5 LUFS integrated target or the reference
    set it's derived from
  - Fixing or re-litigating DEF-009-001 itself (STORY-009's own defect)
  - "Metallic" transient character correction (DOMAIN.md §4 — not
    mastering-fixable)
  - Boosting content above a track's actual measured band limit
  - GUI exposure (STORY-G1)

## Product goal
Make the mastering chain's corrective behaviour match its own measured
evidence across all the bands and dynamics it already reports on, instead
of leaving sub/low_mid as the only bands and integrated LUFS as the only
loudness dimension that actually get corrected.

## Revision history
- 2026-08-20: Story created from product-owner review of a real mastered
  track and `targets.json`, independently re-verified against the pipeline
  source and the actual report JSON by the business-analyst; see
  `requirements.md` for the full grounding and the corrections made to the
  original diagnosis (item 2 restated as two no-op stages, not one dormant
  one; item 1 restated as a per-band aim-point problem, not a uniform
  cap-raise; item 3 scope narrowed by the absence of any wired band-limit
  measurement and by the CLAUDE.md §6.2 standing decision).
