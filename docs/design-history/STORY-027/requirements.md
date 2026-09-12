# STORY-027 — Requirements: Close the spectral and dynamics correction gaps outside sub/low_mid

## Contract
```
Consumes: targets.json (hard_targets, spectral_bands incl. correction_cap_db
          on sub/low_mid only, de_mud policy, no correction_cap_db on
          high_mid/high/air); the current pipeline stage implementations
          — corrective_eq.py, adaptive_harshness.py (STORY-010),
          harshness_control.py (STORY-012, via
          stories/STORY-012/implementation), loudness_limit.py — and the
          frequency-balance measurements they consume (three-band
          presence_harsh/low_mid_mud/low_end exposed in the report; the
          internal seven-band measurement computed transiently at
          pipeline.py's Stage [4b] but not currently exposed in the
          report); STORY-007's artifact_detection output
          (STATIONARY_WHISTLE evidence, relevant to item 3's risk);
          STORY-009's open defect DEF-009-001 (HF-artifact-amplification
          precedent); CLAUDE.md §6.2 (HF extension standing decision).
Produces: (a) a resolved cap/aim-point design for low_mid de-mud and a
          confirmed relaxation for sub's range-compliance cap; (b) a
          decision on the single authoritative 2–8 kHz correction path,
          reachable from both shipped entrypoints; (c) either a narrowly
          evidence-gated HF-lift design cleared through Gate 1 and the
          CLAUDE.md §6.2 process, or an explicit rejection; (d) an
          intra-track dynamics-leveling stage design compatible with the
          existing hard DR-floor/true-peak solver constraints. None of
          this document's output is code or a targets.json edit — it is a
          requirements specification for the architect.
Consumed by: software-architect (architecture.md); mastering-engineer
          Gate 1 (mandatory for items 2 and 3 — see below); python-
          developer / test-case-writer; qa-automation-engineer; STORY-025's
          `evaluate_quality_review`, which already consumes this pipeline's
          before/after audio and artifact-detection output and must be
          able to see and evaluate any new stage's actions.
```

