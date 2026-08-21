# STORY-027 Gate 1 Mastering-Engineer Review

**Date:** 2026-08-21
**Reviewer:** mastering-engineer
**Architecture version reviewed:** v1.1
**Status:** REVIEW COMPLETE — two Blockers must be resolved before item 4 implementation

---

## Blockers — must be resolved before implementation

---

### BLOCKER 1 — Dynamics leveler: the DR coupling makes the stage impotent on its own motivating track

**What is proposed (§7.4):** The runtime attenuation cap is `min(targets_cap, dr_budget × 0.5)` where `dr_budget = source_dr − dr_required`, and `source_dr_db` comes from stage [2] — measured **before the leveler runs**.

**Why it fails:** Running the formula against Sunday Club (the only real evidence available): `source_dr = 9.0`, `dr_floor = 8.0`, `dr_max_reduction_db = 3.0`:

```
dr_required = max(8.0, 9.0 − 3.0) = 8.0
dr_budget   = 9.0 − 8.0 = 1.0 dB
effective_max_attenuation = min(targets_cap, 1.0 × 0.5) = 0.5 dB
```

0.5 dB of attenuation authority against a 9.8 dB LUFS range. Whatever value is set for `leveling.max_attenuation_db` at Gate 1 is irrelevant — the runtime formula dominates and clamps it. The stage will report `applied=True, max_gain_db_applied: −0.5`. That is a silent no-op reported as a run, which requirements.md's non-functional requirements explicitly prohibit.

Generalising: leveler authority scales as `(source_dr − 8.0) / 2`. A track needs source DR ≥ 11.0 to get even 1.5 dB. The `targets.json` reference DR range is [6.599, 8.646] — the reference tracks themselves sit at or below `dr_floor: 8.0`. On reference-compliant material, `dr_budget ≤ 0` and the `no_dr_budget` fallback fires unconditionally. The stage as designed cannot act on the population it targets.

The root cause is that `source_dr_db` is measured at stage [2], before the leveler, but is used to constrain audio the leveler has already changed. This is measurement invalidation — the same class of error as measuring loudness before limiting. The downward-only leveling reduces TT DR (attenuating peaks more than RMS lowers crest factor), so the DR the solver actually sees post-leveler is lower than `source_dr`. The `dr_budget × 0.5` rail is compensating for the wrong baseline.

The architect must choose: re-measure DR after the leveler and pass the post-leveler value to the solver, removing the pre-emptive cap; or remove the DR-coupling constraint entirely and rely on the solver's existing hard constraint as the post-hoc guard. Either path requires re-examining whether `solve_loudness_and_limit` can accept a post-leveler DR without breaking STORY-006/025 contracts. The Gate 1 decision on `leveling.max_attenuation_db` is deferred until the design is revised.

---

### BLOCKER 2 — Sub correction cap: unsettable without the shelf's delivery efficiency across 20–60 Hz

**What is proposed (§3.2):** Gate 1 to set `sub.correction_cap_db` based on "audibility threshold for a 60 Hz low shelf," subject to the constraint that the value must be ≥ 4.886 dB to resolve Sunday Club.

**Why it fails:** The 4.886 dB figure is the **nominal applied gap**, not the delivered correction across the measurement band.

For low_mid, the architecture explicitly derives and uses a 0.75× delivery efficiency factor for the peaking bell. No equivalent factor is stated for the sub low shelf.

