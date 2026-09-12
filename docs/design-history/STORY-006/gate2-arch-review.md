# Gate 2 Architecture Review — STORY-006
Reviewer: mastering-engineer
Date: 2026-08-11
Architecture version reviewed: v1.1

---

## Summary

**VERDICT: BLOCKED**

Two blockers must be resolved in `architecture.md` before implementation starts. Three advisories follow.

**Blockers:**
1. `sosfiltfilt` doubles the delivered dB gain; the architecture is internally inconsistent on its own gain convention and the ±2 dB cap becomes ±4 dB as written.
2. The correction cap is applied to the filter parameter, not to the measured band change; this causes AC14/AC16 three-way classification to mis-report corrections as "met" when the band remains out of range.

---

## Check 1 — Band corrections: which bands are corrected

- **sub (20–60 Hz): PASS.** Soft correction, ±2 dB cap. §5.2–5.4 are consistent.
- **low (60–120 Hz): PASS.** Informational for spectral EQ. Stereo width correction on low band (sub/low narrowing) is a separate and correct decision per gate1 §3 and AC7.
- **low_mid (120–500 Hz): PASS.** Soft correction with de-mud rule. §5.3–5.4 decision tree is logically correct (see Check 2 below for execution concerns that are downstream of the Blocker 1 finding).
- **high_mid, high, air: PASS.** Informational only. §19 explicitly excludes all three. No filter path exists.

---

## Check 2 — De-mud rule logic

Trigger condition, aim point, cap semantics, and decision tree are architecturally correct.

`de_mud_fires = (source_db > mid_db + de_mud_threshold)` reads from TargetsDocument — no literal in corrective_eq.py. `mid_db` is always 0.0 by definition of relative_db. PASS.

Aim point reads `targets.de_mud.correction_aim_point_db = 2.0`, not the subset median (3.394). §9 Category B derivation is sound: the 8.67 dB low_mid span disqualifies the median per DOMAIN.md §5; the two aim points are distinguishable only in the cap-free interval (+4.0, +5.394). PASS.

The decision tree in §5.4 correctly orders: check de_mud first, then out-of-range, then no correction. PASS.

Worked examples verify:
- Source +7.0: flag fires, aim = +2.0, required = −5.0, cap = −2.0, resulting = +5.0. Correct.
- Source +5.0 (within range [−0.145, +8.522] but > mid+4.0): flag fires, aim = +2.0, required = −3.0, cap = −2.0, resulting = +3.0. Correct.
- Source −2.0 (below range floor): range-compliance fires, aim = −0.145, required = +1.855, cap not reached, resulting = −0.145. Correct.

**Note:** these worked examples describe log intent (`resulting_db = source_db + applied_db` arithmetic). The actual Stage [9] measured outcome will differ for reasons stated in the blockers below. §5.3's "semantic clarification" that CorrectiveAction.resulting_db and Stage [9] will diverge is correct and deserves credit; the problem is that the architecture does not correctly derive how much they diverge or which convention governs the cap.

---

## Check 3 — Stereo width method

**PASS** overall, with Category C constants addressed under Advisory 3.

Sub/low narrowing via per-band M/S gain: §6.3 derives the gain formula explicitly under M⊥S and real cross-spectrum assumptions, confirms both the AC20 example (0.60 → 0.45) and the Q1 example (0.80 → 0.65). The derivation is correct.

**Critical implementation note in §6.3 is correct and important:** the cap is applied in width units (`w_target = max(aim, w_src − max_step)`), then `g` is solved for `w_target`. The architecture explicitly warns against clamping `g` directly. This is the right discipline — notably, it is the same discipline that is *absent* from the spectral EQ path (Blocker 2 below).

Floor 0.10: correctly established as a post-condition assertion only, unreachable by construction since `w_target = max(0.15, w_src − 0.15) ≥ 0.15 > 0.10` always holds. PASS.

High-band width: informational only. No width correction path above low band. §19 confirms. PASS.

---

## Check 4 — Filter choices

Sub low shelf at 60 Hz (upper band edge): appropriate filter type and placement for concentrating gain within 20–60 Hz. Bleed into the low band (≈+1 dB at 120 Hz for a +2 dB shelf) is documented in §5.2. The filter choice is defensible; however, the gain convention conflict from Blocker 1 applies here.

