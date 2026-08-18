# Gate 1 Review — STORY-005 Architecture v1.1
# DEF-205: Per-Segment Gate False Positive (Chemical Brothers)

Reviewer: mastering-engineer
Date: 2026-08-09
Architecture version: v1.1

**Verdict: PASS-WITH-FINDINGS**

One Blocker must be resolved before implementation begins. Three Concerns and three Notes
are recorded below.

---

## Preliminary: audit table verification

The §4 25-segment before/after audit table is correct. Checked independently against
gate2-trace-v1.5a.md:

| Track | WT | Seg 1 | Seg 2 | Seg 3 | Seg 4 | Seg 5 | stable | conf |
|---|---|---|---|---|---|---|---|---|
| Black Flute | 15788 | 15788 C | 15788 C | 15788 C | 15788 C | 15788 C | True | 1.0 |
| GusGus | 16251 | 16251 C | 16251 C | 16251 C | 16251 C | 16251 C | True | 1.0 |
| Leftfield | 20475 | 20475 C | 20475 C | 20475 C | 20475 C | 20475 C | True | 1.0 |
| Chemical Bros | 20475 | 14066 FP | None A | 20475 C | 20475 C | None A | False | 0.4 |
| Wavy Gravy | 20475 | 20475 C | None A | None A | 20475 C | 20475 C | True | 0.6 |

Every value in the architecture's §4 table matches the trace. 20 CORRECT, 4 ABSTAIN,
1 FALSE-POSITIVE. This is correct.

---

## Domain answers to the five questions

### Q1 — Is `stable=False, confidence=0.4` the honest correct output for Chemical Brothers?

Yes. The confidence formula counts corroborating segments: 2 of 5 agreed (segments 3 and 4
at 20475 Hz). Segment 1 returned 14066 Hz (outside tolerance, DISAGREE), segments 2 and 5
returned None (not counted as agreement). 2/5 = 0.4, below the 0.6 floor, so `stable=False`.
These are correct arithmetic outputs of the defined formula.

The architecture is not papering over a method problem. The method problem — that the per-segment
gate fires on programme content — is real and acknowledged. The whole-track result (20475 Hz,
strong margin) is unaffected. `stable=False` correctly describes the corroboration count, not
the band limit itself.

### Q2 — Does the §3 DOMAIN.md §2 / CLAUDE.md §5 reconciliation hold?

Yes, with a qualification. DOMAIN.md §2 warns that "a detector reporting it as unstable is
measuring programme content." The architecture correctly distinguishes between:

- The primary measurement (`hf_band_limit_hz = 20475 Hz`) — fixed, correct, not reported as varying
- The corroboration count (`stable = False`) — a statement about how many 50-second windows
  contained sufficient spectral evidence, not about whether the band limit moves

`stable=False` is not a claim that 20475 Hz is uncertain. It is a claim that the per-segment
corroboration mechanism's window-level sensitivity is insufficient on this material. DOMAIN.md §2
applies to the measurement of the fixed property; the whole-track measurement is correct and
unvarying.

Segment 1's false positive (14066 Hz) IS measuring programme content — exactly the failure mode
DOMAIN.md §2 names. The reconciliation honestly acknowledges this as a method limitation, not a
design intent. This is the correct posture.

The qualification: `stable=False` with `confidence=0.4` on a 25+ dB whole-track margin is
semantically misleading to any consumer who reads those two fields without reading `stable`'s
docstring or the new caveat fields. The new fields mitigate this. See Concern 2 below.

### Q3 — Is retaining 14066 Hz as a documented artefact acceptable?

Conditionally yes — with one finding that the caveat string as written is insufficient to cover
it fully (see Blocker F1 and Concern 1 below).

The value 14066 Hz sits squarely within the Suno/generative export range (13–16 kHz per
DOMAIN.md §2). It is also above the 10 kHz commercial-master "obviously broken" floor. A
downstream plausibility filter — exactly the kind of filter that would protect a mastering
workflow — will **pass** this value without objection. That makes `per_segment_reliability_caveat`
the sole barrier between 14066 Hz and a mastering decision. Checking that field must be treated
as mandatory for any consumer of `per_segment_hf_band_limit_hz`, not advisory. The implementation
team should say so in the docstring.

The retained false positive is acceptable under option (c) on the grounds that:
(a) `hf_band_limit_hz` (the primary output) is unaffected;
(b) the caveat field makes machine-readable detection explicit;
(c) requirements.md §Effect 1 explicitly blesses this outcome for option (c).

### Q4 — Is the §4 audit table consistent with the gate2-trace data?

Confirmed. Every value, classification, `stable`, and `confidence` entry in §4 matches the
gate2-trace. The table is accurate.

