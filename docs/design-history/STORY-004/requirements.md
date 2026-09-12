# STORY-004 — Requirements: Measurement correctness (DEF-201, DEF-203, DEF-204)

Governed by `CLAUDE.md`, `docs/DOMAIN.md`, `docs/ARCHITECTURE.md`,
`docs/HANDOFF.md` (H-rules) — all at repo root. This document is
self-contained; the software-architect should not need to re-read
`story.md` or `stories/STORY-002/defects.md` in full, though the latter is
cited by entry name below for traceability.

## Contract

```
Consumes:    existing analysis implementation
             (stories/STORY-001/implementation/suno_mastering/analysis/*)
Produces:    corrected analysis + ground-truth suite
             (Measurements-family output per ARCHITECTURE.md §3.2;
             ground-truth tests under
             stories/STORY-001/implementation/tests/)
Consumed by: STORY-005 (targets derived from these measurements)
```

This is analysis-only. No audio is written, mutated, or mastered. The
Definition of Done's human listening check (HANDOFF.md Part 3) applies
vacuously — there is no audio output to A/B.

---

## Restated intent

Two measurement functions in the shared analysis library produce results
that are provably wrong on real material, and the test suite that should
have caught both shipped green anyway. This story replaces the
band-limit detector's method (not its threshold), replaces the mono-sum
comparator's method (not its constant), and closes the specific test-suite
gaps that let both ship. Nothing here changes what mastering does to
audio — it only changes what is *measured* and *reported* about it, so
that STORY-005 (which derives correction targets from these measurements)
is building on numbers that are actually true.

---

## Rejected as out of scope

None of this story's scope implies a DOMAIN.md §4 impossibility. Band-limit
*detection* is measurement of an existing property of a file, not an
attempt to recover content above the band limit, repair a transient, or
separate stereo elements — none of which this story attempts.

Explicitly out of scope for this story (do not action, even if adjacent
code invites it):

- **DEF-202** (reference targets not wired into mastering) — STORY-005's
  scope, per BACKLOG.md and story.md's coordinator notes.
- **Any change to the mastering chain** (`suno_mastering/mastering/*` or
  equivalent) — this story touches analysis only, per the Contract above.
  ARCHITECTURE.md §1's "analysis and processing are separate" applies.
- **An anchor-only patch to `hf_extension.py`'s per-segment reference-band
  recomputation.** The wiring-gap investigation (`stories/STORY-002/
  defects.md`, "DEF-201 wiring-gap investigation") proved directly that
  pinning the reference anchor to a single whole-track value collapses the
  reported *instability* (9160.4 Hz spread → 706.1 Hz) but leaves the
  reported cutoff on Leftfield unchanged at 8170.2 Hz. Stabilising the
  anchor without changing the underlying threshold-crossing method does
  not close DEF-201 and must not be accepted as a fix.
- **Renaming or restructuring anything in `Measurements` (types.py)
  itself** beyond what's needed to satisfy this story's field-contract
  requirements below — flagged as an open architect decision (see Open
  Questions), not pre-decided here.

---

## Scope and required method changes (H6)

### DEF-201 — band-limit detection: METHOD change required

**Current method (confirmed by reading `hf_extension.py` and the
wiring-gap investigation) is threshold-crossing**: `_segment_rolloff_hz`
scans down from Nyquist for the highest frequency whose (median-filtered)
PSD density exceeds `reference_band_density_db − hf_rolloff_threshold_db`.
This is exactly the "known-wrong pattern" CLAUDE.md §5 names: a fixed
relative-dB threshold is always crossed somewhere on a naturally declining
spectrum, regardless of where — or whether — a real cliff exists.

**Evidence this remains wrong after the prior 6→20 dB parameter change**
(this is why HANDOFF.md H6 classifies the prior fix as a parameter change
to a wrong method, not a fix):
- All five reference tracks now report `stable=False`. A band limit is a
  fixed property of a file (DOMAIN.md §2); universal instability is the
  signature of a detector tracking programme content, not a filter.
- Leftfield — Melt (1995 CD master, ~20 kHz true extension) reports
  8170 Hz.
- The wiring-gap investigation isolated the mechanism directly: pinning
  the reference anchor removes the instability but not the wrong number
  (8170.2 Hz either way) — proving the confound is threshold-vs-tilt, not
  merely anchor drift. Measured sensitivity near the reported "cutoff":
  roughly 1000–1400 Hz of reported rolloff per 1 dB of anchor
  perturbation — the empirical signature of a shelf/tilt crossing a line,
  not a cliff (a true brickwall's crossing point is threshold-depth
  independent; the existing `test_tc020`/`test_tc021` fixtures already
  demonstrate this contrast on brickwall material).

