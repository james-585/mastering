# STORY-009 — Architecture: Wire `suno_dsp` into the mastering chain

Scope per `Story.md`/`requirements.md`: pipeline wiring design and Gate 1
grounding only. No numeric default is cleared for "on" by this document —
every function ships **default off**, per BACKLOG AC1/AC5. This document
resolves what requirements.md left open where a design decision was
possible, and lists the rest as Blockers for mastering-engineer Gate 1.

**Revision note (this version)**: incorporates the mastering-engineer's
Gate 1 methods review (`mastering-review-methods.md`). See §14 for the
resolved status of every original Blocker, and the "Revision history"
section at the end for what changed and why.

Conforms to `docs/ARCHITECTURE.md` §3.4 (MASTERING CHAIN contract): stages
take `AudioBuffer`/array + config, return array + `list[CorrectiveAction]`-
shaped log entries; no target constants invented in this stage's config.

---

## 1. Pipeline placement

Existing numbered stages (`pipeline.py`, current): [1] ingest, [2] pre-
master analysis (+ optional STORY-008 stem repair), [3] resample, [4]
corrective EQ, [5a] per-band stereo width correction, [5b] broadband
stereo/mono correction, [6] loudness/limiting, [7] dither, [8] export, [9]
post-master analysis, [10] report.

New stages inserted:

```
[1] Ingest
[2] Pre-master analysis  (artifact_detection computed here — unchanged)
[3] Resample (conditional)
[3b] repair_whistles  (NEW — config-gated, default off)
[4] Corrective EQ
[5a] Per-band stereo width correction
[5b] Broadband stereo/mono correction
[5c] collapse_swish  (NEW — config-gated, default off)
[5d] shape_transients (NEW — config-gated, default off)
[6] Loudness/Limiting
[7] Dither
[8] Export
[9] Post-master analysis
[10] Report
```

**Rationale for each placement:**