### Q5 — Is the AC6 fixture design physically plausible?

Plausible, but the level-calibration problem is real and the architecture gives the developer
insufficient guidance to hit it on the first attempt. See Concern 3 below for specifics.
The underlying mechanism (superimposed LPF noise in segment 1 to create a false gate candidate;
noise injection above F_real to suppress the real cliff in that segment) is physically correct
for the Chemical Brothers failure mode. The duration requirement (250 s → 5 × 50-s segments,
~73 Welch windows per segment) is the right engineering decision and should not be relaxed.

---

## Findings

---

### F1 — BLOCKER: `hf_band_limit_whole_track_margin_db` field specification is wrong

**What is proposed:** §5.1 defines the field as "the rightward j* margin on the whole-track PSD:
`margin_db = L − suffix_max[j*]`" and cites 25.79 dB as the Chemical Brothers value. The
implementation step (§5.2 Step 1) unpacks `whole_track_result[1]` from `_detect_cliff`.

**Why it fails:** `_floor_onset_index` (hf_extension.py line 208) returns
`min(rightward_margin, leftward_margin)` — the two-sided minimum — not the rightward
component alone. `whole_track_result[1]` is already the two-sided minimum. The field as
implemented will not contain 25.79 dB for Chemical Brothers; it will contain 3.22 dB.

Derivation for all five tracks from the trace:

| Track | rightward (`L − suffix_max[j*]`) | leftward (`levels_db[j*−1] − L`) | field value = min() |
|---|---|---|---|
| Black Flute | 0.39 dB | 1.41 dB | **0.39 dB** |
| GusGus | 7.35 dB | 3.62 dB | **3.62 dB** |
| Leftfield | 22.99 dB | 8.00 dB | **8.00 dB** |
| Chemical Brothers | 25.79 dB | 3.22 dB | **3.22 dB** |
| Wavy Gravy | 19.48 dB | 8.00 dB | **8.00 dB** |

Leftward derivations:
- Black Flute: j*=81, j*−1=80. suffix_max[80]=−80.8081 → levels_db[80]=−80.8081 (it is the max in that suffix). leftward = −80.8081 − (−82.2133) = 1.41 dB.
- GusGus: j*=82, j*−1=81. suffix_max[81]=−86.1349 → levels_db[81]=−86.1349. leftward = −86.1349 − (−89.7510) = 3.62 dB.
- Leftfield: j*=90, j*−1=89 = freeze_index. passband_level = levels_db[89] = −94.6703. L = −102.6703. leftward = −94.6703 − (−102.6703) = 8.00 dB exactly. This is a structural property: when j* = freeze_index + 1, leftward margin = hf_cliff_required_drop_db = 8.00 dB.
- Chemical Brothers: j*=90, j*−1=89. levels_db[89] = suffix_max[89] = −83.3231. leftward = −83.3231 − (−86.5431) = 3.22 dB.
- Wavy Gravy: j*=90, j*−1=89 = freeze_index. leftward = 8.00 dB (same structural case as Leftfield).

