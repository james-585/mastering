# STORY-005 — Requirements: DEF-205 — Per-segment gate false positive (Chemical Brothers)

Governed by `.claude/docs/CLAUDE.md`, `.claude/docs/DOMAIN.md`,
`.claude/docs/ARCHITECTURE.md`, `.claude/docs/HANDOFF.md` (H-rules). This
document is self-contained; the software-architect should not need to re-read
`stories/STORY-004/gate2-trace-v1.5a.md` or `stories/STORY-004/gate2-review-v1.5a.md`
in full, though both are cited by section for traceability.

## Contract

```
Consumes:    hf_extension.py v1.5a (freeze_index = i_max / _floor_onset_index)
             stories/STORY-001/implementation/suno_mastering/analysis/hf_extension.py
             produced by STORY-004

Produces:    corrected or caveated HfExtensionResult analysis
             (stories/STORY-001/implementation/suno_mastering/analysis/hf_extension.py
              and reference_types.py), plus test coverage for the false-positive
             failure mode in the gate scan

Consumed by: reference set report serialized by reference_builder.py
             (stories/STORY-001/implementation/suno_mastering/report/reference_builder.py,
              per_track: List[ReferenceMeasurements] — includes
              HfExtensionResult.per_segment_hf_band_limit_hz per-track);
             test suite (tests/test_ground_truth_hf_extension.py,
              tests/test_ref_ac10_verification_bars.py);
             mastering target derivation story
             (STORY-004 requirements.md named this slot "STORY-005"; that story
              now requires a new ID because this story occupies STORY-005)
```

---

## Restated intent

The existence gate in `_gate_scan()` can be satisfied by ordinary spectral
decline in programme material on a 50-second Welch window, producing a
plausible but wrong non-None result — 14066 Hz on segment 1 of The Chemical
Brothers — instead of abstaining. The whole-track result (20475 Hz, 25.79 dB
margin) is correct and unaffected. This story addresses the segment-level
false positive (a wrong number returned where an honest None is warranted),
characterises its downstream impact on `stable` and `confidence`, and gives
the software-architect the information needed to choose from three candidate
resolutions — one of which (explicit documentation and caveat) is a
legitimate outcome, not a fallback.

---

## Rejected as out of scope

This story concerns gate-criterion sensitivity and per-segment reliability
documentation. It does not imply any operation the mastering chain cannot
perform on a stereo sum. `.claude/docs/DOMAIN.md` §4's impossibility list is
not engaged here. No rejection under that section applies.

---

## Problem anatomy

### The track and the failure

**Track**: The_Chemical_Brothers_-_Live_Again_ft_Halo_Maud.wav
(48 kHz stereo, 254.2 s. Confirmed genuine 48 kHz source: the wall at
band 90 / 20475.06 Hz is a real content cliff, not an SRC anti-alias artefact —
see gate2-review-v1.5a.md §5 for the discriminating argument on the SRC
hypothesis, which is a separate open question tracked as Finding 2 from that
review and is out of scope for this story.)

**Observed per-segment values**: `[14065.89, None, 20475.06, 20475.06, None]`

**Whole-track result**: `hf_band_limit_hz = 20475.06 Hz`, `stable = False`,
`confidence = 0.4`.

**Mechanism (gate2-trace-v1.5a.md / gate2-review-v1.5a.md §4 and §6)**:

- Segment 1: `_gate_scan` returned `i_max = 71` (≈ 12502 Hz). In this 50-second
  window the dense electronic programme content produces a gate-qualifying 8 dB
  slope with pre-slope < 12 dB/oct in the 12–15 kHz region — not at a band-limit
  wall. `_floor_onset_index` correctly localised the floor onset relative to that
  anchor, returning 14066 Hz. The number is plausible-looking (above the DOMAIN.md
  §2 10 kHz commercial-master floor) and wrong. This is a false positive: the gate
  fired on programme content, not a cliff.
- Segments 2 and 5: `_gate_scan` returned `None` — no gate-qualifying window was
  found. These are honest abstentions, consistent with those segments consisting
  of breakdown or filtered material where the wall at 20475 Hz lacked sufficient
  spectral structure to pass all three gate tests. A gate that does not fire on
  every segment regardless of content is working as designed.