Low_mid peaking bell at 244.9 Hz (geometric mean of 120×500), 2.06 octave BW: covers 120–500 Hz. The `2.06` constant is geometrically derived (`log2(500/120)`) and may appear as a literal — correctly noted in §14 AC13 supplementary check. Bleed into the mid reference band at 500 Hz is documented in §5.3.

No filter touches high_mid, high, or air. PASS.

---

## Check 5 — Chain order

Stage [4] Corrective EQ → [5a] Per-band Stereo Width → [5b] Broadband Stereo → [6] Loudness/Dynamics → [7] Dither.

Matches DOMAIN.md §5 normative order: corrective EQ → dynamics/glue → loudness and limiting → dither. The note that stage [6] integrates dynamics/glue is correct for this pipeline. PASS.

---

## Check 6 — Constants derivation

**Category A (reference-derived): PASS.** All spectral band ranges and stereo width ranges in §9 are traceable to per-track values from `reference_set_report.json` with source citations.

**Category B (policy-fixed): PASS.** LUFS (−13.5) and dBTP (−1.0) sourced from CLAUDE.md §4.2. De-mud threshold (+4.0) and aim point (+2.0) derivations in §9 Category B are correct and sufficient. The threshold derivation note (v1.1 fix) is accurate: +4.0 is a policy choice in the open interval (3.394, 8.522) that intentionally fires on Black Flute-like material per requirements.md §3.7 rule 6.

**Category C (unverified): ADVISORY.** See Advisory 3.

---

## Check 7 — Known-wrong patterns

§18 maps all six CLAUDE.md §5 patterns to their resolution. All addressed. PASS.

---

## Check 8 — Excluded features

§19 explicitly excludes: high_mid EQ, high/air EQ, stereo widening, LRA targeting, iterative correction, targets.json runtime regeneration, presence correction. Requirements.md §8 and §6 cover per-element processing and five-track aggregate exclusion. PASS.

---

## Check 9 — Error handling

- Missing `targets.json` at mastering startup: PASS. `TargetsLoadError` raised before stage [1]; non-zero exit; path in message. §16 and §7.3.
- `targets.json` schema validation failure: PASS. Same path.
- Contributing track absent from reference JSON: PASS. §4.2 contributor count assertion; §16 `ValueError` naming the missing track.
- **Missing `reference_set_report.json` when generator runs: ADVISORY.** See Advisory 2.

---

## BLOCKER 1 — `sosfiltfilt` doubles delivered dB; gain convention undefined

**Severity: Blocker**

`sosfiltfilt` applies the filter forward and then backward. The result is `|H(f)|²` — twice the dB response of the design parameter. A `gain_db = −2.0` dB shelf design delivers −4.0 dB. The normative ±2 dB correction cap (CLAUDE.md §4.2, gate1 §3) therefore becomes ±4 dB at the output.

The architecture is internally inconsistent on this. §5.3 calculates the low_mid bell bleed using the single-pass RBJ half-gain-at-bandwidth-edge relationship ("for a −2.0 dB correction: −1.0 dB at 500 Hz"). If `sosfiltfilt` is used, the correct figure is −2.0 dB at 500 Hz. Both calculations cannot be right in the same document. §5.4 specifies `sosfiltfilt`; §5.3 does not account for it. The developer implementing from this document cannot resolve the contradiction.

The CorrectiveAction log's `applied_db` field will report the design parameter, not the delivered gain, with no correction for the doubling. Every downstream report and AC assertion built on `applied_db` is quantitatively wrong.

**What must change:**

The architecture must choose one of two resolutions and apply it consistently throughout:

*Option A — retain `sosfiltfilt`, halve the design parameter.* Specify that `gain_db` passed to `_low_shelf_sos` and `_peaking_sos` is `applied_db / 2`, so the delivered gain equals `applied_db`. Update §5.2, §5.3, and §5.4 to state this convention explicitly. The bleed calculations in §5.3 remain as written (single-pass math is the intent). `SpectralCorrectiveAction.applied_db` logs the delivered gain.

*Option B — use `sosfilt` (single pass).* State this explicitly in §5.4 filter application. The bleed calculations in §5.3 are then exactly correct. Acknowledge the phase shift consequence and state why it is acceptable for offline batch processing on programme material.