**Why this matters:** The rightward margin spans 0.39 to 25.79 dB across tracks — a 25 dB range
that clearly distinguishes Black Flute (marginal) from Chemical Brothers (definitive). The
two-sided minimum spans 0.39 to 8.00 dB, with GusGus and Chemical Brothers both at 3.2–3.6 dB
despite their rightward margins differing by 18 dB. A caller reading `hf_band_limit_whole_track_margin_db`
of 3.22 dB alongside Black Flute's 0.39 dB will conclude both detections are marginal. The
interpretation paragraph in §5.1 ("A margin of 25.79 dB on Chemical Brothers means the floor
onset at 20475 Hz is unambiguous...") is flatly incorrect for the value the field will actually
contain. The §7 Black Flute proof (0.39 dB margin → margin-based stable incompatible with AC3)
is accidentally correct because the rightward and two-sided margins agree for Black Flute, but
this should be stated explicitly rather than relied on by coincidence.

**What to do instead:** Two acceptable fixes, either of which resolves the blocker:

*Option A (preferred):* Change the field specification to rightward margin only. Modify
`_floor_onset_index` to return both components, or alternatively recompute rightward margin in
`measure_hf_extension` directly as `L − suffix_max[j*]` (both values are already available at
that point). Document the field as `L − suffix_max[j*]` and update all cited values to the
rightward figures shown above.

*Option B:* Keep the two-sided minimum (what the current code already produces) and rewrite
the §5.1 interpretation paragraph entirely. Drop the 25.79 dB citation; instead state that
the two-sided minimum is dominated by the passband-proximity component (`levels_db[j*−1] − L`)
rather than the cliff depth, and revise the claim about what it demonstrates. The §7 Black
Flute proof still holds numerically but should cite the two-sided minimum explicitly.

Note for any future story using margin-based `stable` derivation: the two definitions diverge
by up to 22 dB on Chemical Brothers and must not be used interchangeably. Any such story must
state which margin it uses and show the derivation for that definition.

---

### F2 — CONCERN: Caveat string does not satisfy AC5(b)

**What is proposed:** The suggested caveat string in §5.1 says: "Per-segment values on complex
material must not be used as alternative band-limit estimates."

**Why it is insufficient:** AC5(b) specifically requires the caveat to assert that "`None` is
an honest abstention — a distinct state" from a false positive. The suggested string does not
contain this distinction. A consumer reading the caveat knows that the per-segment non-None value
is wrong, but does not know that `None` on segments 2 and 5 is a different, safe state.

**What to do:** Add a clause to the suggested string, e.g.: "None is an honest abstention
(insufficient spectral evidence in that window) and is distinct from a false positive (a wrong
non-None value); None should not be treated as indicating the same problem."

This is a one-sentence addition. The implementation team will copy the suggested string verbatim
or substantively — omitting this clause violates AC5(b) as written.

---

### F3 — CONCERN: Option (a) rejection argument is partially wrong

**What the architecture argues:** §2.1 states that option (a) "achieves no measurable improvement"
because confidence stays 0.4 and stable stays False whether segment 1 returns 14066 Hz or None.

**Why the "no improvement" claim is wrong:** Replacing 14066 Hz with `None` IS a real correctness
improvement. 14066 Hz is a wrong non-None value in a field consumers read; `None` is an honest
abstention that the confidence formula treats correctly and that consumers can distinguish from
a band-limit estimate. That is not zero improvement — it is the difference between a wrong number
and an honest signal. The characterisation "no measurable improvement" will mislead a future story
holding the pre-slope instrumented run into thinking option (a) was rejected on merit.

**What is correct:** Option (a) should be rejected on derivability grounds alone: the 25
per-segment pre-slope values at each candidate needed to derive a principled threshold do not
exist in any artifact, CLAUDE.md §5 prohibits guessing a threshold, and any guessed value that
silences the Chemical Brothers false positive must be verified against all 25 segments before
it can be proposed. The §2.1 AC3/Wavy Gravy joint-satisfiability argument is correct and
independently sufficient. The "no measurable improvement" argument should be removed or corrected
to avoid polluting future story decisions.

---

### F4 — CONCERN: AC6 fixture level calibration needs concrete guidance

**What is proposed:** §9.1 superimposes LPF noise at ~13 kHz on segment 1, and injects noise
above F_real=20 kHz in segment 1 only, to prevent the real cliff from qualifying _gate_scan in
that segment while leaving it visible to the whole-track detector.

**The calibration problem:** The noise injected above F_real in segment 1 bleeds into the
whole-track Welch PSD (which processes all 5 × 50-s of data as one array). If the injected
noise above F_real is at power P in segment 1, it contributes P × (1/5) to the whole-track
PSD above F_real. The injected noise must be:
- HIGH enough that levels_db within the window above F_real in segment 1 rises enough to
  prevent an 8 dB drop at F_real (i.e., ≥ passband_level − 8 + ε within the window above F_real)
- LOW enough that its (1/5)-weighted contribution to the whole-track PSD above F_real still
  leaves a cliff of ≥ 8 dB at F_real visible to the whole-track detector

If the base signal's stopband above F_real is at −N dBFS (where N is large, e.g. 60+ dB below
the passband), a noise injection at just above passband − 8 dBFS in segment 1 will average to
passband − 8 − 7 dBFS in the whole-track (the −7 dB being 10 log10(1/5)). That still gives
a ≥ 8 dB apparent cliff in the whole-track. This window of calibration values is workable but
requires iteration. The "verify with diagnostic log_band_levels_db call" instruction is
necessary — but it is not sufficient. The developer needs concrete targets to avoid multiple
failed fixture runs in a 60-second test-suite budget.

**Additional fixture concerns:**

(a) **Use mono, not stereo.** `measure_hf_extension` calls `_to_mono(audio)` on line 301 as
its first action, averaging channels before any analysis. A stereo float64 250-second file at
44100 Hz is approximately 352 MB; the mono equivalent is 176 MB. Generating stereo provides no
test coverage benefit and doubles the allocation cost. The fixture should generate mono and pass
it as `audio.reshape(-1, 1)` or directly as 1-D.