The v1.5a baseline across the full reference set has a 16% per-segment
abstention rate: 4 of 25 segment calls return None on tracks with confirmed
whole-track walls (Chemical Brothers segments 2 and 5, Wavy Gravy segments 2
and 3). Note: gate2-review-v1.5a.md §6 enumerates all four of these by name
but states "3 instances" — that count is wrong, the enumeration is right. This
document uses the enumeration: 4 abstentions, 16% rate.

### The two separable downstream effects

These two effects have different causes and different remediation paths. They
must not be treated as a single symptom.

**Effect 1 — Spurious value (14066 Hz on segment 1)**

This is a correctness defect. The gate admitted a false-qualifying candidate.
Segment 1 should have returned None (abstention), not a wrong frequency.

- Addressed by option (a) — tightening the gate criterion.
- Addressed by option (b) — per-segment gate parametrisation.
- Left in place by option (c) — documented as a known limitation.

**Effect 2 — `stable = False`, `confidence = 0.4`**

The confidence formula (confirmed in `hf_extension.py` line 297):

```
confidence = agree / len(per_segment_hz)   # denominator always = 5
```

where `agree` counts segments whose non-None value is within
`hf_stability_tolerance_hz` (2000 Hz) of the whole-track value. `None`
counts as not agreeing.

Current breakdown: segments 3 and 4 agree (20475 Hz). Segment 1 disagrees
(14066 Hz is outside the 2000 Hz tolerance). Segments 2 and 5 are None
(not agreeing). Result: `confidence = 2/5 = 0.4`, `stable = False`.

**Critical consequence for options (a) and (b)**: if tightening the gate
converts segment 1's false positive to `None`, the breakdown becomes
`[None, None, 20475.06, 20475.06, None]` — `confidence = 2/5 = 0.4`,
`stable = False`, unchanged. Option (a) and option (b) eliminate the
spurious value but do NOT, by themselves, make `stable = True`. Achieving
`stable = True` requires either: (i) enabling segments 2 and/or 5 to detect
the real wall (so that 3+ segments agree and confidence reaches
`hf_cliff_confidence_stable_floor = 0.6`), or (ii) changing how `stable` is
derived (a further design decision described in Open Questions). Any (a) or (b)
proposal must state explicitly which outcome it achieves.

Option (c) accepts `stable = False` as the correct honest report given the
data, and documents the limitation rather than changing the numbers.

---

## Acceptance criteria

Numbered and testable. Where a criterion's satisfiability depends on the
chosen resolution option, this is stated.

**AC1 — Full reference-set false-positive audit (all options).**
Given the corrected or documented implementation, when `measure_hf_extension`
is run across all five reference tracks using the same five-segment split as
the Gate 2 trace, then a before/after table of all 25 segment measurements
must be produced, classifying each as: CORRECT (within 2000 Hz of the
whole-track value), ABSTAIN (None), or FALSE-POSITIVE (non-None and outside
2000 Hz of the whole-track value), using the whole-track `hf_band_limit_hz`
as ground truth for each track.

The before state (v1.5a baseline) must show exactly one false positive
(Chemical Brothers segment 1: 14066 Hz) and four abstentions (Chemical
Brothers segments 2 and 5, Wavy Gravy segments 2 and 3). The after state
must show zero false positives. The abstention count after must not exceed
the abstention count before by more than a bound established by the architect
(see Open Question 1) — this bound is the formal statement of the abstention-
rate tradeoff. Demonstrating zero false positives for one track while leaving
the abstention-count change unquantified does not satisfy AC1.

