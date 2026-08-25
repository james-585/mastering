# STORY-027 Defects

## DEF-027-007 — TC2757 Gain Trajectory Failure: Leading-Window Look-Ahead Conflict

**Status:** Closed
**Closed:** 2026-08-21 — TC-2757 redesigned to assert leading-window pre-ramp behaviour per architecture §7.2. New assertions: (1) gain near 0 dB at t=1s (before leading windows see the burst), (2) gain pre-ramped below -1 dB at burst entrance t=18s, (3) settled-fraction at τ=1.5s in [0.45,0.80] and 2τ in [0.70,0.95], (4) smoothness <2.5 dB/100ms hop.
**Tag:** Architectural
**Severity:** Test failure — behavioral contract conflict between architecture pseudocode and TC2757
**Filed:** 2026-08-21
**Source:** TC-2757 test_gain_smooths_toward_target; revealed by DEF-027-001 fix (envelope padding)

**Description:**

TC-2757 checks that at the loud-burst entrance (t=18s), the smoothed gain envelope has not yet
exceeded 50% of its final attenuation (`g0 > g_final_db * 0.5`). This test passes only if the
IIR has had little time to ramp before the burst starts — i.e., if there is no look-ahead.

Architecture §7.2 Step 1 specifies leading windows:
```
For n in range(0, len(audio) - window_samples + 1, hop_samples):
    ms = mean_square(kw[n : n + window_samples])
    L[n] = LUFS(ms)
```
The gain_db for hop n is applied to samples starting at position n. With a 3-second window,
the hop at t=15.2s already includes 2.8/3 = 93% loud content from the upcoming burst (t=18s),
yielding a large negative gain that starts the IIR ramp 2.8 seconds before the burst. By t=18s
the IIR has settled to ~70% of its final attenuation (-8.35 dB of -11.98 dB final), failing the
`g0 > g_final_db * 0.5 = -5.99 dB` assertion.

This defect was hidden before the DEF-027-001 fix (envelope padding to n_audio_samples). The
previous code did not apply any envelope to the last 2.9s of the track, so `g_final_db >= -0.1`
and the test SKIPPED. The envelope fix correctly pads the tail, making g_final_db = -12 dB,
which causes the test to RUN and fail on the underlying architectural issue.

**Two contradictory requirements:**
- Leading windows (architecture pseudocode §7.2): gain for sample t uses window [t, t+3s]. Produces 3s look-ahead.
- TC-2757 behavioral expectation: gain should be near 0 dB AT the burst entrance. Requires trailing windows (window [t-3s, t]) OR a gain-timeline shift forward by window_samples.

**Trailing alignment also fails TC-2757 (settled_frac assertion) AND breaks TC-2761:**

Trailing implementation: prepend window_samples zeros, then write hop i's gain into
`[window_samples + i*hop_len : window_samples + (i+1)*hop_len]`. This shifts the entire
gain envelope 3s into the future.

TC-2757 fixture (27s, burst at t=18s):
- At t=18.05s (g0): the gain placed there comes from window [15.05, 18.05], which is still
  predominantly quiet (0.05/3 = 1.7% burst). IIR input ≈ 0 dB. g0 ≈ 0 → PASSES assertion 1.
- At t=19.5s (g1_5): gain from window [16.5, 19.5] (50% burst) ≈ -9 dB input. IIR has been
  ramping from 0 for 1.5s with a ramp input. IIR output ≈ -4 to -5 dB.
  settled_frac_1_5 = (g0 - g1_5) / (g0 - g_final) ≈ 4/11.99 ≈ 0.33 → FAILS [0.45, 0.80].

So trailing alignment passes assertion 1 (`g0 > g_final*0.5`) but fails assertion 2
(`settled_frac_1_5 in [0.45, 0.80]`). Neither leading nor trailing alignment satisfies
all three of TC-2757's assertions simultaneously.

