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

## §6b. `repair_whistles` — harmonic guard (Blocker 3, Gate 2 finding)

**Context.** The OLA-fixed, time-windowed, confidence+prominence co-gated
implementation was validated on `Reference Tracks/Sunday Club.wav`
(2026-08-18). 439 STATIONARY_WHISTLE flags passed all existing gates.
Listening gate result: FAIL — "highly destructive." Root cause: the
STORY-007 detector cannot distinguish a genuine AI encoder whistle (a
narrow isolated tone with no harmonic context in the signal) from a
sustained musical tone or pad harmonic (which has a clear fundamental and
a harmonic series). 439 notches on musical content cause perceptual
destruction regardless of notch precision.

### 1. Option A confirmed closed

Raising `confidence_threshold` above 0.8 is rejected as already settled
in §6/Blocker 2: that number was calibrated to "surface a warning line,"
not "commit an audio edit," and raising it repeats the CLAUDE.md §7
"fix a wrong method by tuning its parameter" anti-pattern — recorded
closed at Gate 1 and not re-opened here.

**H6 classification (this fix):** Method addition. The harmonic guard is a
new, independent filter stage inserted between the existing co-gates and
the frequency-list build step. It uses a different signal property
(harmonic relatedness) rather than retuning any existing threshold.

### 2. Design: harmonic guard in `whistle_repair.py`

**Placement.** After confidence + prominence co-gates, before
`target_frequencies` is assembled:

```
matching_flags  (passed existing co-gates)
   → harmonic_guard_filter(matching_flags, audio, sample_rate)
   → forwarded_flags
   → target_frequencies
   → suno_dsp.repair_whistles
```

The guard operates on the pre-repair `audio` array (the `audio` parameter
to `apply_whistle_repair` before any DSP call). It is pure Python and
analysis-only — it does not alter `audio`.

**Algorithm — for each flag in `matching_flags`:**

*Step 1 — Analysis window selection.*

The analysis window is centred on the flag's midpoint and extended
symmetrically to `l_analysis` samples (a local variable derived below;
not a module-level constant, because it depends on `sample_rate`). This
uses surrounding audio context, which is valid because the harmonic guard
is analysis-only: expanding the window captures more of the sustained
musical content the guard needs to identify, at zero cost to the audio
path.

```python
start_sample = int(round(flag.timestamp_start_s * sample_rate))
end_sample   = int(round(flag.timestamp_end_s   * sample_rate))
mid          = (start_sample + end_sample) // 2
half         = l_analysis // 2
an_start     = max(0, mid - half)
an_end       = min(n_samples, an_start + l_analysis)
segment      = audio[an_start:an_end]   # float64, may be shorter than l_analysis if near edges
```

If `segment` is shorter than `l_analysis` after clamping (only possible
if the audio buffer is very short — §5 already guarantees
`n_samples >= 4096`), the FFT is zero-padded to `l_analysis` for the
transform only.

*Step 2 — Mono-safe magnitude spectrum.*

A time-domain channel mean can null an anti-correlated (L/R phase-inverted)
tone, which is a plausible encoder artefact pattern. Combine in the
magnitude domain by taking the element-wise maximum across channels:

```python
n_fft = l_analysis
if audio.ndim == 2:
    ch_mags = [np.abs(np.fft.rfft(segment[:, c], n=n_fft))
               for c in range(audio.shape[1])]
    spectrum = np.max(np.stack(ch_mags), axis=0)   # max per bin across channels
else:
    spectrum = np.abs(np.fft.rfft(segment, n=n_fft))
freqs = np.fft.rfftfreq(n_fft, d=1.0 / sample_rate)
```

*Step 3 — Log-magnitude with programme-level-relative floor.*

An absolute floor (e.g. `1e-9`) corrupts prominence estimates on spectra
where HF bins sit legitimately below that floor; use a floor relative to
the segment's own peak:

```python
eps_floor = spectrum.max() * 1e-6   # -120 dBFS relative to the segment peak
log_spec  = 20.0 * np.log10(spectrum + eps_floor)
```

The `1e-6` multiplier (−120 dBFS re segment peak) is chosen because it
falls below programme material at any reasonable level and below the
dither floor established in §2 (~−120 dBFS at 20-bit equivalent), so it
cannot create artefactual peaks.

*Step 4a — Candidate fundamental detection (below flagged frequency).*

Find spectral peaks below the flagged frequency using `scipy.signal.
find_peaks` with local-prominence gating:

```python
f_flagged    = flag.details["frequency_hz"]
flag_bin     = int(round(f_flagged * n_fft / sample_rate))
peak_idxs, _ = find_peaks(
    log_spec[:flag_bin],
    prominence=_DETECTOR_PROMINENCE_FLOOR_DB,   # 6.0 dB, from whistle_repair.py line 30
)
```

The `_DETECTOR_PROMINENCE_FLOOR_DB = 6.0` value is **reused**, not
independently re-derived for this purpose. Justification for reuse: the
STORY-007 detector emits STATIONARY_WHISTLE only when a tone is ≥ 6 dB
locally prominent in its spectrum; "a candidate musical fundamental must
clear the same local-prominence bar the detector itself uses to call
something a tonal peak" is a reasonable anchor. This reuse is flagged for
mastering-engineer review before implementation (see §6b.6) — it may need
to be raised if the guard fires on noise peaks.

*Step 4b — Full-spectrum peak set for sibling confirmation.*

The sibling confirmation step (Step 5) checks for spectral energy at up to
four sibling targets per candidate f0. To avoid repeated `find_peaks`
calls, compute all prominent peaks in the full `log_spec` once per flag
and cache the result as an array of peak frequencies:

```python
all_peak_idxs, _ = find_peaks(
    log_spec,
    prominence=_DETECTOR_PROMINENCE_FLOOR_DB,   # same threshold, same justification
)
all_peak_freqs = freqs[all_peak_idxs]   # shape (K_all,) — frequencies of all prominent peaks
```

This is computed once per flag, before the candidate-f0 loop, and reused
for every sibling check within that flag's loop. Note: `all_peak_freqs`
will include the flagged frequency's own bin if it is locally prominent.
Self-match cannot satisfy a sibling test by construction: the sibling
window is `|all_peak_freqs - sibling_f| <= delta·f0`, and
`|f_flagged - sibling_f| = f0 > delta·f0 = 0.08·f0`, so the flagged bin
is always further from any sibling than the window allows. No defensive
exclusion of the flagged bin from `all_peak_freqs` is required.

*Step 5 — Harmonic ratio test with sibling confirmation.*

```python
suppress = False
for idx in peak_idxs:
    f0 = freqs[idx]
    if f0 <= 0.0:
        continue
    r         = f_flagged / f0
    n_nearest = int(round(r))
    if 1 <= n_nearest <= _HARMONIC_GUARD_N_MAX:
        if abs(r - n_nearest) <= _HARMONIC_GUARD_DELTA:
            # Harmonic ratio matched. Require sibling confirmation before suppressing
            # to prevent K-inflation (see §6b.2 discrimination argument below).
            # Four sibling targets: n_nearest ± 1 (adjacent) and n_nearest ± 2 (widened).
            # The ±2 targets cover odd-harmonic-only timbres (square/pulse waves) where
            # n±1 are even multiples and structurally absent, but n±2 are odd multiples
            # and structurally present.
            sibling_confirmed = False
            for sibling_f in [f_flagged + f0, f_flagged - f0,
                               f_flagged + 2.0 * f0, f_flagged - 2.0 * f0]:
                if sibling_f <= 0.0 or sibling_f >= sample_rate / 2.0:
                    continue   # out of Nyquist range; skip without failing
                if abs(sibling_f - f0) <= _HARMONIC_GUARD_DELTA * f0:
                    continue   # self-confirming guard: sibling target is indistinguishable
                               # from the candidate fundamental and provides no independent
                               # evidence of a harmonic series.
                               # Fires at n_nearest=2: f_flagged - f0 = f0 exactly.
                               # Fires at n_nearest=3: f_flagged - 2*f0 = f0 exactly.
                # Contract: sibling_f is accepted if it clears the same local-prominence
                # gate used for candidate peaks (_DETECTOR_PROMINENCE_FLOOR_DB dB).
                # Implementation may use the all_peak_freqs array (frequency-domain match
                # within delta*f0 Hz) or a direct point-check at the sibling bin in
                # log_spec — both satisfy this contract.
                if np.any(np.abs(all_peak_freqs - sibling_f) <= _HARMONIC_GUARD_DELTA * f0):
                    sibling_confirmed = True
                    break
            if sibling_confirmed:
                suppress = True
                break
            # No sibling found for this (f0, n_nearest): continue loop to next candidate f0.
```

The deviation is expressed in **harmonic-number units**: `|f_flagged/f0 −
n_nearest| <= delta`. This makes coverage `2·delta` per harmonic interval,
constant and independent of n. A relative-frequency formulation
(`|f_flagged − n·f0| / f_flagged <= epsilon`) has coverage `2·epsilon·n`,
which saturates (at epsilon = 0.06, n = 9, coverage exceeds 100% — every
frequency is "harmonic-related") and must not be used.