Either option resolves the inconsistency. The choice is a mastering judgment: zero-phase (sosfiltfilt) avoids pre-ringing artifacts on percussive transients; single-pass (sosfilt) has phase shift but correct gain on first use. For broad-band corrections at ≤2 dB, single-pass is defensible. My preference is Option A (retain sosfiltfilt, halve the design parameter) — zero-phase is safer on electronic material with pronounced kick transients.

---

## BLOCKER 2 — Cap applied to filter parameter, not to measured band change

**Severity: Blocker**

The cap is implemented as `applied_db = clamp(required_change, -cap, +cap)` where `applied_db` is then passed to the filter as its gain parameter. This means the cap governs the filter gain, not the resulting change in the measured band level. The two are not equal.

The sub low shelf at 60 Hz delivers less than `gain_db` across the 20–60 Hz sub band. Energy-weighted (music energy in sub concentrates toward 40–60 Hz rather than 20–25 Hz), the effective band gain is approximately 0.55–0.65 × the design parameter — a shortfall of 0.7–0.9 dB on a 2 dB shelf. For a source 1.5 dB below `range_min`, the nominal design applies `applied_db = +1.5`, but the actual sub band level moves by roughly +0.9–1.0 dB, leaving the source still outside range by 0.5–0.6 dB.

The low_mid peaking bell also under-delivers within its own band. At the bandwidth edges (120 Hz and 500 Hz), the gain is half the design parameter in dB. The energy-weighted average across 120–500 Hz is approximately 0.7–0.8 × the design parameter. For AC19 Assertion 2 (source at +4.5 dB, stated separation of 0.89 dB between aim points), the actual measured separation after the bell is applied is approximately 0.89 × 0.75 ≈ 0.67 dB. Against the stated ±0.25 dB test tolerance, the two aim points still separate by 0.42 dB — the assertion technically holds — but the §5.3 error analysis understates the discrepancy by accounting only for mid-band bleed, not for within-band under-delivery.

The AC14/AC16 classification consequence is the clearest problem. The report classifies each band as "met", "outside range but cap reached", or "informational" (AC16). The classification uses `resulting_db = source_db + applied_db` (§5.4 and §3.7). When a source is 1.5 dB below `range_min` and `applied_db = +1.5`, `resulting_db` equals `range_min`, classifying the band as "met." The Stage [9] measurement reads the actual outcome: still outside range. A report built on arithmetic `resulting_db` classifies bands as "met" when they are not. This is an AC16 correctness failure.

The architecture already got this right for the width corrector: §6.3's critical implementation note specifies that the cap is applied in width units, then `g` is solved for the capped target. That discipline — cap the outcome, then solve for the parameter — must be applied to the spectral EQ path.

**What must change:**

Define whether `SpectralCorrectiveAction.resulting_db` and AC16 classification are based on arithmetic (intent) or measured outcome (Stage [9]). The architecture currently assigns `resulting_db = source_db + applied_db` (arithmetic) and calls this the "log intent." That is a legitimate choice IF the classification in AC16 is based on the Stage [9] measurement rather than `resulting_db`. If classification uses arithmetic, a source that is over-corrected (under-delivered toward the range but still outside it) will be misclassified.

Recommended resolution: AC16 three-way classification uses the Stage [9] post-correction band measurement, not `resulting_db`. `resulting_db` in the CorrectiveAction log is labelled "nominal intended outcome" and not used for pass/fail classification. Add this distinction explicitly to §3.7 (normative correction cap semantics) and §7.1 (`SpectralCorrectiveAction` docstring).

Additionally: state in §5.2 and §5.3 the expected delivered gain per unit design parameter for each filter (sub shelf: ~0.6 × design parameter energy-weighted; low_mid bell: ~0.75 × design parameter energy-weighted), so that a developer calibrating test tolerances has the right numbers.

---

## Advisory 1 — `sosfiltfilt` and sub band: magnitude note for test tolerances

Once Blocker 1 is resolved, the sub band shelf will still deliver a range of gains across 20–60 Hz (more correction at 20 Hz, less at 60 Hz by construction of any shelf filter). After halving the design parameter to account for `sosfiltfilt`, the actual band-average delivery will be approximately 0.55–0.65 × the delivered gain. This is expected shelf behaviour. Tests asserting on Stage [9] sub band measurements (not on `resulting_db`) should include a tolerance of ±0.5 dB for this reason.

