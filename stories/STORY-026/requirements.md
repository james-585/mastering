# STORY-026 — Requirements: Spectral de-noise pre-processor for stationary tonal infestation

## Contract
```
Consumes:  raw input audio; STORY-007's ArtifactDetectionResult (specifically
           STATIONARY_WHISTLE flags: frequency_hz, timestamp_start_s/end_s,
           confidence_score, prominence_db, q_factor — the same
           `Measurements.artifact_detection.artifact_flags` field STORY-009
           wired into `repair_whistles`), the existing seven-band spectral
           analysis (for harmonic-content awareness alongside the existing
           STORY-007/STORY-009 harmonic guards).
           CORRECTED from Story.md's original draft: Story.md's contract
           also claims this story consumes "quiet-section ... localization"
           from STORY-001's artifact_detection output. No such output
           exists (see Finding 1 below) — this is a contract gap the
           architect must close, not a silent reconciliation.
Produces:  a de-noised audio buffer plus a noise-profile report (bands/
           frequencies targeted, magnitude of reduction, source sections
           used for profile learning, harmonic-guard suppressions), inserted
           as a new stage before any downstream artifact-repair stage.
Consumed by: the rest of the mastering chain, which receives the de-noised
           buffer as its input; STORY-025's grounded quality review, which
           needs a before/after `overall_artifact_density_score` comparison
           (STORY-025 AC4) — see "STORY-025 handoff" below for what this
           story must actually hand over versus what remains STORY-025's own
           job.
           CORRECTED: `whistle_repair.py` (STORY-009) is **not** a
           confirmed active downstream consumer. It is currently disabled
           by default in production (`RepairWhistlesConfig.enabled = False`,
           `master_track.bat` runs with `--no-detect-whistles
           --no-repair-whistles` since commit `900f9bd`) and carries an
           open defect, DEF-009-001, recording that its output was judged
           "highly destructive to the track" at the listening gate. Whether
           `whistle_repair.py` remains a disabled/no-op layer, is
           re-enabled for whatever residual whistles this new stage
           legitimately cannot reach, or is retired outright is an open
           question for the architect (Open Question 4a) — not settled by
           this document.
```

## Restated intent
Add an offline pre-processing stage that estimates the spectral profile of
sustained, stationary tonal noise from evidence-confirmed sections of a
track and subtracts it (Wiener filtering or an equivalent spectral-
subtraction method), running before the rest of the mastering chain, so
that dense, sustained tonal infestation gets addressed at all — not "more
effectively than the current notch-based repair," but in a case where the
current notch-based repair is disabled in production and has an open
defect recording it as perceptually destructive on real material at almost
any useful scale of application. This document specifies what the stage
must do and what it must not touch; it does not choose an algorithm, a
tunable parameter, or an insertion point inside the pipeline (architect's
job).

**This story does not get a free pass because the method is different.**
The central failure recorded against `whistle_repair.py` (DEF-009-001) is
not an OLA bug or a notch-width problem — those were fixed and the failure
persisted. It is that **the detector-to-repair contract cannot distinguish
AI-generation tonal artifacts from wanted musical content** (sustained synth
tones, pad harmonics, bass fundamentals) at the frequencies it flags. Wiener
subtraction consuming the same `STATIONARY_WHISTLE` flags — or, worse, raw
spectral content from a "quiet section" with no detector gating at all —
faces the **identical** ambiguity. Nothing about spectral subtraction as a
method makes a frequency more identifiable as artifact-vs-musical than a
notch filter does; only better *evidence* would. This is the central risk
for this story, addressed throughout below, not a side note.

---

## Source-grounding: what exists today vs. what the story assumes

### Finding 0 — the story's premise about the state of `whistle_repair.py` was wrong in the original draft; corrected here
Read directly from `stories/STORY-009/defects.md`, `DEF-009-001` (status:
Open):
- After the OLA overlap-normalisation bug was fixed, `repair_whistles` was
  re-tested on "Sunday Club" (2026-08-18): 79% artifact-count reduction,
  LUFS held within 0.01 LU, DR improved by 2. **Listening gate: FAIL.**
  Output was characterised as **"highly destructive to the track."** Root
  cause recorded: "the STATIONARY_WHISTLE detector cannot distinguish AI
  generation artefacts from musical content (sustained synth tones, pad
  harmonics)... A narrowband notch at the correct frequency is
  arithmetically correct but perceptually destructive when applied to a
  musical note rather than a true glitch."