*Step 6 — No-op fall-through.*

There are two distinct fall-through cases, both leaving `suppress = False`
and the flag forwarded to the notch stage:

1. `peak_idxs` is empty (silence, pure noise, or a genuinely isolated
   tone with no strong spectral neighbours below it): the loop body never
   executes. This is the required behaviour for a true AI encoder whistle
   with no harmonic context.
2. `peak_idxs` is non-empty but no candidate f0 produces a sibling-
   confirmed match: the loop runs to exhaustion without setting
   `suppress = True`. This distinguishes genuine musical harmonics (which
   have spectral siblings at regular f0 spacing above and below the
   flagged frequency) from coincidental tonal peaks that happen to have a
   harmonic ratio to the flag but no harmonic neighbourhood.

**Derivation of `_HARMONIC_GUARD_DELTA` and `_HARMONIC_GUARD_N_MAX`.**

Two constraints bound the pair:

*Lower bound — notch protection.* At harmonic n, the guard's Hz window
around that harmonic is `delta · f0` (since
`|f_flagged − n·f0| = |r − n| · f0 <= delta · f0`). The notch
half-bandwidth at Q ≈ 120 is `f_flagged / (2·Q) ≈ n·f0 / 240`. For the
guard to protect a harmonic that the notch will damage, the tolerance
window must span at least the notch half-bandwidth at the highest harmonic
checked:

```
delta · f0  >=  N_MAX · f0 / (2 · Q)
delta       >=  N_MAX / (2 · Q)
delta       >=  10 / 240  ≈  0.042
```

*Discrimination — why harmonic ratio alone is insufficient, and why
sibling confirmation restores it.* The harmonic ratio test has coverage
`2·delta` per harmonic interval for a single candidate fundamental (K = 1).
**On dense club material, `find_peaks` with a 6 dB local-prominence gate
returns K ≥ 15–30 qualifying peaks per flag window.** At K = 20 candidates,
the probability that the harmonic ratio test alone suppresses any frequency
by coincidental harmonic alignment is:

```
P(suppress by ratio alone | K = 20) = 1 − (1 − 2·delta)^K = 1 − (0.84)^20 ≈ 0.97
```

A "2·delta << 1 → discrimination" argument that holds at K = 1 collapses
at K ≥ 10, regardless of delta. The harmonic ratio test alone cannot
discriminate on dense material.

**The sibling confirmation is the discriminating mechanism, not delta.**
A genuine musical fundamental at f0 produces energy at integer multiples
of f0 across its harmonic series: if `f_flagged = n·f0`, at least one of
the four sibling targets `(n ± 1)·f0` or `(n ± 2)·f0` will be
structurally present — for full-harmonic (sawtooth-type) instruments all
four are present; for odd-harmonic-only (square-wave) instruments the ±2
targets are present. A coincidental peak at f0 has no structural reason to
produce energy at any of those frequencies — there is no physical mechanism
linking a noise peak to harmonically spaced frequencies. The false-
suppression rate under sibling confirmation is **not derivable from delta
alone** — it depends on the empirical peak density and harmonic structure
of the material. This is precisely what the §6b.6 null control measures.
No numeric false-suppression probability is asserted here (H4).

**Odd-harmonic mitigation — selected and implemented (rev 6).**

Rev 5 identified that the adjacent-only (±f0) sibling rule fails for
instruments with 50% duty cycle (square waves, pulse pads): if
`f_flagged = n·f0` with n odd, the targets `(n ± 1)·f0` are even multiples
of the true fundamental — structurally absent from an odd-harmonic series.
The mastering engineer selected the **±2·f0 widening** as the mitigation
(rev 6, second review). Parity argument for correctness: `(n ± 2)·f0`,
with n odd, are also odd multiples of the true fundamental — structurally
present in the series. The self-confirming guard (also added in rev 6)
ensures that the widened targets cannot trivially re-confirm the candidate
fundamental itself:

- At n_nearest = 2: `f_flagged − f0 = f0` (self-confirming, skipped by
  the guard).
- At n_nearest = 3: `f_flagged − 2·f0 = f0` (self-confirming, skipped).
- All other n_nearest values: no widened target reduces to f0, so the
  guard never fires spuriously.

Example verification (square-wave pad, 440 Hz fundamental, flag at 1320 Hz,
n_nearest = 3): `f_flagged + 2·f0 = 1320 + 880 = 2200 Hz` (5th harmonic,
odd multiple, structurally present). Self-confirming check:
`|2200 − 440| = 1760 >> 35.2 Hz (delta·f0)` — not self-confirming. Sibling
confirmed, suppress = True. The mitigation works for this case.

