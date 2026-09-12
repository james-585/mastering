# STORY-009 — Mastering-Engineer Review: §6b Harmonic Guard

Reviewed: `stories/STORY-009/architecture.md §6b`, `stories/STORY-009/defects.md`,
`stories/STORY-009/mastering-review-results.md`.
Material context: Sunday Club (club-oriented electronic, dense pad/synth content, 439
STATIONARY_WHISTLE flags, Gate 2 listening result FAIL).

---

## A. Method plausibility — CONCERN

**Finding.** The core idea — check whether the flagged frequency falls near a harmonic of a
spectrally prominent peak below it, and suppress if so — is physically sound as a signal-level
heuristic. A genuine AI encoder whistle is an isolated narrowband artefact with no harmonic
context; a pad harmonic has a strong fundamental below it. The intuition is correct.

**False suppression risk — coincidental alignment.** The guard suppresses a flag when *any*
spectral peak below it has a harmonic within `delta` harmonic-number units of the flag. On
dense club-oriented electronic material, the analysis window (8192 samples, ~186 ms at
44.1 kHz) will contain many spectral peaks from overlapping synth layers, drum machines, and
bass content. Each of these peaks is tested as a candidate fundamental. The guard fires on the
first match; it does not require that the matching candidate be the strongest peak, or that the
flag frequency itself be a prominent spectral peak in the mix, or that harmonic siblings exist
at the flagged frequency.

A genuine AI encoder whistle landing in the 2–10 kHz range on Sunday Club could coincidentally
align with a harmonic of any of the many peaks below it. Whether it does depends on how many
qualifying peaks (K) `find_peaks` returns, not on whether the flag is musically harmonic — see
Section B.1 for the arithmetic.

**False pass-through risk — detuned and inharmonic synthesis.** In supersaw-style pads (very
common in club-oriented electronic production), multiple oscillators are detuned from each
other by several cents to create width and movement. The result in the FFT is not a single peak
at the fundamental but a broadened cluster — energy spread over a few adjacent bins, with each
individual local maximum potentially failing the 6 dB local-prominence gate even though the pad
tone is clearly present and would be perceptually destroyed by a notch. Similarly, FM patches
and physical-model synthesis produce inharmonic spectra (non-integer frequency ratios) that the
integer-harmonic test cannot detect. Both failure modes pass flags through to the notch stage
that should have been suppressed.

The false pass-through risk is second-order to the false suppression risk below, because a
missed suppression means the notch lands on musical content — bad — whereas a false suppression
means a genuine whistle is not repaired — less bad in the short term. However, both are real
concerns that the offline check must probe.

---

## B.1. delta / N_MAX — FAIL

**Finding.** The derivation in §6b is correct for a **single candidate fundamental**, but the
guarantee it establishes breaks down when `find_peaks` returns multiple qualifying peaks (K > 1)
over `log_spec[:flag_bin]` in a dense mix. This is not a calibration question; it is a defect
in the discrimination argument.

**The single-candidate derivation (§6b).** Coverage per harmonic interval is `2·delta = 0.16`.
§6b calls this "84% of each inter-harmonic interval is unprotected" and presents it as the
discrimination bound. This is correct for K = 1.

**What happens at K > 1.** Each qualifying peak is tested independently. The guard fires on the
first match. If the K candidate peaks are approximately independent in frequency, the probability
that *at least one* of them produces a harmonic falling within `delta` of the flag is:

```
P(suppress | K candidates, random flag) ≈ 1 − (1 − 2·delta)^K
                                        = 1 − (0.84)^K
```

| K candidates | P(suppress for a random frequency) |
|---|---|
| 1  | 0.16  (16%) |
| 5  | 0.58  (58%) |
| 10 | 0.83  (83%) |
| 20 | 0.97  (97%) |
| 50 | 0.9998 (≈100%) |

On Sunday Club — club-oriented electronic material with "dense pad/synth content" — the 8192-
point FFT of a 186 ms window in the 0–10 kHz range contains hundreds of bins. Even with a 6 dB
local-prominence gate, `find_peaks` on a complex synth mix will return K well above 10 for most
flags. At K ≥ 20, the guard suppresses nearly any frequency, genuine whistle or not, with ~97%
probability.

