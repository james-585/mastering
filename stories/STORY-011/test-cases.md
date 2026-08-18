# STORY-011 — Test Cases

## TC-0111 drum transient restoration
- Input: a drum stem containing a slow, smeared attack with reduced onset energy.
- Expected: the stage detects a transient deficit, applies a local gain to the onset region, and records a drum-specific action in the report.
- Pass condition: the restored stem shows higher onset energy than the original, while the overall peak remains below the safe limit.
- Note (2026-08-17): "below the safe limit" now means: no ValueError for legal (≤ 1.0 peak) input, and measured post-gain onset-window peak ≤ 0.98 sample peak. Still valid.

## TC-0112 bass transient restoration
- Input: a bass stem with soft contour and weak low-end attack.
- Expected: the stage boosts transient punch only in the onset region and does not generate pumping across the full bass line.
- Pass condition: the attack energy rises and the gain is recorded under the bass reason code without exceeding ±1.0.
- Note (2026-08-17): still valid; the ±1.0 condition is now guaranteed by construction via the headroom clamp plus the retained output clip guard.

## TC-0113 vocal articulation recovery
- Input: a vocal stem with dull consonants and understated articulation.
- Expected: the stage increases local attack energy but avoids broad brightening or sibilance bias.
- Pass condition: the output is slightly more articulate than the input and the report names the vocal stem and reason.
- Note (2026-08-17): still valid.

## TC-0114 synth no-op on already-good input
- Input: a synth stem with natural attack and controlled spectral shape.
- Expected: no restoration is applied.
- Pass condition: the output remains effectively identical to the input and the action list is empty for that stem.
- Note (2026-08-17): still valid. See also TC-0123, which extends this to a hot (peak 0.99) healthy stem.

## TC-0115 clipping guard — INVALIDATED (2026-08-17)
- Status: **INVALIDATED — encodes the rejected DEF-011-01 method. Do not re-automate as written.**
- The original test asserted a ValueError for an input stem peaking at 0.99 (a legal, sub-full-scale value). The 2026-08-17 architecture revision replaces the pre-gain input-peak abort with the deterministic onset-window headroom clamp; a peak in (0.98, 1.0] must never raise.
- The corresponding automation test `test_tc0115_clipping_guard` in `stories/STORY-011/automation/test_story011_transient.py` (line 82) is stale and must be **replaced** (not parameter-tuned) by QA with the semantics of TC-0121 (hot stem with deficit → skipped_headroom, no raise), TC-0122 (raise only when input peak > 1.0, with boundary coverage), and TC-0123 (hot healthy stem → unchanged, no action).
- Kept here for traceability; the ID is retired.

## TC-0116 report visibility
- Input: one or more restored stems.
- Expected: the returned action list includes the stem name, action type, gain in dB, and reason.
- Pass condition: the report entries are explicit and human-readable, with no missing reason text.
- Amended (2026-08-17): the action record contract now additionally requires `requested_gain_db`, `onset_peak_before`, `onset_peak_after`, and `global_peak_before` on every emitted action, and `action_type` must be one of `attack_boost`, `attack_boost_headroom_clamped`, `skipped_headroom`. Clamped and skipped reasons must follow the architecture's reason-string conventions verbatim (requested vs applied dB for clamped; onset-window peak and "returned unchanged" for skipped). No reason string may describe a clamped stem as "true-peak safe" (gate-1 F1 — 0.98 is a sample-peak ceiling, true-peak ownership stays with stage 8).

## TC-0117 local-window gating
- Input: a quiet or near-silent stem with very low amplitude.
- Expected: the stage does not interpret low level as a transient defect.
- Pass condition: the restoration score remains below threshold and the output is unchanged.
- Note (2026-08-17): still valid; also guards the divide-by-near-zero risk of a ratio-based attack metric on near-silent baselines.

---

# DEF-011-01 / DEF-011-02 rework test cases (added 2026-08-17)