**Required replacement method**: cliff detection — sustained slope
≥24 dB/octave (DOMAIN.md §2; the value already exists in config as
`transcode_suspect_slope_db_per_octave`) across adjacent spectral bins,
followed by a floor. No cliff found → report **`None`**, never a fallback
value, never Nyquist, never a mid-band threshold-crossing point. This
is a method change under H6: tuning `hf_rolloff_threshold_db` again, or
stabilising only the reference-band anchor, does not satisfy this
requirement and does not close DEF-201.

**A slope+floor check alone is not sufficient — state the requirement it
must also satisfy, not just the mechanics.** The recovered v3 HF design
(`stories/STORY-002/defects.md`, "DEF-201 — Architect resolution (software-
architect, v3 pass)") itself notes that a slope+floor check with no other
constraint can still be satisfied by a window sitting *inside* an
already-declined region of a normal tilted spectrum, reproducing
Leftfield's exact failure. Whatever detector design the architect chooses
must therefore also enforce that a candidate cliff is not reported from a
region whose starting level has already declined substantially from the
reference-band level — i.e. the detector must distinguish "the top of a
real wall" from "partway down an ordinary slope." This document does not
mandate v3's specific mechanism or its 6 dB figure for that check; it
states the requirement the design must satisfy so a from-scratch design
that discards v3 does not silently reproduce the same failure mode.

