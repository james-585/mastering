# STORY-009 — Mastering-Engineer Gate 1 Review (Methods)

Reviewed against `.claude/docs/CLAUDE.md`, `.claude/docs/DOMAIN.md`, `Story.md`,
`requirements.md`, and `architecture.md`. One targeted read of
`src_cpp/spectral_repair.cpp` lines 298-320 to verify the envelope-follower
rectification method referenced in Blocker 3's required test.

---

## Blocker 1 — `repair_whistles` OLA gain-modulation bug — **PASS (confirmed, blocking as stated)**

Independently re-derived: for 50%-hop Hann analysis+synthesis, window pair
`a = 0.5−0.5cosθ`, `b = 0.5+0.5cosθ` satisfies `a+b=1` (correct COLA
property), but the actual reconstruction numerator carries
`a²+b² = 0.5+0.5cos²θ` against a divisor of `1.0`. This ranges 0.5–1.0
(−6 dB to 0 dB), cycling once per hop → `sample_rate/hop_size ≈ 21.53 Hz` at
44.1 kHz/2048. Standard COLA-violation behaviour for a double-windowed STFT
with a mismatched normalisation divisor — the physics is sound. The
proposed one-line fix (`overlap_weights[...] += hann[i]*hann[i]`) is
correct: it makes numerator and divisor carry the same weighting,
cancelling exactly, and also fixes the edge-frame fade. Confirmed: this
must gate default-on, as architecture states.

**Correction to numbers already in architecture.md §3, not the
conclusion**: the "−1.25 dB average RMS deviation" claim is wrong — RMS
through `g(θ)=0.75+0.25cos2θ` is `sqrt(mean(g²)) = sqrt(0.59375) ≈ −2.26 dB`,
not −1.25, and the "only one channel's worth of modulation survives"
framing is not a coherent derivation. Separately, the §2 tolerance of 1e-6
absolute would fail by roughly five orders of magnitude against a −6 dB
swing — no real level test would pass this by accident. The conclusion (a
scalar level test cannot distinguish static trim from modulation, use
FFT-of-diff-envelope) is correct and should stand; the arithmetic
supporting it must be fixed before it propagates into a defect or test
spec (per CLAUDE.md's known-wrong-pattern list on numbers surviving
uncorrected into reports).

## Blocker 2 — `repair_whistles` confidence threshold reuse (0.8) — **FAIL as proposed; do not raise the threshold**

Reusing 0.8 without re-deriving is fine in principle, but raising it (e.g.
to 0.9) repeats the CLAUDE.md §5 trap — "fixing a wrong method by tuning
its parameter." `confidence_score` was calibrated for "surface a warning
line," not "commit an audio edit." Raising a number calibrated for the
wrong purpose doesn't calibrate it for the right one.

Physically: at Q≈120, a false-positive notch removes ~54 Hz at 6.4 kHz,
against a semitone width of ~380 Hz at that frequency — real but small
harm. The actual gap is that confidence alone doesn't tell you the tone is
prominent enough to matter. `ArtifactFlag.details` already carries
`prominence_db`.

**Recommendation**: co-gate on prominence (require both
`confidence_score ≥ 0.8` AND `prominence_db` above a stated floor) rather
than moving the single threshold. Method addition, not a retune.

## Blockers 3/4 — `shape_transients` gain-law saturation and time constants — **FAIL for default-on; candidate fix necessary but not sufficient**

The saturation analysis and candidate fix (`diff/(slow_env+eps)`) are
correctly identified as a method change. But the fix doesn't reach root
cause. Confirmed from source (line 306-309): both envelope followers are
driven by `std::abs(current_sample)` — full-wave rectification. A sine at
fundamental `f` rectified has no energy at `f`; its lowest AC component is
at `2f`. On a 55 Hz sustained bass note, `fast_env`'s ripple sits at
110 Hz, well inside the fast follower's 79.6 Hz corner (attenuated only
~4.6 dB), while the slow follower's 3.2 Hz corner kills it (~−31 dB). The
result: `diff = fast_env − slow_env` genuinely oscillates at 2× the bass
fundamental regardless of the gain law used to convert it to a multiplier.

**The architecture's own required test (§7, "periodic gain flutter at the
input's fundamental") targets the wrong frequency — it should test for
ripple at 2f and its harmonics, not f. As currently specified, that test
could pass a broken stage.**

The named candidate fix is necessary (removes needless saturation) but not
sufficient — the standard mastering-engineering fix for this class of
problem is a highpassed detector sidechain (so the fast follower doesn't
respond to sub/bass fundamentals at all) or multiband operation, not a
different gain-law shape on the same broadband detector. For this
project's genre context (club-oriented electronic material with strong
sub/kick content), this is close to the median input, not an edge case.

On constants: 50 ms for the "sustain" path is short. At 120 BPM, a 16th
note is 125 ms; conventional mastering-grade transient designers use
100–500 ms for the slow/average path specifically so the discriminator
doesn't fire on the body of a percussive hit, only its leading edge. 50 ms
risks classifying the sustained portion of a kick or clap as "attack"
repeatedly through its decay. Reinforces Blocker 4 — corners are
algebraically derived but not musically justified; the slow constant looks
too fast for mastering-stage (vs. tracking/mixing-stage) use.

## Blocker 5 — `collapse_swish` semantics vs BACKLOG.md — **PASS**