## Shared fixture conventions for TC-0118 – TC-0125

- Sample rate fs = 44100 unless stated; length 22050 samples (0.5 s), mono float64.
- Derived window constants (from the architecture's verbatim formulas):
  - W = min(n_samples, max(32, int(0.08·fs))) = min(22050, 3528) = **3528**
  - T = min(W, max(16, int(0.005·fs))) = min(3528, 220) = **220**
- **Smeared-onset fixture with peak known by construction:**
  `x[n] = p · r[n] · cos(2π·441·n/44100)` for 0 ≤ n < W, where
  `r[n] = min(1.0, 0.05 + 0.95·n/3000)`; for n ≥ W, continue the tone at
  amplitude 0.2 (below p).
  - The 441 Hz cosine has period exactly 100 samples; |cos| = 1 at n ≡ 0, 50 (mod 100).
  - r reaches 1.0 at n = 3000, and 3000 ≡ 0 (mod 100), so x[3000] = p exactly; no
    other sample reaches p. Therefore **max|x[:W]| = p and the global peak = p,
    exactly, by construction** (not measured from tool output).
  - The 0.05 → 1.0 ramp over 3000 samples (~68 ms) is a smeared attack of the same
    character as the TC-0111 fixtures, i.e. a genuine onset deficit.
  - x[0] = 0.05·p ≠ 0, which permits envelope ratio checks at sample 0 (TC-0119).
- **Healthy sharp-attack fixture:** same tone at full amplitude from n = 0
  (r ≡ 1), peak p by the same construction. No onset deficit.
- **Open question (carried from requirements.md, not invented here):** the numeric
  severity mapping from attack evidence to requested gain g_req is not specified
  ("The story does not prescribe a fixed dB gain or attack threshold"). Clamp
  tests therefore assert against the action record's `requested_gain_db` rather
  than a hardcoded g_req. QA must confirm each deficit fixture elicits the
  request level stated in the preconditions; if no such fixture exists, that is a
  requirements/architecture gap to raise — do not tune the test to fit.

## TC-0118 ground-truth headroom clamp (H2)
- Type: functional / audio-quality. Covers: clamp algorithm steps 4–7; AC7 (revised semantics).
- Preconditions: smeared-onset fixture with p = 0.90, fs = 44100. Derived
  headroom: `20·log10(0.98/0.90) = 0.7397 dB`; the clamped linear gain is exactly
  `0.98/0.90 = 1.088889`. Precondition check: the fixture must elicit
  `requested_gain_db > 0.7397 dB` (otherwise the clamp cannot be exercised — see
  the shared open question).
- Steps: run `apply_stem_transient_restoration({"drums": x}, 44100)`.
- Expected:
  - No exception; exactly one action for the stem.
  - `action_type == "attack_boost_headroom_clamped"`.
  - `gain_db == 20·log10(0.98/0.90)` within ±0.0001 dB (pure float64 computation).
  - `requested_gain_db > gain_db` and equals the severity-mapping output.
  - `onset_peak_before == 0.90` and `global_peak_before == 0.90` (±1e-12).
  - Measured `onset_peak_after ≤ 0.90 · 10^(gain_db/20) ≤ 0.98` (+1e-12 float
    tolerance). This is **bound semantics** under the Hann-tapered envelope
    (gate-1 F2): typically strictly below 0.98, never above.
  - Output samples n ≥ 3528 bit-identical to the input.
  - Output sample peak ≤ 0.98 (+1e-12); no inter-sample/true-peak claim is made
    or asserted here (sample-peak ceiling only; true peak belongs to stage 8).
  - `reason` follows the clamped convention, stating both requested and applied
    gain and the 0.98 ceiling; it must NOT contain any "true-peak safe" wording.

## TC-0119 gain-envelope shape (Hann fade-out)
- Type: functional / audio-quality / regression (guards the removal of the
  rectangular window, gate-1 F2).
- Preconditions: any fixture receiving a positive applied gain — reuse the
  TC-0120 negative-control fixture (p = 0.40, unclamped gain known from
  `requested_gain_db`). Run at fs = 44100 (W = 3528, T = 220) **and** fs = 48000
  (W = 3840, T = 240) to verify the W/T integer math at both mandated rates.
- Steps: run the stage; compute the observed envelope `E[n] = out[n]/in[n]` for
  all n in [0, W) with |in[n]| ≥ 1e-6 (skip exact cosine zero crossings).
- Expected (g_lin = 10^(gain_db/20)):
  - `E[0] == g_lin` (rtol 1e-12) — full gain from sample 0; no leading taper.
  - `E[n] == g_lin` for 0 ≤ n < W − T (flat region).
  - Fade region, k = 0..T−1 at n = W − T + k: E matches the closed form
    `1 + (g_lin − 1) · 0.5 · (1 + cos(πk/(T − 1)))` within 1e-12, and the
    observed E sequence is **monotonic non-increasing** across the fade.
  - `E[W−1] == 1.0` exactly (observed ratio within 1 ulp of 1.0) — no
    discontinuity at the window edge.
  - `out[n] == in[n]` bit-exact for all n ≥ W (no modification at or beyond W).
  - The same shape results from a clamped run (TC-0118 fixture): the envelope is
    a pure function of (W, T, g_applied).
  - Short-file variant: repeat with n_samples = 64 (W = 64, T = 64 — fade spans
    the whole window); E[W−1] == 1.0 and the n ≥ W condition is vacuous. This
    covers the "shorter than the analysis window" edge case. Files shorter than
    ~32 samples are degenerate input and out of scope.

## TC-0120 clamp negative control (H3)
- Type: functional / regression (false-positive guard).
- Preconditions: smeared-onset fixture with p = 0.40 (onset-window peak well
  below 0.98). Derived headroom: `20·log10(0.98/0.40) = 7.7833 dB`, far above any
  plausible requested gain, so a modest deficit request satisfies
  g_req < headroom.
- Steps: run the stage on the fixture.
- Expected:
  - `action_type == "attack_boost"`; the clamp must not fire spuriously.
  - `gain_db == requested_gain_db` with exact float equality (same computed value).
  - Measured `onset_peak_after ≤ 0.40 · 10^(gain_db/20)`.
  - `reason` contains no clamp or skip language; samples n ≥ W unchanged.

## TC-0121 DEF-011-01 reproduction: hot stem skipped, not aborted
- Type: regression / functional.
- Preconditions: smeared-onset fixture with **p = 0.9831** — the exact Twilight
  Caverns value from DEF-011-01 — with the constructed peak (n = 3000) inside the
  onset window, so onset peak = global peak = 0.9831. Analytic headroom:
  `20·log10(0.98/0.9831) = −0.0274 dB < 0`, so the clamp yields ≤ 0 dB for any
  positive request and the skip branch is the analytically forced outcome.
- Steps: run the stage on the fixture. Must NOT raise.
- Expected:
  - No ValueError.
  - Returned stem bit-identical to the input array (unchanged, not a modified copy).
  - Exactly one action: `action_type == "skipped_headroom"`, `gain_db == 0.0`,
    `requested_gain_db > 0` (records what would have been applied).
  - `onset_peak_before == global_peak_before == 0.9831` (±1e-12).
  - `reason` states the onset-window peak (0.9831) and that the stem was returned
    unchanged, per the skip reason-string convention; no "true-peak safe" wording.

## TC-0122 input legality guard and 0.98 boundary
- Type: functional / edge case / boundary.
- Steps and expected:
  1. Stem with a single sample at +1.05 → **ValueError** whose message names the
     stem key and the measured peak (1.05).
  2. Boundary: stem peaking at exactly 1.0 (constructed cosine peak) with an
     onset deficit → must NOT raise; headroom `20·log10(0.98/1.0) = −0.1754 dB
     < 0` → `skipped_headroom`, stem unchanged.
  3. Just under the ceiling: p = 0.979 with a deficit → headroom
     `20·log10(0.98/0.979) = +0.0089 dB`; if g_req exceeds this,
     `attack_boost_headroom_clamped` with `gain_db ≈ 0.0089 dB`.
  4. Just over the ceiling: p = 0.981 with a deficit → headroom −0.0088 dB →
     `skipped_headroom`, no raise.
  - (Never a raise for any input peak in (0.98, 1.0].)

## TC-0123 hot-but-legal healthy stem: removed abort stays removed
- Type: regression / functional.
- Preconditions: healthy sharp-attack fixture (no onset deficit) with global peak
  0.99 ∈ (0.98, 1.0].
- Steps: run the stage. Expected: no ValueError; stem returned bit-identical;
  **no action emitted** for the stem (g_req ≤ 0 → unchanged no-op, no record).
- Purpose: direct replacement for the invalidated TC-0115 semantics — a 0.99-peak
  stem is legal programme material; silence in the report means clean no-op.

## TC-0124 determinism
- Type: non-functional / regression.
- Preconditions: mixed stem dict — {"drums": TC-0118 clamp fixture, "bass":
  TC-0121 skip fixture, "vocals": healthy sharp-attack fixture at 0.5 peak}.
- Steps: run the stage twice over the same dict object content.
- Expected: output arrays bit-identical across runs; action lists identical on
  **all** fields (`stem_name`, `action_type`, `gain_db`, `requested_gain_db`,
  `onset_peak_before`, `onset_peak_after`, `global_peak_before`, `reason`,
  `severity`), with exact float equality and identical ordering.

## TC-0125 six-stem (htdemucs_6s) compatibility
- Type: functional / compatibility (STORY-022 path).
- Preconditions: six-stem dict {"drums", "bass", "vocals", "other", "piano",
  "guitar"}: "guitar" = TC-0118 clamp fixture (p = 0.90), "piano" = TC-0121 skip
  fixture (p = 0.9831), remaining stems healthy.
- Expected:
  - No raise. "piano" → `skipped_headroom`, `gain_db == 0.0`, stem unchanged
    (unknown names use the default severity threshold; headroom handling is
    name-agnostic).
  - "guitar" → `attack_boost_headroom_clamped` with
    `gain_db == min(requested_gain_db, 0.7397 dB)`.
  - Healthy stems unchanged with no actions.
  - For **every** emitted action regardless of stem name:
    `gain_db == min(requested_gain_db, 20·log10(0.98/onset_peak_before))` within
    ±0.0001 dB. Note: `requested_gain_db` itself may legitimately differ from a
    same-shaped "drums" fixture because severity thresholds are name-specific —
    this test pins the clamp identity, not the request level.

## TC-0126 stereo known-attack-ratio fixture (DEF-011-02 regression guard)
- Type: functional / regression (mandatory per architecture F6; mono-only
  fixtures cannot catch the Hilbert-axis bug).
- Fixture (fs = 48000, N = 24000 samples, 0.5 s): both channels are 480 Hz sines
  (period exactly 100 samples, integer cycles), same phase.
  - Left: amplitude 0.60 for 0 ≤ n < 3840 (the full onset window W at 48 kHz),
    amplitude 0.10 thereafter.
  - Right: amplitude 0.30 constant throughout.
- Analytic ground truth (derivation): with the correct axis the per-sample
  cross-channel max envelope is 0.60 during the onset and 0.30 outside it, so
  the **true attack ratio R_true = 0.60/0.30 = 2.0**.
- Expected (pure metric path, `_local_attack_ratio` / envelope function):
  measured attack ratio ∈ [1.8, 2.2] (true value 2.0; the tolerance absorbs
  Hilbert edge effects near the amplitude step at n = 3840 and the file
  boundaries).
- Expected (apply path): a ratio of 2.0 is a strong, healthy attack → no boost,
  output bit-identical, no action. (If the metric's convention reports deficit
  rather than strength, QA inverts the sign of the expectation; the derivable
  quantity is the 2:1 onset:baseline envelope ratio either way.)
- Discrimination proof (why this fails on the unfixed code): with `hilbert` on
  the default axis=−1, each 2-point cross-channel transform is the identity (the
  N=2 Hilbert multiplier is [1, 1]), so the "envelope" becomes the rectified
  waveform max(|L|,|R|), oscillating to zero twice per period. Any baseline
  statistic is corrupted: median → (√2/2)·0.30 ≈ 0.21213, mean → (2/π)·0.30 ≈
  0.19099, while the onset peak still reaches 0.60 (the sample grid hits the sine
  peak exactly). Broken-axis ratio ≈ 2.83 (median baseline) or ≈ 3.14 (mean
  baseline) — well outside [1.8, 2.2].
- Refinement variant (if QA observes file-boundary contamination): make the
  fixture wrap-continuous — Left at 0.10 except 0.60 for 6000 ≤ n < 9800 (both
  steps at integer-period zero crossings; N = 240 whole periods) — with tolerance
  tightened to [1.9, 2.1], provided the metric analyzes the full file rather than
  only the first 80 ms window. If the metric is window-restricted, keep the
  primary fixture.

## TC-0127 Non-integer-cycle steady tone: no spurious transient boost (DEF-011-03 regression guard)
- Type: functional / regression (mandatory — written to FAIL on the unfixed code, PASS after the fix)
- Fixture: constant-amplitude sine, amplitude 0.5, at **441 Hz**, duration 0.5 s, sample rate 44100 Hz
  (= 220.5 cycles — non-integer, so the FFT wrap discontinuity between last and first sample is large).
- Expected (`_local_attack_ratio` on this fixture): ratio ∈ **[0.9, 1.3]**
  (true value 1.0 — the envelope is flat; tolerance absorbs residual ringing).
- Control: identical fixture at **440 Hz** (= 220 cycles exactly — integer, so the wrap artefact is absent).
  Expected ratio ∈ **[0.95, 1.05]**.
- Failure mode before fix: 441 Hz fixture returned **2.419** (Hilbert wrap spike at n=0 drove
  `np.max(onset)` to 2.395, inflating the ratio by >2×). Confirmed by
  `stories/STORY-011/automation/_repro_def011_03.py`.
- After fix: 441 Hz returns **1.026**, 440 Hz returns **1.000** (verified 2026-08-18).
- The apply path must also be checked: a ratio ≈ 1.0 must not trigger a boost — no action emitted,
  output array identical to input.
- **Do NOT change TC-0114 or TC-0123** to non-integer-cycle construction — those fixtures are
  intentionally kept on integer cycles so they do not mask this defect. The integer-cycle property
  must be documented in their test file comments.

## Global sanity assertions (apply to every boost-producing test above)
- `gain_db ≤ requested_gain_db` always; equality iff `action_type == "attack_boost"`.
- `onset_peak_after ≤ 0.98 + 1e-12` whenever `gain_db > 0`.
- `onset_peak_before`, `onset_peak_after`, `global_peak_before` ∈ [0, 1.0] for legal input.
- Output arrays preserve input shape, dtype (float64), and sample rate.
- Units discipline: all gain expectations are dB; all peak expectations are
  linear **sample peak** (not dBFS, not dBTP). No test in this story asserts on
  true peak — stage 8 owns the −1.0 dBTP ceiling with oversampled metering.

## Coverage notes (mandatory checklist disposition)
- Happy paths: TC-0111–0113 (existing), TC-0118/TC-0120 (clamped and full-gain paths).
- Boundary values: TC-0122 (peak > 1.0 / exactly 1.0 / just under / just over 0.98).
- Idempotency: no explicit requirement exists in requirements.md — open question.
  If adopted, a second-pass test should assert no ValueError, no larger boost,
  and output peak still ≤ 0.98.
- Bypass/disabled: the stage is default-off orchestration-wise and has no bypass
  flag; no-op semantics are covered by TC-0114, TC-0117, TC-0123.
- Mono: TC-0118–TC-0122. Stereo: TC-0126. Sample rates: 44100 and 48000 (TC-0119
  runs both).
- Silence/near-silence: TC-0117. The `p_onset == 0 → headroom = +inf` branch is
  unreachable via the public path (the g_req ≤ 0 no-op precedes the headroom
  computation, and deficit detection requires onset energy); QA may unit-test
  `_headroom_clamp` directly if coverage tooling requires it.
- Full-scale/clipping input: TC-0122. Very quiet input: TC-0117 (ratio-based
  metric must not blow up on near-zero baseline).
- Very short file: TC-0119 short-file variant (64 samples).
- DC offset: no acceptance criterion covers DC handling for this stage; not
  specified here — add only if QA observes a defect.
- Failure modes (corrupt/truncated/unsupported/missing files): ingest-stage
  concerns; this stage consumes decoded float64 arrays. Wrong channel count
  (> 2): behavior is unspecified in the architecture — flagged as an open
  question rather than assigned an invented expectation.
- True peak: not asserted here by design (see units discipline above).

## Traceability table

| Acceptance criterion / contract | Test cases |
|---|---|
| AC1 drum attack restoration | TC-0111 |
| AC2 bass punch without pumping | TC-0112 |
| AC3 vocal articulation | TC-0113 |
| AC4/AC5 no-op on good/healthy input | TC-0114, TC-0117, TC-0123 |
| AC6 report visibility | TC-0116, TC-0124, TC-0125 |
| AC7 full-scale safety (revised: clamp-then-report; raise only > 1.0) | TC-0118, TC-0120, TC-0121, TC-0122, TC-0123 (TC-0115 retired) |
| Headroom-management contract (clamp algorithm) | TC-0118, TC-0120, TC-0121, TC-0122, TC-0125 |
| Gain-envelope specification (Hann fade-out) | TC-0119 |
| Action-record contract (new fields, reason strings) | TC-0116, TC-0118, TC-0121, TC-0124 |
| Determinism / stem-count agnosticism | TC-0124, TC-0125 |
| DEF-011-02 Hilbert-axis fix | TC-0126 |
| DEF-011-03 Hilbert wrap-boundary spike | TC-0127 |

## Revision history
- 2026-08-17: DEF-011-01 / DEF-011-02 rework coverage. Added TC-0118–TC-0126 per
  the 2026-08-17 architecture revision (headroom-management contract, Hann
  fade-out gain envelope, action-record contract, bundled Hilbert-axis fix).
  Invalidated TC-0115 (asserted ValueError on a legal 0.99-peak input — encodes
  the rejected pre-gain abort method; replaced by TC-0121/TC-0122/TC-0123
  semantics; the stale automation test `test_tc0115_clipping_guard` must be
  replaced, not tuned). Amended TC-0116 for the new action-record fields and
  reason-string conventions. Ground-truth clamp expected values are derived
  analytically from fixture construction (peak p exact by cosine/period
  alignment; headroom = 20·log10(0.98/p)); the post-gain onset-peak assertion is
  stated as a bound per gate-1 F2. Added the mandatory stereo
  known-attack-ratio fixture (TC-0126) so the Hilbert-axis fix cannot regress
  silently. Coverage gap closed: previously no test would have caught the
  whole-run abort on hot-but-legal stems (DEF-011-01) or the meaningless
  cross-channel Hilbert transform on stereo stems (DEF-011-02).
- 2026-08-18: DEF-011-03 coverage. Added TC-0127 (non-integer-cycle steady-tone
  regression guard for the Hilbert wrap-boundary spike). TC-0114 and TC-0123 note
  added: must remain on integer-cycle construction to avoid masking this defect.