**Return-contract requirement (ARCHITECTURE.md §3.2, binding)**: the
measurement's public output must be `hf_band_limit_hz` (nullable —
`None` when no cliff is found, never Nyquist or any other sentinel value)
and `hf_band_limit_confidence`. A previously-circulated design
(`stories/STORY-002/defects.md`, "DEF-201 — Architect resolution
(software-architect, v3 pass)") proposed field names `cutoff_detected` /
`rolloff_hz`, with `rolloff_hz` set to Nyquist when no cutoff is found.
**That naming must be reconciled to §3.2's names, and the Nyquist-as-
"no-cutoff" convention is superseded, not adopted** — ARCHITECTURE.md §3.2
states nullability "never a fallback value" explicitly, and Nyquist is a
fallback value. `hf_band_limit_confidence`'s scale, units, and derivation
are not defined by any governing document or by the v3 design; flagged as
an open question below — do not invent a formula for it.

### DEF-203 — mono-sum baseline: METHOD change required, not a constant edit

**Current comparator (confirmed by reading `mono_sum.py`)**:
`level_change_db = LUFS(mono_sum) − LUFS(stereo)`, where both LUFS values
come from `measure_integrated_lufs`, which implements BS.1770's
channel-**summed** convention for the stereo call. Under that comparator,
the analytically correct ρ=0 floor is **−6.0206 dB**
(`10·log10(0.25)`) — this arithmetic is not in dispute and has been
independently re-derived twice (`stories/STORY-002/defects.md` DEF-101,
and the "DEF-203 — Architect resolution (v3 pass)" entry).

**This is precisely why DEF-203 cannot be closed by editing the −6.02
constant to −3.01.** DOMAIN.md §3 and ARCHITECTURE.md §5 define the
−3.01 dB floor for a *different* comparison: **mono sum compared against
a single channel**, not against BS.1770 channel-summed stereo loudness.
Changing only the constant while leaving the comparator (`stereo_lufs`
computed as the channel-summed BS.1770 reading) would produce internally
inconsistent output — the constant would no longer match what is actually
being measured. **Per H6, this is a method change: what the mono sum is
compared against must change (to a single-channel or channel-mean
reference), not just the number it is compared to.**

**The recovered architect "v3" resolution for DEF-203 in
`stories/STORY-002/defects.md` is CONTESTED and must NOT be followed.**
It argues the −6.02 dB constant is correct as a BS.1770 channel-summed
metric (arithmetically true, for that comparator) and proposes keeping it,
renamed `headroom_db`. This conflicts with DOMAIN.md §3 and
ARCHITECTURE.md §5, which this project's own precedence rule makes
authoritative ("where this document and an agent's assumption disagree,
this document wins" — DOMAIN.md, opening paragraph). **This story follows
the docs, not the v3 entry.** The mastering-engineer Gate 1 review must
confirm this reconciliation before implementation proceeds.

**No constant referencing the superseded channel-summed comparator may
survive anywhere in the analysis code once the comparator is corrected.**
If the architect changes the comparator (as required above) but retains a
derived field computed as `level_change_db − (−6.0206)` (v3's proposed
`headroom_db`), the −6.02 dB constant persists, now anchored to a
comparison that no longer exists — exactly the "stale asserted constant"
pattern H4 exists to prevent. The −4.5 dB excess-cancellation trigger
(below) is evaluated directly on the corrected `mono_sum_level_change_db`.
Whether any additional derived excess/headroom field is retained at all is
an architect decision; if one is kept, it must be re-derived against the
corrected comparator, not carried over from the old one.

**Free internal-consistency check available once corrected (H5 #1),
worth handing to the architect**: `mono_sum.py`'s existing **per-band**
`delta_db` already divides by the channel-**mean** band power
(`_PERBAND_DECORRELATED_FLOOR_DB = −3.0103 dB`) — i.e. the per-band path
already uses the comparison DOMAIN.md §3 specifies and likely needs no
method change, only possible verification. Once the broadband comparator
is corrected, both the broadband and per-band ρ=0 floors become −3.01 dB
and must agree exactly on a synthetic ρ=0 fixture — that agreement is a
direct, cheap internal-consistency check the corrected implementation
should pass.

**Required field name** (ARCHITECTURE.md §3.2, binding): `mono_sum_level_change_db`.

**Required verification points**, each analytically derivable and must be
shown, not asserted, in architecture.md (H4):
- ρ = 1.0 (identical channels) → 0 dB
- ρ = 0.0 (uncorrelated, equal power) → **−3.01 dB**
- ρ = −1.0 (fully inverted) → −∞ dB

**Consequence for expected reference-set values, stated explicitly so it
is not mistaken for a new anomaly**: the previously-reported figures
(−3.47 to −4.03 dB measured level change; 1.995–2.548 dB "excess" under
the old, superseded comparator) were produced under the wrong comparator
and must not be carried forward as the expected post-fix range. Under the
corrected single-channel/channel-mean comparator, values shift by
approximately +3.01 dB relative to the old channel-summed reading
(since BS.1770-summed stereo reads `10·log10(2)` ≈ 3.01 dB above a single
channel for equal-power content), which is consistent with the v3 entry's
own back-solved correlation estimate (ρ ≈ 0.58–0.80) and with DOMAIN.md
§3's stated normal correlation range (0.5–0.9) for commercial electronic
material. Do not require the corrected references to land in the old
−3.0…−4.5 dB band — that band describes near-uncorrelated material, and
correlated commercial references may legitimately read closer to 0 dB.

**Excess-cancellation trigger**: report "excess cancellation" only when
`mono_sum_level_change_db < −4.5 dB` (DOMAIN.md §3), a one-sided
threshold. Do not gate on a two-sided band.

### DEF-204 — test coverage gap

**Do not restate "pink-noise negative control, confirmed failing, then
fixed" as a literal acceptance step — as written it is not satisfiable.**
The wiring-gap investigation (`stories/STORY-002/defects.md`) ran the
existing pink-noise fixture (`test_tc024_pink_noise_no_cutoff`) against
the current shipped code (`hf_rolloff_threshold_db=20.0`) and it
**passes** (reports ~22047 Hz, correctly "no cutoff" on stationary pink
noise, under its current assertion `rolloff_hz >= 0.9 * Nyquist`). The
fixture that actually fails on current shipped code, and is the one whose
absence let DEF-201 ship undetected, is the one the investigation names as
missing: **a fixture combining a realistic, declining-but-not-infinite
spectral tilt with genuine per-segment non-stationarity (time-varying
reference-band energy) and no real cutoff at all.** Neither existing
fixture has both properties: TC-024 (pink noise) has the tilt but is
stationary; TC-025 (drift fixture) has non-stationarity but as a genuine
cutoff-frequency change, not a cutoff-free declining-tilt case.

**The existing pink-noise fixture's assertion must itself be rewritten,
not merely retained, once `hf_band_limit_hz` replaces `rolloff_hz`.** Its
current numeric assertion (`rolloff_hz >= 0.9 * Nyquist`) is incompatible
with the corrected nullable return contract — there is no numeric value to
assert once "no cliff" reports `None`. Rewrite the assertion to
`hf_band_limit_hz is None`. No test in the suite may assert a numeric
value for the no-cliff case; a test that does so is implicitly requiring a
fallback value and would silently pressure the implementation back toward
the superseded Nyquist-sentinel convention.

Required, in this order (H3, H7):
1. Write the missing tilt + non-stationarity, no-real-cutoff negative
   control first. Confirm it fails against the current shipped code.
2. Retain the existing pink-noise negative control, with its assertion
   rewritten as above (it should continue to pass) — but its passing does
   not, by itself, demonstrate DEF-204 is closed, since it already passed
   (under its old assertion) while the real analysis path produced an
   implausible 8170 Hz on Leftfield. State this explicitly in the coverage
   writeup so a future reader does not mistake "pink noise passes" for
   "the coverage gap is closed."
3. Add a fixture at 48 kHz — every real reference track is 48 kHz; the
   existing HF-extension ground-truth suite is 44.1 kHz only. This
   affects Nyquist-relative pass bounds and the Welch/median-filter
   effective-bandwidth behaviour discussed in the wiring-gap
   investigation, and is a second, independently-confirmed coverage gap
   from that investigation.
4. Establish, and record, why none of the above existed before this
   story — the wiring-gap investigation already supplies this finding
   (no fixture combined tilt + non-stationarity; sample rate mismatch);
   this story's implementation should confirm it against the corrected
   detector, not re-investigate from scratch.

---

## Acceptance criteria

Given/When/Then, numbered against BACKLOG.md/story.md's acceptance list,
revised per the findings above.

**AC1 — HF negative control, correctly targeted.**
Given the tilt + non-stationarity + no-real-cutoff fixture required above,
when run against the current (pre-fix) shipped detector, then it must
fail. When run against the corrected cliff-detection method, then it must
report `hf_band_limit_hz = None`. The pre-existing pink-noise fixture is
retained with its assertion rewritten to `hf_band_limit_hz is None`
(replacing the old numeric-threshold assertion, which is incompatible
with the nullable contract) and must continue to pass under the corrected
detector; it is a secondary regression control, not the primary evidence
of DEF-204 closure — see the DEF-204 scope section above for why.

**AC2 — Real reference set plausibility.**
Given all five reference tracks re-run through the corrected detector,
when band limits are reported, then every value is either a plausible
band limit for the file's source characteristics (DOMAIN.md §2's
expected-band-limit table) or `None`; no value below 10 kHz is reported
for a commercial master. Note: the reference tracks' actual provenance
(lossless vs. lossy-sourced) is not established by CLAUDE.md §4.1, which
states only LUFS/DR/role — do not assume CD-lossless provenance. If a
track's true source is lossy, a lower plausible band limit (per DOMAIN.md
§2's table, e.g. ~16–20 kHz depending on bitrate) is an acceptable
outcome, not a defect; only sub-10 kHz values on non-generative material
are automatically implausible.

**AC3 — Stability, scoped correctly.**
Given a track with a genuine, fixed band limit (commercial masters and
CD-sourced references), when measured across segments, then the reported
limit is stable (or reported as `None` — never a wrong-but-stable value).
This stability requirement applies to the commercial reference set. It
does **not** apply as a pass/fail gate to Suno/generative material, which
DOMAIN.md §2 states "may drift within one file" — segment-to-segment
disagreement on generative material is not automatically evidence of a
broken detector and must not be treated as a defect on that basis alone.

**AC4 — Mono-sum derivation.**
Given the mono-sum measurement is re-derived per the METHOD change
described above (single-channel/channel-mean comparator, not a constant
edit), when architecture.md is produced, then it must show the derivation
for all three verification points (ρ=1.0 → 0 dB, ρ=0.0 → −3.01 dB,
ρ=−1.0 → −∞ dB) and each must be verified against a synthetic signal with
that exact, constructed correlation (H4). No constant referencing the
superseded channel-summed comparator (−6.0206 dB) may remain in the
shipped code; see the DEF-203 scope section above.

**AC5 — Excess cancellation threshold.**
Given the corrected `mono_sum_level_change_db`, when a reference track's
value is at or above −4.5 dB, then no "excess cancellation" is reported.
When it is below −4.5 dB, excess cancellation is reported. This is a
one-sided threshold (DOMAIN.md §3), not a two-sided band, and the five
current references are expected — not guaranteed, since this is
measurement, not a target — to no longer show excess cancellation once
the comparator is corrected, since DOMAIN.md's own correlation-plausibility
range (0.5–0.9) for commercial electronic material is consistent with
normal summing.

**AC6 — H5 plausibility gate.**
Given the full corrected reference report, when it is generated, then it
must pass all four H5 checks (internal consistency, material
plausibility, spread check, round-number check) and any failure is
reported as a `plausibility_warnings` entry, not silently dropped.

**AC7 — Gate 1 and Gate 2 review.**
Given architecture.md is produced from this requirements document, when
mastering-engineer reviews it in Gate 1, then it must confirm the DEF-203
reconciliation (this document's method-change requirement, not the v3
entry's constant-rename proposal) before implementation proceeds. Gate 2
review on the resulting real-track output must pass with no unresolved
Blockers.

---

## Audio quality targets

This story does not set or change any mastering target. It corrects two
*measurements*. The only numeric values in scope are:

- Band-limit detection: cliff slope ≥24 dB/octave, sustained across
  adjacent bins, followed by a floor (DOMAIN.md §2). No cliff → `None`.
  No commercial-master band limit is plausible below ~10 kHz (DOMAIN.md
  §2's "any reported cutoff below ~10 kHz on a commercial release is a
  measurement error"). A candidate cliff must not be accepted from a
  region whose level has already declined substantially from the
  reference-band level (see DEF-201 scope section above) — this is a
  requirement on the detector's design, not an additional numeric target.
- Mono-sum floor: 0 dB (ρ=1), −3.01 dB (ρ=0), −∞ dB (ρ=−1) — derived,
  not asserted (H4). Excess-cancellation trigger: below −4.5 dB
  (DOMAIN.md §3), one-sided.

No loudness, dynamic range, spectral, or true-peak target is in scope for
this story — those are governed by CLAUDE.md §4.2 / ARCHITECTURE.md §3.3
and untouched here.

---

## Input/output assumptions

- **Input**: the existing analysis code path (`suno_mastering/analysis/*`)
  consuming `AudioBuffer` (ARCHITECTURE.md §3.1) built from the project's
  five reference WAV files (`Reference Tracks/*.wav`, all 48 kHz per the
  reference set report) and any synthetic fixtures the ground-truth suite
  requires. No new input format handling is in scope.
- **Output**: corrected `Measurements`-family output (the exact owning
  dataclass — `Measurements` in `types.py` vs. the `ReferenceMeasurements`/
  `HfExtensionResult`/`MonoSumResult` wrapper in `reference_types.py` — is
  an architect decision; see Open Questions) exposing `hf_band_limit_hz`
  (nullable), `hf_band_limit_confidence`, and `mono_sum_level_change_db`
  as public field names, per ARCHITECTURE.md §3.2. A markdown/JSON
  reference-set report reflecting the corrected values. A ground-truth
  test suite under `stories/STORY-001/implementation/tests/`.
- This story does not read or write Suno raw exports specifically — it
  operates on whatever the existing analysis pipeline already consumes
  (reference tracks and synthetic fixtures). No new source-format
  assumption is introduced.

---

## Non-functional requirements

- Full test suite runs in under 60 seconds (HANDOFF.md Part 3, Definition
  of Done). **Open tension, not resolved here**: `stories/STORY-002/
  defects.md` (DEF-106) already recommends isolating some slow reference
  tests from the main run, and this story adds at least two new fixtures
  (tilt+non-stationarity, 48 kHz). Whether the 60-second bound is meant to
  cover the full reference-analysis suite including these new fixtures, or
  only a fast subset with the slow reference tests isolated per DEF-106's
  precedent, is not decided by this document — flagged for the architect.
- Reproducibility: given the same input file and config, output must be
  bit-identical across runs (no non-determinism introduced by either
  method change).
- No change to memory or wall-clock budgets already established for the
  reference-analysis pipeline (`stories/STORY-002/defects.md` DEF-102/
  DEF-103) beyond whatever cost the two corrected detectors themselves
  add — this story does not authorize revisiting those budgets.

---

## Explicit out-of-scope

(See also "Rejected as out of scope" above.)

- Wiring `targets.json` or any target derivation into the mastering chain
  (DEF-202 / STORY-005).
- Any change to `suno_mastering/mastering/*` or the correction/dynamics/
  loudness/dither chain.
- Any change to loudness (`loudness.py`), true peak, clipping, dynamic
  range, seven-band balance, or stereo-width measurement code, except
  where `mono_sum.py`'s corrected comparator must call `measure_integrated_
  lufs` differently (single-channel vs. channel-summed) — that call-site
  change is in scope; `loudness.py`'s own implementation is not.
- Introducing a new `hf_band_limit_confidence` formula without it being
  derivable and stated (see Open Questions) — do not ship a placeholder
  constant for this field; that would itself violate H4/H5's round-number
  check.

---

## Open questions

1. **`hf_band_limit_confidence`**: required by ARCHITECTURE.md §3.2, but
   its scale, units, and derivation are defined nowhere — not in
   CLAUDE.md, DOMAIN.md, ARCHITECTURE.md, story.md, or the recovered v3
   HF design. The architect must define and derive it (e.g. from
   per-segment cliff-confirmation agreement, analogous to the existing
   stability check) rather than have it invented ad hoc at implementation
   time, and it must not be a constant.
2. **Field ownership**: `Measurements` (`types.py`) currently has none of
   §3.2's named fields (`hf_band_limit_hz`, `hf_band_limit_confidence`,
   `mono_sum_level_change_db`, `plausibility_warnings`) — they
   presently live, under different names, in the `ReferenceMeasurements`/
   `HfExtensionResult`/`MonoSumResult` wrapper (`reference_types.py`).
   Whether §3.2's contract is satisfied by renaming fields in the existing
   wrapper, or requires promoting them into `Measurements` itself, is an
   architect decision — flagged, not resolved here. Related: the existing
   code uses `sanity_warnings`; ARCHITECTURE.md §3.2 names
   `plausibility_warnings`. Reconcile explicitly.
3. **60-second full-suite bound vs. new slow fixtures** (see Non-functional
   requirements) — whether the new tilt+non-stationarity and 48 kHz
   fixtures count toward the bound or are isolated per DEF-106's
   precedent.
4. **`suspected_transcode` corroboration logic** (`_transcode_slope_check`
   in the current `hf_extension.py`) — the recovered v3 design describes
   deleting this function and folding its slope check into the new
   Stage-1 cliff-existence gate. Whether "suspected transcode" survives as
   a distinct reported signal after the method change, or is subsumed by
   `hf_band_limit_confidence`, is left to the architect; this document
   does not require either outcome.
5. **Retained excess/headroom derived field for mono-sum**: whether a
   derived "excess beyond floor" or "headroom" field is kept at all
   alongside `mono_sum_level_change_db`, and if so what it is named and
   how it is re-derived against the corrected comparator, is left to the
   architect (see DEF-203 scope section) — this document requires only
   that no stale −6.0206 dB constant survives and that the −4.5 dB
   trigger is evaluated on the corrected field directly.

---

## Revision history

v1 (this document) — first pass, produced from story.md, CLAUDE.md,
DOMAIN.md, ARCHITECTURE.md, HANDOFF.md, and stories/STORY-002/defects.md's
DEF-201/DEF-203/DEF-204 history (original entries, REOPENED entries, the
wiring-gap investigation, and both v3 architect-resolution entries). No
prior requirements.md existed for STORY-004.

v1.1 (this document, same pass, pre-delivery revision after advisor
review) — fixed three issues found in self-review before delivery:
(1) AC1/DEF-204 originally said the pink-noise fixture "continues to pass
under both the old and new detector" without addressing that its existing
numeric assertion (`rolloff_hz >= 0.9 * Nyquist`) is incompatible with the
corrected nullable `hf_band_limit_hz` contract — now explicit that the
assertion itself must be rewritten to `hf_band_limit_hz is None`, and that
no test may assert a numeric value for the no-cliff case (this closes a
path by which the superseded Nyquist-sentinel convention could re-enter
via the test suite). (2) DEF-203/AC4 originally allowed the −6.0206 dB
constant to persist under a renamed field (as v3 proposed); now explicit
that no constant referencing the superseded channel-summed comparator may
survive anywhere in the code once the comparator changes, added the
free per-band/broadband agreement check as H5 evidence, and added open
question 5 to flag the retained-field naming as an architect decision
rather than silently allowing v3's `headroom_db` design back in.
(3) AC2 originally asserted the five references are "all CD-sourced per
CLAUDE.md §4.1" — struck; CLAUDE.md §4.1 states only LUFS/DR/role, not
provenance, and asserting CD-lossless origin is not supported by any
governing document. Also added the DEF-201 passband-precondition
requirement (a candidate cliff must not be accepted from a region already
well below the reference-band level) as a design requirement without
mandating v3's specific mechanism, so a from-scratch detector design does
not silently reproduce Leftfield's failure via a naive slope+floor check.
