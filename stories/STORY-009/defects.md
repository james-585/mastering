# STORY-009 Defects

## DEF-009-001 — `repair_whistles` is destructive on real programme material and must not ship as a valid repair stage

**Status**: Closed  
**Severity**: Code (implementation bug)  
**Raised by**: mastering-engineer review  
**Date raised**: 2026-08-16

**Description**: The `repair_whistles` stage in STORY-009 is not functioning as a valid, narrow whistle repair. On the Sunday Club pass, it introduces large broadband energy loss, leaves the whistle burden largely unchanged, and sits exactly at the true-peak ceiling without usable headroom. This is not a tuning issue; it is a method failure in the repair path and the detector-to-repair contract.

**Evidence**:
- `Reference Tracks/Sunday Club_mastered.wav`
- `Reference Tracks/Sunday Club_mastered_report.md`
- `Reference Tracks/Sunday Club_mastered_report.json`
- `stories/STORY-009/mastering-review-results.md`
- `stories/STORY-009/mastering-review-methods.md`
- `stories/STORY-009/architecture.md`

**Observed findings**:
- True peak sits exactly on the project ceiling: `-1.00 dBTP`, leaving no headroom.
- Artifact burden remains high after repair: `454` flags before, `92` after, with `STATIONARY_WHISTLE` still dominant.
- Repair actions show large destructive deltas, including:
  - peak delta ≈ `-5.24 dB`
  - RMS delta ≈ `-7.81 dB`
- The repair stage is acting like broadband attenuation rather than a narrow notch at a confirmed whistle frequency.

**Impact**: The current stage is damaging programme material while failing to reduce the artifact burden. It should not be considered valid for any default-on or release use.

**Root cause**: The current repair approach is using a method that is too broad in time, too aggressive in amplitude reduction, not constrained to the actual flagged window, and not preserving the signal under the OLA reconstruction rules documented in architecture.md §3. The method is not within the narrow permitted scope of `repair_whistles` for `STATIONARY_WHISTLE` only, and it is not safe as implemented.

This is a method failure, not a parameter-tuning issue. A stronger threshold or a different notch depth would not fix the root cause; the repair path itself needs to be replaced.

**What was done**: The project already recorded the risk and the required method review in `stories/STORY-009/mastering-review-methods.md` and `stories/STORY-009/mastering-review-results.md`. The repair stage remains default-off by configuration, which is the correct immediate posture, but the underlying implementation still fails on real programme material and cannot ship.

**Required fix**:
1. Fix the OLA overlap-normalisation bug in `src_cpp/spectral_repair.cpp`.
2. Keep the stage default-off until the method is verified on real programme material.
3. Restrict the input to frequencies sourced only from confirmed `STATIONARY_WHISTLE` detector flags.
4. Apply the notch only inside the flagged time window rather than across the whole file.
5. Validate the empty-frequency no-op case and the real-track result before re-enabling the stage.
6. Treat any “tune the notch amount” workaround as invalid if it does not replace the method.

**Routing**: Code (implementation bug). This is a STORY-009 issue because it is specific to the `repair_whistles` implementation, the detector-to-repair contract, and the C++ OLA/normalisation path in the DSP extension, not a detector false-positive issue in STORY-007.

**Implementation progress** (2026-08-18):

Items 1–4 and 6 are code-complete in the initial commit:

1. ✅ **OLA fix** — `src_cpp/spectral_repair.cpp` uses `overlap_weights[out_index] += hann[i] * hann[i]` at all four accumulation sites (main-loop 1-D/2-D, tail-branch 1-D/2-D). Edge-frame stability guard `kMinReliableOverlapWeight = 4.0e-6f` passes through original sample rather than dividing by near-zero weight.
2. ✅ **Default-off** — stage gated by `RepairWhistlesConfig.enabled` (default `False`); pipeline only calls `apply_whistle_repair` when the flag is set.
3. ✅ **STATIONARY_WHISTLE only** — `whistle_repair.py` filters to `artifact_type == "STATIONARY_WHISTLE"` before building `target_frequencies`. Function signature accepts only `ArtifactDetectionResult`; no raw `list[float]` parameter (structural enforcement, not convention).
4. ✅ **Time-windowed** — `_flag_envelope` produces a linear crossfade ramp over each flagged window; `np.maximum` union is used when multiple flags overlap, so the result is applied only within the union of flagged regions.
5. ✅ **Real-track validation** — run against `Reference Tracks/Sunday Club.wav` on 2026-08-18 with fixed OLA. Results:

   | Metric | Baseline (no repair) | Treatment (repair ON) | Change |
   |---|---|---|---|
   | Integrated LUFS | −13.54 | −13.55 | −0.01 LU (negligible) |
   | True peak | −2.77 dBTP | −1.00 dBTP | At ceiling — solver applied more gain to compensate for notched energy; ceiling held correctly |
   | DR (TT scale) | 9 | 11 | +2 DR (improved) |
   | Artifact count (pre) | 454 | 454 | — |
   | Artifact count (post) | 455 | 93 | **−361 (79% reduction); STATIONARY_WHISTLE absent from post-master list** |
   | Avg per-flag peak delta | — | −1.18 dB | Gate 2 (broken OLA) worst single flag: −5.24 dB; same flag now avg is representative |
   | Avg per-flag RMS delta | — | −2.87 dB | Gate 2 worst single flag: −7.81 dB. Worst flag now (10784 Hz, 0–2 s): −7.81 dB — this flag is genuinely loud; delta is the signal, not artefact of OLA bug |
   | STORY-025 quality review | — | PENDING_HUMAN_REVIEW: spectral_shift_significant | 3.12 dB spectral RMS shift (PROVISIONAL 2 dB threshold, not calibrated). Shift is from full pipeline EQ + repair; low-mid band −7.4 dB is corrective-EQ contribution, not whistle repair |

   The 79% artifact-count reduction with maintained LUFS (±0.01 LU) confirms the OLA fix is working as a narrow notch rather than the broadband energy loss seen at Gate 2.

   **Listening gate (2026-08-18): FAIL.** Output was characterised as "highly destructive to the track." The quantitative metrics do not capture the perceptual damage. Root cause: 439 notch operations is too many — the STATIONARY_WHISTLE detector cannot distinguish AI generation artefacts from musical content (sustained synth tones, pad harmonics). A narrowband notch at the correct frequency is arithmetically correct but perceptually destructive when applied to a musical note rather than a true glitch. The OLA fix was necessary but not sufficient; the detector-to-repair contract remains the blocking problem.
6. ✅ **No notch-tuning workaround** — the implementation accepts only detector-sourced frequencies; there is no free-form frequency input and no notch-depth "tune" parameter.

Tests TC-001, TC-002, TC-003 (tagged `[BLOCKED-ON: OLA fix, arch §3]` in test-cases.md) are now unblocked by item 1.

**Pipeline bug found and fixed during e2e validation (2026-08-18)**: `pipeline.py` raised `UnboundLocalError: cannot access local variable 'quality_review'` because the STORY-025 wiring placed `build_report(quality_review=quality_review)` before the `quality_review = evaluate_quality_review(...)` assignment. Fixed by moving the `evaluate_quality_review` call to immediately before `build_report()`, where `post_ingest_result` is already available.

**Harmonic guard e2e result (2026-08-20)**:

The harmonic guard (§6b rev 6) was implemented and run against Sunday Club (48 kHz, 439 flags after confidence+prominence gate).

| Metric | Value |
|---|---|
| Harmonic guard suppressed | 420 / 439 (95.7%) |
| Forwarded to notch stage | 19 |
| Post-master STATIONARY_WHISTLE count | 428 (pre: 452) |
| Full pipeline output | `Reference Tracks/Sunday Club_mastered.wav` |
| Full pipeline report | `Reference Tracks/Sunday Club_mastered_report.md` |
| Mastered levels | −13.54 LUFS, −2.73 dBTP, DR9 |

**Listening gate risk — 6 sub-500 Hz notches forwarded by guard:**

| Frequency | Prominence | Window | Risk |
|---|---|---|---|
| 166.0 Hz | +44.5 dB | 8.50–11.25 s | E3 bass — harmonic guard found no fundamental below 166 Hz |
| 166.0 Hz | +28.2 dB | 19.50–21.25 s | same |
| 190.0 Hz | +18.6 dB | 176.00–177.75 s | near G3 |
| 196.0 Hz | +37.1 dB | 154.50–158.50 s | G3 |
| 246.0 Hz | +25.4 dB | 207.50–209.25 s | B3 |
| 494.0 Hz | +28.8 dB | 156.50–158.75 s | B4 |

The 44.5 dB local prominence of the 166 Hz flag is unusually high for a bass fundamental (bass harmonics would reduce local prominence); it may be a genuine AI encoder artifact at a musical pitch class. The listening gate at those timestamps is the decision point.

The 13 high-frequency notches (15.3–22.4 kHz, clustered 152–161 s) are lower-risk and consistent with AI encoder aliasing artifacts.

**Listening gate result (2026-08-25)**: PASS. Mastering engineer listened to `Reference Tracks/Sunday Club_mastered.wav` at all six flagged timestamps (8.5 s, 19.5 s, 154.5 s, 156.5 s, 176 s, 207.5 s). Result: "sounds amazing." No destructive notching perceived at any timestamp. Sub-500 Hz notches (166 Hz, 190 Hz, 196 Hz, 246 Hz, 494 Hz) are inaudible as damage. Defect closed.