**The discrimination table in §6b is invalid as stated.** The entry "Discrimination: 2·delta =
0.16 << 1" is derived for K = 1. Restated for K > 1, the discrimination gap is
`(1 − 2·delta)^K`, which collapses toward zero as K grows. For plausible K on Sunday Club
material, the guard is not discriminating between musical harmonics and isolated tones — it is
suppressing almost everything, including genuine whistles.

**Consequence for the offline check.** §6b.6 item 1 specifies the acceptance criterion as
"meaningfully fewer than 439 suppressions, with at least some genuine whistles (if any)
remaining forwarded." At K ≥ 20, suppressing ~430 of 439 flags is the **predicted outcome
whether the guard discriminates or not** — it will happen by coincidental alignment for a
random frequency just as reliably as for a musical harmonic. Counting suppressions cannot
distinguish "guard works" from "guard fires on everything." The specified acceptance check is
non-diagnostic and must be revised before the offline check is run. See Mandatory action
below.

**delta and N_MAX values themselves.** The individual values (0.08, 10) are not the problem;
the underlying algorithm produces inflation of coverage by K regardless of the specific values
chosen within physically reasonable ranges. Tightening delta would raise the suppression floor
slightly but does not fix the structural issue.

**Mandatory action before implementation:** Revise the guard algorithm or the acceptance test
so that the discriminating power of the guard is separated from coincidental K-inflation.
Two concrete options:

1. **Algorithm revision (preferred): require harmonic-sibling confirmation.** A genuine musical
   harmonic has siblings at `f_flagged ± k·f0` for k = 1, 2, ... A genuine AI encoder whistle
   does not. The guard currently parks this as "candidate future extension" (§6b Open risk, last
   paragraph of the harmonic-ratio-test section). Given that K-inflation makes the current
   algorithm non-discriminating on dense material, the sibling check is not a future extension —
   it is the feature that makes the guard discriminating. Require: before suppressing, confirm
   that at least one spectral sibling of the flagged frequency relative to the matched candidate
   f0 is also prominently present (e.g., `f_flagged + f0` or `f_flagged − f0` clears a
   specified threshold). This breaks coincidental alignment because a random noise peak at f0
   will not produce siblings at the flag's harmonics.

2. **Algorithm revision (alternative): restrict K.** Cap the candidate set to the top-M peaks
   by log-magnitude (not all peaks clearing 6 dB), where M is small enough that coverage
   remains bounded. M = 3 gives `P ≈ 1 − 0.84^3 ≈ 0.41` — still higher than desired, but
   bounded. This is a weaker fix because it requires calibrating M and still degrades on very
   dense material, but it is significantly better than unbounded K.

**Revised acceptance test (required regardless of algorithm revision):** Run the guard offline
over the 439 Sunday Club flags and also over 439 randomly selected frequencies in the same 2–12
kHz range from the same audio. Report both suppression counts. If the suppression rate on
random frequencies is within 20 percentage points of the suppression rate on real flags, the
guard has no meaningful discriminating power and the algorithm must be revised before
implementation. A truly discriminating guard will suppress substantially more musical flags than
random frequencies.

Additionally: report the distribution of K (number of peaks clearing 6 dB local prominence)
per flag in the 439-flag set. If the median K exceeds 10, the K-inflation problem applies at
scale and must be addressed in the algorithm.

---

## B.2. Strength threshold (6 dB) — CONCERN

**Finding.** The 6 dB local-prominence threshold for candidate fundamentals is reused from the
STORY-007 detector's own emission floor. The reuse is noted as an anchoring choice ("reasonable
anchor") rather than an independent derivation.

The primary concern is not whether 6 dB is too low or too high in isolation. It is that the
threshold is the lever that controls K. Raising the threshold (e.g., to 10 or 12 dB) reduces
the number of qualifying candidate peaks and therefore reduces K-inflation. However, raising
the threshold without first fixing the K-inflation defect in B.1 does not fix the discriminating-
power problem — it only moves the K-inflation collapse to a less dense mix. On Sunday Club
material, even a 12 dB local-prominence gate will likely return K > 10 for most flags in the
2–10 kHz range where pad harmonics and synth layers are dense.

**What 6 dB means in practice.** On a 44.1 kHz / 8192-point FFT of a club-track segment, a
6 dB local prominence gate typically passes dozens of peaks in the 0–10 kHz range. The
threshold is not wrong in principle for detecting musical fundamentals — a pad's fundamental
that is musically present will generally clear this — but it is too permissive as a control on
K in a dense mix context.

