# STORY-005 Architecture — DEF-205: Per-Segment Gate False Positive (Chemical Brothers)

Governed by `.claude/docs/CLAUDE.md`, `.claude/docs/DOMAIN.md`,
`.claude/docs/ARCHITECTURE.md`. Where they conflict with this document,
they take precedence; raise the conflict rather than deviating.

---

## §1 — Design decision summary

| Item | Decision |
|---|---|
| Resolution option | **Option (c)** — explicit documentation and machine-readable caveat |
| Gate parameters changed | **None** — `_gate_scan` and `_floor_onset_index` unchanged |
| `HfExtensionResult` new fields | `per_segment_reliability_caveat: Optional[str]`; `hf_band_limit_whole_track_margin_db: Optional[float]` |
| SCHEMA_VERSION | `"2.1"` → `"2.2"` (additive fields, MINOR bump per `reference_builder.py` convention) |
| `stable = False` on Chemical Brothers | **Accepted** — this story does not target the `stable` sub-problem |
| Finding 4 (`stable` from margin) | **Incompatible with AC3 given current reference set** — see §7 |
| OQ5 (`robustness_db` as discriminator) | **Deferred** — insufficient per-band trace data to derive; see §8 |
| AC1 zero-false-positives scoping | Scoped to options (a)/(b) by AC4 and by requirements.md §Effect 1; see §3.5 |

---

## §2 — Resolution choice: why option (c), why not (a) or (b)

### §2.1 — Why not option (a): tightened pre-slope gate

**Option (a) is not derivable from available evidence and does not achieve the
story's primary goals.**

If option (a) successfully converts Chemical Brothers segment 1 from `14066 Hz`
to `None`, the per-segment breakdown becomes:

```
Before (a): [14065.89, None, 20475.06, 20475.06, None]   confidence = 2/5 = 0.4
After (a):  [None,     None, 20475.06, 20475.06, None]   confidence = 2/5 = 0.4
```

Converting 14066 Hz to `None` is a real correctness improvement: the
per-segment field would contain an honest abstention instead of a wrong number.
However, `confidence` and `stable` are unchanged — they remain 0.4 and `False`.
The `stable = False` outcome, which suppresses lossless-confidence-N counting on
Chemical Brothers, is the primary downstream consequence of DEF-205, and option
(a) does not address it.

**Cost:** AC3 constrains any parameter tightening. Wavy Gravy holds
`stable = True` by zero margin (`confidence = 0.6 = hf_cliff_confidence_stable_floor`
exactly, gate2-trace-v1.5a.md §2 Finding 4). Three of its five segments agree.
Any parameter tightening that converts one agreeing Wavy Gravy segment to `None`
drops it to `confidence = 2/5 = 0.4`, `stable = False` — an AC3 violation.

**The derivation-unavailability problem:** the gate2 trace records `freeze_index`
and `suffix_max` windows for each candidate but never dumps `levels_db[i - 24] -
levels_db[i]` (the actual pre-slope measurement at candidate `i`). The 25
per-segment pre-slope values that would justify a new threshold do not exist in
any artifact in this repository. Requirements.md §Constraints explicitly
states: "gate parameters may be changed, but only if the full-reference-set
audit shows the effect on all 25 measurements." This is not a soft preference
— AC1 would require generating those values before any parameter could be proposed.

CLAUDE.md §5 prohibits "fixing the wrong method by tuning its parameter." A
guessed value of 9.0 dB/oct — the illustrative candidate in requirements.md §OQ1
— without a derived basis is exactly that pattern. Option (a) is therefore
not derivable from available evidence and simultaneously achieves no measurable
improvement over option (c) in the properties that matter (whole-track result
and `stable`).

### §2.2 — Why not option (b): per-segment gate parametrisation

Requirements.md §Constraints (Complexity cost) states option (b) is warranted
only if "per-segment and whole-track PSDs require structurally different
parameters for reasons the architect can state and derive, not merely assert."

**Both paths use the same `nperseg`.** `welch_nperseg` (verified in
`_psd.py` lines 17–21) returns `min(65536, max(1024, 2^floor(log2(n_samples))))`.
For a 254-second file at 48 kHz (`n_samples ≈ 12.2M`), `2^floor(log2(12.2M))
= 2^23 = 8388608`, capped to `65536`. For a 50-second segment at 48 kHz
(`n_samples ≈ 2.4M`), `2^floor(log2(2.4M)) = 2^21 = 2097152`, capped to `65536`.
Both use `nperseg = 65536`. Frequency resolution is identical.

**But the number of averaged windows differs substantially.** With
`noverlap = nperseg // 2 = 32768`:

- Whole-track (`n_samples ≈ 12201600`): `floor((12201600 − 65536) / 32768) + 1 ≈ 371 windows`
- Per-segment (`n_samples ≈ 2440320`): `floor((2440320 − 65536) / 32768) + 1 ≈ 73 windows`

The Welch estimator's variance per band is proportional to `1 / n_windows`.
Per-segment PSD carries `371 / 73 ≈ 5.1×` higher per-band variance than
whole-track PSD, giving `√5.1 ≈ 2.25×` higher standard deviation per band.

This is the correct structural argument for option (b) — and it makes option
(b) **actively worse**, not better. A tightened pre-slope ceiling applied to
a measurement with 2.25× higher noise discriminates more poorly: the pre-slope
at candidate band `i` on a per-segment PSD carries a larger noise component,
meaning the same physical slope can land anywhere in a wider observed range.
Applying a tighter ceiling to a noisier measurement increases false negatives
(genuine walls missed) without reliably reducing false positives where the
pre-slope is close to the ceiling.

The false positive on Chemical Brothers segment 1 is a programme-content
spectral variation averaged out in the whole-track PSD (dense electronic
material producing a tilt in the 12–15 kHz region within a 50-second window).
This is a content phenomenon, not a resolution phenomenon. A resolution-motivated
parameter split has no mechanism for addressing a content-driven false positive.

Option (b) is therefore option (a) with additional configuration machinery,
applied to noisier measurements, without a mechanism for the actual problem.
It is not preferred.

### §2.3 — Why option (c)

Three conditions from requirements.md §Legitimate outcome status of option (c)
are all met:

1. **The false positive is bounded and detectable by callers.** `stable` and
   `confidence` already signal that per-segment agreement is below the stable
   floor. The new `per_segment_reliability_caveat` field (§5) makes detection
   explicit and machine-readable at the per-track level.

2. **Per-segment values are corroboration material, not primary outputs.**
   `hf_band_limit_hz` is always derived from the whole-track detector. Per-segment
   values feed `hf_band_limit_confidence` and `stable` as an agreement count.
   No caller is expected to treat `per_segment_hf_band_limit_hz[0] = 14066 Hz`
   as a band-limit estimate for Chemical Brothers; the field exists as a
   diagnostic, not as a parallel output.

3. **The documentation obligation under AC5 is met by this architecture.** See §5.

The mastering engineer's Gate 2 review (gate2-review-v1.5a.md §3 Finding 1)
accepts `stable = False, confidence = 0.4` as the correct reported metadata
for Chemical Brothers and characterises segment 1 as "defect-grade" but not
affecting the whole-track result. This architecture codifies that assessment
as designed behaviour.

---

## §3 — CLAUDE.md §5 / DOMAIN.md §2 reconciliation (required by AC5)

### §3.1 — The fixed-property constraint

DOMAIN.md §2: "A band limit is a fixed property of a file. A detector reporting
it as unstable is measuring programme content."

CLAUDE.md §5 known-wrong pattern: "Reporting a fixed property as varying —
instability means the method is wrong."

These constraints apply to the **measurement of the fixed property**.
The fixed property for Chemical Brothers is `hf_band_limit_hz = 20475.06 Hz`.
The whole-track detector returns this value with a 25.79 dB margin. No branch of
the implemented code reports this value as varying. AC2 requires it to remain
stable across runs, and the gate2 trace confirms it does.

### §3.2 — What `stable = False` actually asserts

`stable = False` is not a claim that the band limit varies. It is a claim
about how many 50-second windows contained sufficient spectral evidence to
corroborate the whole-track detection at 20475 Hz. Specifically:

```
confidence = agree / 5     # where agree = |{i : per_segment_hz[i] is not None
                           #                  and |per_segment_hz[i] - 20475.06| ≤ 2000}|
stable = (confidence >= 0.6)
```

`confidence = 0.4` means 2 of 5 windows found enough evidence. The other 3
either had insufficient spectral structure (segments 2 and 5 → `None`) or
misidentified a programme-content tilt as a wall (segment 1 → 14066 Hz).

This is a statement about the corroboration mechanism's window-level sensitivity,
not a statement about the band limit. DOMAIN.md §2 and CLAUDE.md §5 constrain
the measurement of the fixed property — the whole-track result — and that
measurement is correct.

### §3.3 — The honest abstentions (None on segments 2 and 5)

DOMAIN.md §2 names the mechanism: "A detector reporting it as unstable is
measuring programme content." Segments 2 and 5 abstained because those 50-second
windows consisted of breakdown or filtered material where the energy at 20 kHz
was insufficient to pass all three gate tests. The gate not firing is working
as designed — it is preferable to a false positive. These are honest abstentions
in the same sense that a confidence interval does not shrink by misrepresenting
the data.