---

## Advisory 2 — Missing `reference_set_report.json` not covered in §16

§16's error table covers mastering chain runtime failures and generator track-matching failures. It does not specify the generator's response when `reference_set_report.json` is absent or unreadable at the path passed on the command line. Per the "fail loudly" principle (requirements.md §1, AC22), the generator must exit non-zero with an explicit message naming the missing file path. Add this case to §16.

---

## Advisory 3 — Category C constants (width floor 0.10, step 0.15)

The architect correctly flags these in §9 Category C and requests mastering engineer review.

**Floor 0.10:** This is unreachable by construction — `w_target = max(0.15, w_src − 0.15) ≥ 0.15 > 0.10` always holds. It functions solely as a post-condition assertion against programmer error. No derivation from reference data is needed because it has no effect on any computed output. Acceptable as-is.

**Step 0.15:** No reference basis. For Suno material at extreme sub/low widths (hypothetically 0.95), a single pass corrects to 0.80 — modest. For widths just above the threshold (say, 0.20), the step is not limiting and the source reaches the aim point in one pass. For the typical Suno case, where sub widths are likely to be moderate (the reference set shows all three contributing tracks at sub widths of 0.001–0.04, so extreme Suno sub widths would be unusual), the step limit will rarely bind. Acceptable for implementation. Verify on actual Suno exports after STORY-006 is complete and revisit in STORY-007 if cross-track consistency is inconsistent near the threshold.

---

## Blocker verification — v1.2

Reviewer: mastering-engineer
Date: 2026-08-11
Architecture version verified: v1.2

### BLOCKER 1 — sosfiltfilt gain doubling: RESOLVED

Option A was adopted. Every required location now states the convention unambiguously:

- §5.2: "the value passed to `_low_shelf_sos` is `applied_db / 2`" and "`SpectralCorrectiveAction.applied_db` logs the delivered gain (not the design parameter)."
- §5.3: "The value passed to `_peaking_sos` is `applied_db / 2`." The bleed figures (−1.0 dB at 500 Hz for a −2.0 dB correction) are confirmed correct as delivered-gain arithmetic and unchanged from v1.1.
- §5.4 sub call: `_low_shelf_sos(sr, f0=60.0, gain_db=applied_db / 2)` with inline explanation present.
- §5.4 low_mid call: `_peaking_sos(sr, f0=244.9, gain_db=applied_db / 2, bandwidth_octaves=2.06)` with inline explanation present.
- §7.1 `applied_db` docstring: "signed dB of DELIVERED gain at center frequency — equals sosfiltfilt output (= 2 × filter design parameter passed to `_low_shelf_sos` / `_peaking_sos`). This is NOT the raw design parameter."
- §11 library note updated to reference the halved-parameter convention.

Convention is stated once in each of §5.2, §5.3, §5.4 (both filter calls), §7.1, and §11. Internally consistent throughout.

### BLOCKER 2 — Cap on parameter vs cap on outcome: RESOLVED

All five required changes are present:

- §5.2 energy-weighted delivery paragraph: "approximately **0.60 × applied_db** as an energy-weighted band average across 20–60 Hz… test tolerances for Stage [9] sub band level assertions should be ±0.5 dB."
- §5.3 energy-weighted delivery paragraph: "approximately **0.75 × applied_db** as an energy-weighted band average across 120–500 Hz."
- §5.4 AC16 classification rule paragraph: "uses the Stage [9] post-correction measurement, not `resulting_db`" with explicit explanation of why arithmetic `resulting_db` can misclassify.
- §5.4 pseudocode: `resulting_db = source_db + applied_db   # arithmetic nominal intent; NOT used for AC16 classification`.
- §7.1 `resulting_db` docstring: "NOMINAL INTENDED OUTCOME for logging only… NOT used for AC16 pass/fail classification. Stage [9] post-correction measurement governs classification."
- §17.1 AC14/AC16 test note: Stage [9] governs; ±0.5 dB tolerance (sub), ±0.6 dB tolerance (low_mid). AC19 Assertion 2 updated to Stage [9] with ±0.6 dB tolerance.
- §16 error table: row for `reference_set_report.json` absent or unreadable now present (Advisory 2 also resolved).

### Overall verdict: PASS

Both blockers are resolved. Architecture v1.2 is clear for implementation.