**The threshold cannot be calibrated independently of the K problem.** Until the K-inflation
defect in B.1 is addressed by algorithm revision (harmonic siblings or K cap), raising the
threshold is a patch that partially mitigates rather than resolves the structural issue. Once
B.1 is addressed, an appropriate threshold for the revised algorithm should be re-evaluated from
the offline acceptance test distribution.

**Required action:** Defer setting the final threshold value until the B.1 algorithm revision
is designed. If K capping is chosen as the B.1 fix, the threshold and cap interact and must be
tuned together.

---

## B.3. f_min_flag = 2000 Hz assumption — PASS

**Finding.** The assumption that AI encoder whistles from Suno appear predominantly above 2 kHz
is consistent with what I know about neural audio codec reconstruction artefacts. Encoders
of the SoundStream/EnCodec class operate on compressed latent representations; reconstruction
errors (quantisation noise, aliasing of the learned filterbank, phase discontinuities from
vector quantisation) tend to manifest as high-frequency narrowband instabilities rather than
as bass-range tones. Low-frequency artefacts are better controlled in current neural codecs
because the perceptual cost of errors there is much higher and the encoder's residual coding
gives more capacity to low-frequency content. 2 kHz as the practical floor for Suno whistle
flags is defensible.

**Recommended verification before relying on the assumption.** The 439-flag Sunday Club run
already produced `repair_whistles_actions` with `frequency_hz` per flag in the mastered report
JSON. The flag frequency distribution can be checked directly from that data. If a material
fraction of flags (say, > 10%) are below 2 kHz, the l_analysis derived from f_min_flag = 2000
Hz is too small for those flags and the architecture derivation must be revisited. This
verification costs nothing to run.

**l_analysis itself.** The derivation (bin width ≤ delta·f0_min/2, yielding 8192 at 44.1 kHz)
is arithmetically correct given the assumption. If the assumption holds, the FFT length is
adequate.

---

## B.4. Offline check expectation — does not meet the diagnostic bar

**Finding.** Given the K-inflation analysis in B.1, suppressing meaningfully fewer than 439
flags is almost certainly what will happen with the current algorithm on Sunday Club material —
not because the guard discriminates, but because any dense audio segment has enough qualifying
peaks to produce coincidental harmonic alignment for nearly every flag. A suppression count of
380–430 is consistent with *both* "the guard is working" and "the guard is firing on
everything."

**What the offline check will likely show, under the current algorithm.** The flag frequency
distribution of the 439 flags from the STORY-007 detector sits predominantly in the 2–12 kHz
range (given the f_min_flag assumption above). For each flag, the guard examines all spectral
peaks below the flag in an 8192-point FFT of a 186 ms window. Sunday Club's dense pad and
synth content will produce K ≥ 15–30 qualifying peaks for most flags. At K = 20 the per-flag
suppression probability for a random frequency is approximately 97%. The suppression count will
approach 439 regardless of whether the flags are on musical harmonics or genuine AI whistles.

**Conclusion.** The offline check as currently specified in §6b.6 item 1 will not produce a
meaningful result. The guard appears to work because the count is "meaningfully fewer than 439"
(it might be 430 rather than 439) while actually having near-zero discriminating power. This
must be resolved via the revised acceptance test specified in B.1 (suppress-rate comparison
against random frequencies plus K distribution report) before implementation begins.

---

## C. Additional concerns — CONCERN

**1. Test (c) does not catch K-inflation failure.**
§6b test (c) uses a single strong competing peak (500 Hz) alongside the flag at 4327 Hz. The
test correctly probes delta-degeneracy with K = 1. It will pass even when the guard has
zero discriminating power on real material, because real material has K ≫ 1. Test (c) as
specified is a necessary but not sufficient correctness check for the guard. The revised
acceptance test from B.1 (null-control suppression-rate comparison) cannot be replaced by (c).

**2. Analysis window extension — appropriate, but note for implementation.**
Extending the analysis window beyond the flag's time window to capture more musical context is
correct in principle. A sustained pad will be present in the surrounding audio and will
contribute to the FFT. One note for the implementation: if the flag is very short (near the
minimum flag duration from STORY-007) and the surrounding audio contains a brief chord change —
content that is harmonically different from the actual flagged moment — the extended window may
classify a flag as "musical" based on chords that are not actually coincident with the whistle.
This is a minor edge case in club material where pads typically sustain, but it is worth
flagging for the test-case writer.