This AC is not satisfiable by running Chemical Brothers alone. A single-track
demonstration would reproduce the parameter-tuning anti-pattern named in
`.claude/docs/CLAUDE.md` §5 ("DEF-201's first fix moved a threshold 6→20 dB.
Numbers changed; method still wrong") and explicitly inverted here: gate
parameters may be changed, but only if the full-reference-set audit shows
the effect on all 25 measurements.

**AC2 — No regression on whole-track values (all options).**
Given the corrected or documented implementation, when the five reference
tracks are re-measured, then the whole-track `hf_band_limit_hz` values for
all five tracks must be identical to the v1.5a values (Black Flute 15788 Hz,
GusGus 16251 Hz, Leftfield 20475 Hz, Chemical Brothers 20475 Hz, Wavy Gravy
20475 Hz). The whole-track detector is applied to the silence-gated active-
audio PSD; any change to gate parameters that does not touch the whole-track
path should satisfy this vacuously, but it must be verified, not assumed.

**AC3 — No regression on stable tracks (all options).**
Given the corrected or documented implementation, when the five reference
tracks are re-measured, then the three tracks that v1.5a reported with
`stable = True` and `confidence = 1.0` (Black Flute, GusGus, Leftfield) and
the one track with `stable = True` and `confidence = 0.6` (Wavy Gravy) must
not flip to `stable = False`. A proposal that achieves zero false positives by
converting currently-stable results into abstentions does not satisfy AC3.

**Wavy Gravy is the discriminating case here.** It holds `stable = True`
by exactly zero margin: `confidence = 0.6 = hf_cliff_confidence_stable_floor`
(gate2-review-v1.5a.md §2 Finding 4). One of its three currently-agreeing
segments turning to None under a tightened gate drops it to `confidence = 0.4`,
`stable = False`. Because parameter tightening reduces detections uniformly,
AC1 (zero false positives) and AC3 (no stable-flip on Wavy Gravy) may be
jointly unsatisfiable for any parameter value. If the architect's 25-segment
audit under option (a) or (b) finds no parameter value satisfying both, that
finding is the evidence selecting option (c) — not a requirements failure.
State this outcome in architecture.md and cross-reference Open Question 4
(Finding 4's disposition may relieve the constraint by changing how `stable`
is derived).

**AC4 — Chemical Brothers false positive eliminated (options a and b).**
Given the corrected implementation, when Chemical Brothers is measured, then
`per_segment_hf_band_limit_hz[0]` (segment 1) must not return 14066 Hz or
any other non-None value that disagrees with the whole-track value by more
than 2000 Hz. It may return `None` (abstention) or a value within 2000 Hz of
20475 Hz. Returning `None` satisfies AC4 but does not, by itself, change
`stable` or `confidence` — see the problem anatomy above.

**AC5 — Documented per-segment reliability caveat (option c specifically).**
Given that option (c) is selected, `HfExtensionResult` must carry an explicit,
machine-readable caveat about the false-positive risk. This caveat must appear
in both:
- The Python source (dataclass docstring or module docstring in
  `hf_extension.py`), for code-level consumers; and
- The serialized reference set report produced by `reference_builder.py`,
  for downstream JSON consumers. The mechanism is the architect's choice (a
  per-track `plausibility_warnings`-style field, a schema-level note, or a
  dedicated flag on the report schema); the requirement is that a consumer
  reading only the JSON can see the caveat without requiring access to the
  Python source.

The caveat content must assert:
(a) Per-segment values on complex programme material may be false positives
    (wrong non-None numbers, not abstentions) where the gate fires on spectral
    content unrelated to the band-limit wall.
(b) The false-positive condition is distinct from None: None is an honest
    abstention; a non-None value outside `hf_stability_tolerance_hz` of the
    whole-track value is a false positive and must not be treated as an
    alternative band-limit estimate.
(c) `stable = False` with `confidence = 0.4` on a track with a strong
    whole-track margin is a correct report, not a detector failure, under
    current gate parameters.