**Chosen values: `_HARMONIC_GUARD_DELTA = 0.08`, `_HARMONIC_GUARD_N_MAX = 10`.**

Verification of constraints:

| Constraint | Requirement | Value | Status |
|---|---|---|---|
| Notch protection | delta >= N_MAX/(2·Q) = 0.042 | 0.08 | Satisfied |
| Discrimination (ratio alone) | 2·delta << 1 at K=1 only | 0.16 — collapses at K>1 | Insufficient alone |
| Discrimination (with sibling, full-harmonic content) | At least one of four sibling targets structurally present; coincidental noise peak lacks them | Step 5 four-target loop; empirically validated via §6b.6 | Yes |
| Discrimination (with sibling, odd-harmonic-only content) | n±2 targets are odd multiples — structurally present | Resolved by ±2·f0 widening (rev 6) | Yes |

At `_HARMONIC_GUARD_N_MAX = 10`, the minimum candidate fundamental that can
protect a flagged frequency is `f_flagged / (N_MAX + 0.5)` (below which
`n_nearest > N_MAX` and the range check eliminates the candidate). The
true `f0_min` for the analysis-length derivation is therefore
`f_min_flag / N_MAX`, where `f_min_flag` is the lowest expected flagged
frequency — see L derivation below.

**Open risk — N > 10 harmonics.** A flagged frequency that is the Nth
harmonic (N > 10) of a bass fundamental is not protected. Example:
6400 Hz as the 32nd harmonic of a 200 Hz pad — at f0=200 Hz, r = 32,
n_nearest = 32 > N_MAX = 10, the range check fires `continue` before the
sibling block is reached. The sibling check provides no mitigation here:
it cannot run unless the harmonic ratio test passes the range gate first.
If the offline acceptance check (§6b.6 item 1) shows a non-trivial
fraction of real Sunday Club flags coming from this N>10 pattern, N_MAX
must be raised.

**Derivation of `l_analysis` (local variable, not a module-level
constant).**

The FFT bin width must not exceed half the harmonic-guard tolerance in Hz
at the smallest candidate fundamental, or a harmonic match may fall
between bins and be missed.

The harmonic test's range check (`1 <= n_nearest <= N_MAX`) means only
candidate fundamentals above `f_flagged / (N_MAX + 0.5)` participate in
the tolerance check. So the effective `f0_min` is
`f_min_flag / N_MAX`, where `f_min_flag` is the lowest flagged frequency
the guard is designed to handle. AI encoder whistles from this source
material (Suno) are expected to occur predominantly above 2000 Hz; flags
at lower frequencies overlap substantially with normal programme content.
Using `f_min_flag = 2000 Hz`:

```
f0_min = f_min_flag / N_MAX = 2000 / 10 = 200 Hz
required bin width  <=  delta · f0_min / 2  =  0.08 · 200 / 2  =  8.0 Hz
l_analysis          =   2^ceil(log2(sample_rate / 8.0))
```

At 44100 Hz: l_analysis = 2^ceil(log2(5513)) = **8192**. At 48000 Hz:
8192. At 96000 Hz: 16384.

```python
l_analysis = 1 << int(np.ceil(np.log2(sample_rate / 8.0)))
# 44100 Hz → 8192;  48000 Hz → 8192;  96000 Hz → 16384
# Local variable: computed once per apply_whistle_repair call from sample_rate.
```

**Consequence of f_min_flag = 2000 Hz assumption**: for flagged
frequencies below 2000 Hz, the actual minimum resolvable fundamental
(200 Hz) may not resolve candidate fundamentals in the range
`[f_flagged/N_MAX, 200 Hz]` with the required precision. This is
acceptable for this project because sub-2 kHz AI whistle flags are
expected to be rare; the offline acceptance check (§6b.6 item 1) will
reveal if this assumption is wrong.

### 3. Config field

`prominence_floor_db` (existing, required-explicit in §6/§9) remains
unchanged. It must still be set before the stage can run.

No new config field is added for the harmonic guard's internal constants.
`_HARMONIC_GUARD_DELTA` and `_HARMONIC_GUARD_N_MAX` are module-level
constants with derivations shown above; `l_analysis` is a local variable
computed per call from `sample_rate`. All values are physically motivated
but not yet empirically validated against reference programme material —
covered by the mastering-engineer handoff in §6b.6.