**3. The harmonic sibling check is not optional at K > 1.**
§6b designates the sibling check ("energy at f_flagged ± k·f0 for k = 1, 2, ...") as a future
extension and notes it is "out of scope for this revision." Given the K-inflation finding in
B.1, this characterisation must be revisited. The sibling check is the signal property that
actually separates an isolated tone (no siblings) from a pad harmonic (siblings at f0 spacing).
Implementing the guard without it produces a high-recall/low-precision suppressor that does not
add information over simply suppressing all flags. The K-inflation defect in B.1 is partially
the same finding approached from a different angle; this is noted to make the architectural
implication explicit.

**4. FFT approach and magnitude combination — PASS.**
The FFT-based spectral peak approach is appropriate for detecting stationary tonal content in a
sustained segment. The channel-max combination (element-wise max across channels in the
magnitude domain) is correct; time-domain channel mean can null anti-correlated tones.
Log-magnitude with programme-level-relative floor (−120 dBFS re segment peak) is a sound
choice that avoids absolute-floor artefacts.

**5. N_MAX = 10 and sub-bass fundamentals.**
The architecture itself notes this open risk: a pad harmonic at a harmonic number > 10 of a
bass fundamental will not be suppressed. For club material with strong sub-bass fundamentals at
50–80 Hz, the 10th harmonic is only 500–800 Hz, well below the 2–10 kHz range where most flags
are expected. This means a flag at, say, 6400 Hz (the 80th harmonic of an 80 Hz bass) will
pass through to the notch stage. However, for flags in the expected range (above 2 kHz), the
relevant "fundamentals" the guard should detect are mid-range pad tones (200–500 Hz) whose 4th
through 10th harmonics are in the 800–5000 Hz range. N_MAX = 10 is adequate for this sub-range
but not for sub-bass-rooted harmonics. This is a known gap, not a new finding, and is less
urgent than the K-inflation defect.

---

## Summary verdict

**Requires architecture revision.**

The §6b harmonic guard method is physically motivated and the algorithm's individual components
(FFT-based peak finding, harmonic-number-unit tolerance, magnitude-domain channel combination)
are all sound in isolation. However, the discrimination argument in §6b — specifically the claim
that `2·delta = 0.16 << 1` establishes discriminating power — is derived for a single candidate
fundamental and is invalid when `find_peaks` returns K > 1 qualifying peaks over the analysis
window. On Sunday Club material with dense pad and synth content, K is expected to be well
above 10 for most flags, making the per-flag suppression probability for *any* frequency
(musical or non-musical) approach 97–100%. The guard cannot distinguish musical harmonics from
isolated tones under those conditions.

The consequence for the offline acceptance check specified in §6b.6 is that a suppression count
close to 439 is the predicted outcome regardless of whether the guard discriminates — the check
is non-diagnostic as specified.

**One architectural revision is required before implementation may proceed:**

The guard must incorporate a feature that discriminates at K > 1. The harmonic-sibling
confirmation (confirming that energy also exists at `f_flagged ± f0`, i.e., that the flagged
frequency is flanked by spectral neighbours consistent with a harmonic series) is the
recommended revision. It is not a future extension; it is the property that makes the guard
discriminating when multiple candidate peaks are present. An alternative (K capping) is
weaker but may suffice if the cap is small enough.

**The offline acceptance check must be revised** to include a null control: run the guard
against randomly generated frequencies in the same 2–12 kHz range on the same audio and report
the suppression rate alongside the real-flag suppression rate. The null control is the test that
distinguishes "guard works" from "guard fires on everything."

**Items that do not block after the B.1 revision:**
- B.3 (f_min_flag): PASS — assumption is domain-appropriate; verify against existing flag
  frequency distribution from the mastered report JSON.
- C.4 (FFT/channel-combination approach): PASS.
- B.2 (6 dB threshold): CONCERN but co-dependent on B.1 revision — cannot be calibrated
  independently; re-evaluate after algorithm revision.
- N_MAX = 10 sub-bass gap: acknowledged known limitation, not a blocker.