Option (c) must also reconcile with `.claude/docs/CLAUDE.md` §5's statement
"Reporting a fixed property as varying — instability means the method is
wrong" and `.claude/docs/DOMAIN.md` §2's statement "A detector reporting it
as unstable is measuring programme content." This reconciliation is a
**required section of the architecture.md produced from this story if option
(c) is selected**: it must explain why the honest abstentions (None returns on
segments 2 and 5) are consistent with the method being correct, and why the
false positive (segment 1's 14066 Hz) is acknowledged as a known method
limitation rather than a design violation. The architect must make this
argument explicitly; a Gate 1 reviewer will check it.

**AC6 — Test coverage for the false-positive failure mode (all options).**
Given the ground-truth test suite, when the tilt + non-stationarity +
programme-content-decline negative control (required by STORY-004 AC1) is
run, then a new fixture specifically targeting the segment-level false-
positive failure mode must exist. The fixture must:
(a) Generate audio where a gate-qualifying slope exists at a frequency well
    below a real band-limit wall (or below any wall at all), simulating the
    programme-content gate-satisfaction scenario.
(b) For options (a) and (b): assert that `per_segment_hf_band_limit_hz`
    contains no false positives (non-None values disagreeing with the whole-
    track result by more than the tolerance) after this story's changes.
(c) For option (c): assert that the caveat field introduced by AC5 is
    present and non-empty in the report output — a structural completeness
    assertion on the serialized report, not a numeric measurement assertion.

This is a new fixture beyond STORY-004's existing coverage, not a rewrite of
an existing one.

---

## Constraints and risks

### Abstention-rate tradeoff (options a and b)

The current baseline abstention rate is 16%: 4 of 25 segment measurements
return None on tracks with confirmed whole-track walls (see problem anatomy
above for the correct enumeration). The gate parameters
(`hf_cliff_required_drop_db = 8.0 dB`,
`hf_cliff_passband_max_slope_db_per_octave = 12.0 dB/oct`) were derived
from whole-track PSD statistics. Any parameter tightening — whether applied
uniformly (option a) or per-segment only (option b) — trades false positives
for abstentions.

**The tradeoff is not symmetric**. A false positive (wrong number) is
qualitatively worse than an abstention (None), because: (i) abstentions are
honest and recognisable to callers, (ii) wrong numbers propagate silently into
downstream consumers including the reference set report serialized by
`reference_builder.py` (confirmed by grep: `per_track: List[ReferenceMeasurements]`
includes `HfExtensionResult` with `per_segment_hf_band_limit_hz`). But
tightening beyond the point where Wavy Gravy's `stable = True` flips to False
is not acceptable either — see AC3.

**The right per-segment parameters are empirically unknown without wider
study.** The illustrative value in the defect report (lowering
`hf_cliff_passband_max_slope_db_per_octave` from 12.0 to 9.0 dB/oct) is
one candidate; it is not validated. Note on mechanism: this parameter is a
ceiling on the local pre-slope (`if local_pre_slope > max_slope: continue`
in `_gate_scan`), so **lowering** the value tightens the gate by rejecting
candidates where the immediately pre-candidate spectral slope is already
above the ceiling. The architect must quantify the full 25-segment impact of
any proposed value before committing to it. AC1 exists to enforce this.

### Complexity cost (option b)

Maintaining two gate-criterion configurations — one for whole-track PSD and
one for per-segment PSD — adds tunable parameters with no clear derivation
other than "empirically doesn't produce false positives on these five tracks."
This is an architectural complexity cost. If the correct per-segment parameters
are merely tighter versions of the whole-track ones, option (b) is equivalent
to option (a) with extra machinery and should not be preferred. Option (b) is
worth its complexity only if per-segment and whole-track PSDs require
structurally different parameters for reasons the architect can state and
derive, not merely assert.

### Legitimate outcome status of option (c)

Option (c) is not a fallback. It is a legitimate resolution if the architect
determines that: (i) the false-positive is bounded and detectable by callers
via the `stable` and `confidence` fields, (ii) per-segment values are
corroboration material, not primary outputs, and (iii) the documentation
obligation under AC5 is met. The mastering engineer's Gate 2 review
(gate2-review-v1.5a.md §3 Finding 1) states that `stable = False` and
`confidence = 0.4` are the correct reported metadata for Chemical Brothers
under the current implementation, and that the segment 1 false positive is
"defect-grade" but does not affect the whole-track result. Option (c) accepts
that assessment and codifies it as the designed behaviour.

---

## Explicit out of scope

- **Finding 2 (5/5 transcode flags / SRC vs lossy hypothesis)**: whether the
  three tracks at 20475 Hz are lossy-sourced or carry an SRC anti-alias artefact
  from this project's own file preparation is unresolved and must be resolved
  separately before the mastering target derivation story proceeds. It is not
  in scope here. See gate2-review-v1.5a.md §5 for the discriminating test.
- **Finding 3 (Black Flute 0.08 dB margin)**: the confidence metric's
  inability to surface adjacent-band quantization risk at the 2000 Hz tolerance
  is a separate code-level finding. Out of scope.
- **Finding 4 (Wavy Gravy `stable = True` by zero margin)**: `confidence = 0.6`
  exactly at `hf_cliff_confidence_stable_floor = 0.6` is a confidence-
  quantization-boundary issue. Out of scope for this story as a standalone fix.
  However, see Open Question 4 — Finding 4's disposition is mechanically
  entangled with the `stable = False` half of DEF-205 and with AC3's Wavy Gravy
  constraint, and may provide a resolution path for the `stable` sub-problem.
- **Any change to the whole-track PSD path**: this story concerns only
  per-segment gate behaviour. The whole-track detector is correct and must not
  be changed unless option (b)'s per-segment parametrisation design requires a
  code-structural change that also touches the whole-track path, in which case
  AC2 regression coverage applies.
- **Reference set provenance and target derivation**: the mastering target
  derivation story (the downstream consumer of this story's output) is not in
  scope here. STORY-005's deliverable is a corrected or caveated
  `HfExtensionResult`; what the target derivation story does with it is its
  own contract.
- **Wavy Gravy's gate-miss pattern (as a standalone target)**: Wavy Gravy
  segments 2 and 3 returned None under v1.5a. Those are honest abstentions (same
  mechanism as Chemical Brothers segments 2 and 5) and are not false positives.
  They are counted in the AC1 abstention baseline (4/25) but are not specifically
  targeted by this story's fix. If option (a) or (b) incidentally enables Wavy
  Gravy segments 2 and 3 to detect the real wall, that is an acceptable
  improvement; if it introduces new false positives on those segments, AC1
  will catch it.

---

## Non-functional requirements

- Full test suite runs in under 60 seconds (`.claude/docs/HANDOFF.md` Part 3,
  Definition of Done). If the AC6 fixture requires generating audio with
  specific per-segment spectral characteristics, the fixture's generation cost
  must not push the suite above this bound; isolate to a slow-test marker per
  STORY-002 defects.md DEF-106's precedent if necessary.
- Reproducibility: given the same input file and config, output must be
  bit-identical across runs. No new source of non-determinism may be
  introduced by any gate-parameter change or documentation change.
- Schema version: no change to `reference_builder.py`'s `SCHEMA_VERSION`
  unless this story's changes to `HfExtensionResult` fields require it per
  that file's own versioning convention (MINOR bump for additive fields; MAJOR
  for removed or reshaped fields). Changing a parameter constant or adding
  docstring text does not require a bump. If option (c) adds a new per-track
  field to carry the caveat in the report, that is a MINOR bump.

---

## Open questions

1. **Acceptable abstention-rate ceiling after option (a) or (b)**: the 16%
   baseline (4/25) was not a design target — it is the empirical outcome of
   the current parameters on these five tracks. The architect must propose a
   ceiling and derive it from a principled criterion (e.g. "at least 2 segments
   must corroborate the whole-track result for confidence ≥ 0.4, which requires
   no more than 3 additional abstentions beyond the baseline 4") rather than
   tuning until the Chemical Brothers false positive disappears. This ceiling
   is a required input to AC1 and must appear in architecture.md.

2. **Which resolution option to choose**: options (a), (b), and (c) all satisfy
   the problem statement subject to their respective acceptance criteria. The
   decision belongs to the architect, not this document. The architect should
   consider:
   - Option (a): simplest, but the correct parameter value is unknown without
     the full 25-segment study; lowers `hf_cliff_passband_max_slope_db_per_octave`
     from 12.0 to a value to be determined; may not fix `stable = False` (see
     problem anatomy); may flip Wavy Gravy to `stable = False` (see AC3).
   - Option (b): allows whole-track parameters to remain unchanged, but adds
     complexity; same `stable = False` limitation as (a) unless segments 2/5
     also detect the real wall at the tighter per-segment criterion.
   - Option (c): no code change to the gate; documentation obligation under AC5
     is non-trivial and includes a JSON-serialized report caveat; the CLAUDE.md
     §5 / DOMAIN.md §2 reconciliation argument is required in architecture.md;
     accepted by the Gate 2 mastering-engineer review as describing the correct
     honest output.

3. **`stable = False` residual after options (a) and (b)**: if the architect
   selects option (a) or (b) and the tightened gate converts segment 1 to None
   but does not enable segments 2 and 5 to detect the real wall, Chemical
   Brothers will remain at `confidence = 0.4`, `stable = False`. The
   architecture.md must state explicitly whether this outcome is accepted as the
   result of STORY-005, or whether the story also targets the `stable = False`
   half. If the latter, the architect must specify which mechanism achieves it
   (enabling more segments to detect the wall vs. changing how `stable` is
   derived — see Open Question 4).

4. **Finding 4 entanglement with the `stable = False` half and with AC3**: the
   options enumerated above ((a), (b), (c)) do not exhaust the space of
   resolutions for the `stable = False` half. Finding 4 from gate2-review-v1.5a.md
   §2 notes that `hf_cliff_confidence_stable_floor = 0.6` sits exactly on a
   quantization boundary for five segments, and suggests that deriving `stable`
   from the whole-track margin directly (rather than from segment agreement
   count) would better reflect what "stable" means for a track with a 25.79 dB
   whole-track margin. If the architect selects this approach as part of the
   STORY-005 design: (i) it must be noted in architecture.md as addressing
   Finding 4's disposition, (ii) it may relieve the AC3 Wavy Gravy constraint
   (since `stable` would no longer depend on segment agreement count), and (iii)
   it changes the meaning of `stable` for all tracks, not just Chemical Brothers —
   the architect must state what `stable` means under the new derivation and
   verify the redefined field against all five reference tracks. Do not treat
   "derive `stable` from whole-track margin" as a standalone fourth option; it
   is a potential component of the `stable` sub-problem within whichever of
   options (a), (b), or (c) is chosen.

5. **Whether `hf_band_limit_robustness_db` (the minimum per-segment j* margin)
   can discriminate false positives from true walls**: the comment in
   `reference_types.py` notes this field "Does NOT validate the anchor itself —
   see DEF-205 (open)." A false-positive segment's reported j* margin may be
   shallower than a true-wall segment's (the gate fired on a tilt, not a wall,
   so the floor onset is less definitive). The architect may consider whether
   this field can serve as a post-hoc discriminator rather than or in addition
   to tightening the gate up-front. If this is pursued, it must be derived, not
   asserted (H4), and demonstrated on a synthetic fixture that distinguishes
   the two cases.

---

## Revision history

v1 (2026-08-09) — first pass. Produced from: story context provided in the task
prompt, `stories/STORY-004/gate2-trace-v1.5a.md`, `stories/STORY-004/gate2-review-v1.5a.md`,
`stories/STORY-001/implementation/suno_mastering/analysis/hf_extension.py` (confidence
computation confirmed at line 297 — denominator is always 5), and `reference_types.py`
(HfExtensionResult fields confirmed; DEF-205 citation at line 62 confirmed). Consumer
of `per_segment_hf_band_limit_hz` confirmed as: test suite and the reference set report
serialized by `reference_builder.py` (`per_track: List[ReferenceMeasurements]`). No prior
requirements.md or story.md exists for STORY-005.

v1.1 (2026-08-09) — advisor review before delivery. Three blockers fixed: (1) abstention
baseline corrected to 4/25 = 16% throughout — the problem anatomy section previously
quoted gate2-review-v1.5a.md §6's "3 instances" figure, which that source's own
enumeration contradicts (four segments named, three stated); the enumeration is
authoritative. (2) AC3 now explicitly states that Wavy Gravy's zero-margin status
makes it the discriminating constraint: if no parameter value satisfies AC1+AC3
simultaneously, that is the evidence selecting option (c), not a requirements failure.
(3) AC5 now requires the caveat to appear in both the Python source and the serialized
JSON report — a docstring-only caveat does not reach report consumers. AC6(c) updated
to assert on the report-level field, not the docstring. One minor clarification: the
option (a) mechanism is now stated unambiguously as lowering (not raising)
`hf_cliff_passband_max_slope_db_per_octave` from 12.0 to a value to be determined.