Honest abstentions do not violate the fixed-property constraint because they
do not assert a different value for the band limit. They report ignorance, not
variation.

### §3.4 — The false positive (segment 1: 14066 Hz)

Segment 1 IS measuring programme content — the gate fired on a spectral tilt
in the 12–15 kHz region of a 50-second window of dense electronic material.
This is the failure mode DOMAIN.md §2 names.

This failure mode is confined to `per_segment_hf_band_limit_hz`. The value
`14066 Hz` never feeds `hf_band_limit_hz`. The false positive affects only the
agreement count (one count that would have been `None → agree` under a tighter
gate becomes `14066 → disagree` instead).

The false positive is acknowledged as a real method limitation. Option (c)
does not deny it. It makes it machine-detectable (§5) and documents the
boundary: per-segment values on complex programme material in 50-second windows
can produce gate-qualifying slopes from spectral content unrelated to a band-limit
wall. A caller who reads `per_segment_reliability_caveat` knows this.

### §3.5 — AC1 zero-false-positives scoping

AC1's zero-false-positives clause is scoped to options (a) and (b). Two
cross-references in requirements.md establish this:

- Requirements.md §Effect 1 states explicitly: "Left in place by option (c) —
  documented as a known limitation." This is not an oversight; the BA wrote this
  alongside the AC1 requirement.
- AC4 is titled "(options a and b)" and is the requirement that explicitly mandates
  `per_segment_hf_band_limit_hz[0]` must not return a value disagreeing with the
  whole-track. No equivalent obligation exists for option (c) in requirements.md.

Under option (c), the after state retains one segment-level false positive
(Chemical Brothers segment 1: 14065.89 Hz). This is expected, stated, and
disclosed via `per_segment_reliability_caveat`. Gate 1 review should confirm
this scoping is consistent with the BA's intent.

---

## §4 — 25-segment before/after audit

Option (c) makes no gate parameter changes. **Before state = after state.**
The audit table is presented to establish the baseline formally, as AC1 requires.

Classification key: **C** = CORRECT (within 2000 Hz of whole-track value),
**A** = ABSTAIN (None returned), **FP** = FALSE-POSITIVE (non-None, outside
2000 Hz of whole-track value), **WT** = whole-track `hf_band_limit_hz`.

| Track | WT (Hz) | Seg 1 | Seg 2 | Seg 3 | Seg 4 | Seg 5 | stable | conf |
|---|---|---|---|---|---|---|---|---|
| Black Flute | 15788 | 15788 (C) | 15788 (C) | 15788 (C) | 15788 (C) | 15788 (C) | True | 1.0 |
| GusGus | 16251 | 16251 (C) | 16251 (C) | 16251 (C) | 16251 (C) | 16251 (C) | True | 1.0 |
| Leftfield | 20475 | 20475 (C) | 20475 (C) | 20475 (C) | 20475 (C) | 20475 (C) | True | 1.0 |
| Chemical Brothers | 20475 | **14066 (FP)** | None (A) | 20475 (C) | 20475 (C) | None (A) | **False** | 0.4 |
| Wavy Gravy | 20475 | 20475 (C) | None (A) | None (A) | 20475 (C) | 20475 (C) | True | 0.6 |

**After-state summary (option c — no gate change):**
- CORRECT: 20 / 25 (80%)
- ABSTAIN: 4 / 25 (16%) — baseline, unchanged
- FALSE-POSITIVE: 1 / 25 (4%) — retained; disclosed via `per_segment_reliability_caveat`

**Abstention ceiling (OQ1):** Under option (c) no parameters change, so the
abstention count cannot increase. The effective ceiling is the current baseline:
4/25 = 16%. No formal derivation is required because no parameter changes.
If a future story selects option (a), OQ1 must be re-opened with a derivation
principled around the minimum-corroboration property ("at least 2 segments must
agree for `confidence ≥ 0.4`" → at most 3 additional abstentions beyond baseline
4, i.e., ceiling = 7/25 = 28%).

**AC3 Wavy Gravy constraint:** Satisfied trivially. No gate parameters change;
Wavy Gravy's `confidence = 0.6 = stable floor` is unchanged.

**AC2 whole-track regression:** Satisfied trivially. The whole-track detection
path is untouched.

**AC4 (options a and b only):** Not applicable to option (c).

---

## §5 — Schema and implementation changes

### §5.1 — New fields on `HfExtensionResult` (`reference_types.py`)

Two new fields, both defaulting to `None` (backward-compatible; no existing
code breaks):

**Field 1: `per_segment_reliability_caveat: Optional[str] = None`**

Population condition (computed in `measure_hf_extension` after per-segment
results are assembled):