- STORY-009 then added a harmonic guard (§6b, 2026-08-20 e2e result, same
  defect file): on Sunday Club, 439 confidence/prominence-gated flags went
  in; **420 (95.7%) were suppressed** by the guard as likely-musical; only
  **19 were forwarded** to the notch stage. Post-master `STATIONARY_WHISTLE`
  count: 428 (pre: 452) — i.e. even the 19 forwarded notches barely moved
  the total flag count, and the guard's own suppression rate confirms the
  detector is finding mostly musically-plausible frequencies, not isolated
  glitches.
- Even among the 19 forwarded, the defect log records six sub-500 Hz
  notches (166/166/190/196/246/494 Hz) flagged as still-uncertain
  ("harmonic guard found no fundamental below 166 Hz... may be a genuine AI
  encoder artifact at a musical pitch class. The listening gate at those
  timestamps is the decision point") — the defect is explicitly **not
  closed** pending a further listening pass on those specific timestamps.
- Consequence for production config: commit `900f9bd` set
  `--no-detect-whistles --no-repair-whistles` as the `master_track.bat`
  default, because running detection without a safe, actionable repair
  path only inflated reported artifact counts (202 → 476) with no
  correction benefit. `RepairWhistlesConfig.enabled` defaults to `False` in
  `config.py` today.

**Correction to this document's own earlier draft**: an earlier version of
this requirements.md treated `whistle_repair.py` as an active downstream
fallback layer ("whistle_repair.py remains the fallback/spot-repair layer
for anything this stage does not fully resolve") and read the "Sunday Club"
mastered-report action list as inconclusive-but-neutral evidence about
whistle_repair's effectiveness. Both readings undersold the actual, already-
documented state: `whistle_repair.py` is disabled by default, and the one
documented attempt to run it at meaningful scale (439 candidate flags) was
judged destructive by a human listener even after both the OLA bug and a
harmonic guard were fixed/added. **This story is not "more sophisticated
than a working system."** It is addressing a capability gap that is
currently unmet — the 420 (95.7%) of flags the harmonic guard correctly
judged too risky to notch, plus whatever fraction of the disabled-by-
default state reflects a genuinely unsolved detector-to-repair contract
problem, not merely an implementation bug in one method.

### Finding 1 — "quiet-section localization" does not exist in artifact_detection.py
Read directly from `stories/STORY-001/implementation/suno_mastering/analysis/artifact_detection.py`:
the module detects `SMEARED_TRANSIENT`, `DIGITAL_HAZE`, `STATIONARY_WHISTLE`,
and `PHASE_SWISH`. None of these functions identify or localize "quiet
sections" of a track. The only near-silence/quiet-passage logic in the
codebase is `stories/STORY-001/implementation/suno_mastering/analysis/silence.py`
(`block_rms_db`, `active_block_mask`, `extract_active_audio`), and it exists
for the **opposite** purpose: excluding near-silent blocks from spectral
measurement so they don't skew analysis, not identifying quiet blocks as a
usable noise-learning source.

Story.md's Contract line asserts this story consumes "quiet-section ...
localization" from STORY-001's artifact_detection output as if it already
exists. It does not. This is a contract gap — see Acceptance Criteria and
Open Questions below.

### Finding 2 — `silence.py`'s existing threshold is the wrong order of magnitude for this use, if reused naively
`active_block_mask` gates at `threshold_db=-60.0` — a near-silence/lead-
in/lead-out gate. A "quiet section" in the sense this story needs (a
breakdown, intro, or low-energy passage where a stationary tone is audible
without being masked by full-mix energy, as on "Sunday Club") typically sits
far above −60 dBFS — commonly in the −30 to −20 dBFS range on dense
electronic material. Reusing `-60.0` as-is would likely find only true
silence/lead-in, yielding little or no usable material to learn a profile
from on a track that is "quiet" only in the relative sense the story
describes. No threshold is asserted here (CLAUDE.md §7 — see Open
Questions).

### Finding 3 — `extract_active_audio`'s all-silent fallback must not be inherited
`extract_active_audio` returns the **whole unmodified buffer** when every
block in the file is judged near-silent. If whatever quiet-section-finder
this story ends up using follows the same pattern, a track with no
qualifying quiet section could silently learn a "noise profile" from the
entire (non-quiet) track, subtracting broadband musical content rather than
noise. This must be explicitly designed against.

### Finding 4 — the existing exception (CLAUDE.md §4.2a / DOMAIN.md §4) does not cover this stage
DOMAIN.md §4's "Narrow exception — confirmed whistle artifacts" and
CLAUDE.md §4.2a grant a dated, named exception to `repair_whistles` notching
at machine-confirmed `STATIONARY_WHISTLE` coordinates — the very mechanism
DEF-009-001 shows is currently unsafe at any real scale of application. That
exception does not, by its own text, extend to a new spectral-subtraction
module, and its track record on the underlying detector evidence is now
worse than "unproven" — it is documented as having failed a listening gate.
Gate 1 must obtain either an extension of the existing exception (with the
DEF-009-001 evidence explicitly weighed) or a new, similarly narrow and
dated exception before implementation proceeds. This document does not
self-grant that exception.

### Finding 5 — "Wiener filtering" as commonly implemented is broadband; this story's target is not
Standard spectral-subtraction/Wiener-filter noise reduction estimates a
noise floor across the **entire spectrum** and attenuates it everywhere,
continuously — a different and riskier operation than removing specific,
machine-confirmed stationary tones. A full-spectrum noise-floor subtraction
on a finished stereo mix risks the DOMAIN.md §4 "Cannot" case — "baked-in
ambience or reverb: requires source information or stem separation, not
broadband EQ" — because a general noise floor is not distinguishable from
quiet ambience, room tone, or reverb tail without per-element access this
project does not have from a stereo sum. In scope only: subtraction
confined to spectral evidence carrying the same class of confirmation
CLAUDE.md §4.2a already requires for `repair_whistles` — not a general
broadband noise floor.

### Finding 6 — the harmonic-guard problem is not solved by switching methods; it is the story
Two guards already exist and both operate on **detector flags**, not raw
spectral content:
1. `_detect_stationary_whistle`'s Step 4a/4b: suppresses proto-flags with
   ≥2 matching harmonic positions at `{2f, 3f, f/2, f/3}` relative to a
   stronger fundamental, cascade-suppressing remaining overtones.
2. `whistle_repair._harmonic_guard_filter` (§6b): suppresses a flag only if
   harmonically related to a strong lower peak **and** an independently
   confirmed sibling harmonic exists.

Per Finding 0, applying both guards in sequence on Sunday Club still
suppressed 95.7% of candidate flags — meaning the guards, as currently
built, judge the overwhelming majority of this track's stationary-tone
evidence as *plausibly musical, not confirmed artifact*. **If this new
stage routes its candidate frequencies through the same two guards and
stops there, it inherits the same 95.7% suppression rate and closes none
of the gap this story exists to close** — it would simply be a differently-
implemented version of the same narrow 19-flag capability that already
exists and is already judged insufficient.

**A hypothesis, not a design decision, for the architect to evaluate**: the
one piece of evidence the existing guards do not use, and that this story's
own premise (learning from *quiet* sections) could plausibly supply, is
level-invariance across dynamic sections. A stray stationary artifact tone
baked into a generation is plausibly present at roughly constant amplitude
regardless of what else is happening in the mix, whereas a genuine musical
harmonic's prominence should track the loudness/density of the section it
belongs to (quieter in a breakdown that is quiet because the instrument
playing it is also quieter, louder in a full section). If a candidate
frequency's amplitude in a quiet section does *not* scale down consistently
with the rest of the quiet section's energy the way surrounding musical
content does, that is a distinct piece of evidence neither existing guard
currently checks. This is offered here only as the plausible *source* of
any genuine discriminating power this story could add beyond
`whistle_repair`'s existing guards — it is unproven, it is not asserted as
a requirement, and it does not relax the requirement below that the
resulting stage clear an equivalent listening-gate bar to the one
DEF-009-001 failed.

### Grounding from the motivating case — "Sunday Club"
From `artifacts/Sunday Club_mastered_report.md` (2026-08-20 pipeline run,
config with whistle-repair disabled per current defaults) and
`stories/STORY-009/defects.md` DEF-009-001 (2026-08-20 harmonic-guard e2e
entry, run separately with whistle-repair enabled):
- Pre-master: density score **1.0000**, 454 total flags, 452
  `STATIONARY_WHISTLE`, over a 254.7 s track.
- With `repair_whistles` disabled (the production default, matching the
  `master_track.bat` config): post-master density still 1.0000, total
  flags 455, `STATIONARY_WHISTLE` 453 — consistent with the stage not
  running at all; the small drift is plausibly EQ/loudness-stage
  measurement noise, not evidence about whistle repair.
- With `repair_whistles` enabled and the §6b harmonic guard active
  (DEF-009-001's separate validation run): 439 gated flags in, 420 (95.7%)
  suppressed by the guard, 19 forwarded, post-master `STATIONARY_WHISTLE`
  count 428 (barely moved from 452) — and the **listening gate on the
  broader 439-flag run (before the guard existed) failed outright**,
  characterised as "highly destructive."
- **`overall_artifact_density_score` is saturated at its ceiling on this
  track in both configurations** (`clip(total_flagged_s / duration_s, 0.0,
  1.0)`, `artifact_detection.py` line ~1141, reads exactly 1.0000 pre and
  post in both runs above). A saturated metric cannot register improvement
  or regression on this track — see AC10a below, which is unchanged by
  this revision but now doubly load-bearing: the density score could not
  have distinguished the destructive 439-flag run from the disabled run
  either, which is itself evidence the metric is the wrong instrument for
  judging this story's success on its own motivating case.

---

## Rejected as out of scope

- **General/broadband noise-floor subtraction across the full spectrum**
  (the naive/default behaviour of most off-the-shelf Wiener-filter noise
  reduction). Per DOMAIN.md §4 "Cannot" — baked-in ambience/reverb/room
  tone cannot be distinguished from a general noise floor at the master
  stage without per-element source access this project does not have from
  a finished stereo mix. In scope only: subtraction confined to spectral
  evidence carrying confirmation at least as strong as CLAUDE.md §4.2a
  already requires for `repair_whistles` — and, per Finding 6, this
  document does not consider "confirmed by the same two guards that already
  suppress 95.7% of this track's evidence" to automatically satisfy that
  bar for the remaining action the story needs to take. What additional
  evidence (if any) clears that bar is an open question, not decided here.
- **Non-stationary noise** — clicks, dropouts, transient artifacts. Story.md
  already excludes this; DOMAIN.md §4 independently confirms transient
  repair is impossible at this stage.
- **Recovering or reconstructing content the profile subtraction removes in
  error.** DOMAIN.md §4, "source recovery from a final stereo mix" — not
  possible if the guard under-fires.
- **Learning a noise profile from anything other than detector-confirmed
  quiet/stationary-tone evidence**, i.e. bypassing the detector and its
  guards to learn directly from raw spectral content of a "quiet" section.
  Per Finding 5/6, this is out of scope pending the Gate 1 exception in
  Finding 4 and is exactly the design DEF-009-001's root-cause finding
  warns against repeating under a different method name.
- **Treating "different method than the notch filter" as sufficient
  justification for a lighter evidentiary/listening-gate bar than
  DEF-009-001 required.** Explicitly rejected — see "This story does not
  get a free pass" above.

---

## Acceptance criteria

### General
1. Given the pipeline runs with this stage enabled, when it executes, then
   it runs before any downstream artifact-repair stage (currently only
   `whistle_repair.py`, itself disabled by default — see Open Question 4a
   for whether it remains, is re-enabled, or is retired) and before
   corrective EQ, and its output becomes the input to whatever stage runs
   next. Its position relative to stem separation is explicitly **not**
   settled by this criterion — see Open Question 4.
2. Given a track's `STATIONARY_WHISTLE` flags (or whatever evidence this
   story's design ultimately requires per Finding 6/AC7), when the stage
   selects candidates for subtraction, then only spectral evidence meeting
   that bar is eligible — never a full-spectrum noise floor (Finding 5).
3. Given the stage is disabled (config flag off), when the pipeline runs,
   then the stage is never invoked and downstream audio is bit-identical to
   the stage's input.
4. Given no quiet section in the track meets whatever definition the
   architect establishes for "quiet" (Finding 2), when the stage runs, then
   it must not fall back to learning a profile from the whole/non-quiet
   track (Finding 3) — it must either skip de-noising and pass audio
   through unmodified, or fail loudly, with the choice recorded in
   architecture.md. Silent whole-track fallback is rejected.
5. Given identical input audio and identical config, when the stage runs
   twice, output must be bit-identical.
6. Given the stage fails to import or initialize its underlying DSP
   dependency while enabled, the pipeline must fail loudly before
   processing begins — never silently skip the stage while reporting it as
   run.

### Harmonic-vs-artifact discrimination / no-damage guarantee
7. **This is the load-bearing criterion for the whole story, not a routine
   guard-rail.** Given a candidate frequency, the stage must not subtract
   it unless it is supported by evidence at least as strong as the existing
   two guards (Finding 6) require — and, given that those two guards alone
   already suppress 95.7% of this track's candidate evidence as plausibly
   musical (Finding 0), the architect must explicitly state what
   *additional* evidence, if any, this stage supplies that lets it safely
   act on some meaningful fraction of that suppressed 95.7% (e.g., along
   the lines of the level-invariance hypothesis in Finding 6, or some other
   architect-determined signal). If the answer is "no additional evidence,
   the stage applies the same two guards and stops," that must be stated
   explicitly as a limitation, because it means this story does not close
   the gap DEF-009-001 documents — it only re-implements the already-
   insufficient 19-flag capability under a different DSP method.
8. Given a synthetic test signal containing a sustained musical tone (e.g. a
   pad note held through a quiet passage) at a frequency that would not
   clear the evidentiary bar established in AC7, when the stage runs, then
   that tone's level in the output must be unchanged within a tight,
   explicitly stated tolerance (negative control).
9. Given a synthetic test signal containing a genuine confirmed stationary
   whistle present through a quiet section and the rest of the track, when
   the stage runs, then the whistle's measured level (via re-running
   `detect_artifacts`) must be reduced by a measurable, reported amount
   (positive control).
10. **Mandatory human listening gate, equivalent to the one DEF-009-001
    failed.** Given the stage runs on real material (at minimum "Sunday
    Club"), before this stage's default may move to "on" or before it is
    accepted as resolving any part of the gap DEF-009-001 documents, a
    human listener must evaluate the result and record a pass/fail
    judgment, the same posture DEF-009-001 required and the notch approach
    failed. Passing automated metrics (AC7–9, AC10a below) is necessary but
    explicitly **not sufficient** — DEF-009-001 demonstrates a case where
    metrics (79% artifact-count reduction, LUFS held, DR improved) passed
    while the listening gate failed outright. This story must not be
    declared done on metric evidence alone.

### Musical-noise / regression guard
11. Given the stage runs on any test or reference track, when
    `detect_artifacts` is re-run on the de-noised output, then
    `overall_artifact_density_score` must not increase relative to the
    pre-stage input, and no new `SMEARED_TRANSIENT` or `DIGITAL_HAZE` flags
    may appear that were not present before.
11a. **AC11 alone is not sufficient evidence of improvement, and on the
    motivating case it cannot even register regression.**
    `overall_artifact_density_score` is a clipped ratio that reads exactly
    1.0000 on "Sunday Club" in every configuration measured so far —
    disabled, and enabled-with-guard (Grounding above) — meaning it could
    not have distinguished the destructive 439-flag run from the disabled
    run either. Therefore this story must also report and be judged
    against the **unsaturated** measures: raw `STATIONARY_WHISTLE` flag
    **count** and `total_flagged_s`, before and after the stage runs.
    Recorded baselines for "Sunday Club": 452 flags pre-stage in the
    disabled config; 439 gated flags / 420 guard-suppressed / 19 forwarded
    / 428 post-repair in the enabled-with-guard config; duration 254.7 s. A
    result that leaves the flag count materially unchanged, or that only
    matches the already-insufficient 19-flag/428-residual outcome, does not
    satisfy this story's product goal even if AC11's density check
    trivially "passes."
12. Automated musical-noise proxies (AC11/AC11a) are necessary but not
    sufficient; whether the specific implementation avoids audible
    metallic/burbling artifacts on real material is a Gate 1/Gate 2
    mastering-engineer listening judgment per AC10, consistent with
    CLAUDE.md §5's "metrics necessary but not sufficient" position.

### Reporting / STORY-025 handoff
13. Given the stage runs (enabled and actually invoked, not skipped per
    AC4), when it completes, then the returned report must include: the
    specific frequencies targeted and the evidence basis for each (per
    AC7), the magnitude of reduction applied, which section(s) of the track
    were used to learn the profile (timestamps), and which candidate
    frequencies were suppressed and why (mirroring the existing
    `harmonic_guard_suppressed`/`harmonic_guard_suppressed_count` fields
    already present on `ArtifactDetectionResult`) — this is the artifact
    STORY-025 and QA need to consume; it must not be produced without a
    named consumer reading it.
14. Given STORY-025's requirement (AC4/AC5) that any before/after
    `overall_artifact_density_score` delta be computed only after LUFS
    level-matching, this story's report must supply the unmatched pre-
    stage and post-stage audio (or their independently measured density
    values) for STORY-025 to level-match and compare — this story does not
    perform the LUFS-matching itself. Because density can saturate at 1.0
    (AC11a), the report must **also** hand over the unsaturated
    `STATIONARY_WHISTLE` flag count and `total_flagged_s` alongside the
    density score, with an explicit note that density is
    degenerate/non-discriminating above the saturation point. This
    division of labour must be stated explicitly in architecture.md.

---

## Audio quality targets
No new loudness/DR/spectral targets are introduced by this story. The
de-noise stage operates before loudness/limiting in the existing chain
order (DOMAIN.md §6). It must not alter integrated LUFS, true peak, or TT
DR by more than an incidental, reported side-effect of the subtraction
itself; no explicit loudness/DR target is set here. The magnitude of
spectral subtraction, any oversubtraction/noise-floor-offset factor,
minimum quiet-section duration, and FFT/frame size are all DSP tunables
with no established value anywhere in this codebase — none is asserted
here; all are Open Questions for the architect and Gate 1 review.

## Input/output assumptions
- Input: the pipeline's in-flight raw audio buffer, at whatever stage
  position the architect confirms is "first" relative to stem separation
  (Open Question 4) — `float32`/`float64` NumPy array, mono or stereo,
  matching the existing plain-array convention (per STORY-007
  architecture.md §7.2 / SPRINT-007-01, which this story does not resolve).
- The stage additionally consumes `Measurements.artifact_detection`
  (`STATIONARY_WHISTLE` flags with frequency/timestamp/confidence), already
  computed elsewhere in the pipeline — this story should reuse that call
  rather than duplicate detection.
- Output: a de-noised buffer of the same shape/channel layout as the input,
  plus the report described in AC13/AC14, in-pipeline (no new file
  artifact type), consumed next by whatever stage the architect designates
  per Open Question 4a.

## Explicit out-of-scope
- Fixing or re-validating `whistle_repair.py`/DEF-009-001 itself — that
  remains STORY-009's open defect, tracked there, not folded into this
  story's acceptance.
- Any change to STORY-007's detector, its thresholds, or STORY-009's
  existing harmonic guard/`repair_whistles` behaviour — this story consumes
  their output/evidence, it does not modify them (though AC7 requires this
  story to state clearly whether it relies solely on that existing
  evidence or supplies additional evidence of its own).
- Choosing the specific spectral-subtraction algorithm, library, FFT/frame
  parameters, oversubtraction factor, or the numeric definition of "quiet
  section" — architect/Gate 1 decision.
- Real-time/streaming processing — offline pass only.
- Performing STORY-025's LUFS level-matching itself (AC14).
- GUI exposure (STORY-G1 is separate).
- Resolving whether this stage runs on the stereo sum or per-stem
  post-separation, and whether `whistle_repair.py` is retired, kept
  disabled, or re-enabled for residual whistles this stage cannot safely
  reach — both are open questions for the architect, not decided here.

## Non-functional requirements
- Reproducibility: bit-identical output for identical input + config (AC5).
- Failure posture: fail loudly on missing/broken DSP dependency when
  enabled (AC6); never a silent whole-track-as-quiet-section fallback
  (AC4, Finding 3).
- No processing-speed or throughput target is specified here.
- Every invocation (including a deliberate skip/no-op) must be logged
  sufficiently for a human to reconstruct what was and was not subtracted.
- **A documented human listening-gate result is a release-readiness
  requirement for this stage, not optional QA colour** (AC10) — this
  mirrors DEF-009-001's own required-fix item 5 ("validate... the real-track
  result before re-enabling the stage") and its still-open status pending a
  listening pass at specific flagged timestamps.

## Open questions
1. **What defines a "quiet section" for profile learning?** No existing
   detector or threshold answers this (Finding 1/2). `silence.py`'s `-60.0`
   dBFS gate is very likely too strict; no replacement value is asserted
   here.
2. **Does this stage require a new or extended CLAUDE.md §4.2a-style
   exception before Gate 1 can clear it, given DEF-009-001's evidence
   against the existing exception's underlying detector-to-repair
   contract?** (Finding 4.) Treated as required and unresolved here.
3. **Evidentiary/confidence gate for candidate frequencies** — is reusing
   the two existing guards (which already suppress 95.7% of Sunday Club's
   evidence) sufficient, or does this story require a materially different
   evidence source (per the level-invariance hypothesis in Finding 6, or
   another architect-chosen signal) to act on any of that suppressed
   majority? This is the central open design question the whole story
   turns on (AC7).
4. **Stem-first placement**: before or after stem separation? CLAUDE.md
   §3's stem-first principle is not reconciled by Story.md's wording, and
   the answer materially changes the design.
4a. **Fate of `whistle_repair.py`**: retired, kept permanently disabled, or
    re-enabled as a residual layer for whatever narrow set of high-
    confidence isolated whistles this new stage still cannot or should not
    touch? Not settled by Story.md or this document — flagged explicitly
    per the coordinator's correction, not assumed to remain "the fallback."
5. **Algorithm and tunables**: Wiener filter vs. spectral gating vs.
   another variant, FFT/frame size, oversubtraction factor, minimum
   quiet-section duration/coverage — architect/Gate 1 decisions, none
   asserted here.
6. **STORY-025 division of labour** (AC14): exact data STORY-026 hands to
   STORY-025's level-matching step — not specified by Story.md's contract.
7. **Behaviour when the (possibly extended) evidence gate suppresses all
   candidates on a track**: clean no-op report, or a distinct "nothing
   met the bar" report state QA needs to assert on separately?
8. **What tolerance defines "musical-noise regression" beyond the
   density-score/flag-count checks in AC11/AC11a?** AC10's human listening
   judgment is required regardless; whether an additional automated proxy
   should also gate Gate 1 clearance is not decided here.
9. **Listening-gate protocol**: should this story define its own listening-
   gate checklist (timestamps, listener, sign-off record), or reuse
   whatever protocol DEF-009-001's still-open remediation eventually
   formalises for STORY-009? Not decided here — flagged so the two stories'
   release gates don't silently diverge.

## Revision history
- 2026-08-20: Initial requirements.md written for STORY-026.
- 2026-08-20 (same-day revision, pre-handoff): corrected the Sunday Club
  grounding after re-checking the mastered report's action list —
  `whistle_repair` had not run on that particular file, so the 452→453
  flag drift was not evidence of notch-filter damage. Added AC10a-equivalent
  language addressing `overall_artifact_density_score` saturating at 1.0000
  on that track.
- 2026-08-20 (coordinator-directed revision): corrected a materially larger
  error — `whistle_repair.py` is not an active downstream fallback; it is
  disabled by default in production and carries an open defect
  (DEF-009-001) recording a failed listening gate ("highly destructive to
  the track") even after the OLA bug was fixed and a harmonic guard was
  added, with the guard itself suppressing 95.7% (420/439) of candidate
  flags on "Sunday Club" as likely-musical and leaving 428/452 flags
  untouched. Rewrote Contract, Restated Intent, Findings 0 and 6, Rejected-
  as-out-of-scope, and Acceptance Criteria (new AC7 as the load-bearing
  criterion, new AC10 mandatory listening gate, AC11a) to: (1) stop
  assuming whistle_repair.py is an active fallback layer; (2) require this
  story to clear the same evidentiary/listening-gate bar that sank the
  notch approach, explicitly rejecting "different method" as sufficient
  justification for a lighter bar; (3) add Open Question 4a on
  whistle_repair.py's fate as an explicitly unresolved question rather than
  a settled assumption; (4) reframe the story's actual target as the
  420/439 (95.7%) guard-suppressed, currently-unactionable majority that
  the notch method cannot scale to, per the coordinator's direction, while
  keeping the level-invariance discrimination idea explicitly labelled a
  hypothesis for Gate 1, not a proven method or a requirement.