DC-gain-unity derivation for the RBJ lowpass is textbook-correct; confirms
HF-side collapse with LF-width preservation, the opposite of BACKLOG's
wording. Musically sensible — mid/side HF-mono-ing to tame swishy/phasey
top end is an established mastering technique, and lines up with what a
PHASE_SWISH remediation should do. **BACKLOG.md's wording is the error,
not the code.**

## Blocker 6 — `collapse_swish` default cutoff vs PHASE_SWISH's 8 kHz partition — **PASS (architecture's conclusion correct); one addition**

Correct that a single 12 dB/oct pair cannot brick-wall at 8 kHz. Real-world
M/S HF-taming tools are almost always gentle-slope shelves, not brick
walls — a 2nd-order slope is consistent with normal mastering practice.
The problem is specifically attempting to *match* PHASE_SWISH's binary
detector boundary with it, which correctly should not be attempted. No
objection to leaving the cutoff unset pending measurement.

## Blocker 7 — non-detector-driven trigger posture — **PASS**

Correctly avoids broadening the §4.2a exception. Matches how §4.2a is
scoped (STATIONARY_WHISTLE only, narrow and dated).

## Blocker 8 — `collapse_swish` vs [5a]/[5b] stacking — **CONCERN — mitigation as stated is insufficient**

The physical point is right (a 12 dB/oct filter starts perceptibly
narrowing roughly an octave below its nominal cutoff — at 8 kHz that means
measurable narrowing from ~4 kHz up), but "report separate attributed
deltas" doesn't by itself tell an operator *which* [5a] per-band correction
is being undone. **Recommend the report explicitly name which [5a] target
bands fall inside the collapse filter's −1 dB and −3 dB skirt**, so the
interaction is legible without the reader doing octave arithmetic
themselves. Report-content requirement, not a new interlock — doesn't
block default-off shipping, but should close before any default-on
consideration for either stage.

## Blocker 9 — float32 mid-chain round-trip — **PASS**

Derived tolerance (~−120 dBFS) is well below any audible threshold and
below typical dither noise floors. Explicit cast-in/cast-out at wrapper
boundaries is the right implementation discipline. No mastering-domain
objection.

## Blocker 10 — sub-frame refusal — **PASS**

93 ms is not a plausible mastering-stage input. Refuse-don't-pad-or-bypass
is correct, consistent with the story's "never silently fall back to
unmodified audio" NFR.

## Blocker 11 — L/R-independent processing across all three functions — **split verdict**

- **`repair_whistles`**: requirements.md's stated risk ("unlinked notching
  can shift inter-channel phase/level relationship at the notch
  frequency") is **physically incorrect** and should not be carried
  forward. The notch multiplies identical bin indices by the identical
  real scalar (0.01) in each channel independently — the same LTI
  operation applied to both channels. It cannot introduce an inter-channel
  phase or level *relationship* shift; L and R can only change by the same
  factor, differing only via real signal content at that bin. Independent
  per-channel processing here is fine — this wrong claim should not be
  treated as a live concern going forward (same class of error CLAUDE.md
  flags for DEF-203).
- **`collapse_swish`**: inherently M/S, single shared filter state on one
  side signal — no per-channel linking question exists here.
- **`shape_transients`**: **real concern, elevate past "unlikely to
  meaningfully decorrelate width."** Unlinked stereo dynamics processors
  are a well-known source of image-shift/pumping-pan artifacts in
  mastering — independent envelope followers per channel respond to
  whatever transient content dominates that channel, and on club material
  with hard-panned hi-hats/percussion against a centred kick, L and R will
  trigger the attack/sustain switch at different instants. Placement at
  [5d], *after* [5a]/[5b] stereo-width correction, compounds this: an
  unlinked per-channel gain change re-opens the width relationship those
  stages just corrected toward the reference target, on every transient.
  **Recommend stereo-linked detection (control signal derived from the
  channel sum or max, applied identically to both channels) as a
  prerequisite for default-on**, not just a judgement call to note and
  move past.

---

## Summary / Verdict

**Sound as-is**: Blockers 5, 6, 7, 9, 10, and the `repair_whistles` half of
Blocker 11.

**Correctly diagnosed, needs arithmetic fix before it propagates**:
Blocker 1 (OLA bug) — conclusion and proposed fix stand; the −1.25 dB
figure and "one channel survives" framing in architecture.md §3 must be
corrected to −2.26 dB RMS / periodic-modulation framing.

**Needs rework before default-on, not just Gate 1 sign-off**:
- Blockers 3/4 (`shape_transients`): the required test as written targets
  the wrong frequency (f instead of 2f, given full-wave-rectified envelope
  followers) and would not catch the flutter it's meant to catch. The
  candidate gain-law fix doesn't address the fast follower's
  bass-frequency sensitivity — the actual mechanism. Needs a highpassed
  detector sidechain or multiband approach, plus musically-justified time
  constants (slow path likely needs to move well past 50 ms).
- Blocker 11 (`shape_transients` half): stereo-linked detection is a
  prerequisite for default-on, not an optional note, given placement after
  the stereo-correction stages.
- Blocker 2: don't move the confidence number — co-gate on
  `prominence_db` instead.

**None of this blocks the story shipping with all three stages
default-off**, which is what requirements.md and architecture.md both
already commit to. It blocks any future default-on story for
`repair_whistles` (pending the OLA fix and corrected test) and
`shape_transients` (pending the sidechain/highpass fix, corrected test
target, and stereo-linking), and defines what that future story's Gate 1
will need to see.