```
populated when:
    whole_track_hz is not None
    AND any(
        s is not None
        and abs(s - whole_track_hz) > config.hf_stability_tolerance_hz
        for s in per_segment_hz
    )
```

When populated, the string must assert the three AC5 content requirements
verbatim or substantively equivalent:

(a) Per-segment values on complex programme material may be false positives
    where the gate fires on spectral content unrelated to the band-limit wall.

(b) A non-None value outside `hf_stability_tolerance_hz` of the whole-track
    value is a false positive and must not be treated as an alternative
    band-limit estimate. `None` is an honest abstention — a distinct state.

(c) `stable = False` with low confidence on a track with a strong whole-track
    margin is a correct report under current gate parameters, not a detector
    failure.

Suggested string (developer may match this exactly or rephrase without weakening
content):

```python
(
    "per-segment gate false positive detected: one or more segments returned a "
    "non-None value disagreeing with the whole-track result by more than "
    f"{config.hf_stability_tolerance_hz:.0f} Hz. "
    "This indicates the per-segment gate fired on programme-content spectral "
    "decline, not a band-limit wall. Per-segment values on complex material "
    "must not be used as alternative band-limit estimates. "
    "None on a segment is an honest abstention (insufficient spectral evidence) "
    "and is distinct from this false-positive condition: None does not indicate "
    "the gate misfired. "
    "stable=False with low confidence and a strong whole-track margin is the "
    "correct honest report under current gate parameters."
)
```

The string interpolates `config.hf_stability_tolerance_hz` rather than
hardcoding 2000 Hz, so the caveat text remains consistent with the threshold
actually applied if the config value changes. This is the only config-derived
element; the rest of the string is invariant.

The field is `None` on tracks where no per-segment false positive is detected.
A consumer performing `if result.per_segment_reliability_caveat is not None`
can detect and handle affected tracks without parsing the string content.

**Field 2: `hf_band_limit_whole_track_margin_db: Optional[float] = None`**

The `measure_hf_extension` function at `hf_extension.py` line 322 already
computes the whole-track `(cliff_hz, margin_db)` tuple from `_detect_cliff`.
The margin is currently discarded. This field exposes it.

Population condition: `hf_band_limit_hz is not None`. Set to the `margin_db`
value returned by the whole-track `_detect_cliff` call. `None` when no
whole-track cliff is found.

**Margin definition (Gate 1 F1 correction):** `_floor_onset_index` returns
`min(rightward_margin, leftward_margin)` — the two-sided minimum — and
`_detect_cliff` passes this through unchanged (hf_extension.py lines 184–209).
The field therefore contains the **two-sided minimum j* margin** on the
whole-track PSD, not the rightward margin alone.

Per-track values (derived from gate2-trace-v1.5a.md; see gate1-review.md F1):

| Track | Two-sided min margin |
|---|---|
| Black Flute | 0.39 dB |
| GusGus | 3.62 dB |
| Chemical Brothers | 3.22 dB |
| Leftfield | 8.00 dB |
| Wavy Gravy | 8.00 dB |

For Leftfield and Wavy Gravy, j* immediately follows the passband anchor
(`j* = freeze_index + 1`), so the leftward component equals exactly
`hf_cliff_required_drop_db = 8.0 dB` — a structural floor on the two-sided
minimum when the cliff is adjacent to the anchor.

**Interpretation:** The two-sided minimum margin bounds how far noise can move
`j*` in either direction on the full PSD. A margin above the Welch noise floor
(approximately 0.5 dB at these signal levels) indicates the whole-track cliff
location is not dominated by measurement noise. Chemical Brothers' 3.22 dB
margin confirms the whole-track cliff at 20475 Hz is well-localised, and the
`stable = False` outcome is a segmentation artifact, not whole-track measurement
ambiguity. Black Flute's 0.39 dB margin (within Welch noise) remains the
marginal-detection finding noted in gate2-trace-v1.5a.md §Black Flute.

Callers can read this field together with `per_segment_reliability_caveat` to
understand whether `stable = False` reflects genuine whole-track uncertainty
or merely insufficient per-segment corroboration.

This field is structurally parallel to `hf_band_limit_robustness_db` (the
minimum two-sided j* margin across per-segment cliff detections), which already
exists. Both fields use the same two-sided margin definition from
`_floor_onset_index`. Together:

| Field | What it measures |
|---|---|
| `hf_band_limit_whole_track_margin_db` | Two-sided min j* margin on the whole-track PSD (definitiveness of whole-track result) |
| `hf_band_limit_robustness_db` | Min two-sided j* margin across per-segment detections (localization sensitivity within those segments; may incorporate a false-positive segment's margin when `per_segment_reliability_caveat` is non-None) |

**`hf_band_limit_robustness_db` note (OQ5):** Requirements.md OQ5 asks whether
this field can discriminate false positives from true walls post-hoc. It cannot
be confirmed without the per-band `levels_db` arrays for Chemical Brothers
segment 1, which are not in any trace artifact. This field remains a
localization robustness indicator; its utility as a false-positive discriminator
is deferred. The comment at `reference_types.py` line 62 already flags this:
"Does NOT validate the anchor itself — see DEF-205 (open)." No change to that
comment; this story does not resolve that open item.

### §5.2 — `hf_extension.py` changes

**Location of population:** in `measure_hf_extension`, after the whole-track
`_detect_cliff` call returns `(whole_track_hz, whole_track_margin_db)` (or
`None`), and after the per-segment loop completes.

**Step 1** — expose whole-track margin. Line 322 already has `whole_track_result`
available. The developer should unpack it:

```
if whole_track_result is not None:
    whole_track_hz, whole_track_margin_db = whole_track_result
else:
    whole_track_hz, whole_track_margin_db = None, None
```

**Step 2** — compute caveat after the per-segment loop:

```
per_segment_reliability_caveat = None
if whole_track_hz is not None:
    for s in per_segment_hz:
        if s is not None and abs(s - whole_track_hz) > config.hf_stability_tolerance_hz:
            per_segment_reliability_caveat = <caveat string using config.hf_stability_tolerance_hz>
            break
```

**Step 3** — pass both new fields into the `HfExtensionResult(...)` constructor.

No other changes to `hf_extension.py`. Gate functions (`_gate_scan`,
`_floor_onset_index`, `_detect_cliff`) are unchanged.

### §5.3 — `reference_render.py` changes

**JSON path:** `render_json` uses `dataclasses.asdict(report)` (verified at
`reference_render.py` line 25). Any `Optional[str]` or `Optional[float]` field
on `HfExtensionResult` propagates automatically to JSON. No change to `render_json`.

**Markdown path:** `_track_section` (lines 86–138 of `reference_render.py`)
renders `HfExtensionResult` fields individually. Two new rendering blocks must
be added after the existing `robustness_db` block (around line 115):

1. If `m.hf_extension.per_segment_reliability_caveat is not None`, render:
   `"  - Per-segment reliability caveat: {m.hf_extension.per_segment_reliability_caveat}"`

2. If `m.hf_extension.hf_band_limit_whole_track_margin_db is not None`, render:
   `"  - Whole-track j* margin: {_fmt(m.hf_extension.hf_band_limit_whole_track_margin_db, 2)} dB"`

The developer should follow the pattern of the existing `robustness_db` block
(lines 104–115).

### §5.4 — `reference_builder.py` schema version

Bump `SCHEMA_VERSION` from `"2.1"` to `"2.2"`. This is an additive change
(two new optional fields, both defaulting to `None`); existing consumers of
the v2.1 schema receive `None` for both new fields and are unaffected. Per
the file's own convention (verified at lines 27–45): MINOR bump for additive
backward-compatible changes.

The `_config_summary` function (or its equivalent docstring block documenting
schema history) must record the v2.2 change, consistent with how v2.1 was
documented.

---

## §6 — `stable = False` disposition and the segment-agreement sub-problem (OQ3)

**Disposition for STORY-005:** `stable = False, confidence = 0.4` on Chemical
Brothers is accepted as the correct output. This story does not target the
`stable = False` half. The `stable` formula and `hf_cliff_confidence_stable_floor`
configuration parameter are unchanged.

**Rationale:** Two of five segments on Chemical Brothers returned `None` (honest
abstentions — insufficient spectral structure in those 50-second windows to
pass all three gate tests). Enabling those segments to return 20475 Hz would
require either (i) loosening the gate (which worsens the false positive problem)
or (ii) a fundamentally different segment strategy. Neither is in scope here.

The whole-track result remains the definitive measurement. `stable = False` is
correctly interpreted by callers as "fewer than 60% of segments corroborated the
whole-track result" — a factually accurate statement.

---

## §7 — Finding 4 disposition: margin-based `stable` derivation (OQ4)

Requirements.md OQ4 asks whether deriving `stable` from the whole-track margin
(rather than segment agreement count) would better reflect the fixed-property
character of a band limit.

**This approach is incompatible with AC3 given the current reference set.**

The whole-track j* margin for Black Flute is **0.39 dB** (rightward margin,
used here because it is the binding constraint for Black Flute; rightward and
two-sided minimum coincide when leftward > rightward). Derivation:
gate2-trace-v1.5a.md §Black Flute whole-track section, line 29:
`margin at j* = L - suffix_max[j*] = -82.2133 - (-82.6015) = 0.39 dB`.
Confirmed in the gate2-trace summary table: `0.39 (min 0.08)` where 0.08 dB
is the minimum per-segment margin (segment 2, same file). Both figures are
measurement values read from the trace, not asserted.

Any margin threshold high enough to be meaningful — to distinguish "clearly
stable" from "marginal" — must exceed 0.39 dB. But such a threshold would flip
Black Flute from `stable = True` to `stable = False`, violating AC3.

Any threshold at or below 0.39 dB falls within Welch estimator noise at these
signal levels. A 0.08 dB minimum segment margin on Black Flute (gate2-trace
line 47–53) confirms that the per-band standard deviation is comparable to
this margin magnitude; a threshold this small would be vacuous, firing on every
detected cliff regardless of measurement quality.

There is no threshold derivable from the current five-track reference set that
satisfies both:
- AC3: no `stable` flips on the four currently-stable tracks (including Black Flute at 0.39 dB margin), and
- Meaningful discrimination: the threshold selects something about the detection, not merely "a cliff was detected."

The impossibility is shown, not asserted. The constraint is Black Flute's
0.39 dB whole-track margin — a measured value with a named derivation.

**Finding 4 is therefore deferred as a future story,** pending a wider
reference set that includes tracks with genuinely marginal whole-track
detections. The margin-based `stable` approach cannot be designed correctly
until such tracks exist. The secondary benefit of the new
`hf_band_limit_whole_track_margin_db` field (§5.1) is that it makes
whole-track margins available for that future analysis without requiring a
new instrumented run.

The existing field semantics (`stable = confidence >= hf_cliff_confidence_stable_floor`)
are unchanged by this story.

---

## §8 — Open questions dispositions (all OQs from requirements.md)

**OQ1 — Abstention-rate ceiling:** Under option (c), no parameter changes, so
the abstention count cannot change. The effective ceiling is the current baseline:
4/25 = 16%. No ceiling derivation is required because nothing is being tuned.
If a future story selects option (a), OQ1 must be re-opened with a derivation
principled around the minimum-corroboration property.

**OQ2 — Which option:** Option (c). Decided in §2.

**OQ3 — `stable = False` residual:** Accepted. See §6.

**OQ4 — Finding 4 / margin-based `stable`:** Incompatible with AC3 given
current reference set. Deferred. See §7.

**OQ5 — `robustness_db` as false-positive discriminator:** Deferred. The
per-band `levels_db` arrays for Chemical Brothers segment 1 needed to determine
whether the false-positive j* margin is systematically shallower than a
true-wall j* margin are not in any trace artifact. The field comment at
`reference_types.py` line 62 already documents this limitation.

---

## §9 — Test targets (AC6)

### §9.1 — New fixture: segment-level gate false positive

**File to add:** New test function in `tests/test_ground_truth_hf_extension.py`
or a dedicated `tests/test_hf_extension_gate_false_positive.py`. The developer
may choose; existing file conventions from STORY-004 AC1 apply.

**Required duration:** The fixture must generate a signal of at least 250 seconds
so that the five-segment split used internally by `measure_hf_extension` produces
segments of approximately 50 seconds each — the same geometry as Chemical Brothers.
A shorter signal (e.g., 100 s) produces 20-second segments with `floor((20s × 44100 -
65536) / 32768) + 1 ≈ 25 Welch windows` per segment, versus the `≈73 windows`
on the actual Chemical Brothers geometry. The test must exercise a per-segment
PSD that is representative of the failure mode, not a noisier regime. Mark the
fixture with the slow-test marker established in STORY-002 defects.md
(DEF-106 precedent) — do not leave it in the default suite without timing it.

**Fixture signal design:**

Generate a stereo `float64` signal at 44100 Hz, ~250 seconds
(`≈ 11025000 samples per channel`), with the following spectral structure:

- **Whole-track shape:** A shaped-noise signal with a hard cliff at frequency
  `F_real` (choose `F_real ≈ 20000 Hz`). The whole-track PSD must trigger
  `_gate_scan` and return `whole_track_hz ≈ F_real`. Generate as bandlimited
  white noise filtered to drop sharply (≥ 40 dB) above `F_real` using
  `scipy.signal.firwin` with a sharp cutoff.

- **Segment 1 spectral override:** In the first `n_samples / 5` samples only,
  superimpose a second spectral component: white noise filtered to drop by ≥ 8 dB
  in the 12–15 kHz region with a pre-slope in the preceding octave below
  12 dB/oct. This produces a gate-qualifying slope at `F_false ≈ 12500–13500 Hz`
  within the first-segment Welch PSD. The real cliff at `F_real` must NOT pass
  `_gate_scan` in this segment — achievable by ensuring the energy above `F_real`
  in segment 1 is high enough (relative to `F_real`) that the cliff at `F_real`
  does not produce an 8 dB drop within the search window (inject noise above
  `F_real` in segment 1 only, then rely on the whole-track average to suppress
  it). The developer should verify with a diagnostic `log_band_levels_db` call
  that segment 1's PSD shows the intended shape before running the full fixture.

- The resulting `per_segment_hf_band_limit_hz` should contain at least one
  value near `F_false` (disagrees with whole-track by `> hf_stability_tolerance_hz`)
  and `whole_track_hz` should be near `F_real`.

**Assertions:**

```python
sr = 44100
# AC6(a): fixture produces the false-positive scenario
assert result.hf_band_limit_hz is not None, "whole-track cliff must be detected"
assert any(
    s is not None and abs(s - result.hf_band_limit_hz) > config.hf_stability_tolerance_hz
    for s in result.per_segment_hf_band_limit_hz
), "at least one per-segment false positive required"

# AC6(c): caveat field is populated and non-empty
assert result.per_segment_reliability_caveat is not None
assert len(result.per_segment_reliability_caveat) > 0

# AC6(c): caveat propagates through JSON serialization
import dataclasses, json
d = dataclasses.asdict(result)
assert d["per_segment_reliability_caveat"] is not None

# AC6(c): caveat appears in markdown report (closes R4 in risk register)
from suno_mastering.report.reference_render import render_markdown
md = render_markdown(build_reference_set_report(...))
assert result.per_segment_reliability_caveat in md, \
    "caveat must appear verbatim in markdown output"
```

Note: the numeric false positive value is specific to the synthesised stimulus.
Do not hardcode the expected Hz value; assert only that a false positive exists
and the caveat fires. The markdown assertion uses `in` containment, not `==`,
because the caveat string may be embedded in a larger sentence.

### §9.2 — Performance constraint

The ~250-second fixture at 44100 Hz (stereo `float64`) generates approximately
11M samples per channel. Signal generation using `scipy.signal` filtering is
fast (sub-second), but `measure_hf_extension` on 250 seconds involves 5 Welch
PSD computations on ~2.4M-sample windows. The developer must time the full
fixture and apply the slow-test marker (established in STORY-002 defects.md,
DEF-106 precedent) if it exceeds approximately 20 seconds, keeping the default
suite within the 60-second budget (`.claude/docs/HANDOFF.md` Part 3 Definition
of Done).

### §9.3 — Existing test coverage — no regressions

All existing tests in `tests/test_ground_truth_hf_extension.py` and
`tests/test_ref_ac10_verification_bars.py` must continue to pass. No existing
fixture is modified by this story; the only code changes are in:
- `hf_extension.py` (capturing whole-track margin; computing caveat; adding fields to result constructor)
- `reference_types.py` (two new optional fields)
- `reference_render.py` (rendering two new fields in markdown)
- `reference_builder.py` (SCHEMA_VERSION bump)

Gate functions are unchanged, so synthetic-signal gate behaviour is unaffected.

---

## §10 — AC5 compliance summary

| AC5 requirement | How satisfied |
|---|---|
| Machine-readable caveat in Python source | `per_segment_reliability_caveat` field on `HfExtensionResult` (docstring in `reference_types.py`); population logic in `hf_extension.py` |
| Machine-readable caveat in serialized JSON | Via `dataclasses.asdict` in `reference_render.py` line 25 — automatic propagation; no change to `render_json` |
| Markdown caveat | New rendering block in `_track_section` (§5.3); asserted by AC6 test |
| AC5(a): per-segment values may be false positives | Asserted in caveat string content |
| AC5(b): non-None outside tolerance ≠ alternative estimate; None is distinct | Asserted in caveat string content |
| AC5(c): stable=False + low confidence + strong margin = correct report | Asserted in caveat string content |
| CLAUDE.md §5 / DOMAIN.md §2 reconciliation | §3 of this document |

---

## §11 — Risk register

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | Gate 1 review interprets AC1 "zero false positives" as requiring gate-level elimination regardless of §Effect 1 and AC4 scoping | Low | §3.5 cites the two cross-references in requirements.md that establish scoping. If Gate 1 disagrees, option (a) can be selected in a STORY-005 revision, subject to providing the 25-segment pre-slope instrumented run that AC1 requires before any parameter change. |
| R2 | `per_segment_reliability_caveat` condition over-fires on tracks it should not | Medium | The condition is strict: whole-track result must be non-None AND a per-segment value must be non-None AND must exceed `hf_stability_tolerance_hz`. Tracks with all-None or all-agreeing per-segment values are immune. Gate 1 should verify against all 5 reference tracks after implementation. |
| R3 | Developer refactors `whole_track_result` variable in `hf_extension.py` line 322, losing the margin | Low | The variable is already named `whole_track_result`; capturing margin is additive. The reference-set ground-truth test will catch any regression on the 5 tracks. |
| R4 | Markdown rendering of the two new fields is silently omitted | Low | Closed by §9.1 assertion: the AC6 test asserts `per_segment_reliability_caveat in md`. A missing rendering block causes the test to fail. |
| R5 | Future story attempts option (a) without re-reading the §2.1 AC1+AC3 joint-satisfiability analysis | Medium | Self-resolving if the future story re-reads this architecture.md. The §7 Black Flute 0.39 dB margin finding is the primary evidence; it should be reproduced with derivation in any successor architecture. |

---

## §12 — Files touched by this story

| File | Change | Scope |
|---|---|---|
| `stories/STORY-001/implementation/suno_mastering/analysis/reference_types.py` | Add 2 fields to `HfExtensionResult` | Additive; backward-compatible |
| `stories/STORY-001/implementation/suno_mastering/analysis/hf_extension.py` | Capture whole-track margin; compute caveat; pass new fields to result | Algorithm unchanged; output structure extended |
| `stories/STORY-001/implementation/suno_mastering/report/reference_render.py` | Add markdown rendering for 2 new fields | JSON path unchanged (automatic via asdict) |
| `stories/STORY-001/implementation/suno_mastering/report/reference_builder.py` | `SCHEMA_VERSION` "2.1" → "2.2" | One string constant |
| `tests/test_ground_truth_hf_extension.py` (or new file) | Add AC6 fixture for gate false positive | New test only |

Gate functions (`_gate_scan`, `_floor_onset_index`, `_detect_cliff`) in
`hf_extension.py` are **not touched**. The whole-track detection path is
**not touched**. No configuration constants change.

---

## §13 — Pipeline and data flow contract (for completeness per ARCHITECTURE.md)

This story does not change the stage contracts defined in `.claude/docs/ARCHITECTURE.md`.
`HfExtensionResult` remains in the ANALYSIS stage. The two new fields are
additive outputs of the existing `measure_hf_extension` entry point; no stage
boundary changes.

**Internal representation:** float64 throughout. The new `Optional[str]`
caveat field carries no numeric content. The `hf_band_limit_whole_track_margin_db`
field is `float` (Python `float` = float64), consistent with all other dB values
in `HfExtensionResult`.

**Data flow:** in-memory, unchanged. No new file I/O, no new temp files,
no new subprocess calls.

---

## §14 — Revision history

| Version | Date | Change |
|---|---|---|
| v1 | 2026-08-09 | Initial architecture for STORY-005. Option (c) chosen. Includes 25-segment audit, 2 new schema fields, AC5 compliance map, Finding 4 disposition (incompatible with AC3, shown via Black Flute 0.39 dB whole-track margin), OQ1–OQ5 dispositions, AC6 fixture design. |
| v1.1 | 2026-08-09 | Advisor review fixes: (1) §7 Black Flute 0.39 dB figure now cites gate2-trace-v1.5a.md line 29 with full derivation (was cited without source). (2) AC1 triple-hedge collapsed to §3.5 with single scoping statement; §12 A1 block and R1 High-severity removed — AC1 is scoped to options (a)/(b) by requirements.md AC4 and §Effect 1. (3) §9.1 fixture duration corrected to ~250 s (5 × 50 s segments matching Chemical Brothers geometry); 100 s was wrong (gives 20 s segments, 25 Welch windows vs required ~73). Slow-test marker now required, not conditional. (4) §5.1 caveat string note added: interpolates `config.hf_stability_tolerance_hz` to stay consistent with threshold actually applied. (5) R4 risk closed by AC6 markdown assertion added to §9.1. |
| v1.2 | 2026-08-09 | Gate 1 review (gate1-review.md) fixes: F1 — §5.1 Field 2 definition corrected: field exposes the two-sided minimum margin from `_detect_cliff` (not rightward-only); correct per-track values added (Chemical Brothers: 3.22 dB, not 25.79 dB); table and interpretation paragraph rewritten accordingly; `hf_band_limit_robustness_db` note updated to flag false-positive contamination when caveat is non-None. F2 — caveat string extended with None/abstention distinction sentence. F3 — §2.1 "no measurable improvement" claim corrected: option (a) is rejected on derivability + AC3 grounds, not on the claim it changes nothing. F7 — §7 now states explicitly that the Black Flute proof uses the rightward margin (the binding constraint there). |