TC-2761 fixture (F07, 12s, loudest block at t=[9,12]s = END of track):
- With trailing alignment, the last valid hop covers window [9s, 12s]. Its gain would be
  placed at t = 12s + 9s*hop_density (effectively after the audio ends). The loudest
  block (blk3) receives NO attenuation. std_lufs_after ≈ std_lufs_before; second pass
  applies again → TC-2761 fails.

**Root cause:** TC-2757's `settled_frac_1_5` assertion assumes the IIR begins from 0 dB
at t=0 of the burst and that the input is a step to g_final, giving e^{-1} ≈ 0.632
settled at τ=1.5s. Neither leading nor trailing alignment produces this ideal step because
the gain input is itself a ramp (window content changes gradually over the 3-second
window). TC-2757's model (IIR step response) does not match the gain ramp geometry.

**Method change required (H6 — not a parameter change):**
The architect must choose one of:
  a. Accept leading-window look-ahead and relax TC-2757's assertion 1 (`g0 > g_final*0.5`)
     to account for up to 2.8s of pre-ramp before the burst. Assertion 2 (`settled_frac`)
     may then be satisfiable depending on the exact g0 measured after relaxing assertion 1.
     The test-case-writer must update TC-2757 to match the measured look-ahead behavior.
  b. Redesign TC-2757 to test the actual causal-IIR ramp trajectory rather than the
     idealized step-response model. The IIR ramp from -8 dB at burst entrance to -12 dB
     at burst + 1.5s is still a monotone trajectory that can be tested quantitatively.

**Reproducer:** TC2757::test_gain_smooths_toward_target with fixture: 6 quiet windows at
-24 dBFS + 3 loud windows at -6 dBFS (27s total). g0 = -8.35 dB, g_final = -11.98 dB.
Assert `g0 > g_final*0.5 = -5.99` fails: -8.35 is not > -5.99.

---

## DEF-027-001 — BS.1770 Intra-Window Gating Bias in Dynamics Leveler

**Status:** Fixed-Pending-Retest
**Tag:** Architectural (resolved in architecture v1.3; code fix applied)
**Severity:** Method-level concern (H6 — not a parameter tuning issue)
**Filed:** 2026-08-21
**Source:** Gate 1 Concern 2 (gate1-review.md)

**Description:**

`dynamics_leveler.py` calls `pyloudnorm.Meter(sr).integrated_loudness(window_audio)` on each
non-overlapping 3-second window (architecture §7.2 Step 1). BS.1770's relative gating applies
*within* each window: a window that straddles a breakdown→drop boundary gates out the quiet half
and returns a LUFS value reflecting primarily the loud half. The resulting per-window LUFS value
drives a uniform gain applied to the entire 3-second chunk, including the pre-transition zone —
causing over-attenuation of content before the section change.

Gate 1 Concern 2 identifies this as a method problem, not a parameter problem. The correct tool
is BS.1770 short-term loudness (3-second sliding window, 100 ms hop, no intra-window relative
gate), which eliminates both the gating bias and the 3-second step quantisation that the IIR
smoothing is compensating for downstream.

**Implemented as-specified:** architecture §7.2 Step 1 specifies `Meter(sr).integrated_loudness`.
This story implements the architecture as written. This defect routes the method concern back to
the architect for a revision decision.

**Root cause:** Architecture §7.2 specifies the wrong BS.1770 measurement mode for windowed
leveling.

**Method change required (not a parameter change — H6):** Replace
`Meter(sr).integrated_loudness(window_audio)` with a short-term loudness measurement
(100 ms hop, no relative gate) to correctly characterise loudness at section boundaries.

**Impact:** Audible over-attenuation at section entry points (e.g. drop entrances) when a
3-second window straddles a loud→quiet→loud boundary. AC21 (listening gate) must specifically
test this on real material.

**Fix notes:** (python-developer, 2026-08-21)
Method change (H6 compliant): `dynamics_leveler.py` now implements K-weighted ungated
mean-square per architecture §7.2 v1.3. Specific changes:
- `_kw_prefilter_sos(sr)`: BS.1770-4 Stage 1 high-shelf filter computed at actual sample rate.
  Verified: produces coefficients matching the BS.1770-4 reference at 48 kHz within FP precision.