The shelf's delivery efficiency across 20–60 Hz depends on:
- The shelf corner frequency. If the corner is at 60 Hz (the band's upper edge), the shelf's transition band is almost entirely outside the measurement band (20–60 Hz), and delivery efficiency could be substantially below 1.0 — perhaps 0.7 or less.
- The shelf slope / filter order.

If delivery efficiency is 0.7, a 4.886 dB nominal cap delivers ~3.4 dB, sub lands at 6.83 − 3.4 = +3.43 dB re mid, which is still above range_max (+1.944 dB). AC1 requires the correction to reach the nearer range edge. A cap set to the nominal gap fails AC1 if delivery efficiency < 1.0.

The minimum safe cap is `4.886 / delivery_efficiency`. That denominator does not exist in the architecture. The implementation must state the shelf corner frequency and slope/order. Once those are known I can confirm whether the audibility ceiling (~6 dB for a single-pass 60 Hz shelf cut) leaves enough headroom above the computed floor.

Also: the shelf's transition band incidentally affects 60–120 Hz (the `low` informational band). At 5–6 dB nominal, this could be 1–3 dB at 80–100 Hz. Not blocking, but the implementation must characterise and document it.

---

## Concerns — should be addressed before QA

---

### CONCERN 1 — de_mud marginal case inversion is new under the raised cap and not tested

Architecture §3.3 shows the worst-case and Sunday Club outcomes. The minimal trigger (src = 4.1 dB, just above the 4.0 threshold) produces: applied = −2.1 dB, delivered ≈ −1.58 dB, post ≈ +2.53 dB re mid. This is the lowest landing point across any de_mud trigger — paradoxically, the mildest cases land furthest below the reference median (+3.394). Under cap=2.0, every firing produced ~−1.5 dB regardless of source and the inversion was masked. Under cap=6.522 it is fully visible. +2.53 dB is inside the reference range and 2.7 dB above the floor, so this is not a blocker. But QA will not find it without an explicit near-threshold test case. The test brief must include src ≈ 4.1 dB.

### CONCERN 2 — Chunked `integrated_loudness` applies BS.1770 relative gating within the window, producing measurement bias at section boundaries

`pyloudnorm.Meter(sr).integrated_loudness(window_audio)` on a 3-second chunk applies BS.1770's relative gate within that chunk. A chunk straddling a breakdown→drop transition gates out the quiet half and returns a LUFS value that reflects primarily the loud half. That biased value then drives a uniform gain applied to the entire chunk, including the quiet pre-transition zone. The quiet zone is over-attenuated.

The correct tool for window-based leveling is BS.1770 short-term loudness (3-second sliding window, 100 ms hop, no intra-window relative gate) or K-weighted ungated mean-square. Same window length, same sensitivity, no gating distortion, and the overlapping hop eliminates the 3-second step quantisation that the IIR smoothing is currently trying to fix downstream.

### CONCERN 3 — `presence_harsh` reference (−4.0 dB round number) and seven-band `high_mid` median (−6.714 dB derived) cover the same frequency range and disagree by 2.7 dB

Both cover 2000–5000 Hz. The −4.0 is a round number, which CLAUDE.md §7 names as a known-wrong pattern ("placeholder values survive in production"). Against −4.0, Sunday Club pre-correction deviation is −0.16 dB (not flagged). Against the derived −6.714, it is +2.56 dB (would flag). The architecture routes harshness detection through `presence_harsh.deviation_db`, selecting the placeholder. This is safe for now because the stage is default-off and thresholds are deferred to targets-derivation. But the two references cannot coexist — they must be reconciled before the stage can be enabled. The targets-derivation pass for this stage must address which value is authoritative.

### CONCERN 4 — 1.5-second IIR time constant is potentially audible at drop entrances

For a 5 dB gain step at a window boundary: after 1.5 seconds (one TC), 63% settled; after 3 seconds, 86%; after 5 seconds, 96%. The first 4–5 seconds of a drop hear a gain still ramping toward full attenuation. At 130 BPM this is 2–3 bars. In a genre where the first bar of the drop is the emotional climax, this is perceptible. A longer TC (3–5 seconds) would be more transparent for arrangement-level mastering. AC21 (listening gate) must specifically test the drop entrance on real material.

Note: this concern is downstream of Blocker 1. Until the DR coupling is fixed and the leveler has meaningful authority, the TC cannot be evaluated on real material.

---

## Gate 1 explicit decisions — standing record

---

### DECISION 1 — HF lift (air/shimmer) for STORY-027: REJECTED

Per CLAUDE.md §6.2: "HF extension: report-only unless justified by the actual signal."

The rejection is confirmed and this is the Gate 1 record of that decision. It is not a soft recommendation — it is a recorded gate hold.

**Reasons, each independently sufficient:**
1. CLAUDE.md §6.2 standing decision not cleared.
2. DEF-009-001 is open. HF-territory processing was judged "highly destructive to the track" at the listening gate after technical guards passed. That failure mode is not resolved.
3. Suno exports at 13–16 kHz nominal cutoff begin rolling off at 10–12 kHz. A shelf aimed "below the cutoff" at, say, 12 kHz amplifies content that is already in the rolloff zone where artifact-to-signal ratio is worsening, not content at reference level.
4. STORY-007 STATIONARY_WHISTLE artifacts are located in this frequency territory. A below-cutoff shelf amplifies them.
5. Air-band reference range across 3 tracks: [−20.05, −11.44] dB re mid = 8.6 dB spread. Any shelf magnitude would be unsupported by the reference data (DOMAIN.md §6: "the median is a shape no real record has").
6. The per-file band-limit measurement (hf_extension.py) was not wired into the pipeline before this story. Even as STORY-027 wires it in, the result has not been validated on a meaningful Suno sample set.

**Future gate conditions:** A future story may revisit only if all of the following hold: DEF-009-001 is resolved; `hf_band_limit_hz` has been validated on a representative Suno sample set; a listening test on real Suno material shows net improvement with a scoped below-cutoff shelf; and the band-limit confidence field confirms a reliable detection for the specific track.

---

### DECISION 2 — de_mud aim=2.0 with cap=6.522: CONFIRMED (conditional)

The delivered outcomes are acceptable:
- Sunday Club (src=6.54 dB): post≈+3.1 dB re mid — inside range, 3.25 dB above floor, 0.3 dB below reference median.
- Worst in-range case (src=8.522 dB): post≈+3.6 dB re mid — inside range, near median.

The concern about correcting "toward a value no real record occupies" (DOMAIN.md §6) is addressed: the delivered outcome is approximately the reference median, not 2.0 dB (the nominal aim), because the peaking bell delivery efficiency undershoots for large deviations. This is the intent working as it should.

**Conditions on this confirmation:**
1. QA must include the marginal-trigger test case (src≈4.1 dB) per Concern 1 above.
2. The 0.75× delivery efficiency is flagged as a maintenance dependency per §3.3. If the filter design changes, this review must be re-run.
3. The Gate 2 STORY-006 aim=2.0 decision is not revisited; this confirmation is specific to the new cap regime.

---

### DECISION 3 — Sub correction cap: deferred pending shelf delivery efficiency (see Blocker 2)

Cannot be set to a specific value until the shelf corner frequency, slope, and measured 20–60 Hz delivery efficiency are stated in the implementation.

When those are provided:
- My audibility ceiling for a single-pass low shelf cut at or below 60 Hz on a Suno mastering track is approximately 6 dB. Above that, the bottom of the mix becomes noticeably thin.
- The floor is `4.886 / delivery_efficiency`. The architect must compute and state this number.
- The developer must also characterise and document the shelf's incidental effect on 60–120 Hz (the `low` informational band).

---

### DECISION 4 — per-segment PSD for hf_extension.py: keep it enabled, do not config-gate

The architecture flags this as a Gate 1 runtime-cost decision (§6.2).

Decision: keep per-segment analysis active. The segment-to-segment stability confidence is the signal that distinguishes a real filter cutoff from a spurious or drifting detection. DOMAIN.md §2 explicitly records that "Suno / generative exports: may drift within one file." An `hf_band_limit_hz` value with no confidence assessment is not reliable enough to be the prerequisite gating condition for any future HF lift. Gating per-segment analysis away to save runtime removes the check that validates the measurement.

The two full PSD+segment calls per run (pre and post) are acceptable. The post-master call is informational given that no HF processing is applied in this story; its primary value is confirming that upstream stages did not alter the band limit (they should not, but the measurement confirms it).

---

### DECISION 5 — Adaptive harshness reachable but default-off: CONFIRMED

The approach in §4.3 is correct. Making the stage reachable from both entrypoints without enabling it by default is the only safe option given:
- `AdaptiveHarshnessConfig` thresholds are round numbers (5.0 / 2.5 / 2.0 / 3.0 / 4.0) — not derived from the reference set
- The `presence_harsh.reference_db` is itself a round number (see Concern 3)
- AC5 partial satisfaction is correctly documented

The stage must not become default-on until: (a) all `AdaptiveHarshnessConfig` thresholds are moved to `targets.json` with reference-derived values, and (b) the `presence_harsh` / `high_mid` reference conflict is resolved.

---

### DECISION 6 — no_op_threshold_db aggregation procedure: method is sound, value to follow from reference measurement pass

The procedure in §7.3 (compute window-LUFS std for each reference track, aggregate using max if max ≤ 1.59 dB else median, check and record the contingency) is methodologically sound. The conditional is reasonable — if reference tracks' own std exceeds Sunday Club's measured std, using max as the threshold would defeat the leveler on its motivating case.

The specific value cannot be confirmed here; it requires running the three reference tracks through the leveled measurement. The procedure for recording the outcome is correct.

---

## Incidental notes (not blocking, informational)

**Gate ordering in Step 5 (§7.2):** The no-op gate check is listed after Steps 3 (envelope computation) and 4 (apply). The implementation should perform the std_L check immediately after Step 1, before computing or applying the gain envelope. If the gate check occurs post-application, the implementation must return the original audio buffer, not `audio_out`. This is a correctness risk if the developer reads Step 5 literally and returns the wrong buffer.

**Mean vs median as internal LUFS target (§7.2, Step 2):** Mean is pulled upward by outlier-loud windows, reducing attenuation on moderately loud sections. Median is more robust for material with isolated loud segments. Either is defensible for Suno material with typical arrangement patterns. The choice should be explicitly stated and documented, not silently defaulted.

**dr_floor vs reference DR structural observation (not in scope for STORY-027):** `dr_floor: 8.0` versus reference DR range `[6.599, 8.646]`. Two of three reference tracks sit at or below the project's own DR floor. This is not STORY-027's problem to fix, but it is the same structural tension that drives Blocker 1, and a future story should address it.

**Leveling.max_attenuation_db derivation:** Cannot be provided until Blocker 1 is resolved. After the DR coupling design is clarified, I can supply an audibility-based ceiling (the maximum gain ride I'd apply in an arrangement-level mastering pass without audible pumping). That is a listening question, not a reference-statistics question, and I have an answer once the framework is stable.

---

## Gate 1 v1.2 follow-up

**Architecture version reviewed:** v1.2
**Date:** 2026-08-21

---

### BLOCKER 1 — RESOLVED

The v1.2 architecture removes the `dr_budget × 0.5` pre-emptive cap entirely. The leveler measures TT DR from its own output buffer and returns `post_leveler_dr_db` in `LevelingAction`. `pipeline.py` passes that value to the solver instead of Stage [2] `source_dr_db`.

The proof in §7.4 is correct and sufficient. Because downward-only leveling can only reduce TT DR (`post_leveler_dr_db ≤ source_dr_db`), the solver's `dr_required_new ≤ dr_required_old` follows directly. The solver's existing hard constraint is never harder to satisfy than before the leveler was introduced. Tracks that master successfully without the leveler continue to master successfully with it.

The STORY-006/025 API compatibility note is also correct: `solve_loudness_and_limit` accepts any float for `source_dr_db`, and the meaning of the guarantee ("achieved DR ≥ dr_required, where dr_required is computed from the supplied source DR") is unchanged — it now refers to the leveler's output as the relevant source, which is the physically correct baseline.

The `no_dr_budget` fallback is correctly removed. There is nothing to guard against because the solver constraint takes over post-hoc.

One note for the implementation: `post_leveler_dr_db` must be populated in `LevelingAction` even when `applied=False` (the no-op path). The module contract (§7.5) shows it as always present, which is correct. When the gate fires and audio is returned unchanged, `post_leveler_dr_db` should equal the pre-leveler DR (measured from the same unchanged buffer). The developer must not leave it as 0.0 or None in the no-op branch, since `pipeline.py` passes it to the solver unconditionally.

**Blocker 1 is resolved. Item 4 implementation may proceed on the DR coupling question.**

---

### BLOCKER 2 — PARTIALLY RESOLVED. New constraint created: the minimum cap (8.14 dB nominal) exceeds the audibility ceiling I previously stated (~6 dB).

The v1.2 architecture now states the shelf is RBJ Butterworth low-shelf at fc=60 Hz, S=1.0, with ~0.60× delivery efficiency over 20–60 Hz. The minimum safe nominal cap of 8.14 dB is correctly derived: 4.886 / 0.60 = 8.143, rounded up.

The delivery efficiency information resolves the information gap that made Blocker 2 impossible to answer. However, it creates a new constraint conflict.

**The audibility concern at 8.14 dB nominal:**

My original ceiling of "approximately 6 dB" was stated in terms of the perceived correction. An 8.14 dB nominal RBJ low-shelf at fc=60 Hz produces the following actual gain profile:
- Above 60 Hz: ~0 dB (shelf above the corner)
- At 60 Hz: approximately −4 dB (the half-power point for S=1 Butterworth)
- At 40 Hz: approximately −6 to −7 dB
- Approaching DC (20 Hz): approaching −8.14 dB

The 30–50 Hz zone is where kick drum fundamentals and sub-bass energy in club material reside. A nominal 8.14 dB shelf delivers approximately 6–7 dB of actual cut at 40 Hz. This is at and above the ceiling I stated. On a track where the sub is this problematic (Sunday Club: source +6.83 dB vs range max +1.944 dB), a cut of this magnitude is warranted — the source IS genuinely excessive. But a blanket cap of 8.14+ dB applied to any track triggering sub range-compliance would thin the low end of a track with only a modest sub excess.

**Resolution:**

The 8.14 dB nominal figure is the correct minimum for Sunday Club specifically. I am raising the audibility ceiling to accommodate it, with the following conditions:

1. **The cap is appropriate for Sunday Club.** The source is 4.886 dB above range max. A correction delivering that much band-energy change, even if it requires 8.14 dB nominal to get there given the shelf's efficiency, is justified. The output should land at the range edge, not be left 2+ dB short because the nominal number looks large.

2. **The cap is not safe as a general ceiling for mild sub deviations.** A track 1 dB above sub range_max receiving an 8.14 dB nominal shelf would be grossly over-corrected — delivering ~0.6 dB of band-energy change but applying 6–7 dB at 40 Hz is not the correct framing; the correction would be capped at the required gap by the algorithm, so 1 dB excess → ~1.67 dB nominal applied → ~1.0 dB delivered. The cap is a maximum, not a target. The algorithm corrects only as much as needed toward the range edge and caps at the nominal ceiling. A 8.14 dB cap for a 1 dB excess case applies 1.67 dB nominal (well within the cap) and is fine.

3. **Therefore:** I revise the audibility ceiling to 9 dB nominal. This provides headroom above Sunday Club's 8.14 dB minimum, handles future tracks with similar or worse sub excess, and is within the range where a single-pass mastering shelf at 60 Hz is still corrective rather than destructive (at 40 Hz, 9 dB nominal delivers approximately 7–8 dB of actual cut — aggressive but justified when the source warrants it).

**Gate 1 confirmed value: `sub.correction_cap_db = 9.0`**

Derivation basis: audibility limit for a single corrective pass; Sunday Club minimum floor (8.14 dB); 0.86 dB headroom above that floor for tracks with worse excess. This is not a round number chosen arbitrarily — it is the first round number above the derived minimum (8.14 dB) that provides meaningful headroom. The implementation must confirm this value produces an acceptable result on Sunday Club by listening before QA sign-off (AC21).

**Shelf spillover note (from Blocker 2 concern, now confirmed):** An RBJ low-shelf at fc=60 Hz, S=1.0, at 9 dB nominal will produce meaningful gain in the 60–120 Hz low band. The `low` band is classified informational and has no correction target, but the spillover should be characterised and included in the implementation documentation. At 80 Hz, expect approximately 4–5 dB of incidental cut; at 100 Hz, approximately 2–3 dB. This is not a blocker — the low band informational classification means no correction fires there — but QA should verify the post-master seven-band `low` band figure changes in the expected direction and magnitude.

**Blocker 2 is resolved with `sub.correction_cap_db = 9.0`. Implementation may proceed.**