- **`repair_whistles` at [3b], after resample, before EQ.** The detector's
  `frequency_hz` values are in Hz, not bins, so they remain valid across a
  resample — but running the notch at the *final* sample rate means the
  bin math done inside the C++ (which is sample-rate-dependent, per
  requirements.md's finding that notch width scales with `sample_rate`) is
  computed once, at the rate the rest of the chain will use. Running it
  before EQ means EQ's seven-band measurement (Stage [4]) sees the post-
  notch spectrum, so EQ doesn't "correct" a band that the notch has already
  altered.
- **`collapse_swish` at [5c], after both existing stereo-correction stages
  (5a/5b), not interleaved with them.** [5a] corrects per-band stereo width
  toward the reference target; [5c] then unconditionally collapses HF side
  content per its cutoff. Running collapse_swish first would have [5a]
  "correct" a width value that immediately changes again. Running it last
  makes the interaction visible and attributable (see §8 below) rather than
  hidden inside a shared measurement.
- **`shape_transients` at [5d], after stereo correction, before loudness/
  limiting.** It is a dynamics/glue stage (per requirements.md's explicit
  reframing — never described as artifact repair), and DOMAIN.md §5 fixes
  chain order as EQ → dynamics → loudness → dither. Placing it immediately
  before [6] keeps it in the "dynamics" slot and ensures the loudness
  solver sees its output, not the pre-shaped signal (loudness must be
  measured after all dynamics processing, consistent with "loudness
  measured after limiting, never before").

---

## 2. Data-representation contract deviation — flag, don't hide

`docs/ARCHITECTURE.md` §1 principle 5: "Float64 internally, convert only at
I/O." All three `suno_dsp` functions are compiled against
`py::array_t<float, py::array::forcecast>` and return `float32`. Every
enabled stage therefore performs a float64→float32→float64 round-trip
**mid-chain**, not at an I/O boundary. This is a deviation from the stated
principle.

**Decision**: accepted as unavoidable without modifying/recompiling the
C++ extension (out of scope per requirements.md "Explicit out-of-scope").
The deviation is confined to the three wrapper functions: each wrapper
casts to `float32` explicitly on the way in and back to `float64`
immediately on the way out — never left implicit via pybind's hidden cast,
so it is visible in a diff and testable.

```python
def _to_dsp_input(audio: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(audio, dtype=np.float32)

def _from_dsp_output(result: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(result, dtype=np.float64)
```

**Derived tolerance for "no-op" claims (closes AC7's open tolerance)**:
float32 mantissa is 24 bits → relative machine epsilon 2⁻²⁴ ≈ 5.96e-8. For
a 4096-point float32 FFT/IFFT round trip, rounding error accumulates
roughly as `sqrt(log2(N)) · eps` ≈ `sqrt(12) · 5.96e-8` ≈ 2.06e-7 relative.
On full-scale (±1.0) audio this bounds absolute sample error at
~2e-7. **Test tolerance: 1e-6 absolute peak difference** — roughly 5x the
derived numerical-noise bound, equivalent to about −120 dBFS, inaudible and
far below any dither floor. AC7 and AC10's "no-op"/"empty-list" tests must
use this tolerance, not literal bit-identity, and must not silently accept
a materially larger deviation by widening the tolerance without
re-deriving it (H4).

This tolerance applies **only** to `shape_transients` and `collapse_swish`
no-op cases and to `repair_whistles` *if and only if* the OLA fix in §3 is
applied first. Until that fix lands, `repair_whistles` with an empty
frequency list is **not** expected to pass this tolerance — see §3.

---

## 3. `repair_whistles` — OLA gain-modulation finding (Blocker, not asserted-safe)

Requirements.md flagged a suspected ~−2.5 dB mean level shift from the
window/divisor mismatch (`hann²` in the numerator, plain `hann` in the
`overlap_weights` divisor) and asked for it to be measured, not assumed.
Working the arithmetic here rather than deferring it entirely, because it
changes what the required test must check:

At 50%-hop Hann overlap, two frames contribute to each output sample at
phase θ, with window values `a = 0.5 − 0.5·cosθ` and `b = 0.5 + 0.5·cosθ`
(`a + b = 1` identically — this is why the *intended* divisor,
`overlap_weights = hann + hann` summed, would be exactly 1 and the
reconstruction unity-gain). The **actual** numerator carries `a² + b²`
(because the signal is windowed on both analysis and synthesis, but the
divisor only accumulates the single un-squared window):

```
a² + b² = 0.5 + 0.5·cos²θ    → ranges 0.5 to 1.0 depending on θ
divisor = a + b = 1.0        → constant
```

So the reconstruction gain is **not a static trim** — it is a periodic
amplitude modulation between 0.5 (−6 dB) and 1.0 (0 dB) as a function of
position within the hop, i.e. **at `sample_rate / hop_size` ≈ 21.5 Hz** at
44.1 kHz/hop 2048. The mean of that swing, `mean(0.5 + 0.5cos²θ) = 0.75`
→ −2.5 dB, is the figure requirements.md carried forward — arithmetically
correct as a mean, but not descriptive of what the signal actually does.
Edge frames (first/last hop of a run, where only one frame contributes)
are worse still: gain there is the single `hann(n)` value, i.e. a fade
in/out artifact at the start and end of every processed region.

**Required test — not RMS delta (numbers corrected per Gate 1 review,
`mastering-review-methods.md` Blocker 1).** A scalar RMS/level-delta test
on the empty-frequency-list case is exactly what the review confirms is
insufficient, for a concrete reason: the correct scalar RMS figure for
this modulation, worked precisely, is **−2.26 dB**, not the "−1.25 dB,
half the −2.5 dB mean" figure this document previously (incorrectly)
carried. Derivation: the instantaneous amplitude gain is
`g(θ) = a²+b² = 0.75 + 0.25·cos2θ` (double-angle rewrite of
`0.5+0.5cos²θ` above); its RMS over a full cycle is
`sqrt(mean(g²)) = sqrt(0.75² + 0.5·0.25²) = sqrt(0.59375) ≈ 0.7706` →
**−2.26 dB**. This is a different statistic from the −2.5 dB *mean* gain
already noted — mean and RMS of a periodic signal are distinct quantities,
and neither substitutes for the test below. The earlier "only one
channel's worth of modulation survives a naive RMS" framing was not a
coherent derivation and is retracted; there is one signal path here, not
two channels' worth of anything, per the review.

The point that matters for the test spec is **not** that a scalar level
test would pass by accident — it wouldn't. Against the §2 tolerance
(1e-6 absolute), a sample-diff of order 0.5 (the −6 dB swing) fails by
roughly five orders of magnitude, loudly, every time a naive tolerance
check is run. **A scalar level test fails today, but its failure is
uninformative**: "output ≠ input" is also true of a legitimate,
correctly-implemented notch, so a bare failure alone doesn't tell a reader
whether they're looking at expected notch behaviour or the OLA bug. What a
scalar test categorically cannot do is (a) verify the fix once it lands —
after the fix, output should differ from input by nothing on an
empty-frequency-list call, and a scalar peak-diff check is the right tool
*then*, and (b) distinguish, before the fix, whether a given non-zero
delta reflects a static level change or a **21.5 Hz periodic modulation**
(audible amplitude modulation/tremolo on programme material) versus some
other broadband cause. The test must therefore target the periodic
component directly, both to diagnose the present bug specifically and to
serve as the fix-verification test later:
1. Process a steady test tone (or DC-adjacent constant) through
   `repair_whistles` with `target_frequencies=[]`.
2. Compute the sample-wise diff against the (float32-cast) input.
3. Assert the diff has **no periodic component at `sample_rate /
   hop_size`** (e.g. FFT the diff envelope, assert no prominent peak
   near 21.5 Hz at 44.1 kHz / proportionally at other rates) — this is
   the check that actually falsifies "no-op," not a scalar level
   comparison.
4. Separately assert peak absolute diff against the 1e-6 tolerance in §2
   **only if** the modulation check in (3) passes clean (i.e. only
   meaningful once the underlying bug is fixed).

**Decision**: this is a **method bug** in the OLA normalisation (H6 — not
a parameter to retune), located in the C++ divisor accumulation
(`overlap_weights[...] += hann[i]` should be `+= hann[i] * hann[i]`, so
numerator and divisor use the same weighting and cancel exactly; this also
fixes edge-frame fade artifacts). Fixing the `.cpp` file is outside this
architecture's scope (per requirements.md "Explicit out-of-scope" — that
is implementation/python-developer or a follow-up C++ patch), but per AC10
and BACKLOG AC4, **this stage's default may not move to "on," and the
"no-op" claim in AC7 may not be asserted as passing, until the measured
test in this section is green.** This is recorded as **Blocker 1** below.
Gate 1 confirms the physics and the fix as correct; see §14.

---

## 4. `repair_whistles` — time-window handling

**Decision: windowed crossfade in the Python wrapper**, not a whole-file
notch, and not a signature change to the C++.

Rationale: `repair_whistles` notches the entire file uniformly at a Q
≈120 (54 Hz wide at 6.4 kHz), which requirements.md correctly frames as
near-inaudible on broadband programme material but capable of gutting a
genuine sustained tonal element at the same pitch class elsewhere in the
track. The detector already reports `timestamp_start_s`/`timestamp_end_s`
per flag, so preserving time-locality is achievable without touching the
C++ signature — process the full buffer once (§3's per-frame notch is
already whole-file inside the C++), then crossfade between the original
and processed buffers so only the flagged window (plus a skirt) carries
the processed signal:

```python
def _apply_windowed_notch(
    original: np.ndarray,
    processed: np.ndarray,
    start_s: float,
    end_s: float,
    sample_rate: int,
    crossfade_ms: float = 50.0,
) -> np.ndarray:
    """Linear crossfade original -> processed -> original across
    [start_s - skirt, end_s + skirt]. Outside that range, output is
    bit-identical to `original` (not `processed`)."""
```

`crossfade_ms` default 50.0 ms matches the existing
`config.stereo_crossfade_ms` convention in `MasteringConfig` (consistency
with an already-reviewed value, not a new invented constant per CLAUDE.md
§5 — flagged for Gate 1 confirmation since it is being reused in a new
context, not re-derived for this purpose).

**Hard ordering constraint**: this crossfade design is only correct once
the §3 OLA fix lands. While the OLA bug is live, crossfading composites
unmodulated audio (outside the window) against 21.5 Hz-modulated audio
(inside the window), producing an audible step/beat at each crossfade
boundary — worse than either whole-file or no windowing. **The windowed-
crossfade design and the §3 OLA fix are coupled; the crossfade must not
ship ahead of the fix.** Recorded as part of Blocker 1.

For multiple flags in one track: crossfade windows are applied
independently per flag against the *same* fully-processed buffer (not
recursively), then unioned — overlapping flag windows produce a single
merged processed region.

---

## 5. `repair_whistles` — short-input handling

**Decision: refuse, do not pad or silently bypass.**

Confirmed from the C++: for `n_samples < frame_size` (4096), neither the
main loop (`start + frame_size <= n_samples`) nor the tail branch
(`n_samples > frame_size`) executes, `overlap_weights` stays all-zero, and
the divide-by-zero guard (`if (overlap_weights[i] > 0.0f)`) leaves the
output buffer at its initialised value — zeros. Silence.

Padding would change OLA edge behaviour in ways not evaluated here, and a
silent bypass directly contradicts the story's own NFR: "never a silent
fallback to unmodified audio when a flag is explicitly enabled and the
call was attempted." The wrapper must therefore check `n_samples <
frame_size` **before** calling into `suno_dsp` and raise:

```python
class SubFrameAudioError(MasteringError):
    """Raised when repair_whistles is enabled but the input is shorter
    than one STFT analysis frame (4096 samples, ~93 ms at 44.1 kHz)."""
```

Sub-93 ms input is not a realistic master-stage input; refusing is the
correct default posture (per requirements.md, "not resolved here" — this
architecture resolves it). Gate 1 confirms this posture; see §14.

---

## 6. `repair_whistles` — Python wrapper contract, scope enforcement, and gating

**Contract (`mastering/whistle_repair.py`, new module):**

```python
def apply_whistle_repair(
    audio: np.ndarray,              # float64, shape (n, channels)
    sample_rate: int,
    artifact_detection: ArtifactDetectionResult | None,   # STORY-007 output
    config: RepairWhistlesConfig,
) -> tuple[np.ndarray, list[dict]]:
    """Returns (audio, actions). `actions` is a list, one entry per flag
    processed (possibly empty) plus a summary entry stating whether the
    stage ran at all."""
```

**Enforcement is structural, not conventional (AC8 / CLAUDE.md §4.2a):**
- The function signature accepts **only** `ArtifactDetectionResult | None`
  — never `list[float]`. There is no code path by which a caller can pass
  a raw frequency list; the only way frequencies reach `suno_dsp.
  repair_whistles` is by extracting `flag.details["frequency_hz"]` from
  flags where `flag.artifact_type == "STATIONARY_WHISTLE"`,
  `flag.confidence_score >= config.confidence_threshold`, **and
  `flag.details["prominence_db"] >= config.prominence_floor_db`** (see
  below), inside this function.
- `RepairWhistlesConfig` (new dataclass, added to `MasteringConfig` via
  `field(default_factory=RepairWhistlesConfig)`, mirroring the existing
  `StemConfig` pattern) carries **only** `enabled: bool = False`,
  `confidence_threshold: float = 0.8`, and `prominence_floor_db: float |
  None = None` (new field, see below). **No frequency field exists on the
  config dataclass at all** — this is what makes a config-sourced
  frequency list unrepresentable, not merely discouraged.
- `suno_dsp.repair_whistles` itself is called from exactly one call site:
  inside `apply_whistle_repair`. `pipeline.py` never imports `suno_dsp`
  directly.
- Required tests (for test-case-writer, not designed here): (a) assert
  `RepairWhistlesConfig` has no attribute containing "freq" or
  "frequenc"; (b) assert `apply_whistle_repair`'s signature has no
  `list[float]`-typed parameter; (c) assert passing a raw list where
  `artifact_detection` is expected raises `TypeError` (Python's own type
  system) rather than being silently accepted; (d) assert a flag meeting
  the confidence threshold but not the prominence floor is **not**
  forwarded to `suno_dsp.repair_whistles`, and vice versa.

**Confidence + prominence co-gating (resolves Blocker 2 per Gate 1
review).** Gate 1 confirmed reusing STORY-007's 0.8
`CONFIDENCE_THRESHOLD_TO_WARN` is fine in principle, but explicitly
rejected raising it as the fix — moving a number calibrated for "surface a
warning line" doesn't calibrate it for "commit an audio edit," and repeats
the CLAUDE.md §5 "tune the parameter instead of fixing the method" trap.
The actual gap: confidence alone doesn't establish that the tone is
prominent enough for an automated edit to be preferable to leaving it for
manual review. `ArtifactFlag.details` already carries `prominence_db`
(confirmed present — `STORY-007/architecture.md` §"ArtifactFlag" and
`types.py`'s `details: dict` field; STORY-007's own detector only ever
emits `STATIONARY_WHISTLE` at `prominence_db >= 6.0`, its own detection
floor, per `STORY-007/requirements.md` AC5). Because 6 dB is already
guaranteed by the detector for every flag this stage will ever see, a
co-gate floor **at or below 6 dB has no effect** — only a floor set
*strictly above* 6 dB changes which flags get edited.

**Decision**: `apply_whistle_repair` gates each flag on **both**
`confidence_score >= config.confidence_threshold` (unchanged, 0.8
default) **and** `prominence_db >= config.prominence_floor_db`. This is a
method addition (a second, independent gate), not a retuning of the
first — satisfies H6.

**No default value is asserted for `prominence_floor_db` by this
document.** It can be derived that the floor must be > 6 dB to have any
effect at all, but a specific defensible value (10 dB vs 15 dB vs
something else) is not derivable from data available to this
architecture — it needs either empirical validation against reference
material or a mastering judgement call about how prominent a tone must be
before an automated notch is preferred over leaving it for manual review.
Left as `prominence_floor_db: float | None = None` in config (§9);
`apply_whistle_repair` raises a config-validation error if `enabled=True`
and `prominence_floor_db is None`, so the stage cannot silently run
without an explicit value — same posture as `collapse_swish`'s
`cutoff_freq_hz=0.0` guard (§8/§9). **Recorded as Blocker 2 (revised): a
specific `prominence_floor_db` value, strictly above 6 dB, must be set by
the mastering engineer before default-on** — Gate 1 resolves the *method*
(co-gate, don't retune) but not the number.

---

## 7. `shape_transients` — gain-law finding, root cause, and Python wrapper contract

Requirements.md's finding, confirmed: `diff / (|diff| + 1e-6)` saturates to
±1 for any audio-scale envelope difference, making the stage a near-binary
switch. Deriving further, because it changes what "near-binary switch"
actually means in practice:

`alpha = 1 − exp(−1/(τ·sample_rate))`; the corresponding one-pole −3 dB
corner is `f_c = 1/(2πτ)`. For the hardcoded constants:
- fast (τ=2 ms) → f_c ≈ 79.6 Hz
- slow (τ=50 ms) → f_c ≈ 3.2 Hz
- smoother (τ=5 ms) → f_c ≈ 31.8 Hz

**Root cause (revised per Gate 1 review — `mastering-review-methods.md`
Blockers 3/4): not the gain-law shape alone.** Gate 1 traced the mechanism
to source (`src_cpp/spectral_repair.cpp` lines 306-309): both envelope
followers are driven by `std::abs(current_sample)` — full-wave
rectification. Rectifying a sine at fundamental `f` produces no energy at
`f`; its lowest AC component is at `2f` (standard rectifier-spectrum
result). On a 55 Hz sustained bass note, the rectified ripple sits at
110 Hz. The fast follower's 79.6 Hz corner attenuates that only ~4.6 dB
(110 Hz is inside its passband), while the slow follower's 3.2 Hz corner
kills it almost entirely (~−31 dB). So `diff = fast_env − slow_env`
genuinely oscillates at **2× the input fundamental**, independent of the
gain law used to convert that oscillation into a multiplier. Replacing the
gain law alone (`diff/(slow_env+eps)`, below) removes the *saturation* but
not the *oscillation itself* — the fast follower will still track sub/bass
content it should be blind to. For this project's genre context
(club-oriented electronic material with strong sub/kick content), this is
close to the median input, not an edge case.

**This corrects the required test from the previous version of this
document, which targeted the wrong frequency.** A test that measures gain
flutter at the input's *fundamental* `f` can pass a stage that still
flutters at `2f` — see "Revised required test" below.

**Required design element (not optional): highpassed detector sidechain.**
The fix is not a different gain-law shape applied to the same broadband
detector signal — it is excluding sub/bass fundamentals from what the
envelope followers see at all, i.e. a **highpass filter placed ahead of
both envelope followers** (a detector-sidechain filter only; the audio
actually being shaped/output is *not* run through this filter).
Specification for the next implementation step (a C++ patch to
`spectral_repair.cpp`, python-developer's task next, guided by this spec
— not implemented in this document):
- Insert a highpass filter (single-pole or 2nd-order biquad; either
  acceptable, 2nd-order preferred for a steeper transition) ahead of the
  `std::abs()` rectification stage, applied identically to the signal
  feeding *both* the fast and slow envelope followers.
- **Cutoff: 150 Hz**, stated as this specification's working value within
  the review's suggested 150-250 Hz range. Justification: (a) it sits
  above the fundamental range of kick/bass content typical of
  club-oriented electronic material (roughly 40-120 Hz for kick drums and
  bass synths/808s), so the 2× ripple causing this problem (80-240 Hz for
  those same fundamentals) is substantially attenuated *at the source*,
  before rectification, rather than needing removal after the fact; (b)
  transient attacks (kick clicks, claps, hi-hat/percussion transients)
  carry broadband energy well above 150 Hz, so a highpassed sidechain
  still detects the attack instant — only the sustained low-frequency
  body is excluded from triggering the discriminator.
- This cutoff is **not** exposed as a `ShapeTransientsConfig` field in
  this revision — it is a fixed internal constant in the C++, consistent
  with how the other envelope constants (2 ms / 50 ms / 5 ms) are
  currently hardcoded. Whether it needs to become a tunable is deferred
  pending empirical validation (below); exposing it later does not
  require a fresh architecture review if the sidechain design itself
  (highpass-before-rectify) is unchanged.
- This is a **method-level design requirement, not optional**: per the
  review, the candidate gain-law fix (`diff/(slow_env+eps)`) is necessary
  but **not sufficient** on its own to clear default-on — both elements
  (normalised gain law *and* highpassed sidechain) are required together.

**Required design element (elevated from a note to a hard prerequisite):
stereo-linked control signal.** Gate 1's Blocker 11 review found the
original "unlikely to meaningfully decorrelate width" framing for
`shape_transients` insufficient. Unlinked stereo dynamics processors are a
known source of image-shift/pumping-pan artifacts, and placement at [5d],
*after* [5a]/[5b] stereo-width correction, compounds this: an unlinked
per-channel gain change re-opens the width relationship those stages just
corrected, on every transient. On club material with hard-panned
hi-hats/percussion against a centred kick, independent per-channel
envelope followers will trigger the attack/sustain switch at different
instants between L and R.

**Decision**: the envelope-follower control signal (both fast and slow,
post-highpass per above) must be derived from a **stereo-linked source** —
`link_signal = max(|L|, |R|)` per sample (peak-linking, standard for
transient designers, avoids under-response on hard-panned content) — and
the resulting gain multiplier applied **identically to both channels**.
This is a **prerequisite for default-on**, not a note to revisit later.
(`repair_whistles`'s independent per-channel notching is confirmed fine by
the same review and is **not** subject to this requirement — see §14
Blocker 11.)

**Channel-count contract.** `apply_transient_shaping` accepts `(n,
channels)` with no channel-count guard (unlike `collapse_swish`, which is
stereo-only and rejects other channel counts). The stereo-linked control
signal generalises without a special case: `link_signal[n] = max over
channels c of |audio[n, c]|`, which degenerates correctly to
`|audio[n, 0]|` for mono input and extends unchanged to any channel
count. No mono/multi-channel branch is required in the wrapper or the
C++ — stated explicitly here so the developer does not add an
unnecessary guard, or, worse, leave the mono case undefined.

**Revised required test (for test-case-writer):** sustained sine tone and
sustained pink noise, at bass-register fundamentals well below the
sidechain highpass corner (e.g. 55 Hz, 110 Hz — attenuated at the source,
should show little/no flutter), at mid/high fundamentals well above it
(e.g. 440 Hz — 880 Hz ripple, ~21 dB down at the fast follower's 79.6 Hz
one-pole corner, should show minimal flutter), **and, critically, at one
or more fundamentals just above the highpass corner (e.g. 160-250 Hz)** —
the worst-case residual, since a fundamental in this band produces ripple
at 320-500 Hz, only ~12-16 dB down through a single one-pole highpass,
and is the case most likely to still show audible flutter after the fix.
All cases well above the noise floor, processed with
`attack_boost_db=+3, sustain_cut_db=-3`; measure the output envelope's
spectrum for periodic gain flutter **at 2× the input fundamental and its
harmonics** (not at the fundamental itself — the previous version of this
document specified the wrong target frequency) and for output-spectrum
sidebands not present in the input. The near-corner case doubles as the
empirical basis for choosing the final sidechain cutoff within the stated
150-250 Hz range (above) — if it still flutters audibly at 150 Hz, that
is evidence for moving the cutoff toward 250 Hz, deferred to
implementation + listening validation, not decided here. Additionally, a
stereo test: hard-panned percussive transient on one channel only,
sustained low content on both — assert L and R gain multipliers are
sample-for-sample identical (validates the stereo-linking requirement
above).

**2 ms / 50 ms / 5 ms constants (H4), tightened per review**: derivation
is shown above (corners of 79.6 Hz / 3.2 Hz / 31.8 Hz) — satisfies
"derivation shown," but Gate 1 found the 50 ms slow/sustain constant
specifically too short for mastering-stage use: conventional transient
designers use **100-500 ms** for this role (vs. tracking/mixing-stage use,
where faster values are more common) specifically so the discriminator
doesn't fire on the sustained body of a percussive hit, only its leading
edge — at 120 BPM a 16th note is 125 ms, and 50 ms risks re-classifying
the decaying body of a kick or clap as "attack" repeatedly through its
decay. **Revised guidance: the slow/sustain constant must move into the
100-500 ms range**; the exact final value within that range is deferred
to implementation + listening validation against reference tracks (same
posture as Blocker 4's empirical-justification question, now narrowed to
a bounded range rather than left fully open). The 2 ms fast and 5 ms
smoother constants are not flagged by the review and are unchanged
pending the same empirical validation.

**Contract:**

```python
def apply_transient_shaping(
    audio: np.ndarray,       # float64, shape (n, channels)
    sample_rate: int,
    config: ShapeTransientsConfig,
) -> tuple[np.ndarray, list[dict]]:
    """Signature deliberately excludes any detector/artifact-flags
    parameter -- see AC11/AC12 guard below."""
```

**SMEARED_TRANSIENT guard (AC11, structural not commentary — requirements
explicitly asks for a code-level guard, not a comment):** the function
signature above has no parameter through which `ArtifactDetectionResult`
or any `ArtifactFlag` list can reach it — it accepts only the audio array,
sample rate, and a config carrying `enabled: bool = False`,
`attack_boost_db: float`, `sustain_cut_db: float` as plain user-supplied
constants. This is stronger than a runtime assertion: there is no
parameter slot to misuse. Required test: signature introspection
(`inspect.signature(apply_transient_shaping).parameters`) asserting no
parameter name or annotation contains "artifact", "flag", "detection", or
"smear" (case-insensitive substring check). Report/log text is generated
from a hardcoded template ("Transient shaping (dynamics/glue): attack
±X dB, sustain ±Y dB") that never references artifact/repair vocabulary —
satisfies AC12.

---

## 8. `collapse_swish` — semantics, placement, and cutoff

**Confirmed reading of the biquad** (source-grounded, resolving
requirements.md's Open Question 5): the coefficients
`b0=(1−cosω)/2, b1=1−cosω, b2=(1−cosω)/2` normalised by `a0=1+α` are
textbook RBJ **lowpass**, Direct Form I, Q = 0.7071 (Butterworth), applied
to the side signal only, with a single filter state (`x1,x2,y1,y2`) shared
across the whole side channel — no per-channel state bug, no cross-talk
into mid.

Derivable properties, stated because they settle the semantic question
without further probing:
- **DC gain is exactly 1**: `(b0+b1+b2)/(a0+a1+a2) = (2−2cosω)/(2−2cosω)
  = 1` (algebraically, independent of ω) — so side content at and below
  the cutoff is passed at unity gain, meaning low-frequency stereo width
  is **preserved**, not collapsed.
- Encode/decode round trip is unity when `filtered_side = side`:
  `M=(L+R)/2, S=(L−R)/2 → L=M+S, R=M−S` reconstructs exactly. So a cutoff
  placed at/above Nyquist (degenerate case, guarded against by the C++'s
  own `cutoff_freq < sample_rate/2` check) would be a full passthrough —
  useful as a ground-truth test.
- At the cutoff itself, response is −3 dB (Q=0.7071 defines this);
  rolloff above cutoff is 12 dB/octave (2nd-order).

**This confirms BA's reading, not BACKLOG.md's**: the function collapses
HF side content toward mono while preserving LF stereo width — the
opposite of "mono-sum the side channel below a cutoff." BACKLOG.md's
wording is the drafting error. **Recorded as Blocker 5**: BACKLOG.md and
any downstream doc referencing "mono bass below crossover" for this
function must be corrected once Gate 1 confirms this reading; not done in
this architecture per H9 (this doc does not edit BACKLOG.md). Gate 1
confirms this reading; see §14.

**Cutoff default and PHASE_SWISH relationship — Blocker, not resolved
here.** STORY-007's PHASE_SWISH detector partitions its spectrum at 8 kHz
(LF < 8 kHz stays intentionally stereo-coherent-gated, HF ≥ 8 kHz is where
decorrelation is flagged). It is tempting to set `cutoff_freq = 8000` to
match. **This does not work as a direct mapping**: a 2nd-order (12 dB/oct)
lowpass is too gentle a slope to both "collapse ≥8 kHz" and "leave <8 kHz
untouched" with one cutoff — at `cutoff=8000`, the side signal is already
−3 dB at 8 kHz (partial collapse starting well below the detector's
boundary) and only reaches roughly −12 dB by 16 kHz (nowhere near full
collapse at the top of the audible range the detector is concerned with).
A single-pole-pair filter cannot produce PHASE_SWISH's implicit brick-wall
partition. **No default cutoff is asserted by this document.** Recorded as
**Blocker 6**: Gate 1 must set a provisional cutoff with its measured
consequence stated in both directions (how much side energy is trimmed
below the nominal target region, how much survives above it), or accept
that this stage cannot precisely target PHASE_SWISH-shaped problems and
must be scoped as a general (not detector-matched) stereo tool. Gate 1
confirms this conclusion (2nd-order slope cannot brick-wall) as correct;
no cutoff value is set by that review either — see §14.

**Trigger design — general stage, not detector-driven (resolves
requirements.md's implicit tension with its own out-of-scope section).**
requirements.md explicitly lists "Repair of ... PHASE_SWISH ... using
these functions" under **Explicit out-of-scope**, and states the §4.2a
exception "must not be read as extending to ... PHASE_SWISH." Auto-
triggering `collapse_swish` on PHASE_SWISH flags would extend that
exception without a fresh Gate 1 review — exactly what CLAUDE.md §4.2a
prohibits. **Decision: `collapse_swish` is a general, config-gated,
default-off, manually-enabled stage. It is never automatically invoked by
STORY-007 detector output.** When `artifact_detection` contains
PHASE_SWISH flags, the stage's action log includes them as **advisory
human-facing context only** ("N PHASE_SWISH flag(s) present in this
track; collapse_swish is available but was not auto-triggered by them"),
giving the operator the connection without making the code path a
detector-driven trigger. Whether §4.2a should be broadened to cover a
PHASE_SWISH-driven auto-trigger in a future story is raised as **Blocker
7** — not decided here. Gate 1 confirms this posture; see §14.

**Channel-count guard (AC14)**: the C++ raises `std::invalid_argument` on
non-2-channel input, but the pipeline must not rely on catching that as
control flow (requirements.md is explicit). Wrapper checks
`audio.shape[1] == 2` before calling `suno_dsp.collapse_swish` and, if
false, records a "skipped — not stereo" action entry and returns the
audio unmodified — same posture as the existing `if before.channels == 2`
guard already used for per-band width measurement and [5a] in
`pipeline.py`.

**Interaction with [5a]/[5b] (AC16) — named, not silently stacked.**
Running collapse_swish after [5a]/[5b] means: [5a] corrects HF-band
stereo width toward the reference target range; collapse_swish then
unconditionally narrows HF side content per its cutoff, **undoing part or
all of [5a]'s correction** for any band above the cutoff. This is a
double-correction risk exactly as requirements.md AC16 names it.
**Decision on CLAUDE.md §4.2's "explicit requirement" question: this
architecture does not treat STORY-009 as that explicit requirement.**
Enabling `collapse_swish` is an operator decision (default off, config-
gated), not an automatic pipeline behaviour, so CLAUDE.md §4.2's "do not
correct without explicit requirement" is satisfied by the flag itself
being explicit per-run — but whether a *default-on* future state would
also satisfy it is a separate question, deferred to whichever story
proposes flipping the default (per AC5, any default flip needs its own
Gate 1 record).

**Mitigation, tightened per Gate 1 review (Blocker 8).** Separate
attributed deltas alone were found insufficient by the review — they tell
a reviewer *that* an interaction may exist but not *which* [5a] band is
affected, requiring the reader to do octave arithmetic themselves.
**Revised requirement**: the report must explicitly name which of [5a]'s
configured per-band target ranges (existing `pipeline.py` band
definitions, not redefined here) fall inside collapse_swish's −1 dB and
−3 dB skirt, computed from the deployed 2nd-order Butterworth lowpass's
own response, not asserted:
- The −3 dB point is `cutoff_freq_hz` itself, by construction (Q=0.7071,
  per the coefficient derivation above).
- The −1 dB point: the analog Butterworth prototype relation
  `|H(f)|² = 1/(1+(f/fc)^4)` gives `f/fc ≈ 0.713` (solving
  `1/(1+(f/fc)^4) = 10^(-0.1) ≈ 0.7943` → `(f/fc)^4 ≈ 0.2589`), but the
  deployed filter is the RBJ **digital biquad**, which is a bilinear-
  transform warp of that analog prototype — the warp is small at
  `cutoff_freq_hz` well below Nyquist but grows as `cutoff_freq_hz`
  approaches Nyquist. **The wrapper must compute both the −1 dB and
  −3 dB points numerically from the deployed biquad's actual transfer
  function** (evaluate `H(e^jω)` from the `b0,b1,b2,a0,a1,a2`
  coefficients already held by the wrapper, over a fine frequency grid,
  and find where `|H|` crosses −1 dB / −3 dB), not by applying the
  analog-prototype formula directly. `f₋₁dB ≈ 0.713 · cutoff_freq_hz` is
  retained here only as an analytic cross-check on the numeric result,
  per the project's derive-don't-assert discipline — it is not the value
  the wrapper should use directly.
- The wrapper computes both frequencies numerically (as above) from the
  run's actual `cutoff_freq_hz` and classifies each of [5a]'s band edges
  against them (below f₋₁dB: unaffected; between f₋₁dB and f₋₃dB:
  partial, −1 to −3 dB; at/above f₋₃dB: significant, entering the
  12 dB/oct rolloff), attaching the classified list to the action log
  (see §11's revised `collapse_swish` entry).

This satisfies "regression is attributable to a specific stage" (AC6) at
band-name granularity, not just at the level of separate numbers. This
report-content requirement doesn't block default-off shipping but should
close before any default-on consideration for either stage, per the
review.

**Contract:**

```python
def apply_collapse_swish(
    audio: np.ndarray,       # float64, shape (n, 2) -- stereo only
    sample_rate: int,
    config: CollapseSwishConfig,
    artifact_detection: ArtifactDetectionResult | None = None,  # advisory only
) -> tuple[np.ndarray, list[dict]]:
    """artifact_detection is consumed only to append advisory PHASE_SWISH
    context to the action log -- it never gates or parameterises the call
    into suno_dsp.collapse_swish. See §8: not a detector-driven trigger."""
```

---

## 9. Config design

New dataclasses, added to `MasteringConfig` following the existing
`StemConfig` pattern (`field(default_factory=...)`):

```python
@dataclass
class RepairWhistlesConfig:
    enabled: bool = False
    confidence_threshold: float = 0.8   # reuses STORY-007's
                                         # CONFIDENCE_THRESHOLD_TO_WARN;
                                         # unchanged per Gate 1 review --
                                         # see §6, Blocker 2
    prominence_floor_db: float | None = None
                                         # NEW -- co-gate per Blocker 2
                                         # revision. Must be set (> 6.0,
                                         # the detector's own emission
                                         # floor) before enabled=True is
                                         # usable; see §6.
    crossfade_ms: float = 50.0          # see §4; Gate 1 to confirm reuse
    # No frequency field. Deliberately absent -- see §6 enforcement.

@dataclass
class ShapeTransientsConfig:
    enabled: bool = False
    attack_boost_db: float = 0.0        # no default asserted -- Blocker 3/4
    sustain_cut_db: float = 0.0         # no default asserted -- Blocker 3/4
    # Detector-sidechain highpass cutoff (150 Hz working value, §7) and
    # the slow-envelope time constant (100-500 ms range, §7) are NOT
    # config fields in this revision -- they are internal C++ constants,
    # consistent with existing hardcoded envelope constants.

@dataclass
class CollapseSwishConfig:
    enabled: bool = False
    cutoff_freq_hz: float = 0.0         # no default asserted -- Blocker 6
                                         # (0.0 deliberately invalid --
                                         # forces Gate 1 to set it before
                                         # this stage can ever run)

@dataclass
class MasteringConfig:
    ...
    repair_whistles: RepairWhistlesConfig = field(default_factory=RepairWhistlesConfig)
    shape_transients: ShapeTransientsConfig = field(default_factory=ShapeTransientsConfig)
    collapse_swish: CollapseSwishConfig = field(default_factory=CollapseSwishConfig)
```

`attack_boost_db`/`sustain_cut_db`/`cutoff_freq_hz` are deliberately left
at values that either do nothing (`0.0` dB = no gain change) or are
invalid and will raise (`cutoff_freq_hz=0.0` fails the C++'s own `> 0.0f`
guard) — this is intentional: even if a caller flips `enabled=True`
without also setting a real value, the stage cannot silently do something
unreviewed. `prominence_floor_db=None` follows the same discipline: a
config-validation error is raised in `apply_whistle_repair` if
`enabled=True` and `prominence_floor_db is None` (§6). This is a stronger
AC5 guard than a comment.

---

## 10. Import failure posture (AC3)

Mirrors the existing `load_targets` fail-fast pattern (`pipeline.py` line
~141) and reuses the existing `DependencyError` (`errors.py`, already used
for STORY-008's demucs/torch optional-dependency posture — same shape of
problem).

```python
# Immediately after load_targets(), before Stage [1]:
any_dsp_stage_enabled = (
    config.repair_whistles.enabled
    or config.shape_transients.enabled
    or config.collapse_swish.enabled
)
if any_dsp_stage_enabled:
    try:
        import suno_dsp  # noqa: F401 -- presence check only
    except ImportError as exc:
        raise DependencyError(
            "suno_dsp extension is required because at least one of "
            "repair_whistles/shape_transients/collapse_swish is enabled, "
            "but the module could not be imported. Build it via "
            "CMakeLists.txt (see src_cpp/spectral_repair.cpp) before "
            "enabling these stages.",
        ) from exc
```

All three flags off → this block is skipped entirely → import failure
(or absence) never affects the run, satisfying AC3's second clause.

---

## 11. Action logging and report contract (AC1, AC2, AC6)

`pipeline.py`'s existing `actions` dict pattern:

```python
actions = {
    "resample": resample_action,
    "eq": eq_actions,
    "stereo_correct": stereo_actions,
    "loudness_limit": loudness_limit_action,
    # NEW -- keys present only when the corresponding flag is enabled:
    **({"repair_whistles": whistle_actions} if config.repair_whistles.enabled else {}),
    **({"collapse_swish": swish_actions} if config.collapse_swish.enabled else {}),
    **({"shape_transients": transient_actions} if config.shape_transients.enabled else {}),
}
```

**AC1 literalism**: "no related action appears in the report" means the
**key is absent**, not present with value `None` or `[]` — the existing
`"resample": resample_action` pattern already sets `None` when unused,
which is a different (weaker) contract. The three new stages must use key-
absence, and a required test asserts `"repair_whistles" not in
result.actions` (not `is None`) when the flag is off.

**Each stage's action entries, minimum fields (AC2):**

- `repair_whistles`: one entry per processed flag —
  `{"frequency_hz": float, "confidence_score": float, "prominence_db":
  float, "timestamp_start_s": float, "timestamp_end_s": float,
  "peak_delta_db": float, "rms_delta_db": float}` (peak/RMS measured
  within the crossfaded window only, per AC2's "peak/RMS delta for the
  processed region"; `prominence_db` added so the co-gate in §6 is
  auditable from the report, not just from log-level reasoning) — plus
  one summary entry `{"frequencies_notched": list[float], "stage_ran":
  bool}` even when the list is empty (covers AC7's "invoked with an empty
  frequency list" case explicitly).
- `shape_transients`: single entry `{"attack_boost_db": float,
  "sustain_cut_db": float, "peak_delta_db": float, "rms_delta_db": float}`.
- `collapse_swish`: single entry `{"cutoff_freq_hz": float,
  "side_energy_delta_db": float, "phase_swish_flags_present": int,
  "overlapping_5a_bands": list[{"band_name": str, "band_range_hz":
  [float, float], "skirt_severity": str}]}` — `phase_swish_flags_present`
  is `0` when `artifact_detection` is `None` or has no PHASE_SWISH flags;
  `overlapping_5a_bands` is the Blocker-8-revision field from §8,
  `skirt_severity` one of `"unaffected"`, `"partial(-1..-3dB)"`,
  `"significant(>=-3dB)"`, computed numerically from the deployed
  biquad's transfer function per §8's derived −1 dB / −3 dB points.

Report builder (`report/builder.py`) must render all three when present,
following the existing eq_actions/stereo_actions convention — not
designed further here (implementation detail), but the dict keys above
are the contract the report consumes.

---

## 12. Determinism (AC4)

All three C++ functions are single-threaded, purely feed-forward (no RNG,
no wall-clock dependency) — confirmed by reading the source: `repair_
whistles`'s FFT is a fixed radix-2 iterative implementation with no
randomness; `shape_transients`'s envelope followers are deterministic
recursive filters seeded at 0; `collapse_swish`'s biquad has fixed initial
state. Determinism is expected to hold. **Required test, not assumed**:
run the full pipeline twice with identical input+config (each of the three
flags on individually and in combination) and assert byte-identical output
WAV files. This is a straightforward regression-style test (H2 does not
apply — determinism is a property test, not a ground-truth-value test) but
must still exist per AC4's explicit wording ("assert this, don't assume
it").

---

## 13. Testability notes

- All three wrappers are testable on short synthetic signals (a few
  seconds), consistent with `docs/ARCHITECTURE.md`'s general testability
  expectation — with the specific exception noted in §5 (repair_whistles
  requires >= 4096 samples / ~93 ms by the C++'s own constraint; test
  fixtures for repair_whistles must be at least this long, and a separate
  fixture just under this length is required to test the refusal path).
- `collapse_swish`'s passthrough ground truth (§8): cutoff at/above
  Nyquist round-trips encode/decode exactly — usable as an exact (not
  tolerance-bounded, modulo the §2 float32 cast) ground-truth test.
- `shape_transients`'s flutter/sideband test (§7, revised) requires
  spectral analysis of the *output at 2× the input fundamental*, across a
  spread of fundamentals bracketing the sidechain highpass corner
  (including the near-corner worst case), plus a stereo-linking test
  comparing L/R gain multipliers directly — test-case-writer should use
  `scipy.signal` for the envelope/FFT analysis, consistent with
  `.claude/agents` library guidance elsewhere in this project (not this
  document's concern to specify further, flagged for test-case-writer).
- `repair_whistles`'s OLA modulation test (§3) is the one ground-truth-
  adjacent test in this story that is a genuine correctness check, not a
  regression lock — the expected "no periodic component" result is
  derivable from the OLA arithmetic shown in §3, satisfying H2.

---

## 14. Blockers for mastering-engineer Gate 1 — resolved status per review

Reviewed in `mastering-review-methods.md` (Gate 1, methods pass). Status
legend: **Resolved (no design change)** = review confirmed the original
design sound as-is; **Resolved (design revised)** = review found a defect
and this document has now fixed it; **Open, narrowed** = the review
confirms the concern is real and this document now specifies a required
design element, but a specific number is still deferred to
implementation/empirical validation or a further Gate.

1. **`repair_whistles` OLA gain-modulation bug (§3) — Resolved (design
   revised).** Physics and the proposed C++ fix confirmed correct by
   independent re-derivation. Numbers in §3 corrected per review: RMS
   deviation is **−2.26 dB** (not −1.25 dB), framed as periodic
   modulation (the earlier "one channel's worth... survives" framing is
   retracted, not a coherent derivation). Required test
   (FFT-of-diff-envelope, not scalar RMS) confirmed as the right approach
   and preserved. Still gates default-on until the C++ fix lands and the
   test is green — posture unchanged.
2. **`repair_whistles` confidence threshold (§6) — Resolved (design
   revised).** Review rejected raising the 0.8 threshold (repeats
   CLAUDE.md §5's "tune the parameter" trap). Revised design: co-gate on
   `confidence_score >= 0.8` **and** `prominence_db >=
   prominence_floor_db` (new config field). `prominence_floor_db` must be
   > 6 dB (the detector's own emission floor) to have any effect; no
   specific value is asserted here. **Open, narrowed**: a specific floor
   value is still needed from the mastering engineer before default-on.
3. **`shape_transients` gain-law saturation (§7) — Open, narrowed (design
   revised, not fully resolved).** Root cause corrected per review: both
   envelope followers full-wave-rectify, so a bass fundamental `f`
   produces ripple at `2f`, not `f` — this, not gain-law saturation
   alone, is what causes the flutter. The candidate gain-law fix
   (`diff/(slow_env+eps)`) is confirmed necessary but **not sufficient**.
   §7 now specifies a required highpassed detector sidechain (150 Hz
   working value, justified in §7) as an additional required design
   element, and corrects the required test's target frequency from `f`
   to `2f`. Remains default-off pending implementation of both elements.
4. **`shape_transients` 2ms/50ms/5ms constants (§7) — Open, narrowed.**
   Review confirms the 50 ms slow/sustain constant is short for
   mastering-stage use versus conventional transient-designer practice
   (100-500 ms). §7 revised to require the slow constant move into that
   range; exact value still deferred to implementation + listening
   validation, per the original Blocker 4 posture, now with a tightened
   acceptable range rather than an unconstrained one.
5. **`collapse_swish` semantics vs. BACKLOG.md (§8) — Resolved (no design
   change).** Coefficient derivation confirmed correct by review.
   BACKLOG.md's wording is the error, not this document; correcting
   BACKLOG.md remains out of this document's scope (H9).
6. **`collapse_swish` default cutoff (§8) — Resolved (no design change;
   numeric decision remains open by design).** Review confirms a
   2nd-order lowpass cannot brick-wall-match PHASE_SWISH's 8 kHz
   partition. No default cutoff is asserted by this document, unchanged
   — this is not a defect, it is an open numeric decision the review
   agrees should stay open pending measurement.
7. **`collapse_swish` vs. §4.2a scope (§8) — Resolved (no design
   change).** Review confirms the general/non-detector-driven trigger
   posture correctly avoids broadening the §4.2a exception. Whether a
   future story should propose a PHASE_SWISH-driven auto-trigger remains
   open for that future story, not this one.
8. **`collapse_swish` vs. [5a]/[5b] stacking (§8, AC16) — Resolved
   (design revised).** Review found "separate attributed deltas" alone
   insufficient — it doesn't say *which* [5a] band is affected. §8/§11
   revised to require the report explicitly name [5a] bands falling
   inside collapse_swish's derived −1 dB and −3 dB skirt, computed
   numerically from the deployed biquad (with the analog-prototype
   `0.713·cutoff_freq_hz` retained only as a cross-check, not the value
   used).
9. **Float32 mid-chain round-trip (§2) — Resolved (no design change).**
   Review confirms the derived ~−120 dBFS tolerance is inaudible and
   below dither floors; explicit-cast wrapper discipline is correct.
10. **Sub-frame input refusal (§5) — Resolved (no design change).**
    Review confirms 93 ms is not a plausible mastering-stage input and
    refuse-don't-pad/bypass is correct.
11. **L/R-independent processing (§7/§8, split by function):**
    - `repair_whistles`: **Resolved (concern retracted).** Review found
      requirements.md's stated risk physically incorrect — an identical
      LTI notch applied per-channel cannot introduce an inter-channel
      phase/level *relationship* shift (same class of reasoning error
      CLAUDE.md flags for DEF-203). Independent per-channel processing is
      confirmed fine; not carried forward as a concern in this document.
    - `collapse_swish`: **Resolved (not applicable).** Inherently M/S
      with one shared side-channel filter state — no per-channel linking
      question exists.
    - `shape_transients`: **Open, narrowed — elevated to a hard
      prerequisite for default-on.** §7 revised to require a
      stereo-linked control signal (`max(|L|,|R|)`, applied identically
      to both channels), not an optional note, given placement after
      [5a]/[5b]'s stereo-width correction.

**Net effect on default-on readiness**: unchanged from the original
document — all three stages remain default-off, and this story's scope is
unaffected. What has changed is that Blockers 3, 4, and the
`shape_transients` half of 11 now specify a **concrete required design**
(highpassed sidechain + stereo-linked control signal + tightened constant
range) rather than leaving those as open questions with no shape, and
Blocker 2 now specifies co-gating rather than leaving "raise the
threshold" as the implied fix.

---

## 15. Assumptions pending BA/Gate 1 confirmation

- `repair_whistles`'s per-flag action entries measure peak/RMS delta
  **within the crossfaded window** rather than across the whole file —
  read as the more informative choice per AC2 ("before/after measurements
  sufficient to see what changed"), but not explicitly specified in
  requirements.md.
- `crossfade_ms=50.0` for `repair_whistles`'s windowing reuses
  `stereo_crossfade_ms`'s value as a starting point without claiming it is
  independently derived for this purpose — flagged in §4, not asserted as
  settled.
- `prominence_floor_db` (new, §6/§9): only the constraint (> 6 dB) is
  derived here; the specific value is an open question for the mastering
  engineer, not assumed by this document.
- The `shape_transients` detector-sidechain highpass cutoff (150 Hz, §7)
  and the revised slow-envelope time constant (100-500 ms range, §7) are
  working values within a justified range, not empirically validated
  against reference material — flagged for implementation + listening
  validation before default-on, per §7.
- STORY-007 documentation reconciliation (requirements.md Open Question 8
  — `architecture.md` §7.3's "report-only" language, DOMAIN.md §4's
  "Cannot" table) is out of this document's scope to fix; noted here only
  so it is not lost.

---

## Revision history
- 2026-08-16: Initial version.
- 2026-08-16 (rev 2): Incorporated mastering-engineer Gate 1 methods
  review (`mastering-review-methods.md`). Changes: (1) §3 corrected two
  wrong numbers (−1.25 dB → −2.26 dB RMS; removed the incoherent "one
  channel's worth of modulation survives" framing) and corrected the
  "required test" paragraph's own reasoning (a scalar level test fails
  loudly today against the §2 tolerance — it does not "pass by
  accident" — but its failure is uninformative; the FFT-of-diff-envelope
  test is required for diagnostic specificity, not to catch a
  false-pass). No change to the required test's steps or the fix, both
  already correct. (2) §6/§9: added `prominence_floor_db` co-gate for
  `repair_whistles`, replacing the rejected "raise the 0.8 threshold"
  approach — **downstream impact: the python-developer's implementation
  must add this field and the co-gate check; a specific floor value is
  still needed from the mastering engineer.** (3) §7: corrected root
  cause of `shape_transients` flutter from "gain-law saturation" to
  "full-wave-rectified envelope followers responding to 2× the input
  fundamental"; added a required highpassed detector-sidechain design
  element (150 Hz working value) as a prerequisite alongside the gain-law
  fix; corrected the required test's target frequency from `f` to `2f`
  and added a near-corner (160-250 Hz) fundamental to the required test
  set to catch the sidechain design's own worst-case residual; tightened
  the slow-envelope constant guidance to 100-500 ms (was: unconstrained
  "empirically validate") — **downstream impact: this is a materially
  different C++ design than the previous revision specified (gain-law
  change alone is no longer sufficient); if any implementation work
  started against the prior architecture.md, it is stale and must
  incorporate the sidechain design.** (4) §7: elevated `shape_transients`
  stereo-linking from an informal note to a hard prerequisite for
  default-on (`max(|L|,|R|)` control signal), and added an explicit
  channel-count contract (`max` over channels degenerates correctly to
  mono, no special-case guard needed) — **downstream impact: new required
  design element, not present in any prior implementation.** (5) §8/§11:
  tightened the `collapse_swish`/[5a] stacking report requirement to
  explicitly name overlapping bands via −1 dB/−3 dB skirt points computed
  numerically from the deployed biquad's own transfer function (the
  analog-prototype `0.713·fc` formula is a cross-check only, not the
  computed value, since the digital biquad is a bilinear-transform warp
  of that prototype) — **downstream impact: `collapse_swish`'s
  action-entry contract gained a new field, `overlapping_5a_bands`.**
  (6) §14 rewritten to show per-Blocker resolved status so a fresh reader
  does not need to cross-reference the review document. (7) §1: fixed a
  stale internal cross-reference (collapse_swish stacking discussion is
  §8, not §5). No change to pipeline placement, the float32 boundary-cast
  design (§2), the windowed-crossfade design (§4), the sub-frame refusal
  (§5), or `collapse_swish`'s core semantics/placement (§8 apart from the
  noted report-field addition).