- `_kw_highpass_sos(sr)`: BS.1770-4 Stage 2 Butterworth highpass at 38.135 Hz.
- `_apply_k_weighting(audio, sr)`: applies both filters in sequence via scipy.signal.sosfilt
  (causal forward-pass; NOT sosfiltfilt).
- `_compute_block_lufs(audio, sr)`: K-weights each non-overlapping block INDEPENDENTLY (fresh
  filter state per block). Required to prevent IIR transient from loud blocks contaminating
  adjacent silent blocks. Without per-block K-weighting, a loud-to-silent transition at a block
  boundary leaves ~-35 dBFS of IIR energy in the first 54ms of the silent block, raising its
  mean-square above the -70 LUFS absolute gate threshold (blocks at -90 dBFS appear at -66 LUFS).
- `_compute_window_lufs(kw, sr)`: 100ms hop sliding windows on the pre-computed full-track kw.
  Used for the gain envelope only (IIR continuity is appropriate here).
- `_iir_smooth_envelope(gain_db_per_window, sr, n_audio_samples)`: pads gain_db_samples to
  n_audio_samples with the last hop's gain before the IIR pass, ensuring the envelope covers
  the full audio. Without this, the last 2.9s of audio received no envelope (the hop that
  starts at t=n_audio_samples - window_samples only generated one hop_len worth of gain samples
  rather than covering the full 3-second window's duration).
- `_lufs_from_ms(ms)`: absolute gate at -70 LUFS — silent blocks return -inf and receive
  gain=0 in the envelope.
TC-2752 (gated windows, unchanged audio) now passes. TC-2761 (second-pass no-op) now passes.
TC-2757 (gain trajectory) was previously SKIPPING due to the envelope coverage bug — now FAILS
due to an architectural conflict (see DEF-027-007). pyloudnorm is not used in the leveler
window measurement path.

**Architectural deviation (§7.2 literal wording):** Architecture §7.2 says "Apply K-weighting
to the full audio buffer" (one pass, buffer-wide). `_compute_block_lufs` deviates from this by
K-weighting each 3-second block independently (fresh IIR state per block). Rationale: applying
K-weighting buffer-wide causes IIR filter state from a loud block to bleed into an adjacent
silent block, corrupting the silent block's LUFS from the correct ~-94 LUFS to -66 LUFS —
above the -70 LUFS absolute gate, preventing correct gating. The full-track K-weighted buffer
(kw) is still computed and used for the 100ms hop sliding windows in the gain envelope, where
IIR continuity is meaningful. Per-block K-weighting applies only to `_compute_block_lufs` (used
for reporting, gating, and target_mean). This deviation is required for correctness and is
documented here for architect review.

---

## DEF-027-002 — Dynamics Leveler Targets Not Yet Derived

**Status:** Fixed-Pending-Retest — threshold committed; max_attenuation_db pending AC21 listening  
**Tag:** Architectural  
**Severity:** Stage blocked (no-op until resolved)  
**Filed:** 2026-08-21  
**Source:** Architecture §7.3, §14.3; Gate 1 DECISION 6

**Description:**

The dynamics leveling stage requires two values from `targets.json`:
- `leveling.no_op_threshold_db`: window-LUFS std below which the stage is a no-op
- `leveling.max_attenuation_db`: maximum per-window downward gain

Architecture §7.3 specifies that `no_op_threshold_db` must be derived from the window-LUFS std
of the three target-derivation reference tracks using `median()` aggregation. Gate 1 DECISION 6
confirms the procedure is sound but cannot supply the value without running the measurement.
`max_attenuation_db` requires a listening test at the 1.5-second smoothing time constant (Gate 1
incidental note on leveling derivation).

Neither value is present in `targets.json` as of STORY-027 implementation.

**Current behaviour:** When the `leveling` block is absent from `targets.json`, the stage returns
`applied=False, reason="leveling_targets_not_derived"` and populates `post_leveler_dr_db` from
the unchanged buffer (correct pipeline contract). The stage is fully implemented but inert.

**Measurement pass run 2026-08-21 — §7.3 procedure invalid for this material:**

The derivation pass was executed using the exact same `_compute_block_lufs` path the runtime gate
uses (non-overlapping 3-second blocks, per-block K-weighting, -70 LUFS absolute gate). The 100 ms
hop sliding-window std (§7.3 literal) was also recorded.

Per-track results:

| Track | Block std (gate method) | Hop std (§7.3 literal) |
|-------|------------------------|------------------------|
| Chemical Brothers — Live Again | 4.7504 dB | 4.7295 dB |
| GusGus — Over (Arabian Horse)  | 4.1495 dB | 3.4878 dB |
| Black Flute (Remastered)       | 2.7365 dB | 2.7135 dB |
| **Sunday Club (motivating)**   | **2.0179 dB** | **1.8695 dB** |

Derived threshold via §7.3 `median()`:
- Block method: **4.1495 dB**
- Hop method: **3.4878 dB**

**Sanity check FAILS:** The derived threshold (4.1 dB) is above Sunday Club's measured std
(2.0 dB) by 2.1 dB. Committing this value would leave the stage permanently inert on Sunday
Club — the exact track the stage was designed for. Both block and hop methods fail.

**Root cause of §7.3 failure:** The procedure's rationale was that good reference masters would
have lower loudness variation than Suno-generated material, so `median(ref_stds)` would sit below
the motivating track's std and allow leveling to fire. The measured data shows the opposite:
all three reference masters (professional dance/electronic productions) have substantially more
arrangement-level loudness variation than Sunday Club (2.75–4.75 dB vs 2.02 dB). The median
aggregator does not rescue the procedure when all three references are outliers in the wrong
direction.

**Architect decision required — two viable paths:**

a. **Absolute threshold from motivating-track population.** Set `no_op_threshold_db` to a fixed
   value below Sunday Club's measured std (2.02 dB block). Candidates: 1.0 dB (conservative),
   1.5 dB (moderate). Document the rationale as "leveler targets Suno material, not reference
   masters; threshold set below the lowest known motivating-track std." This replaces the §7.3
   procedure entirely.

b. **Expand the reference population to Suno material.** Measure window-LUFS std on a set of
   Suno tracks that represent the population the leveler should not touch (already well-leveled
   Suno outputs or Suno tracks where leveling is undesirable), take the median. This is a
   new derivation procedure, not a correction to §7.3.

In either case, `max_attenuation_db = 3.0` (§7.3 initial candidate) remains a reasonable
starting point pending AC21 listening confirmation.

**Values NOT committed to targets.json.** Committing 4.1 dB would make the stage inert on all
Suno material below that threshold and is worse than the current "not derived" state.

**Architect resolution (2026-08-21):** Path a selected. `no_op_threshold_db = 1.0 dB` committed to
`targets.json` — absolute threshold calibrated to Suno material, below Sunday Club's measured std
(2.02 dB). §7.3 procedure abandoned for this target; architecture.md §7.3 updated to document the
corrected derivation. `max_attenuation_db = 3.0` committed as §7.3 initial candidate; AC21 listening
confirmation still required before this defect can be fully closed.

---

## DEF-027-003 — Post-Leveler DR Assumption May Not Hold After Large Sub EQ

**Status:** Open  
**Tag:** Architectural  
**Severity:** Low risk — solver regression guard (§7.7) is the safety net  
**Filed:** 2026-08-21  
**Source:** Advisor review; architecture §7.4 proof assumption

**Description:**

Architecture §7.4 proves that `post_leveler_dr_db ≤ source_dr_db` because downward-only
leveling reduces TT DR (attenuates peaks more than raising RMS, lowering crest factor). This
proof holds when the leveler is the last stage that changes the audio before DR is measured.

However, the leveler sits at Stage 3c, downstream of Stage 3a (corrective EQ). STORY-027 now
permits up to 9 dB of sub-band shelf cut (sub.correction_cap_db = 9.0). A large sub shelf
cut substantially reduces RMS in the 20-60 Hz band, which can *raise* the crest factor (reduce
RMS more than peak), potentially increasing TT DR. If the post-EQ audio has higher TT DR than
`before.dynamic_range_db` (the pre-EQ baseline), then after downward leveling,
`post_leveler_dr_db` may still be ≤ post-EQ DR but > pre-EQ `before.dynamic_range_db`.

In that case `dr_required_new > dr_required_old` and the solver's constraint is harder than
without the leveler, contrary to the §7.4 proof.

**Current implementation:** The §7.7 solver-regression guard (named test requirement) is the
designed safety net for this risk. The guard test must run on a track where the sub correction
is large (e.g. Sunday Club) and verify no `UnresolvableMasteringConstraintError` is raised.

**Root cause:** The §7.4 proof uses `source_dr_db` (pre-EQ) as the reference, but the relevant
comparison is against the post-EQ DR that the solver would have seen without the leveler. The
proof is tight if the EQ does not materially change TT DR, which holds for small corrections but
may not hold for a 9 dB sub shelf.

**Action for architect:** Assess whether the §7.7 guard test is sufficient or whether the
proof needs to be tightened to account for EQ-induced DR changes. No code change is required
until the listening gate confirms an issue.

---

## DEF-027-004 — Sub Shelf Correction Non-Compensating (OQ-A Delivery Efficiency Ignored)

**Status:** Fixed-Pending-Retest  
**Triage:** Code-level  
**Reported by:** qa-automation-engineer  
**Linked test case:** TC-2710, TC-2711  
**Filed:** 2026-08-21

**Description:**

`corrective_eq.py` applies the raw spectral gap as the shelf gain without compensating for the
sub shelf delivery efficiency (~0.60×). The sub shelf filter (`_low_shelf_sos`) with gain_db=G
in a `sosfiltfilt` (forward-backward) pass delivers ≈0.60×G at the band centre (20–60 Hz) on
band-limited noise, not G.

For a fixture with sub_band_level = +0.5 dB above range_max (1.944 dB), the raw gap to aim =
+0.5 − 1.944 = −1.444 dB. The compensating applied_db should be −1.444 / 0.60 = −2.41 dB,
which would land sub_after ≈ 1.944 dB (at range_max). Instead the non-compensating code applies
−1.444 dB and delivers only −0.86 dB, leaving sub_after = 2.88 dB — still 0.94 dB above range_max.

**Measured values (TC-2710):**
- sub before: 2.88 dB (constructed +0.5 above range_max 1.944 dB, i.e. actual level ≈ 2.44 dB)
- sub after:  2.88 dB (no effective change; non-compensating shelf delivered ~0 net correction)
- range_max:  1.944 dB
- Failure: `sub_after (2.882) > range_max (1.944)`

**TC-2711 measured:**
- delivered_db = −3.93 dB; expected ≤ −4.3 dB (aim point minus construction offset)

**Required fix:** In `corrective_eq.py`, divide the raw spectral gap by the sub shelf delivery
efficiency before passing to `_low_shelf_sos`:
`applied_db = raw_gap / DELIVERY_EFFICIENCY_SUB`  where `DELIVERY_EFFICIENCY_SUB ≈ 0.60`.

This is a method correction (OQ-A compensating path), not a parameter change (H6 compliant).

**Fix notes:** (python-developer, 2026-08-21)
Method change (H6 compliant): added `_DELIVERY_EFFICIENCY_SUB = 0.60` constant and
computed `nominal = raw_gap / _DELIVERY_EFFICIENCY_SUB` for the sub band filter design.
The filter now receives `-8.14` dB nominal (for the F01 fixture gap of -4.886 dB), so the
delivered 20-60 Hz band-energy change is ≈ -4.886 dB, placing sub at or below range_max.
`action.applied_db` stores `effective_band_change = applied * _DELIVERY_EFFICIENCY_SUB`
(the expected delivered band-level change), keeping semantics consistent with the low_mid
path. Low_mid: DEF-027-004 "check" confirmed non-compensating is correct — TC-2720 tests
expect `applied_db = raw_gap` and post-result ≈ 2.525 (= 4.1 - 0.75×2.1), which is the
no-compensation outcome. Low_mid code unchanged.
TC-2711 and TC-2720 both pass at 110/110 (verified locally, exit code 0).

---

## DEF-027-005 — master_track.bat Does Not Wire --harshness-correction

**Status:** Fixed-Pending-Retest  
**Triage:** Code-level  
**Reported by:** qa-automation-engineer  
**Linked test case:** TC-2731  
**Filed:** 2026-08-21

**Description:**

`master_track.bat` hardcodes the Python command without `%*` passthrough or the
`--harshness-correction` flag:

```
python -m suno_mastering "%INPUT%" --split-stems --stem-model htdemucs_6s \
  --no-detect-whistles --no-repair-whistles --no-shape-transients --no-collapse-swish
```

The AC5b acceptance criterion requires that `master_track.bat` wires harshness correction so
users can invoke it via the bat file. The current bat cannot pass any additional flags.

STORY-027 architecture §4.3 states the stage must be "reachable from both shipped entrypoints
(cli.py and master_track.bat)". cli.py is confirmed reachable (TC-2730 passes); bat is not.

**Required fix:** Add either:
- `%*` at the end of the Python command so any additional bat arguments are forwarded, OR
- An explicit `--harshness-correction` flag (if the bat is always meant to run with harshness)

**Fix notes:** (python-developer, 2026-08-21)
Parameter change: appended `%*` to the Python invocation line in `master_track.bat`.
All CLI arguments passed to the bat file are now forwarded verbatim to `cli.py`, including
`--harshness-correction` and `--no-harshness-correction`. TC-2731 passed at 110/110.

---

## DEF-027-008 — adaptive_harshness sosfiltfilt Delivers 2× Configured Gain

**Status:** Fixed-Pending-Retest
**Tag:** Code-level (design-parameter convention mismatch)
**Severity:** High — blocked default-on; when enabled, stage was applying double the intended correction
**Filed:** 2026-08-22
**Source:** STORY-027 threshold derivation pass; documented in AdaptiveHarshnessAction docstring

**Description:**

Both filter constructors in `adaptive_harshness.py` pass `gain_db / 40.0` as the RBJ `a`
parameter (line 78 for `_peaking_sos`, line 94 for `_low_shelf_sos`). The RBJ formula with
this convention delivers `gain_db` at ω₀ in a single-pass filter. However, `apply_adaptive_harshness`
uses `sosfiltfilt` (forward + backward pass), which doubles the gain, delivering `2 × gain_db`
at ω₀.

This is documented in the `AdaptiveHarshnessAction` docstring:
> "gain_db/40 is passed to the RBJ formula, giving gain_db at ω0 single-pass and 2×gain_db
>  after sosfiltfilt — the discrepancy is a pre-existing STORY-010 design issue"

**Consequence:**
- `narrow_gain_db = -3.0` → actual cut ≈ **-6 dB** at ω₀
- `broad_gain_db = -2.0` → actual cut ≈ **-4 dB** at ω₀
- `max_gain_db = 4.0` caps the design parameter, not the delivered gain; effective ceiling ≈ **8 dB**

The `after_db = before_db + gain_db` estimate in `AdaptiveHarshnessAction` is also wrong by 2×
(understates the correction actually applied).

`targets.json` `broad_gain_db` and `narrow_gain_db` derivation strings note this defect and
flag the values as uncalibrated until this is resolved.

**Inert while default-off.** This defect does not affect any track processed without
`--harshness-correction`.

**Required fix (H6 — method change):** Use `gain_db / 2.0` as the design parameter to the
RBJ constructors so that `sosfiltfilt`'s doubling yields the intended `gain_db` at ω₀.
Update `applied_db` population in both action sites to `gain_db` (no further change needed;
the value already equals the intended delivered gain after the fix). Update the docstring.
Verify with a unit test: apply `_peaking_sos` at gain_db=-3.0 via `sosfiltfilt` on
band-limited noise at f₀=3162 Hz, measure band-energy delta, assert it is within ±0.5 dB
of -3.0 dB.

**Fix notes:** (2026-08-22)
Method change (H6 compliant). Both RBJ call sites in `apply_adaptive_harshness()` now pass
`gain_db / 2` as the design parameter: `_low_shelf_sos(sr, f0, gain_db / 2)` for the
broad_shelf branch and `_peaking_sos(sr, f0, gain_db / 2, bw)` for the narrow_cut branch.
`sosfiltfilt`'s forward+backward doubling then yields the intended `gain_db` at ω₀. Matches
the corrective_eq.py convention. Docstring updated to document the convention rather than flag
a bug. `targets.json` derivation strings updated to remove the "uncalibrated" caveat for
`broad_gain_db` and `narrow_gain_db` (the values are now delivered as configured).
Two new tests added to `test_story010_adaptive_harshness.py`:
- `test_tc_def027008_peaking_gain_delivery`: sinusoid at 3162 Hz, peaking sos, asserts
  delivered gain within ±0.5 dB of configured gain_db=-3.0. PASSES.
- `test_tc_def027008_shelf_gain_delivery`: sinusoid at 100 Hz, low-shelf sos at fc=3500 Hz,
  asserts delivered gain within ±0.5 dB of configured gain_db=-2.0. PASSES.
All 6 harshness tests pass at 6/6.

---

## DEF-027-006 — AdaptiveHarshnessAction Missing Spec-Required Fields

**Status:** Fixed-Pending-Retest  
**Triage:** Code-level  
**Reported by:** qa-automation-engineer  
**Linked test case:** TC-2733  
**Filed:** 2026-08-21

**Description:**

AC19 specifies that every new correction path must be logged with before/after evidence.
The test-cases.md TC-2733 specifies that `AdaptiveHarshnessAction` objects must carry:
`before_db`, `after_db`, `classification`, `applied_db`.

The actual dataclass in `adaptive_harshness.py` has only:
`method`, `reason`, `center_hz`, `gain_db`, `bandwidth_octaves`.

The fields `before_db`, `after_db`, `classification`, and `applied_db` are absent.

**Measured:**
- `hasattr(action, 'before_db')` → False
- Available fields: `['method', 'reason', 'center_hz', 'gain_db', 'bandwidth_octaves']`

**Required fix:** Add the four missing fields to `AdaptiveHarshnessAction` and populate them
in `apply_adaptive_harshness()`:
- `before_db`: band RMS level before the harshness filter is applied
- `after_db`: band RMS level after the harshness filter is applied
- `classification`: `"broad_shelf"` or `"narrow_cut"` (same as `method` — can alias or add)
- `applied_db`: the actual gain_db delivered (may differ from `gain_db` if delivery efficiency applies)

**Fix notes:** (python-developer, 2026-08-21)
Method addition: added four fields to `AdaptiveHarshnessAction` dataclass with defaults so
existing callsites without these fields do not break: `before_db: float = 0.0`,
`after_db: float = 0.0`, `classification: str = ""`, `applied_db: float = 0.0`.
Both action-creation sites in `apply_adaptive_harshness()` now populate all four fields:
- `before_db = float(presence.relative_db)` (band level from pre-filter FrequencyBalanceResult)
- `after_db = before_db + gain_db` (estimated post-filter band level at centre frequency)
- `classification = method` ("broad_shelf" or "narrow_cut")
- `applied_db = gain_db` (delivered gain at centre frequency)
TC-2733 passed at 110/110.