## Restated intent
The mastering chain currently only meaningfully corrects two of the seven
measured spectral bands (`sub`, `low_mid`) and one dimension of loudness
(integrated LUFS via a single global gain solve). This story closes four
gaps in that coverage, each independently diagnosed from a real mastered
track and re-verified here against the pipeline source: (1) the `low_mid`
de-mud correction is capped well short of its own aim point; (2) the two
existing paths that could correct broadband 2–8 kHz excess both produce no
output on real material, for different reasons; (3) no stage adds
high-frequency air/shimmer content, and DOMAIN.md constraints narrow what
such a stage could legitimately do; (4) no stage addresses within-track
loudness swings — only the overall integrated level is controlled. This
document specifies the problem and the constraints on each; it does not
choose an algorithm, a cap value, or a filter design (architect's job).

---

## Source-grounding: what was independently verified

All four items below were re-checked directly against
`artifacts/Sunday Club_mastered_report.json` (2026-08-20 run),
`targets.json`, and the named source files — not taken on the product
owner's word alone. Three of the four original diagnoses needed
correction; all three corrections are load-bearing for the acceptance
criteria below.

### Finding 0 — the report does not currently expose the seven-band measurement item 1 needs to verify against
`pipeline.py`'s comment at Stage [4b] is explicit that the three-band
`frequency_balance` block (`low_end`/`low_mid_mud`/`presence_harsh`, the
only spectral data present in `before`/`after` in the report) and the
seven-band scheme used internally for corrective EQ **use different
frequency ranges for the same band name**: three-band `low_mid_mud` covers
200–500 Hz against a `reference_db` of −3.0, while seven-band `low_mid`
(what `de_mud`/`correction_cap_db` in `targets.json` actually govern)
covers 120–500 Hz against a reference *range* of `[-0.145, 8.522]` dB re
mid. **`low_mid_mud` is not a substitute for seven-band `low_mid` and must
not be used to verify a de-mud correction.** Confirmed directly: grepping
the report JSON for `"seven_band"`, `"high_mid"`, `"high"`, and `"air"`
returns no matches at all — `measure_seven_band_balance` runs at
pipeline.py:337 and computes every band, but only `sub`/`low_mid`/`mid`
are extracted into `pre_band_levels` for corrective EQ; `high_mid`/`high`/
`air` values are computed and then discarded, never reaching the report.
**This is a prerequisite for items 1 and 2, not a detail**: without
exposing the seven-band `relative_db` (pre- and post-correction) in the
report, there is no way to verify item 1's low_mid correction or evaluate
item 2's `high_mid`/`high` evidence against the bands `targets.json`
actually defines ranges for.

### Finding 1 — `low_mid`'s cap problem is a de_mud/aim-point problem, not a uniform "cap too low" problem
From `eq_actions` in the report:
```
sub:     source_db=6.83, aim_point_db=1.94 (range max),  applied=-2.0, cap_reached=true
low_mid: source_db=6.54, aim_point_db=2.00 (de_mud aim), applied=-2.0, cap_reached=true
```
(Both `source_db` values here are the seven-band measurement — the same
one Finding 0 shows is computed but not exposed in the report; this is the
`pre_band_levels` value `corrective_eq.py` actually acts on, distinct from
the report's three-band `low_mid_mud`.)

`targets.json`'s `spectral_bands.low_mid.range_db_re_mid` is
`[-0.145, 8.522]` — **`low_mid`'s +6.54 dB source measurement is inside its
own reference range.** It is the separate `de_mud` trigger
(`flag_threshold_db_above_mid: 4.0`, firing because 6.54 > mid + 4.0) that
aims at `de_mud.correction_aim_point_db` = 2.0, a value *below* `low_mid`'s
reference median (3.39 dB re mid) and near the range floor. `sub`, by
contrast, genuinely sits outside its own range
(`[-3.747, 1.944]` vs. source 6.83) — a straightforward range-compliance
case. Raising `correction_cap_db` uniformly would let `low_mid` swing from
a mid-range measured value to near the bottom edge of a band where the
three contributing reference tracks spread 8.7 dB apart — precisely the
"correcting hard toward a value no real record occupies" failure
`docs/DOMAIN.md` §6 names, on a band whose spread already exceeds that
section's ~4 dB disagreement threshold. `correction_cap_db: 2.0` is itself
an asserted policy constant carried over from STORY-006 ("reference
spectral agreement is poor"), not independently reference-derived — this
document does not treat it as sacred, but any replacement must be argued,
not asserted (`CLAUDE.md` §7 — "hardcoded round-number targets" and
"asserting a baseline constant without derivation" are both named
known-wrong patterns).

Also note (from `corrective_eq.py`'s own docstring): the *delivered*
low_mid correction is further attenuated to roughly 0.75× the logged
`applied_db` by the peaking-bell's energy-weighted response across the
120–500 Hz band — the effective corrected outcome is smaller than even the
capped 2.0 dB figure suggests. The architect/QA should quantify
under-correction from the post-master seven-band measurement (once exposed
per Finding 0), not from `applied_db`.

### Finding 2 — two no-op stages, not one dormant one
- `adaptive_harshness.py` (STORY-010): `AdaptiveHarshnessConfig.enabled`
  defaults to `False`. STORY-010's own acceptance criteria require this
  ("The stage is default-off unless explicitly enabled") — it is a
  deliberate default, not an accidental one. However, neither
  `master_track.bat` nor `cli.py` exposes any flag to turn it on, so the
  intentional "off by default" has hardened into **unreachable from either
  shipped entrypoint**. Separately, it implements only 2 of STORY-010's 3
  required classification branches (`broad_shelf`, `narrow_cut`) — the
  third, "reference-target adjustment when the material is consistently
  above the curve" (STORY-010 requirements.md item 5, test-cases.md
  TC-0103), has no corresponding code. No `defects.md` or recorded QA run
  exists for STORY-010 at all.
- `harshness_control.py` (STORY-012, `apply_stem_harshness_control`): **no
  config gate** — called unconditionally inside
  `_apply_story_11_17_stem_mastering` on every run. On the Sunday Club
  report it produced zero actions
  (`"harshness_control_actions": []`) for two independent, compounding
  reasons: (a) that run had `stem_runtime: null` — stem separation was
  off, so `stems = {"mix": audio}` and `_band_edges("mix")` fell through
  to the generic `(2500, 5000)` Hz default rather than a stem-specific
  band; (b) the whole-signal FFT band-energy-ratio trigger
  (`ratio < 1.25` → no-op) never fired on that signal shape. Note: the
  shipped `master_track.bat` entrypoint *does* pass `--split-stems` by
  default — the specific report used for this diagnosis was generated
  without it (directly via `python -m suno_mastering` or an older
  invocation), so this evidence reflects the **stereo-fallback path**, not
  necessarily the product's actual default. The architect must determine
  and state which of stem-on / stem-off / both this story's fix must cover.
- The one 2–5 kHz measurement actually exposed in the report
  (`presence_harsh`) is **not flagged**, before or after, on Sunday Club
  (deviation −0.16 dB pre, +0.27 dB post — both inside the implicit
  no-flag tolerance). The structural gap (no reachable, working correction
  path for `high_mid`/`high`/`air`) is real and verified; a proven audible
  defect specifically in the 2–5 kHz band *on this track* is not — the
  product owner's "metallic/harsh" impression may reflect content in the
  unmeasured 5–10 kHz / 10–24 kHz bands (currently invisible in the report
  per Finding 0), transient character (see Rejected, below), or a
  different track. This story targets the structural gap, not a specific
  measured deviation on Sunday Club.

### Finding 3 — no HF-lift stage exists, and DOMAIN.md narrows what one could legitimately do
`hf_extension.py` performs band-limit *detection* only (cliff detection
per STORY-004's corrected method) and is not called anywhere inside
`analysis.measure_all` — confirmed by absence in both the module's own
call sites and the report JSON, which has no `hf_band_limit`/`hf_extension`
field at all. **There is currently no per-file measured band-limit
available anywhere in the pipeline's output to scope an air/shimmer boost
against.** This is a prerequisite, not a detail: `docs/DOMAIN.md` §2
records Suno/generative exports typically band-limiting around 13–16 kHz —
inside the nominal "air" band (10–24 kHz per `targets.json`). §4's Cannot
table is explicit: "Content above the band limit — Silence. A shelf boost
mostly amplifies the noise floor." `CLAUDE.md` §6.2 records HF extension
as a **standing decision**: "Report-only unless justified by the actual
signal." Per `CLAUDE.md`'s own preamble, a standing decision that blocks a
task must be raised as an `Architectural` defect, not silently worked
around — this document does not self-grant an exception to §6.2.

### Finding 4 — no dynamics-leveling stage exists; confirmed by absence
Every file in
`stories/STORY-001/implementation/suno_mastering/mastering/` was checked;
none implements a compressor, multiband leveler, RMS gain-rider, or
equivalent. `loudness_limit.py` performs exactly one global gain solve
(bisection to a target integrated LUFS, subject to a hard DR-floor
constraint and a hard true-peak ceiling) plus a lookahead limiter for
peak safety — no stage anywhere addresses loudness variation *within* a
track. The product owner's 3-second-window loudness-curve measurement
(pyloudnorm; source 9.8 dB range / 1.59 dB std, mastered 10.1 dB / 1.54 dB,
essentially unchanged) is **cited as product-owner-reported evidence, not
independently re-run by this business-analyst pass** — it is consistent
with, and explained by, the code-level finding that no stage exists that
could have altered it.

---

## Rejected as out of scope

- **"Metallic" character correction as part of item 2.** `docs/DOMAIN.md`
  §4: "Transient smearing / metallic cymbals — Fast attack was never
  rendered; information is absent, not masked." If the product owner's
  "metallic" impression is transient-smear character rather than broadband
  2–8 kHz excess energy, mastering-stage EQ cannot fix it — that must be
  reported back as an unfixable-at-this-stage finding, not routed into a
  more aggressive EQ move. Only broadband/narrow-band *excess energy*
  correction (STORY-010's original scope) is in play here.
- **Boosting content above a track's actual band limit (item 3).**
  `docs/DOMAIN.md` §4 — a shelf boost above the band limit "mostly
  amplifies the noise floor." Any HF-lift design must be scoped to content
  *below* the per-file measured cutoff only.
- **Any HF-lift design that does not first establish a wired, reported
  per-file band-limit measurement.** Without it there is no way to
  distinguish "lifting present-but-attenuated content" from "amplifying
  silence/noise floor" — this is a hard prerequisite for item 3, not an
  optional nice-to-have.
- **Silently working around `CLAUDE.md` §6.2's standing decision** that HF
  extension is report-only. Item 3 requires either an explicit,
  Gate-1-reviewed exception (parallel to how `docs/DOMAIN.md` §4's narrow
  whistle-repair exception was granted) or the item does not proceed to
  implementation.
- **Amplifying HF content that overlaps STORY-007's `STATIONARY_WHISTLE`
  evidence or otherwise risks the failure mode recorded in DEF-009-001**
  ("highly destructive to the track" at the listening gate, even after an
  OLA bug fix and a harmonic guard). An HF-lift stage must not boost
  frequencies at or near confirmed-artifact coordinates.
- **Changing the −13.5 ±0.5 LUFS integrated target, or the 3-track
  reference set it's derived from.** Explicitly out of scope per the
  product owner's own clarification — flagged only as a pointer for a
  future story, not folded in here.
- **Re-litigating or fixing DEF-009-001 itself.** That remains STORY-009's
  own open defect.

---

## Acceptance criteria

### Prerequisite — reporting gap (blocks verification of items 1 and 2)
0. Given corrective EQ or any item-2 correction runs, the pipeline's
   before/after report must expose the seven-band `relative_db` for every
   band (`sub`, `low`, `low_mid`, `mid`, `high_mid`, `high`, `air`) —
   currently computed at pipeline.py Stage [4b] but discarded after
   extraction into `pre_band_levels` (Finding 0). This is a reporting
   change (surfacing an existing computation), not new DSP, and it must
   land before AC3 or AC5 can be evaluated against real measurements. The
   existing three-band `frequency_balance` block (`low_end`/`low_mid_mud`/
   `presence_harsh`) must remain unchanged and must not be conflated with
   or substituted for the seven-band figures — they measure different
   frequency ranges under overlapping names (Finding 0).

### Item 1 — low_mid / sub correction cap and aim point
1. Given a track whose `sub` band measures outside `targets.json`'s
   `sub.range_db_re_mid`, when corrective EQ runs, then the applied
   correction reaches the nearer range edge (or the architect's justified
   replacement cap), and the pipeline reports whether the cap was the
   limiting factor.
2. Given a track whose `low_mid` band triggers `de_mud` (source > mid +
   `flag_threshold_db_above_mid`), when corrective EQ runs, then the
   architect must state, with justification tied to `low_mid`'s reference
   range and spread (8.7 dB), what the `de_mud` aim point and its
   associated cap should be — a design decision, not merely "raise the
   existing 2.0 dB cap" (Finding 1). The resulting aim point must not sit
   below `low_mid`'s reference range floor unless explicitly justified.
3. Given the same synthetic/real test case used to diagnose this gap
   (Sunday Club: seven-band `low_mid` source +6.54 dB, de_mud aim +2.0 dB),
   when the revised policy runs, then the **post-master `after`
   seven-band measurement** (exposed per AC0; not the three-band
   `low_mid_mud` figure, which is a different frequency range — Finding 0;
   and not the logged `applied_db`, per Finding 1's ~0.75% delivery-
   efficiency note) must land measurably closer to the de_mud aim point
   than the current −2.0 dB cap allows, and the amount of remaining gap
   (if any) must be explicit in the report.
4. Given a track within range on both `sub` and `low_mid` and not
   triggering `de_mud`, when corrective EQ runs, then no correction is
   applied (negative control, unchanged from STORY-006's existing
   behaviour).

### Item 2 — 2–8 kHz broadband harshness correction path
5. Given the pipeline runs (stem-on or stem-off, per whatever the
   architect determines this item must cover — Finding 2), when broadband
   2–8 kHz excess energy is present by the existing measurement definition
   (three-band `presence_harsh`, and/or the seven-band `high_mid`/`high`
   figures once exposed per AC0 — architect's choice of evidence, but it
   must be a figure the report actually surfaces, not an internal-only
   value), then exactly one authoritative correction path fires and is
   reachable from both `master_track.bat` and `cli.py` — not a
   config-only flag with no entrypoint exposure.
6. Given the architect chooses to retain, replace, or merge
   `adaptive_harshness.py` and/or `harshness_control.py`, when the
   decision is made, then it must explicitly resolve: (a) which stage is
   authoritative going forward; (b) whether the other is retired,
   deprecated, or kept as a documented fallback; (c) whether
   `harshness_control`'s stem-name-based band selection (`_band_edges`)
   is adequate when stem separation is off and stems fall back to a single
   `"mix"` pseudo-stem, or needs a distinct stereo-sum band definition.
7. Given a track with no broadband 2–8 kHz excess (matching Sunday Club's
   actual `presence_harsh` measurement — Finding 2), when the corrected
   pipeline runs, then no correction fires (negative control) — this
   story must not introduce a correction that fires on already-compliant
   material.
8. Given STORY-010's original 3-way classification (broad shelf / narrow
   cut / reference-target mismatch), when the resolved stage is specified,
   then the architect must state explicitly whether all three branches are
   in scope for this story or whether the reference-target-mismatch branch
   remains unimplemented, and why.

### Item 3 — HF-lift (air/shimmer) — conditional scope
9. **Prerequisite, blocking implementation of any lift behaviour**: a
   per-file measured band-limit (via `hf_extension.py` or equivalent) must
   be wired into the pipeline's measurement/report output before any
   HF-lift design may act on a track. Until this exists, item 3 may only
   proceed as far as a design + Gate 1 review, not implementation.
10. Given the CLAUDE.md §6.2 standing decision ("HF extension: report-only
    unless justified by the actual signal"), when this story proposes any
    HF-lift behaviour, then it must be raised and cleared as an explicit,
    scoped exception (parallel in form to `docs/DOMAIN.md` §4's whistle-
    repair exception) before implementation — not silently overridden.
11. Given a track's measured band limit, when an HF-lift (if approved)
    runs, then it must not add or boost energy above that measured cutoff
    (Rejected, above) — boosting only content demonstrably present below
    the cutoff is the only permitted behaviour.
12. Given STORY-007's `STATIONARY_WHISTLE` evidence for a track, when an
    HF-lift (if approved) runs, then it must not boost frequencies at or
    near confirmed-artifact coordinates — mirroring the caution
    DEF-009-001 established for HF-territory processing generally.
13. Given all of AC9–12 are not satisfiable within this story's evidentiary
    and process constraints, the architect and Gate 1 reviewer may
    reject item 3 outright as out of scope for implementation while items
    1, 2, and 4 proceed independently — this criterion exists so a Gate 1
    rejection of the air-lift does not block the rest of the story.

### Item 4 — intra-track dynamics leveling
14. Given the existing hard constraints in `loudness_limit.py`
    (`achieved_dr >= max(dr_floor, source_dr - dr_max_reduction_db)` and
    true-peak ceiling), when a dynamics-leveling stage is designed, then
    the architect must state where it sits in the chain relative to the
    existing solver and how it interacts with — without silently
    violating — both hard constraints.
15. Given the product owner's window-based loudness-range/std evidence
    (3 s windows, pyloudnorm) versus the pipeline's existing TT-DR
    (crest-factor-based) dynamic-range metric, the architect must state
    explicitly which metric (or both) gates this item's acceptance — a
    leveler can reduce loudness-range/std while barely moving TT DR, or
    vice versa; this document does not assume they move together.
16. Given a track with genuinely uniform section-to-section loudness (no
    swings beyond the architect's chosen tolerance), when the leveling
    stage runs, then it must not apply audible gain-riding (negative
    control) — this must not become a blanket compressor applied
    regardless of source behaviour (`CLAUDE.md` §7 — "blanket global
    correction on one stereo sum ignores actual signal structure").
17. Given `CLAUDE.md` §3's stem-first product direction, the architect
    must state whether this stage operates on the stereo sum, per-stem, or
    both, and justify the choice against the same stem-vs-sum question
    raised for item 2 (Finding 2) — these should not be decided
    inconsistently within one story.
18. Given a track processed with this stage, when `detect_artifacts` is
    re-run, then `overall_artifact_density_score` and flag counts must not
    increase relative to a run without this stage (regression guard,
    consistent with the pattern established in STORY-026's AC11/AC11a).

### Cross-cutting
19. Every new or materially-changed correction (item 0's reporting change;
    items 1, 2, and 4; item 3 only if approved) must be logged in the
    report with before/after values and the evidence basis for firing,
    consumable by STORY-025's `evaluate_quality_review` and by QA —
    mirroring the existing
    `eq_actions`/`adaptive_harshness_actions`/`harshness_control_actions`
    pattern already in the report schema.
20. A mastering-engineer Gate 1 review is mandatory before implementation
    for items 2 (CLAUDE.md §6.2-adjacent reachability change) and 3
    (CLAUDE.md §6.2 standing decision + DEF-009-001 precedent). Items 1
    and 4 should also pass through Gate 1 per the existing project
    process but do not carry the same standing-decision/precedent
    dependency.
21. Automated metrics (AC3, AC7, AC18, etc.) are necessary but not
    sufficient. Consistent with `CLAUDE.md` §5 and the precedent set by
    DEF-009-001 (metrics passed, listening gate failed), a human listening
    check on real material (at minimum Sunday Club) is required before any
    of items 1, 2, or 4 is accepted as resolving the gap it targets, and
    is an unconditional prerequisite for item 3 if approved at all.

---

## Audio quality targets
No new integrated-LUFS, true-peak, or overall DR target is introduced.
Item 1 operates within `targets.json`'s existing `spectral_bands` ranges
and the `de_mud` policy — this document does not assert a replacement
`correction_cap_db` or `de_mud.correction_aim_point_db` value; both are
open questions for the architect, to be justified against the reference
spread, not asserted as round numbers (`CLAUDE.md` §7). Item 2 does not
introduce new spectral targets for `high_mid`/`high`; it makes the
existing `presence_harsh`/seven-band evidence actionable via a working,
reachable stage — noting that `high_mid`/`high`/`air` currently carry no
`correction_cap_db` in `targets.json` at all (see Open Questions). Item 3,
if approved, introduces no fixed dB lift value here — any magnitude is an
architect/Gate 1 decision bounded by AC9–12. Item 4 introduces no fixed
leveling ratio/window/attack-release values here — all are open questions.

## Input/output assumptions
- Input: the pipeline's in-flight audio buffer at whichever stage
  position(s) the architect determines for each item, consistent with the
  existing chain order (`docs/DOMAIN.md` §6: corrective EQ → transient/
  harshness → stereo → dynamics/glue → loudness/limiting → dither).
- Items 1 and 2 read from the existing three-band (`frequency_balance`)
  and seven-band spectral measurements — the latter must first be exposed
  in the report per AC0/Finding 0.
- Item 3, if approved, additionally requires wiring `hf_extension.py`'s
  band-limit detection into `measure_all`/the report (a new dependency
  this story surfaces but does not itself specify in detail).
- Item 4 requires no new external input beyond the existing audio buffer;
  it may reuse or extend existing loudness-measurement code
  (`analysis/loudness.py`) for window-based measurement if the architect
  chooses that metric (AC15).
- Output: a mastered buffer plus extended report fields per AC0/AC19, in
  the existing report schema — no new file-artifact type.
- This story must state, per item, whether its fix applies to the
  stem-separation-enabled path, the stereo-fallback path, or both (Finding
  2, AC6, AC17) — Story.md's background evidence was generated on the
  stereo-fallback path specifically and must not be assumed representative
  of the shipped stem-first default without restating for that path too.

## Explicit out-of-scope
- Changing the integrated LUFS target or reference set (see Rejected,
  above).
- "Metallic"/transient-smear character correction (DOMAIN.md §4).
- Any HF-lift above a track's measured band limit.
- Re-litigating DEF-009-001.
- Choosing specific filter designs, cap values, aim points, leveling
  algorithms, attack/release times, or window sizes — architect/Gate 1
  decisions throughout.
- GUI exposure (STORY-G1 is separate).
- Deriving a new reference/target set for loudness (flagged as a pointer
  for a future story only).

## Non-functional requirements
- Reproducibility: bit-identical output for identical input + config,
  consistent with the rest of the pipeline's existing guarantee.
- Every new correction path must be reachable from both shipped
  entrypoints (`master_track.bat`, `cli.py`) — a repeat of item 2's own
  root cause (an existing stage that is technically config-gated but has
  no way to be turned on in practice) must not recur for any new stage
  this story adds.
- Failure posture: consistent with the existing pipeline, no silent
  no-op reported as "run" (mirrors STORY-026's AC6 precedent).
- No new processing-speed/throughput target is specified here.
- A documented human listening-gate result is a release-readiness
  requirement (AC21), not optional QA colour — consistent with the
  precedent DEF-009-001 established.

## Open questions
1. What is the justified `de_mud` aim point / cap pair for `low_mid`,
   given its 8.7 dB reference spread? Not asserted here (Finding 1, AC2).
2. What replacement (if any) for `sub`'s `correction_cap_db` is justified,
   and by what derivation rather than a round number?
3. Which of `adaptive_harshness.py` / `harshness_control.py` becomes
   authoritative for item 2, and what happens to the other? (AC6.)
4. Does item 2's fix need to work correctly with stem separation both on
   and off, or is one path acceptable as the primary target with the
   other explicitly deferred? (Finding 2, AC5/AC6.)
5. Is STORY-010's third classification branch (reference-target mismatch)
   in scope for this story, or explicitly deferred? (AC8.)
6. Can `CLAUDE.md` §6.2's standing decision be extended to permit a
   scoped HF-lift exception, and if so, on what evidentiary basis
   parallel to `docs/DOMAIN.md` §4's whistle-repair exception? Unresolved
   here — routed to Gate 1 (AC10).
7. What per-file band-limit detection method/threshold gates item 3's
   permitted lift range, and is `hf_extension.py` as currently implemented
   sufficient, or does it need its own revalidation before being wired
   into reporting? (AC9.)
8. Which metric (window-based loudness range/std, TT DR, or both) gates
   acceptance of item 4's leveling stage? (AC15.) Not decided here.
9. Does item 4 operate on the stereo sum, per-stem, or both? (AC17.)
10. What tolerance defines "genuinely uniform" for item 4's negative
    control (AC16)? Not asserted here.
11. Should items 1/2/4's Gate 1 reviews be combined into a single review
    pass (since they share the same source track and report) or run
    separately? Not decided here — a coordination question for the
    architect/Gate 1 reviewer, not a technical requirement.
12. If item 2's resolved stage corrects `high_mid` and/or `high` against
    `targets.json` ranges, someone must derive a `correction_cap_db` for
    those bands (they currently have none — only a `range_db_re_mid` and
    `classification: "informational"`) and change their `classification`
    to something other than `informational`. This is a `targets.json`
    edit this document cannot make and the architect cannot make either
    (per this project's process) — flagged here as a target-derivation
    dependency that must be routed to whichever story/process owns
    `targets.json` changes, not silently absorbed into STORY-027's
    implementation.

## Revision history
- 2026-08-20: Initial requirements.md written for STORY-027, following
  independent re-verification of the product owner's four-item diagnosis
  against `artifacts/Sunday Club_mastered_report.json`, `targets.json`,
  and the named pipeline source files. Three corrections made to the
  original diagnosis: (1) item 1 restated as a `de_mud` aim-point problem
  specific to `low_mid`, not a uniform cap-too-low problem shared with
  `sub`; (2) item 2 restated as two independently no-op stages
  (`adaptive_harshness.py`, dormant by design but unreachable from either
  entrypoint; `harshness_control.py`, always-on but no-op on the
  stereo-fallback path used in the motivating evidence) rather than one
  simply-disabled stage, with a note that the motivating track's own
  `presence_harsh` measurement is not flagged; (3) added Finding 0 and
  AC0 — the report does not currently expose the seven-band measurement
  item 1's own diagnosis depends on, and the three-band `low_mid_mud`
  field (200–500 Hz) is a different band than seven-band `low_mid`
  (120–500 Hz, what `targets.json`'s `de_mud`/`correction_cap_db` actually
  govern) and must not be substituted for it when verifying AC3. Item 3
  narrowed to a conditional, Gate-1-gated scope given the absence of any
  wired band-limit measurement and the CLAUDE.md §6.2 standing decision.
  Item 4 evidence attributed explicitly to the product owner's own
  measurement, not independently re-run here. Added Open Question 12
  (missing `correction_cap_db` on `high_mid`/`high`/`air`).