Adding a `None`-defaulted config field (per §9's standing discipline)
would be premature: that pattern is for values with no defensible default.
Here the derived values are shown; the open question is empirical
calibration, not derivation. If the mastering engineer's review produces
evidence that a different range is required, this section must be revised
and a config field added at that revision.

### 4. Implementation scope

Python-only addition to `mastering/whistle_repair.py`. No change to
`src_cpp/spectral_repair.cpp`. No change to STORY-007's detector, its
thresholds, or its `ArtifactFlag` output schema.

Required imports: `numpy.fft.rfft` and `numpy.fft.rfftfreq` (already
available), and `scipy.signal.find_peaks` (add import; consistent with the
project's library guidance that `scipy.signal` is the analysis library).

The harmonic guard algorithm is fully specified in §6b.2 (Step 5, four-
target sibling loop with self-confirming guard). Implementation may
proceed. The offline acceptance check in §6b.6 item 1 must still be run
and must pass before the stage is cleared for default-on.

### 5. Required tests

Three synthetic tests are required. All test through the `apply_whistle_repair`
interface — the harmonic guard is not callable independently.

**(a) Harmonic suppression — guard fires.**

Signal: 3 seconds at 44100 Hz, a sawtooth-approximation:
`sum(sin(2·pi·n·440·t) / n for n in 1..10)`, giving a 440 Hz fundamental
with harmonics at 880, 1320, 1760, 2200, 2640, 3080, 3520, 3960, 4400 Hz.
All harmonics are above the `_DETECTOR_PROMINENCE_FLOOR_DB` floor.

Fake flag: `ArtifactFlag(artifact_type="STATIONARY_WHISTLE",
confidence_score=0.85, details={"frequency_hz": 1320.0,
"prominence_db": 15.0}, timestamp_start_s=0.5, timestamp_end_s=2.5)`.
Config: `prominence_floor_db=10.0`.

Harmonic ratio check: 1320/440 = 3.0, n_nearest=3, deviation=0.0 ≤ 0.08
— passes. Sibling confirmation: `f_flagged + f0 = 1760 Hz` (4th harmonic,
present; self-confirming check: |1760−440| = 1320 >> 35.2 Hz) — sibling
confirmed at first target. `suppress = True`.

Note: add a square-wave variant of this test (odd harmonics only at 440 Hz:
440, 1320, 2200, 3080, 3960 Hz) with the same flag at 1320 Hz. With the
±2·f0 widening: `f_flagged + 2·f0 = 1320 + 880 = 2200 Hz` (5th harmonic,
odd multiple, present in the series; self-confirming check:
|2200−440| = 1760 >> 35.2 Hz). Sibling confirmed, suppress = True. The
square-wave variant must now SUPPRESS (not forward) the flag — this
verifies the ±2·f0 mitigation is implemented correctly.

Assert: `actions[-1].harmonic_guard_suppressed` contains 1320.0 Hz.
Assert: `actions[-1].frequencies_notched` does not contain 1320.0 Hz.
Assert: `np.array_equal(output, audio)` — when the guard suppresses all
flags, `target_frequencies` is empty and `apply_whistle_repair` returns
`audio.copy()` immediately (whistle_repair.py:162-164) without calling
into `suno_dsp`. The §2 float32 tolerance does not apply here; there is
no DSP round-trip, and the assertion is exact bit-identity.

**(b) Isolated tone pass-through — guard does not fire.**

Signal: 3 seconds at 44100 Hz, a single pure sine at 6427 Hz. No other
energy above `_DETECTOR_PROMINENCE_FLOOR_DB` in the spectrum below
6427 Hz.

Fake flag: `ArtifactFlag(artifact_type="STATIONARY_WHISTLE",
confidence_score=0.85, details={"frequency_hz": 6427.0,
"prominence_db": 15.0}, timestamp_start_s=0.5, timestamp_end_s=2.5)`.
Same `prominence_floor_db`.

No candidate fundamentals below 6427 Hz clear the prominence gate, so
`peak_idxs` is empty. No-op fall-through (Step 6, case 1).

Assert: `actions[-1].harmonic_guard_suppressed` is empty.
Assert: `actions[-1].frequencies_notched` contains 6427.0 Hz (flag
forwarded and notched).

**(c) Negative control (H3): strong bass fundamental present plus a strong
within-N_MAX candidate, genuinely isolated whistle at a non-harmonic
frequency — guard does not fire.**

Signal: 3 seconds at 44100 Hz, mixing: (i) a 70 Hz sawtooth-approximation
with harmonics at 70, 140, ..., 700 Hz; (ii) a strong isolated sine at
500 Hz; and (iii) an isolated sine at 4327 Hz.

The 500 Hz peak is the degeneracy probe: it is within N_MAX=10 reach of
4327 Hz (`4327/500 = 8.654`, `n_nearest = 9`), but the tolerance check
fails (`|8.654 − 9| = 0.346 > delta = 0.08`). If delta were ≥ 0.35, the
500 Hz peak would suppress the whistle — exactly what this test detects as
a tolerance-degeneracy failure.

The 70 Hz harmonic series peaks whose n_nearest is in range for 4327 Hz:
4327/700 ≈ 6.18 → n=6, |0.18| > 0.08; 4327/630 ≈ 6.87 → n=7, |0.13| >
0.08; 4327/560 ≈ 7.73 → n=8, |0.27| > 0.08; 4327/490 ≈ 8.83 → n=9,
|0.17| > 0.08; 4327/420 ≈ 10.3 → n=10, |0.30| > 0.08. All fail the
tolerance check; the sibling check never runs for any of them.

Fake flag at 4327 Hz (same confidence/prominence as (b)).

Assert: `actions[-1].harmonic_guard_suppressed` is empty.
Assert: `actions[-1].frequencies_notched` contains 4327.0 Hz.

**Note: test (c) cannot detect K-inflation failure — not because K ≤ 12
is small (at K=12, `1 − (0.84)^12 ≈ 0.88`, so K-inflation is already
fully active at that K) but because test (c)'s frequencies are hand-picked
to be non-coincident with 4327 Hz: none of the 12 peaks land within delta
of any harmonic of that frequency. Coincidental alignment with arbitrary
frequencies on real programme material is what the offline null-control
measures; this test cannot and does not test for it.**

### 6. Mastering-engineer handoff

The harmonic guard method is fully specified and cleared for implementation
(second review, rev 6). The following items remain for mastering-engineer
review before the stage is cleared for default-on:

**Item 0 — Odd-harmonic sibling rule: Resolved (rev 6).** The mastering
engineer selected ±2·f0 widening as the mitigation. This is now specified
in Step 5. Implementation may proceed against the rev 6 algorithm.

1. **Offline acceptance check with null control.** Run the guard offline
   over the 439 Sunday Club STATIONARY_WHISTLE flags. Report all four of:
   (a) Suppression count on the 439 real flags.
   (b) Suppression count for 439 randomly selected frequencies in the
       same 2–12 kHz range, run against the same audio (same flag
       timestamps, random frequencies substituted for the detected
       frequencies). This null control measures how often the guard
       suppresses a non-whistle frequency purely by coincidence on this
       material.
   (c) The distribution of K (number of peaks clearing the
       `_DETECTOR_PROMINENCE_FLOOR_DB` prominence gate in the analysis
       window) per flag window, reported as median, 90th percentile, and
       maximum.
   (d) Of the real flags **not suppressed** by the guard: how many found
       a harmonic-ratio match (both the range check
       `1 <= n_nearest <= N_MAX` and the tolerance check
       `abs(r - n_nearest) <= delta` passed) but were not suppressed
       because sibling confirmation failed? This separates "no prominent
       candidate fundamental found below the flag" (guard's intended
       fall-through, Step 6 case 1) from "harmonic match confirmed but
       no sibling confirmed" (Step 6 case 2). A non-trivial count here
       warrants investigation into whether N_MAX or the prominence
       threshold needs adjustment.

   **Acceptance criterion**: if the suppression rate for real flags is
   within 20 percentage points of the suppression rate for random
   frequencies (null control), the guard has no discriminating power on
   this material and the algorithm must be further revised before
   implementation. If median K > 10, K-inflation is active on this
   material; verify that the sibling confirmation is correctly reducing the
   suppression rate relative to the null control (a meaningful gap between
   real-flag and null-control rates confirms the sibling check is
   functioning). If suppression count is 0 on real flags, the strength
   threshold or N_MAX is too restrictive.

2. **Strength threshold (prominence >= 6.0 dB local prominence)**: this
   reuses `_DETECTOR_PROMINENCE_FLOOR_DB` as a convenient derivation, not
   an independent calibration. If the guard suppresses genuine whistles
   because a noise peak triggers it, this threshold must be raised; if the
   guard misses musical harmonics because their fundamental does not clear
   this floor, it must be lowered. Both failure modes are visible in the
   offline acceptance check (item 1 above).

3. **f_min_flag = 2000 Hz assumption**: this determines the FFT analysis
   length. If STORY-007 flags whistles at frequencies below 2000 Hz where
   the relevant musical fundamentals are below 200 Hz, `l_analysis` must
   be increased and the derivation revised accordingly.

4. **The stage remains `enabled: bool = False` by default.** Enabling the
   stage still requires an explicit `prominence_floor_db` value per §6/§9.
   The harmonic guard does not change this requirement.

### Action-log contract addendum (§6b only)

The existing `WhistleRepairSummary` (§11) gains two fields introduced by
the harmonic guard. These are recorded here and should be reconciled into
§11's rendering contract when §11 is next revised:

```python
harmonic_guard_suppressed: list[float] = field(default_factory=list)
    # frequencies (Hz) suppressed by the guard; empty if guard fired on none
harmonic_guard_suppressed_count: int = 0
    # len(harmonic_guard_suppressed); present for operator convenience
```

These fields belong to the summary entry (`stage_ran=True`) appended to
`actions`. `frequencies_notched` and `stage_ran` in §11 are unchanged.

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
- `repair_whistles`'s harmonic guard tests (§6b) use synthetic signals
  with analytically known harmonic structure, making the guard's pass/
  suppress decision verifiable without reference material. Test (c)'s
  within-N_MAX-but-outside-delta near-miss (500 Hz peak, 4327 Hz flag)
  provides a degeneracy probe that fails loudly if delta is ≥ 0.35.
  Test (c) cannot detect K-inflation failure — not because K ≤ 12 is
  small (at K=12, `1 − (0.84)^12 ≈ 0.88`, so K-inflation is already
  fully active at that K) but because test (c)'s frequencies are hand-
  picked to be non-coincident with 4327 Hz: none of the 12 peaks land
  within delta of any harmonic of that frequency. Coincidental alignment
  with arbitrary frequencies on real programme material is what the
  offline null-control measures. The three synthetic tests (a), (b), (c)
  are necessary but not sufficient correctness checks; the offline null-
  control acceptance test from §6b.6 item 1 is the discriminating-power
  check that catches K-inflation failure on real material. The square-wave
  variant of test (a) verifies the ±2·f0 odd-harmonic mitigation (rev 6):
  it must now suppress, not forward, the flag.

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
- §6b harmonic guard: `_HARMONIC_GUARD_DELTA = 0.08`,
  `_HARMONIC_GUARD_N_MAX = 10`, the `_DETECTOR_PROMINENCE_FLOOR_DB = 6.0`
  strength threshold (reused), and `f_min_flag = 2000 Hz` (determines
  `l_analysis`) are physically derived or reused-with-justification but
  not empirically validated against the Sunday Club flag distribution —
  flagged for mastering-engineer review in §6b.6 before default-on.
- §6b harmonic guard sibling rule: the ±2·f0 four-target form (plus self-
  confirming guard) is the selected algorithm as of rev 6. The odd-harmonic
  mitigation question is resolved. Implementation may proceed against this
  specification.

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
- 2026-08-19 (rev 3): Added §6b — `repair_whistles` harmonic guard
  (Blocker 3, Gate 2 finding). Context: Gate 2 listening test returned
  FAIL ("highly destructive") on Sunday Club — 439 STATIONARY_WHISTLE
  flags passed all existing co-gates, producing 439 notches on musical
  content (synth pads, pad harmonics) indistinguishable by the detector
  from genuine AI encoder whistles. **Method addition (H6): the harmonic
  guard is a new, independent filter stage between the existing co-gates
  and `target_frequencies` assembly — not a parameter change to any
  existing threshold.** Design: FFT-based spectral peak finding over an
  extended analysis window centred on each flag; if the flagged frequency
  is within `_HARMONIC_GUARD_DELTA = 0.08` harmonic-number-units of the
  Nth harmonic (N = 1..`_HARMONIC_GUARD_N_MAX = 10`) of any spectral peak
  that clears `_DETECTOR_PROMINENCE_FLOOR_DB = 6.0` dB local prominence,
  the flag is suppressed; otherwise it passes through. Delta and N_MAX are
  derived from two inequalities: notch-protection lower bound
  (delta >= N_MAX/(2·Q) = 0.042) and discrimination upper bound
  (2·delta = 0.16 << 1). The harmonic-number-unit deviation formulation
  is essential — a relative-frequency tolerance saturates above N~9 and
  would suppress all flags on any track with a strong bass fundamental.
  Magnitude spectra are combined across channels by element-wise max (not
  time-domain mean) to avoid phase-cancellation nulling. Log-magnitude
  floor is relative to the segment peak (−120 dBFS) rather than absolute.
  `l_analysis` is a local variable (not a module-level constant) derived
  from `f_min_flag = 2000 Hz` assumption: `l_analysis = 2^ceil(log2(
  sample_rate/8))` (8192 at 44.1 kHz). **Downstream impact on
  implementation:** `whistle_repair.py` must add the harmonic guard filter
  between the existing prominence-gate loop and the `target_frequencies`
  build step; `scipy.signal.find_peaks` import required; `WhistleRepairSummary`
  gains `harmonic_guard_suppressed: list[float]` and
  `harmonic_guard_suppressed_count: int` fields (these are documented in
  §6b's action-log contract addendum and should be reconciled into §11
  when §11 is next revised). Test (a): suppress-and-assert-exact-equality
  (no DSP call when list is empty, so `np.array_equal` not float32
  tolerance). Test (c) uses a within-N_MAX-but-outside-delta near-miss
  (500 Hz strong peak, flag at 4327 Hz, 4327/500=8.654, deviation=0.346
  > 0.08) as the degeneracy probe. §15 updated with harmonic guard
  assumption notes.
- 2026-08-19 (rev 4): §6b revised — sibling confirmation added to
  harmonic guard per mastering-engineer review (Gate 2 blocking finding:
  K-inflation). **Problem**: at K = 20 qualifying peaks per flag window
  (typical for dense club material), `P(suppress by harmonic ratio alone)
  ≈ 1 − (0.84)^20 ≈ 0.97` regardless of musical content — the harmonic
  ratio test alone cannot discriminate on this material. **Method addition
  (H6)**: sibling confirmation required between the harmonic match and the
  `suppress = True` assignment. After a harmonic match at (f0, n_nearest),
  the guard checks whether at least one of `f_flagged ± f0` carries a
  prominently present peak. If no sibling is confirmed, the loop continues
  to the next candidate f0 rather than suppressing. Step 4 split into 4a
  and 4b. Self-match excluded by construction. Step 6 updated to document
  both fall-through cases. Discrimination table updated. N>10 open-risk
  paragraph corrected. §6b.6 item 1 acceptance criterion replaced with
  null-control methodology. No change to delta=0.08, N_MAX=10. **Downstream
  impact**: any implementation written against rev 3 is stale and must
  incorporate the sibling confirmation before review.
- 2026-08-19 (rev 5): §6b.2 — identified blocking open risk: the
  adjacent-only (±f0) sibling rule fails systematically for odd-harmonic-
  only timbres (square waves, pulse pads). Parity argument: if
  f_flagged = n·f0 with n odd, then (n±1)·f0 are even multiples — absent
  from the series. Sibling confirmation fails for every candidate, on
  every flag, for this timbre class. Two candidate mitigations offered for
  mastering-engineer decision: (a) widen to ±2·f0; (b) generalise to any
  m·f0, m ≠ n_nearest. §6b.6 added Item 0 (implementation blocked until
  mitigation selected) and item 1(d) (sibling-rejection count). §13
  corrected K-inflation reasoning. Discrimination table updated.
  **Downstream impact**: implementation blocked pending mastering-engineer
  resolution of Item 0.
- 2026-08-19 (rev 6): §6b.2 Step 5 revised per second mastering-engineer
  review — **Proceed to implementation.** Two targeted changes: (1)
  **±2·f0 sibling targets added** (odd-harmonic mitigation selected).
  Sibling loop now checks four targets:
  `[f_flagged + f0, f_flagged - f0, f_flagged + 2*f0, f_flagged - 2*f0]`.
  Parity argument: for an odd-harmonic series with n_nearest odd,
  (n±2)·f0 are also odd multiples and structurally present. Example
  verified: 440 Hz square-wave pad, flag at 1320 Hz (n=3),
  f_flagged + 2·f0 = 2200 Hz (5th harmonic, present). (2) **Self-
  confirming sibling guard added**. Inside the sibling-target loop, skip
  any target where `abs(sibling_f - f0) <= delta * f0` — the target is
  indistinguishable from the candidate fundamental and provides no
  independent evidence. Fires at n_nearest=2 (f_flagged − f0 = f0) and
  n_nearest=3 (f_flagged − 2·f0 = f0). Odd-harmonic risk note in §6b.2
  updated to show mitigation selected. §6b.4 implementation blocker
  removed. §6b.5 test (a) square-wave variant updated: must now SUPPRESS
  (not forward) the flag. §6b.6 Item 0 marked resolved. §15 assumption
  updated. §13 updated with square-wave variant note. DEF-009-001 remains
  Open pending implementation and listening gate. **Downstream impact**:
  the Step 5 sibling loop in `whistle_repair.py` must implement the four-
  target form with the self-confirming guard. Any implementation begun
  against rev 5 is stale at this loop only; all other design is unchanged.