(b) **Use constant-level broadband content throughout all segments, not just the injected
components.** `extract_active_audio` (hf_extension.py line 310) gates out silence before the
5-segment split on line 334. Any low-level passage in the fixture (transitions between the
LPF-noise segment and the flat segments) risks having the gated active array split at a point
other than the intended 1/5 boundary. If segment 1's injected LPF component shifts into what
should be segment 2, the fixture does not test what it claims to. Keep all spectral energy
above the silence gate threshold throughout all 250 seconds.

(c) **Suggest quantitative targets for the developer.** At minimum: specify that the base
signal stopband above F_real should be −50 dB or more below the passband; specify that the
injected noise above F_real in segment 1 should be approximately `passband_level − 6 dBFS`
(enough to reduce the within-window drop to ~2 dB); and show the developer how to verify both
segment 1 and whole-track PSDs with log_band_levels_db before running the full AC6 assertions.

---

### F5 — NOTE: AC1 "zero false positives" literal language vs option (c) scoping

Requirements.md AC1 literally states "the after state must show zero false positives" without
option-scoping. The architecture's §3.5 scoping argument relies on requirements.md §Effect 1
("Left in place by option (c) — documented as a known limitation") and AC4 being labelled
"(options a and b)" as implicit carve-outs. The BA's intent is clear from §Effect 1, and this
reading is defensible. However, QA should be advised explicitly: Chemical Brothers segment 1
retaining 14066 Hz in the after state is expected and documented under option (c), not a
defect. The expected caveat firing pattern is: **exactly 1 of 5 reference tracks** fires the
caveat (Chemical Brothers). Black Flute, GusGus, and Leftfield have all-agreeing per-segment
values; Wavy Gravy's non-None values are all exactly 20475.06 Hz (|diff| = 0 < 2000 Hz
tolerance). Any other caveat firing pattern from the implementation is a defect.

---

### F6 — NOTE: `hf_band_limit_robustness_db` contaminated by false-positive margin (pre-existing)

The existing code at hf_extension.py lines 358–361 computes `hf_band_limit_robustness_db` as
`min(segment_margins)` where `segment_margins` includes the j* margin from every non-None
per-segment result. For Chemical Brothers, this includes segment 1's j* margin at 14066 Hz —
a false-positive margin — alongside segments 3 and 4's true-wall margins at 20475 Hz.
The minimum may be dominated by the false-positive measurement, making `hf_band_limit_robustness_db`
report a value that does not characterise the true-wall detection robustness. This is a
pre-existing issue, not introduced by STORY-005, and is correctly deferred under OQ5. No action
required in this story. However, the field's comment at `reference_types.py` line 62 should
note that when `per_segment_reliability_caveat` is non-None, this field may incorporate a
false-positive segment's margin in the minimum.

---

### F7 — NOTE: §7 proof survives by coincidence; should be stated explicitly

The §7 Black Flute impossibility proof (margin-based stable incompatible with AC3) uses
Black Flute's 0.39 dB margin to show no meaningful threshold is derivable. This proof is valid
as long as "0.39 dB margin" refers to the margin the threshold would be compared against. For
Black Flute, the rightward margin and two-sided minimum are both 0.39 dB (the rightward component
is the binding constraint). This is coincidence, not structure. The proof should note which
margin definition it uses (rightward, citing gate2-trace line 29) so a future story cannot
invalidate it by switching definitions.

---

## Summary for implementation team

| # | Severity | Action required |
|---|---|---|
| F1 | **Blocker** | Fix `hf_band_limit_whole_track_margin_db` field specification: either expose rightward margin (preferred) or rewrite §5.1 interpretation paragraph for two-sided minimum. Resolve before any code is written. |
| F2 | Concern | Add None-vs-false-positive distinction to the caveat string (one sentence). |
| F3 | Concern | Remove or correct the "no measurable improvement" claim in §2.1; rejection of option (a) rests on derivability grounds only. |
| F4 | Concern | Provide concrete level targets for AC6 fixture; use mono not stereo; ensure constant broadband level throughout to keep silence gating from shifting the 1/5 segment boundary. |
| F5 | Note | Advise QA that caveat fires on exactly 1 of 5 tracks (Chemical Brothers); Chemical Brothers segment 1 retaining 14066 Hz is expected under option (c). |
| F6 | Note | Note false-positive margin contamination of `hf_band_limit_robustness_db` in its comment; no code change required. |
| F7 | Note | §7 proof should state explicitly that it uses the rightward margin (which equals the two-sided minimum for Black Flute by coincidence). |

The overall architecture decision (option c, additive fields, no gate changes) is sound.
The §3 reconciliation holds. The audit table is accurate. The AC6 fixture mechanism is
physically correct. F1 is the only item that changes what the developer writes.
