# STORY-001: World-class streaming master for Suno tracks — Architecture

Status: v5 — resolves a residual **Architectural** defect surfaced during QA
re-verification of the v4 true-peak FIR filter (defects.md DEF-002,
verification note 2026-08-01): the filter's passband is verified flat
(<0.01 dB) only up to ~80% of original Nyquist, not the full
~99.9%-of-Nyquist aspirational target architecture.md v4 §2/§7 had implied,
and closing that fully is computationally infeasible within the 5-minute NFR
budget (~40,000+ taps). v5 formalizes a tiered ripple-vs-frequency envelope
that matches the verified, already-implemented filter behavior, documents
the residual near-Nyquist under-read risk explicitly (bounded, safety-
relevant direction, but narrow in practice — see §9 risk #3), and requires
**no code change** — `true_peak.py` is already conformant; only the
aspirational test target in §7 needed correcting to match reality. See §12
Revision history for full detail.

v4 (unchanged by this revision, retained below) resolved the two residual
Architectural defects raised by python-developer's investigation of DEF-001
and DEF-002 (defects.md, 2026-07-31): (1) the loudness/DR/true-peak solver's
-16 LUFS floor could not be held simultaneously with the DR floor for some
legitimate high-crest-factor long-form fixtures (TC-015, TC-130) — resolved
by making the -16 LUFS value a soft, reported threshold rather than a hard
solver constraint (see §1, §11); (2) `soxr`'s near-Nyquist passband
attenuation affected true-peak accuracy at some oversampling factors
(TC-022) — resolved by replacing `soxr` with a purpose-built FIR
interpolation filter for the true-peak path specifically, while `soxr`
remains the resampler elsewhere (see §2, §9 risk #3).

Based on requirements.md v3 (all open questions, including #11/#12 raised
during v4's own defect resolution, resolved).

This document is the build contract for the python-developer and the
reference frame for the test-case-writer/QA agent. Where I've had to make a
call the BA didn't fully specify, it's called out explicitly rather than
silently baked in — see §8, §10, and §11.

## 1. Pipeline design

The tool is a single-file, offline (non-real-time) batch pipeline with two
passes over the audio (before-measurement, after-measurement) around one
in-memory mastering chain. Stage order matters and is fixed as follows:

```
[1] Ingest & Validate
      ↓
[2] Pre-Master Analysis  ──────────────► "before" Measurements
      ↓ (same buffer, now mutated only from here on)
[3] Resample (conditional: only if source rate ∉ {44.1kHz, 48kHz})
      ↓
[4] Corrective EQ (frequency-balance correction)
      ↓
[5] Stereo/Mono Correction (targeted narrowing of offending elements)
      ↓
[6] Loudness/Limiting (iterative LUFS/true-peak/DR reconciliation)
      ↓
[7] Dither & Bit-Depth Conversion (→ 24-bit)
      ↓
[8] Export (write WAV, re-inject preserved metadata/BWF chunks)
      ↓
[9] Post-Master Analysis  ──────────────► "after" Measurements
      (re-loads the file written in [8] from disk — see §3)
      ↓
[10] Report Generation (pre + post + corrective-action log)
```

Stage responsibilities:

- **[1] Ingest & Validate** — owns reading the source WAV, detecting
  sample rate/bit depth/format (PCM16/24/float32)/channel count, extracting
  every non-audio RIFF chunk verbatim for later re-injection, and failing
  fast (with a clear error, not a crash) on corrupt headers, zero-length
  audio, or unreadable files. This is also where the "read-only" contract
  on the input file is enforced (see §4).
- **[2] Pre-Master Analysis** — owns AC1: computes all six assessment
  criteria (LUFS, true peak, DR, frequency balance, stereo/phase, clipping)
  against the *original, untouched* audio, at the *original* sample rate.
  This must run before stage [3]'s resample, because the "before" report
  has to reflect what the producer actually exported from Suno, not a
  resampled proxy of it.
- **[3] Resample** — only invoked if source rate is not 44.1 or 48 kHz
  (per resolved spec, default to 44.1 kHz in that case). Runs first in the
  mastering chain (not analysis) so every downstream DSP stage — filter
  coefficient design, oversampling ratios for true-peak/limiting — operates
  against one fixed, final sample rate for the rest of the pipeline.
- **[4] Corrective EQ** — owns AC7: applies capped (≤3 dB/move), logged
  parametric correction for thin-low-end/muddiness/harshness flags raised
  in [2]. Runs before stereo correction and loudness so that later stages
  see the tonally-corrected signal (loudness/limiting should be gain-staged
  against the final tonal balance, not the raw one).
- **[5] Stereo/Mono Correction** — owns AC5's *corrective* half (detection
  already happened in [2], driving *what* to correct here): narrows only
  the specific time-windows classified as offending stereo-widened
  elements, not the whole mix, to preserve intentional width elsewhere.
- **[6] Loudness/Limiting** — owns AC2/AC3/AC4 jointly. This is the one
  stage where three constraints interact (LUFS band, -1 dBTP ceiling, DR
  floor) and must be reconciled by one iterative solver — see design notes
  below (**revised in v4** — see the dedicated subsection). It is
  deliberately the *last* gain-affecting stage before dither, since it
  needs to see the true-peak and DR impact of everything upstream.
- **[7] Dither & Bit-Depth Conversion** — the *only* place bit depth is
  reduced, and it happens exactly once (see §3 on avoiding round-trips).
  Owns AC output-format requirement (24-bit) plus the quantization-noise
  requirement from the edge cases section (TPDF dither, never a bare
  truncation).
- **[8] Export** — owns AC9 (valid WAV, metadata/BWF chunks preserved) and
  AC11 (new file, original never touched).
- **[9] Post-Master Analysis** — same analysis code as [2], called again,
  but against the file actually written to disk (not the pre-dither
  in-memory buffer — see §3 for why).
- **[10] Report Generation** — owns AC8/AC10 traceability: assembles
  before/after values side by side, plus an explicit log of every
  corrective action taken (EQ moves with band/gain/reason, stereo
  narrowing windows, gain/limiting amount, resample if applied, dither
  seed used), the rationale text required when landed loudness is below
  -14.5 LUFS (and, **new in v4**, an escalated rationale/flag when landed
  loudness is below -16 LUFS — see below), and a source-file identity
  record (see §4) for traceability.

### Note on the DR/loudness solver interaction

AC4 compares the **final output DR** against the **original source's
pre-master DR** (from stage [2], before any processing at all). But stage
[6]'s solver only has visibility into the DR *after* EQ and stereo
correction ([4],[5]) — those stages are capped/corrective by design and
shouldn't move DR much, but they do move it some. The solver's iteration
loop should track DR against the true original ([2]'s value), not against
its own stage-[6]-entry DR, to avoid a compounding-error blind spot where
small EQ/stereo-stage DR erosion goes uncounted. This is called out
explicitly because it's an easy place to introduce a subtle correctness
bug.

The solver's job, precisely (**revised v4** — see the dedicated subsection
below for the full rationale): find the highest achievable integrated
LUFS, preferring the -14.5 to -13.5 LUFS target band, subject to two
**hard** constraints that must never be violated: never exceeding -1 dBTP
(post-limiting, oversampled), and never dropping DR below
max(DR8, source_DR − 3dB). Loudness itself — including the -16 LUFS value
previously (v1–v3) treated as a hard lower bound — is now a fully **soft**
target: the solver backs off from -13.5 toward -16 and, if the two hard
constraints still cannot both be satisfied even at -16, continues backing
off further, always selecting the *highest* achieved LUFS a real,
DR/peak-feasible gain value can actually deliver, rather than raising
`UnresolvableMasteringConstraintError` purely because the result landed
under -16. This ordering — peak ceiling and DR floor as hard constraints,
LUFS as a fully soft, open-ended target below -13.5 — directly implements
the story's "don't over-limit a build-driven track" instruction. Use a
bounded, deterministic iteration (fixed max iteration count, no
wall-clock-based cutoffs) so re-runs are reproducible (AC10).

### Solver resolution for high-crest-factor sources (v4, resolves DEF-001 residual)

**What was wrong.** python-developer's investigation (defects.md DEF-001
fix notes, 2026-07-31) numerically proved that for high-crest-factor
fixtures (TC-015: quiet sustained body + brief near-ceiling transients,
measured source DR=19; TC-130: source DR=20) there is **no broadband gain
value** under which the v1–v3 solver design (single global gain,
feasibility requiring the DR floor AND `achieved_lufs >= -16` at once) can
succeed. Root physical cause, confirmed by hand-bisecting the achievable-
gain space for both fixtures: BS.1770 gating means integrated loudness for
this signal shape is dominated by the already-near-ceiling transient
blocks, since the quiet body is gated out by the -10 LU relative gate.
Raising broadband gain to chase a louder integrated LUFS mostly raises the
already-loud transients; the peak limiter then has to clamp them back
toward the ceiling, which erodes DR in near lock-step with any loudness
gain — DR drops below the DR floor well before achieved LUFS can climb
back to -16. This is a genuine physical property of the source material
and the gain-then-limit signal chain, not a code defect, and it is not
rare or contrived: high body/transient crest factor is exactly what a
long-form, build-driven progressive house/techno track — this story's core
use case — is expected to have.

**Options considered (from python-developer's fix notes) and why (b) was
chosen:**

- **(a) RMS/multiband or program-dependent gain stage** ("leveler" that
  raises the quiet body disproportionately to the loud transients, ahead
  of the limiter) — investigated and **rejected for v1**. It does not
  actually decouple the two constraints for this signal class: the TT
  DR-meter computes DR as (2nd-highest peak) / (RMS of the 3-second blocks
  remaining after excluding the loudest 20%) — for a body-dominated track,
  the "remaining blocks" *are* the body. Any leveler that raises body RMS
  enough to meaningfully move gated integrated LUFS (which is itself
  dominated by the near-ceiling transient blocks, not the body — see root
  cause above) would, by the DR-meter's own definition, raise the
  DR-floor's denominator and directly erode DR — the same tension,
  restated rather than resolved. It also reintroduces exactly the
  "smarter compressor" complexity §9 risk #6 already flagged as deferred
  past v1, with uncertain payoff. Not ruled out as a *future* refinement
  if listening-based QA later shows it helps in specific cases, but not
  adopted now on the strength of a numeric argument that it would not
  reliably help the fixtures that actually motivated this fix.
- **(c) Recalibrate `dr_max_reduction_db`/DR-floor meaning for
  very-high-source-DR material** — rejected: this touches a second,
  independently BA-resolved number (requirements.md §8 Open Question #1)
  and has the same "contradicts an explicit target" problem as touching
  the LUFS floor, with a weaker justification. Between the two
  BA-resolved numbers in tension, the -16 LUFS value is the one the BA's
  own language frames as a landing point under adverse conditions ("*may*
  land as low as -16 LUFS"), not as an inviolable value, whereas the DR
  rule is framed as a strict "whichever is stricter binds" requirement
  protecting the story's central "don't flatten the build/payoff" concern.
  Given a choice of which explicitly-resolved number to relax, the DR
  floor is the one most directly tied to the story's stated creative
  intent and should stay hard.
- **(b) Chosen**: make the -16 LUFS value a **soft, reported threshold**
  rather than a hard solver constraint. The solver's hard constraints
  become exactly the two the story treats as non-negotiable for audio-
  safety/creative-intent reasons: the -1 dBTP peak ceiling
  (streaming-safety) and the DR floor (the story's explicit "don't
  over-limit a build-driven track" instruction). LUFS — including how far
  below -16 it may need to land — is fully solved-for as "the highest
  value achievable without violating either hard constraint," with the
  existing rationale-logging mechanism (already required by AC2 for
  anything under -14.5) extended with a second, more prominent escalation
  tier specifically for anything under -16. This makes
  `UnresolvableMasteringConstraintError` genuinely rare for legitimate
  long-form dynamic tracks (TC-015/TC-130-class sources now resolve to a
  real, reported LUFS value — around -19.5/-20.0 per the developer's
  hand-bisected figures — instead of throwing), while still throwing for
  genuinely pathological sources. See §11 for this as an explicit
  assumption pending BA confirmation, since it changes what AC2
  guarantees.

**Revised solver algorithm (implementation guidance for python-developer):**

1. The existing bounded, deterministic bisection over candidate gain
   values is unchanged in mechanism (fixed iteration count, deterministic,
   per AC10).
2. `_render_candidate()`'s feasibility check drops the
   `candidate.achieved_lufs >= config.lufs_floor - solver_lufs_tolerance`
   clause entirely (the clause added in the code-level portion of the
   DEF-001 fix). Feasibility is now exactly: `achieved_dr >= dr_required`
   AND `achieved_true_peak_dbtp <= config.true_peak_ceiling_dbtp` (the
   limiter enforces the peak side by construction, so the DR check remains
   the one that actually binds in practice).
3. Candidate selection (`best`) changes from "closest to target within
   [-16, -13.5]" to: among **all** DR/peak-feasible candidates evaluated
   during the bisection, select the one with the **highest
   achieved_lufs** (i.e. closest to -13.5 from below), with no lower bound
   at all. Because achieved-LUFS-vs-gain is not guaranteed monotonic near
   the point where the limiter starts heavily engaging (exactly what the
   developer's manual bisection found for TC-015/TC-130), the algorithm
   must track the best-feasible candidate seen across **all** evaluated
   iterations rather than assuming the most recently evaluated candidate
   is the best one — extend whatever "track the best feasible candidate
   seen" pattern the code-level DEF-001 fix already introduced (the
   `floor_candidate` fallback) to be the **sole** selection mechanism, with
   no separate floor-anchored fallback path needed once the floor is soft.
4. `UnresolvableMasteringConstraintError` now fires only if **no evaluated
   candidate across the full bisection range is DR/peak-feasible at all**
   — i.e. even the most conservative, near-zero-gain candidate cannot hold
   the DR floor (meaning the source itself, essentially unprocessed, is
   already at or below its own DR floor), or the peak ceiling cannot be
   held even at unity/near-unity gain. Both are genuinely rare,
   source-level pathological cases, not ordinary high-crest-factor
   long-form tracks.
5. `MasteringResult` (and the rendered report) gains a new boolean field,
   `below_documented_lufs_floor` (true iff
   `achieved_lufs < config.lufs_floor`, default threshold -16.0),
   computed directly rather than inferred from report text, so QA/
   downstream tooling can assert on it without string-parsing. When true,
   the report's rationale text must name the specific hard constraint that
   forced it (in practice, always the DR floor — cite the exact
   `dr_required` value and the achieved DR at the selected candidate) —
   this is a stronger, more specific escalation of the existing "why
   -13.5 wasn't reached" rationale already required for anything under
   -14.5.
6. `config.lufs_floor` keeps its name and default value (-16.0), but its
   **role** changes from a hard solver constraint to a report-escalation
   threshold only, per the above.

## 2. Library choices

The venv already has a relevant set of libraries installed
(`requirements.txt`): `numpy`, `scipy`, `soundfile`, `soxr`, `pyloudnorm`,
`librosa`, `pydub`, `scikit-learn`. Choices below are deliberate, not
default-to-whatever's-installed — including one explicit *non*-use, and
(new in v4) one explicit narrowed-use.

| Concern | Library | Rationale |
|---|---|---|
| WAV I/O (read/write, 16/24-bit PCM + 32-bit float) | `soundfile` (libsndfile) | Native float64/float32 read path, correct handling of 24-bit PCM and float WAV without an intermediate 16-bit downconvert. This is the sample-accurate I/O backbone. |
| Non-audio chunk preservation (BWF/`bext`, `iXML`, `LIST`/INFO, etc.) | custom `wav_chunks.py` (hand-rolled RIFF parser, stdlib `struct`/`io` only) | `soundfile`/libsndfile does not guarantee round-tripping arbitrary/unknown RIFF chunks — it reconstructs the container around the chunks it understands. AC9 requires *not silently dropping* existing metadata, so this needs an explicit, dependency-free binary-chunk-preserving layer. See risk #4 in §9. |
| Integrated loudness (BS.1770-4, gated) | `pyloudnorm` | Direct BS.1770-4 implementation (absolute -70 LUFS gate, relative -10 LU gate) — this is exactly the resolved reference standard. Used for both the pre- and post-master LUFS measurement. |
| True peak (BS.1770-4 Annex 2, ≥4x oversampling) | custom `true_peak.py`, built on a **purpose-built polyphase FIR interpolation filter** (`scipy.signal.firwin` design + `scipy.signal.upfirdn` application) + `numpy` (peak search) — **changed in v4, was `soxr`; see the dedicated note below the table** | Oversampling for true-peak metering has different requirements than general-purpose sample-rate conversion: it doesn't need anti-aliasing margin (the oversampled buffer is discarded after the peak search, never played back), and instead needs the flattest possible passband response right up to the original Nyquist, since near-Nyquist content is exactly the highest-risk region for inter-sample peaks. `soxr` (and general resamplers generally) deliberately pull their passband cutoff in from Nyquist to leave transition-band margin for anti-aliasing on real rate conversion — the wrong optimization target here, and the confirmed root cause of DEF-002's residual TC-022 failure (soxr showing ~0.54 dB real passband attenuation near Nyquist across all quality presets, not correctable via the Python binding). A fixed-factor (4x/8x/etc.) polyphase FIR designed and applied directly via `scipy.signal`, with its cutoff placed at exactly the original Nyquist rather than pulled in for anti-aliasing margin, is the correct tool for this specific job and stays within the already-installed dependency set. **v5**: this filter's own passband ripple approaching Nyquist is itself bounded but non-zero (tiered envelope, see below) — a second, narrower residual than the one v4 fixed; see §9 risk #3 (updated). |
| Dynamic range (TT DR-meter scale) | custom `dynamic_range.py`, `numpy`/`scipy` | **Gap**: no PyPI package implements the published TT DR-meter algorithm (Pleasurize Music Foundation spec: 3-second RMS blocks, exclude loudest 20% of blocks, ratio of remaining-block RMS to 2nd-highest peak). Implement directly against that published spec rather than inventing a crest-factor approximation — flagged as risk #2 in §9, needs calibration against known reference DR values. |
| Frequency-balance analysis (band energy vs. genre reference) | `scipy.signal.welch` (PSD) + `numpy` | Welch's method gives a stable, well-understood PSD estimate for the three defined bands (20–120 Hz, 200–500 Hz, 2–5 kHz). `librosa` (already installed) is available as an optional auxiliary tool (e.g. spectral centroid cross-checks) but is not required for the core measurement — keeping the required path on `scipy`/`numpy` avoids an unnecessary heavy/JIT (numba) dependency on the critical path. |
| Genre reference curve | flat data file (`reference/progressive_house_124bpm.json`), consumed by `frequency_balance.py` | Not a library concern — see risk #1 in §9 and §8, this is a content/calibration gap, not a code gap. |
| Corrective EQ (parametric peaking/shelving) | custom `eq.py`: RBJ Audio-EQ-Cookbook biquad coefficient design (hand-computed in `numpy`), applied via `scipy.signal.sosfiltfilt` | No library ships a "peaking EQ with gain-in-dB and Q" primitive directly; RBJ cookbook formulas are standard, well-documented DSP and straightforward to implement correctly. `sosfiltfilt` (zero-phase) is deliberately chosen over a single-pass `sosfilt` for the corrective EQ specifically, so the correction doesn't introduce its own phase shift that could work against the mono-compatibility goal — defensible since this is offline batch processing with no latency constraint. |
| Stereo phase correlation / mid-side processing | custom `stereo_phase.py`, `numpy` | Straightforward: correlation coefficient and M/S transforms are simple vectorized numpy math; no library gap here, just needs the windowed-segmentation design discussed in §1/§9. |
| Clipping/inter-sample-over detection | custom `clipping.py`, reuses `true_peak.py`'s oversampled buffer | Sample-peak clipping (consecutive full-scale samples) is a simple numpy scan; inter-sample overs reuse the true-peak oversampling machinery rather than recomputing it — a performance/consistency choice. Unaffected in its own logic by the v4/v5 filter changes — it just inherits whichever oversampled buffer `true_peak.py` now produces. |
| Dither (TPDF) | custom `dither.py`, `numpy` | Simple, standard technique (sum of two uniform random variables scaled to 1 LSB at 24-bit). Must use a seeded `numpy.random.default_rng` (config-supplied seed, fixed default) — **not** unseeded randomness — to satisfy AC10 reproducibility. |
| Resampling (non-standard rate → 44.1 kHz, stage [3] only) | `soxr` | Best-quality resampler available in the installed set for genuine arbitrary-ratio, anti-aliased sample-rate conversion; avoids the phase/aliasing issues of naive FFT-based resampling. **Narrowed in v4**: retained here, but no longer used for true-peak oversampling — see the true-peak row above and the dedicated note below. |
| Limiter (lookahead, true-peak-aware) | custom `limiter.py` | No library gap exactly, but no library does this *for you* either — flagged as the highest-complexity custom DSP component; see design note below and risk #6. |
| CLI argument parsing | stdlib `argparse` | No need for a third-party CLI framework for a single-file-in/single-file-out tool. |

**Deliberate non-use: `pydub`.** It's present in `requirements.txt`, but I
am recommending it **not** be used anywhere in the precision-critical
signal path (ingest, EQ, stereo correction, loudness/limiting, dither,
export). `pydub`'s effects and internal representation are built around
`audioop`, which is oriented toward integer PCM (historically 16-bit) and
does not reliably preserve 24-bit or 32-bit-float precision through
processing. Given this story's explicit emphasis on final-master quality
and avoiding unnecessary precision loss, running the mastering chain
through `pydub` risks a silent bit-depth round-trip degradation. If a
developer wants a convenience helper for something trivial and
non-precision-sensitive (e.g. quick format sniffing during manual
debugging), that's fine, but it must never touch the sample data that ends
up in the exported master. Flagged explicitly since it's already installed
and might otherwise look like the "obvious" choice.

**True-peak oversampling filter, v4 (resolves DEF-002 residual, TC-022).**
`soxr` remains the resampler for stage [3] (format-rate conversion, e.g. a
non-standard source rate → 44.1kHz) — that is a genuinely general-purpose,
arbitrary-ratio resampling problem where soxr's anti-aliasing-margin bias
is the *correct* trade-off. `true_peak.py`'s oversampling (used for AC3
measurement, and reused by `clipping.py`'s inter-sample-over scan per the
existing design) is a different, narrower problem — always a fixed
integer oversample factor (4x/8x) — and moves to a purpose-built FIR
filter as described in the table above. Concretely: `true_peak.py` builds
(once, cached per factor) a linear-phase FIR lowpass via
`scipy.signal.firwin(numtaps, cutoff=0.5/factor, window=('kaiser', beta))`
with `numtaps` scaled to the factor (32×factor taps, `beta=9.0`) for
adequate stopband rejection, and applies it via
`scipy.signal.upfirdn(fir, x, up=factor)` (zero-stuff-and-filter, the
standard polyphase-interpolation approach) rather than any general
resampler call. This exact tuning is implemented and numerically verified
(see the tiered ripple envelope introduced in v5, below, and §9 risk #3)
— the design approach (purpose-built FIR-via-firwin/upfirdn instead of a
general resampler, cutoff placed exactly at original Nyquist for
image-safety) is the fixed architectural decision. The existing DEF-002-fix
guard-region trim (~5ms at the oversampled rate, excluded from the peak
scan to avoid filter-edge transients) is unaffected and still applies on
top of this filter.

**Accepted tolerance for TC-022's cross-factor monotonicity check.** Even
a well-designed FIR filter will not be perfectly flat to floating-point
precision at Nyquist, so requiring strictly
`factor_n_reading >= factor_(n-1)_reading` for every pair of tested
oversampling factors is an unreasonably tight bar for a synthetic
near-Nyquist test tone. Adopt a documented tolerance:
`factor_n_reading >= factor_(n-1)_reading - true_peak_monotonicity_tolerance_db`
(new `config.py` value, default **0.05 dB**). This tolerance applies
**only** to TC-022-style cross-factor self-consistency assertions, never
to the actual -1 dBTP ceiling enforcement in the limiter/solver path,
which must continue to treat the *higher* of any close readings as
authoritative (never round toward "safe" when deciding whether a
candidate violates the ceiling) — the tolerance is a test-assertion
concession to real filter-design limits, not a relaxation of AC3's actual
zero-exceptions safety bar. See §11 for this framing as an explicit
assumption pending BA confirmation.

### True-peak passband ripple target — revised (v5, resolves DEF-002 second residual)

**What was wrong.** v4 §2/§7 set an aspirational verification target of
<0.01 dB passband ripple "across a sweep of frequencies approaching
Nyquist" without an explicit upper frequency bound, and §9 risk #3's v4
note implied this should eventually extend close to Nyquist itself.
qa-automation-engineer's re-verification pass (defects.md DEF-002,
2026-08-01) measured the *implemented* filter (numtaps=32×factor,
beta=9.0, cutoff at exactly original Nyquist — unchanged, see below) via a
`freqz` sweep and found it holds <0.01 dB only up to ~80% of original
Nyquist, degrading to roughly ~0.02 dB at 85%, ~0.4 dB at 90%, ~1.5–2 dB at
94–95%, and ~5.9 dB at 99.9%. A second, independently-verified tuning
attempt (pushing the filter's cutoff above Nyquist to flatten the passband
further) was tried and *rejected*: it reintroduces `upfirdn`'s
zero-stuffing image (which converges toward the same frequency as the
fundamental as both approach Nyquist), causing worse, 5-6 dB *time-domain*
errors — a regression a frequency-response-only (`freqz`) check would not
catch. `scipy.signal.kaiserord` confirms that closing the gap to <0.01 dB
genuinely to 0.999× Nyquist while keeping the image-safe cutoff placement
would require on the order of 40,000+ taps at factor=8 — verified
computationally infeasible within the 5-minute NFR processing budget
(measured ~1.1s per true-peak call at 257 taps scaling roughly linearly to
~4.3s at 1025 taps, and the solver calls this measurement dozens of times
per run; §9 risk #8's benchmarking is still outstanding, so recommending
more taps without evidence of headroom would be guessing against the NFR).

**Direction of the error, and why it matters.** The filter is a lowpass
with its passband ending at Nyquist by construction (the image-safety
requirement above) — so the degradation approaching Nyquist is *always
attenuation*, never gain (confirmed directly by
`test_fir_filter_image_rejection_beyond_nyquist`'s
`attenuation_db = unity_db - mag_db`, positive throughout the transition
band). This means the residual risk is specifically an **under-read** near
Nyquist — a genuine inter-sample peak concentrated in the top ~10-20% of
the band could, in principle, read *below* its true value, which is the
unsafe direction for a "zero exceptions" ceiling (a false negative on a
real violation, not a false positive). This must be stated plainly rather
than minimized: it is the same category of risk as the pre-v4 `soxr`
defect (also an under-read near Nyquist), reduced in *practical extent* by
the v4 filter but not eliminated in *kind*.

**Why this is an acceptable, bounded residual rather than a blocking gap:
the composite-peak argument.** For this under-read to cause a real
ceiling miss, the *track's own maximum inter-sample peak* — the single
sample the -1 dBTP ceiling enforcement cares about — would have to be
dominated by content whose energy sits above roughly 0.90-0.94× original
Nyquist (>19.8-20.7 kHz at 44.1 kHz), since that is where the error
becomes large enough to matter (≥0.4-2 dB). This is a narrow condition for
real mastered music in this genre: melodic progressive house/techno at 124
BPM does not carry meaningful full-scale energy that high, and — per
requirements.md §3's own caveat — Suno's generation pipeline and any prior
lossy encoding stages typically leave that region well down from full
scale already. A composite peak dominated by near-Nyquist content, at or
near -1 dBTP specifically, is an edge case, not the common case this tool
is built for. This is a materially stronger, more specific argument than
"rare in general" — it identifies exactly the (narrow) condition under
which the residual risk would actually bite.

**Decision: formalize a tiered ripple-vs-frequency envelope matching the
verified, already-implemented behavior, rather than a single flat
target.** Replacing the single <0.01 dB-to-0.999×-Nyquist aspirational
figure (which the implementation was never actually going to meet, given
the infeasible tap count) with a tiered target that has headroom over the
measured points, so the frequency-sweep test in §7 passes against the real
filter and remains a meaningful regression guard rather than a
permanently-red assertion:

| Fraction of original Nyquist | Ripple bound |
|---|---|
| up to 0.80× | ≤ 0.01 dB (the verified-flat region) |
| up to 0.85× | ≤ 0.05 dB (measured ~0.02 dB) |
| up to 0.90× | ≤ 0.5 dB (measured ~0.4 dB) |
| up to 0.95× | ≤ 2.5 dB (measured ~1.5-2 dB) |
| up to 0.999× | ≤ 6.5 dB (measured ~5.9 dB) |

This is a **distinct property from, and must not reuse,
`config.true_peak_monotonicity_tolerance_db`** (0.05 dB) — that value
governs TC-022-style cross-oversampling-factor self-consistency assertions
(requirements.md v3 §8 Q12's framing), a different, narrower question than
the filter's own absolute passband flatness at a given factor. See §7 for
the corresponding test-spec update.

**Options considered and rejected:**

- **Increase FIR taps** to close some of the gap short of the full
  40,000+: rejected for now — §9 risk #8 (in-memory processing time
  budget) is still unbenchmarked, and the solver calls
  `measure_true_peak()` dozens of times per run, so recommending more taps
  without measured headroom evidence would be trading a documented,
  bounded metering-accuracy risk for an unverified processing-time risk.
  Revisit if/when risk #8's benchmarking is done and shows real headroom.
- **Source the literal published ITU-R BS.1770 Annex 2 filter
  coefficients** instead of a `firwin`-designed approximation: still the
  most rigorous fix (already flagged in §9 risk #3 pre-v5) but not
  resolved in this pass — no verified source for those coefficients has
  been located yet. Remains open, tracked alongside TC-024.
- **Add a flat safety margin to ceiling enforcement** (e.g. treat
  -1.1 dBTP as the effective internal ceiling to absorb some of the
  near-Nyquist under-read): considered and **rejected**. A margin large
  enough to meaningfully cover the worst-case error (~1.5-6.5 dB in the
  0.94-0.999× range) would cost real, unjustified loudness/headroom on
  every track regardless of its actual spectral content near Nyquist — the
  vast majority of which have no meaningful energy there at all. A margin
  small enough not to cost loudness broadly (e.g. 0.1 dB) would not
  materially cover the risk it's nominally for. This is decoration on the
  residual, not a real mitigation, so it is not adopted.
- **Condition a margin on measured near-Nyquist energy** (stage [2]
  already computes a Welch PSD for frequency-balance analysis; a future
  enhancement could have `true_peak.py`/the analysis layer report the
  energy fraction above ~0.85× Nyquist and apply enforcement-only margin
  when that fraction is unusually high, without changing the reported
  dBTP value): a real, near-zero-cost mitigation path, but **not
  implemented in this pass** — it is new logic (a python-developer task)
  and the composite-peak argument above already bounds the practical risk
  acceptably without it. Flagged here as the recommended next step if
  TC-024's eventual external cross-validation (below) finds this residual
  actually matters in practice.
- **Accept the residual, formalize the tiered target, and rely on TC-024**
  (external cross-validation against a known-good true-peak meter, already
  an open residual-validation dependency per defects.md) **as the real
  closure path**: chosen. This is honest about what the tool currently
  guarantees (exact, safety-critical accuracy across the vast majority of
  the band that carries real programme energy for this genre; a bounded,
  documented, direction-known residual in the narrow top ~10-20% of the
  band) without pretending a synthetic aspirational number was ever
  actually being met.

No BA-specified target is being relaxed by this change — AC3's -1 dBTP
delivered-audio ceiling (requirements.md v3, confirmed unchanged) remains
exact, with the true-peak *enforcement* logic (not the metering filter)
required to treat the higher of any close readings as authoritative, per
the "Accepted tolerance for TC-022's..." paragraph above. The <0.01
dB-to-0.999×-Nyquist figure being revised here was architecture's own
aspirational *verification* target for the metering implementation, not a
number requirements.md ever specified — requirements.md v3 §8 Q12 already
confirmed AC3's zero-exceptions bar is about the delivered-audio ceiling,
not the metering tool's internal precision, which is exactly the
distinction this revision formalizes. No new §10 "assumption pending BA
confirmation" entry is needed for this reason.

### Limiter design note

Two viable approaches exist; I'm recommending the simpler one for v1 and
flagging the fuller one as a possible follow-up if it doesn't converge
cleanly in practice:

- **Recommended for v1**: keep the limiter operating at the track's native
  (post-resample) sample rate. Use the oversampled true-peak measurement
  ([true_peak.py]) purely as a *metering* signal to drive an iterative
  gain-reduction loop (lookahead envelope follower at 1x rate, broadband
  gain applied, re-measure oversampled true peak, adjust, repeat within a
  bounded iteration count). Lower implementation complexity, lower risk of
  oversample/downsample filter artifacts interacting badly with a brickwall
  stage.
- **Possible future refinement**: perform the actual limiting in the
  oversampled domain (oversample → lookahead brickwall limit → downsample
  back with `soxr`). More surgical true-peak control, but real risk of
  pre-ringing/artifacts from the oversample/downsample filters themselves
  interacting with a hard limiter — needs listening-based QA, not just
  numeric verification, before it could be trusted as the default. Not
  recommended to build this for v1 without a specific quality complaint
  about the simpler approach. (Note: this refinement is orthogonal to the
  v4 true-peak *metering* filter change above — if built later, it should
  reuse the same purpose-built FIR/`upfirdn` oversampling approach for
  consistency, downsampling back via `soxr` since that leg is genuine
  format-rate conversion.)

## 3. Data flow

**Fully in-memory, single read / single write, no intermediate temp
files.** A 7–10 minute stereo track at 48 kHz is on the order of
50–60 million samples per channel — comfortably within RAM on "typical
consumer hardware" as float64. There is no streaming requirement (no
faster-than-real-time constraint either) and no reason to add file-based
staging between DSP stages — it would only add I/O overhead against the
5-minute budget and introduce more surface area for accidental precision
loss.

Precision handling, specifically:

- Audio is read once at ingest and immediately up-cast to **float64**
  regardless of source bit depth (16/24-bit int, or 32-bit float — Suno
  exports may be float). All analysis and DSP math (EQ filtering, M/S
  transforms, gain, limiting) happens in float64.
- **Bit-depth reduction happens exactly once**, at stage [7], immediately
  before export — never at ingest, never between intermediate stages. This
  is the single most important precision rule for this pipeline: no
  stage-to-stage round-trip through a lower-precision integer
  representation.
- **Post-master analysis re-reads the file actually written to disk**
  (stage [9] loads the output of stage [8]), rather than reusing the
  pre-dither in-memory float64 buffer from stage [6]/[7]. This closes a
  subtle but real gap: without this, the "after" numbers in the report
  could describe a slightly different signal than what was actually
  delivered (pre- vs. post-dither, or any bug in the write path). Given
  AC8's explicit requirement that the report prove the improvement on the
  *delivered* file, measuring the delivered file directly is the safer
  design, at negligible extra cost (one more disk read of an already-small
  WAV).
- Resampling (stage [3]) is the one unavoidable place where a
  precision/quality decision is made deliberately rather than avoided —
  it's conditional (only non-standard source rates) and uses the
  best-available general resampler (`soxr`) rather than a naive one, per
  the resolved spec's own rationale for defaulting to 44.1 kHz. (True-peak
  metering's own oversampling, elsewhere in the pipeline, is a separate
  concern with a separate filter as of v4/v5 — see §2.)

## 4. Non-destructive handling

- The input file is opened in read-only mode throughout ingest and
  pre-master analysis; nothing in the pipeline ever opens the input path
  in a write/append mode.
- Output path is always derived (e.g. `<name>_mastered.wav` in a
  configurable output directory) and the pipeline **hard-fails** if the
  resolved output path would equal the input path — this isn't just a
  convention, it's an enforced guard.
- The report records a content hash (SHA-256) of the input file computed
  at the start of the run, and the pipeline re-hashes the input file again
  at the very end of the run, asserting they match. This is a cheap,
  strong, automatically-checkable guarantee of AC11 (non-destructive
  processing) that the test-case-writer/QA agent can assert on directly,
  rather than relying on "we didn't call any write function on that path"
  as an implicit argument.
- The output report itself references the output WAV's own hash and the
  input's hash, tool version, and settings/config used — this is the
  traceability mechanism for AC8/NFR "traceability."

## 5. Integration points

Per requirements.md Section 3, the input to this tool is the **raw Suno
export directly** — not an Audacity-processed or bx_mastering-processed
intermediate file. Audacity and bx_mastering appear in the story only as
the *manual baseline this tool replaces* (the NFR "fidelity vs. manual
baseline" bar), not as an upstream integration point requiring format
compatibility beyond a standard WAV reader. I'm calling this out explicitly
because the task brief that prompted this architecture pass mentioned
"Audacity exports as input" and "Suno Studio Track EQ outputs as source
material" as things to consider — but neither appears as an actual
requirement in requirements.md. Building explicit support for
Audacity-specific or Suno-Studio-specific export quirks would be scope
creep against this story; if either turns out to matter in practice,
that's a requirements gap for the BA to resolve, not something to silently
architect around here.

Downstream, this tool's output is the **final master** (resolved Open
Question #7) — it is handed directly to LANDR/Spotify, not back through
another mastering pass. No API/upload integration with LANDR or Spotify is
in scope (Section 5, explicit out-of-scope) — the tool's job ends at
producing a valid, delivery-ready WAV + report on disk.

## 6. Constraints for implementation

### Module layout

```
suno_mastering/
  __init__.py
  cli.py                    # thin argparse wrapper around pipeline.run()
  pipeline.py               # orchestrates stage order; run()/master() entry points
  config.py                 # single source of truth for all thresholds/targets
  errors.py                 # exception hierarchy
  io/
    ingest.py                # load + validate + format/channel detection
    wav_chunks.py            # RIFF chunk extraction/splicing (metadata/BWF)
    export.py                 # write final WAV + reinject preserved chunks
  analysis/
    types.py                  # Measurements dataclass(es) — shared pre/post shape
    loudness.py                # BS.1770 integrated LUFS (pyloudnorm)
    true_peak.py                # oversampled true-peak dBTP (v4: purpose-built FIR, v5: tiered ripple target — see §2)
    dynamic_range.py             # TT DR-meter (custom, from published spec)
    frequency_balance.py          # band-energy vs. genre reference curve
    stereo_phase.py                # correlation + stereo-widened segmentation
    clipping.py                     # sample-peak + inter-sample-over detection
    silence.py                       # shared near-silence/gating utility
  mastering/
    resample.py                # soxr-based conditional resample (stage [3] only)
    eq.py                        # RBJ biquad corrective EQ
    stereo_correct.py              # windowed M/S narrowing correction
    loudness_limit.py                # iterative LUFS/DR/true-peak solver (v4: soft LUFS floor, see §1)
    limiter.py                        # core lookahead limiter primitive
    dither.py                          # seeded TPDF dither + bit-depth convert
  reference/
    progressive_house_124bpm.json      # genre reference curve (see §8/§9 risk #1)
  report/
    builder.py                  # assembles pre/post Measurements + action log
    render.py                     # renders to markdown/json
```

### CLI vs. library API

Expose both, with the library API as the primary/tested surface:

- **Library API** (what tests should call): `suno_mastering.pipeline.master(input_path, output_dir=None, config=None) -> MasteringResult`, where `MasteringResult` bundles the output file path, the before/after `Measurements`, the corrective-action log, and (v4) the `below_documented_lufs_floor` flag described in §1. Exceptions propagate to the caller — no swallowed errors at this layer.
- **CLI** (`python -m suno_mastering <input.wav> [--output-dir DIR] [--config PATH]`): a thin wrapper that calls the library API, catches the exception hierarchy from `errors.py` at the top level to print a clear message and exit non-zero, and writes the rendered report alongside the output WAV.

### Error handling

Define a small typed exception hierarchy in `errors.py` (e.g.
`MasteringError` base, `InvalidWavError`, `UnsupportedFormatError`,
`UnresolvableMasteringConstraintError` for the case where the loudness
solver genuinely cannot satisfy the peak ceiling and DR floor
simultaneously at **any** gain — **narrowed in v4**: no longer scoped to
"even at -16 LUFS," since -16 is no longer a hard constraint; see §1).
Every pipeline stage raises typed exceptions rather than letting raw
`ValueError`/`IndexError`/etc. leak up — this both satisfies the "fail
gracefully, don't crash" robustness NFR and gives the test-case-writer
concrete, named error conditions to write tests against.

### Config as single source of truth

All magic numbers — LUFS band (-14.5/-13.5, floor -16 — **v4: `lufs_floor`
is now a report-escalation threshold, not a hard solver constraint; see
§1**), true-peak ceiling (-1.0 dBTP), oversampling factor, DR floor (DR8)
and max-reduction rule (3 dB), frequency-band definitions and thresholds
(4 dB/3 dB/3 dB) and the EQ move cap (3 dB), phase-correlation thresholds
(0.0 overall, +0.3 on widened elements), output bit depth (24) and
supported sample rates (44100/48000, default 44100), dither seed default,
solver max-iteration count, and (**new in v4**)
`true_peak_monotonicity_tolerance_db` (default 0.05, governs only
TC-022-style cross-factor test assertions, never actual ceiling
enforcement — see §2) — live in `config.py` as a single dataclass,
overridable at the `master()` call site. This is both good practice and
directly useful to the test-case-writer for boundary-condition tests (e.g.
constructing a signal that sits exactly at the DR8 boundary). (**v5**: the
new tiered passband-ripple envelope in §2 is a *test-spec* constant, not a
runtime `config.py` value — it governs `tests/test_smoke_true_peak_fir.py`
assertions only, not any pipeline decision, so it does not need a config
entry.)

## 7. Testability notes

- Every `analysis/*` and `mastering/*` module's primary function signature
  should take **plain numpy arrays + sample rate** (and, where relevant, a
  `config` object), not file paths. This makes each stage unit-testable
  with synthetic signals independent of file I/O — e.g. a calibrated 1 kHz
  sine at a known dBFS/LUFS, a full-scale square wave for clipping
  detection, an out-of-phase stereo pair for correlation edge cases, a
  silence-only buffer, a mono buffer.
- For loudness/true-peak calibration specifically, recommend the
  test-case-writer use the published ITU-R BS.1770 / EBU Tech 3341
  reference test signals — these exist precisely to validate a BS.1770
  implementation against known-correct LUFS/true-peak values, and are the
  right way to gain confidence in `true_peak.py` in particular, since
  there's no off-the-shelf library to trust here (see risk #3).
- **(v5, supersedes the v4 version of this bullet)** For `true_peak.py`'s
  FIR filter (§2), add a dedicated frequency-response test independent of
  any specific track fixture: sweep calibrated sine tones from roughly
  0.5× to ~0.999× of the original Nyquist at a fixed, known amplitude, and
  assert the filter's oversampled peak reading stays within the **tiered
  ripple envelope** from §2 (≤0.01 dB to 0.80×, ≤0.05 dB to 0.85×,
  ≤0.5 dB to 0.90×, ≤2.5 dB to 0.95×, ≤6.5 dB to 0.999×) — **not** a single
  flat bound, and **not** `true_peak_monotonicity_tolerance_db` (that
  value is reserved for TC-022-style cross-factor self-consistency checks,
  a different property — see §2). This isolates filter-design correctness
  from any single test fixture's frequency choice, and is a more direct
  test of the DEF-002 root cause than TC-022's single-frequency
  monotonicity check alone. `tests/test_smoke_true_peak_fir.py`'s existing
  0.80×/0.01 dB check already satisfies the first tier of this envelope;
  recommend test-case-writer/QA extend it with the remaining tiers
  (0.85/0.90/0.95/0.999×) so the full envelope — including the documented
  near-Nyquist degradation — is regression-protected rather than only
  spot-verified in defects.md's prose.
- `dither.py` must accept an injectable seed (default fixed, not
  time-based) — this is required for AC10 reproducibility and also lets
  tests assert exact byte-for-byte output for a fixed input+seed.
- The loudness/DR/true-peak solver (`loudness_limit.py`) should expose its
  iteration bound and convergence tolerance via `config`, so tests can
  construct a case designed to hit the "can't reach -13.5, back off toward
  -16 LUFS" path deliberately (e.g. a highly dynamic source that wants a
  large gain to reach -13.5) and assert the correct backing-off behavior
  and rationale text, rather than only testing the "everything converges
  cleanly" happy path. **(v4)** Additionally, construct at least one
  fixture (e.g. TC-015/TC-130-shaped: quiet sustained body, brief
  near-ceiling transients, high source DR) that is *known* to be
  unresolvable at -16 LUFS under the DR floor, and assert: (a) the solver
  does **not** raise `UnresolvableMasteringConstraintError`, (b)
  `MasteringResult.below_documented_lufs_floor` is `True`, (c) the
  achieved DR still meets `max(DR8, source_DR-3dB)` exactly (the hard
  constraint held), and (d) the report's rationale text names the DR
  floor as the reason. Separately, construct a fixture where DR floor and
  peak ceiling genuinely cannot both be held at any gain (e.g. a source
  already violating its own DR floor pre-processing) and assert
  `UnresolvableMasteringConstraintError` **is** raised — this is now the
  narrower, correctly-scoped condition for that exception per §1.
- For `stereo_phase.py` specifically (see revised §8 #2): test with a
  synthetic single hard-panned transient (varying duration 20–600ms,
  varying amplitude) positioned mid-track and assert `is_widened`/element
  classification does **not** produce a `StereoWidenedRegion`, alongside a
  companion synthetic sustained-pan fixture (>=1000ms, i.e. spanning >=2
  non-overlapping windows) that **does**. Also test a transient positioned
  to straddle a window boundary (e.g. starting 20ms before a window
  boundary) to exercise the known boundary-dilution edge case noted in §9
  risk #5.
- Recommend one golden-file regression test at the pipeline level once a
  reference input is available: process a fixed input with a fixed config
  (including fixed dither seed), and assert the output hash and full report
  contents are stable across runs and across otherwise-unrelated code
  changes — this is the concrete implementation of AC10.
- Each pipeline stage should be callable in isolation from
  `pipeline.py`'s orchestration (i.e. `pipeline.py` should be a thin
  sequencer, not where the actual logic lives) so tests can exercise, say,
  `mastering.eq.apply_corrective_eq()` directly against a crafted
  "muddiness-flagged" synthetic signal without running the full chain.
- Performance: all per-sample logic must be vectorized (numpy/scipy), not
  Python-level loops over samples — this matters for the 5-minute budget
  and is worth an explicit test-case-writer note since a naive
  implementation of, say, the DR-meter block loop or the limiter envelope
  follower could accidentally end up sample-by-sample in Python and blow
  the time budget on longer tracks.
- **Pipeline-level AC2/AC3 fixtures must use solver-feasible source audio.**
  Any test that calls `pipeline.master()` and expects a `MasteringResult`
  (not an exception) must supply a source whose pre-EQ stage [2] DR
  satisfies `source_DR ≥ config.dr_floor` (i.e. ≥ 8.0 with defaults). The
  recommended range for AC2/AC3 fixtures is **10 ≤ source_DR ≤ 11**
  (pre-EQ): the floor term in
  `dr_required = max(dr_floor, source_DR − dr_max_reduction_db)` binds at
  8.0 throughout this range (2 dB headroom), and source_DR ≤ 11.0 stays
  below the threshold at which the stale-measurement bug (measuring
  source_DR pre-EQ while the solver evaluates post-EQ DR) becomes active.
  Note the TT DR formula's factor-of-2 convention:
  `block_TT_RMS = sqrt(2 × mean(x²))`; for a pure sine body at peak
  amplitude A, `block_TT_RMS = A`, so
  `DR ≈ 20 × log₁₀(transient_amp / body_peak_amp)`. For
  `transient_amp = 0.95` and DR = 10: `body_peak_amp ≤ 0.300`
  (≈ −14 dBFS body RMS). A fixture with body at −9 dBFS or louder cannot
  reach DR ≥ 8 with any physically realizable transient amplitude and must
  not be used as a pipeline-level pass/result fixture. **Separately, the
  §7-mandated positive test for `UnresolvableMasteringConstraintError` must
  use a hard assert (not `pytest.skip`)** — the DR3–5 source shapes
  confirmed in DEF-009's retriage are reliable triggers for this exception
  and should be used. (See defects.md DEF-009 for full derivation.)

## 8. Resolved architecture-level decisions (2026-07-31)

requirements.md v2 resolves all ten of its own listed open questions, but
two implementation-shaping details were left genuinely undefined at the
*architecture* level in the v1 pass of this document — the resolved spec
gives relative thresholds/targets but not the underlying baseline/method
they're relative to. Both are now decided below, with concrete parameters,
so `frequency_balance.py` and `stereo_phase.py`/`stereo_correct.py` can be
built against a fixed spec rather than a placeholder. Residual calibration
risk remains (see §9, risks #1 and #5) — that's a validation task for
QA/production use, not a blocker for implementation to start.

**Item #2 below (stereo-widened-element identification) was revised in v3
to fix DEF-003 — a mathematically-proven flaw in the v2 debounce design.
See §12 Revision history for the defect and its resolution rationale.**

1. **Genre reference spectral curve — RESOLVED.**
   `reference/progressive_house_124bpm.json` ships with the following
   default curve: broad-band relative levels, expressed in dB relative to
   the 500 Hz–2 kHz band's own average energy (that band is the 0 dB
   baseline, since it's the least genre-contentious "midrange" reference
   point):
   - 20–120 Hz (low-end band): **-1.5 dB**
   - 200–500 Hz (low-mid/mud band): **-3.0 dB**
   - 2–5 kHz (presence/harsh band): **-4.0 dB**

   These values reflect the general character of well-mastered deep/melodic
   progressive house & techno relative to louder festival-EDM masters: a
   present but controlled sub/low-end, deliberately slightly-recessed
   low-mids (avoids boxiness on club systems), and a smoother, less
   forward top end than festival material. Combined with the resolved
   thresholds, this means: thin low-end triggers below **-5.5 dB**
   relative, muddiness triggers above **0.0 dB** relative, harshness
   triggers above **-1.0 dB** relative.

   This is a defensible starting default, not a producer-verified
   ground truth — same category of judgment call as the LUFS/DR tolerance
   values resolved in requirements.md §8. To close the residual
   calibration gap without blocking v1, add
   `scripts/build_reference_curve.py` (offline, not part of the runtime
   pipeline): given 3–5 producer-nominated reference WAVs the producer
   considers well-mastered in this genre, it computes each track's Welch
   PSD in the same three bands, normalizes each to its own 500 Hz–2 kHz
   average, averages across tracks, and writes a replacement
   `progressive_house_124bpm.json` in the same schema. Running this script
   is a recommended follow-up task, not a precondition for
   python-developer/test-case-writer to start building against the default
   curve.

2. **"Stereo-widened element" identification method — RESOLVED (revised
   in v3, see DEF-003).**

   **What was wrong (v2 design, now superseded):** v2 specified a 500ms
   sliding window with a 250ms hop (50% overlap) and a "≥2 consecutive
   windows" debounce, with the stated intent that this would reject a
   single brief hard-panned transient (e.g. one drum hit) from qualifying
   as a sustained "element." QA (DEF-003, TC-043) proved this is
   mathematically impossible as specified: because the window length is
   exactly 2x the hop length, *every* interior time position — including
   an instantaneous, single transient — falls inside exactly 2
   overlapping windows by construction. The 2-consecutive-window debounce
   therefore never filters anything; it is satisfied by every transient,
   not just sustained ones. This was a parameter-choice defect in the
   architecture, not an implementation bug — the code correctly
   implemented what was specified.

   **Corrected design:** switch to **non-overlapping** analysis windows
   (hop = window length), which structurally decouples "touches 2
   windows" from "is a brief, single event." Two non-overlapping windows
   can only both classify as widened if the underlying wide content
   genuinely extends across the window boundary into a second, disjoint
   500ms segment — a single 20–200ms transient positioned away from a
   window boundary now falls entirely inside one window and cannot
   satisfy a ≥2-window debounce at all.

   - Window: **500 ms**, hop **500 ms** (no overlap; windows tile the
     track contiguously, `window_index = floor(t / 500ms)`).
   - Per window: mid = (L+R)/2, side = (L-R)/2; compute each channel's
     energy (sum of squares) over the window.
   - Classification: a window is **stereo-widened** when
     `side_energy / mid_energy > 0.6`.
   - Debounce: a window only counts as part of a stereo-widened
     *element* (subject to the +0.3 correlation target and to correction
     in stage [5]) if **≥2 consecutive** (contiguous, non-overlapping)
     windows are classified as widened — i.e. the widened content
     genuinely spans **≥1000 ms** of real, disjoint track time. A single
     transient occurring entirely within one 500ms window, or one that
     spills only briefly across a window boundary without materially
     shifting that neighboring window's own side/mid ratio above 0.6,
     will not be classified as an element. This is a materially stronger
     and now-actually-deterministic guarantee than the "~750ms sustained"
     framing in v2 — v2's 750ms figure was itself an artifact of
     conflating window-span with actual signal-sustain duration, which is
     exactly the bug being fixed here.
   - Known boundary edge case (carried forward, not new): a genuinely
     sustained widened region whose start/end falls very close to a
     500ms window boundary can have its edge window's side/mid ratio
     diluted below 0.6 by the narrow/silent content sharing that same
     window, causing that one edge window to under-count. This biases
     the detector toward *under*-detection at region edges (a few tens
     of ms of a real element's boundary may not be corrected), never
     toward false-positive misclassification of a single transient — an
     acceptable, explicitly-flagged trade-off (see §9 risk #5), and the
     opposite failure direction from DEF-003.
   - Correction (`stereo_correct.py`, stage [5]): for a sustained
     stereo-widened region (≥2 contiguous flagged windows) whose phase
     correlation dips below the 0.0 floor, scale down the side-channel
     energy within that region by the minimum amount needed to bring
     correlation back to ≥0.0 (not a full mono-sum — least correction
     necessary), applying a **50 ms raised-cosine crossfade** at each
     region boundary specifically to avoid the zipper/pumping artifacts
     flagged as a risk in the v1 pass of this document (§9 risk #5).
     Iterate with the same bounded, deterministic approach as the
     loudness solver (fixed max iterations, no wall-clock cutoffs) for
     AC10 reproducibility. This stage is unaffected in its own logic by
     the v3 windowing change — it consumes whatever contiguous flagged
     regions `stereo_phase.py` now correctly produces.

   **Why this option over the alternatives considered:** DEF-003's fix
   notes offered three options — (a) remove overlap, (b) raise the
   debounce threshold to 3 with the existing 50%-overlap windows, or (c)
   redefine the criterion in terms of a wall-clock-independent minimum
   sustained duration measured more finely than the window grid. Option
   (a) is chosen because it is the simplest fix that is *exactly*
   mathematically sound (no residual "does N windows really mean N*hop of
   real content" ambiguity — with no overlap, each window is a genuinely
   disjoint slice of track time, so "2 consecutive flagged windows" means
   exactly what it says). Option (b) was rejected: raising the threshold
   to 3 under 50% overlap changes the *minimum* qualifying span but does
   not remove the underlying conflation between window-touch-count and
   actual duration, and would still admit some short-but-not-truly-brief
   content (anything spanning just over one extra hop) at an
   arbitrary-feeling boundary that's harder to reason about and explain
   than a clean non-overlapping tiling. Option (c) (fine-grained,
   sub-window duration measurement, e.g. 50ms micro-frames) is the most
   theoretically precise but adds real implementation complexity (a
   second, finer analysis grid purely for gating) and a second energy-
   ratio computation whose own window-length-vs-stability trade-off would
   need separate justification — not worth it given option (a) fully
   resolves the proven defect with a simpler, easier-to-verify design.
   AC10 determinism is preserved: the window/hop/debounce parameters are
   fixed constants in `config.py`, the windowing is purely a function of
   sample position (no adaptive or wall-clock-based behavior), and the
   same input+config always produces the same classification.

## 9. Open architectural risks

1. **Genre reference curve default (§8 #1) is a reasoned placeholder, not
   producer-verified.** The concrete -1.5/-3.0/-4.0 dB curve is fixed and
   implementable now, but until `scripts/build_reference_curve.py` is run
   against producer-nominated reference tracks, frequency-balance
   flags/corrections are only as good as that default. Recommend running
   the calibration script early in QA rather than treating the default as
   final.
2. **TT DR-meter has no mature Python library.** Implementing directly
   from the published Pleasurize Music Foundation spec is the right call,
   but it needs validation against known reference DR values (e.g.
   cross-checking a handful of tracks with published/independently-verified
   DR numbers) before AC4 can be trusted end-to-end.
3. **True-peak metering has no mature Python library either**, and this
   one is safety-critical: AC3 tolerates zero exceptions (on the delivered
   audio's -1 dBTP ceiling — requirements.md v3 §8 Q12). **Updated v4
   (DEF-002 resolution):** the oversampling filter itself moved from
   `soxr` to a purpose-built `scipy.signal.firwin`/`upfirdn` FIR design
   specifically to fix a confirmed near-Nyquist passband-attenuation
   defect that broke TC-022's cross-factor monotonicity (see §2) — this
   is a `firwin`-designed *approximation* of the properties BS.1770-4
   Annex 2 wants, not the standard's own literal published filter
   coefficients (which were not sourced/verified in that pass). **Updated
   v5 (second DEF-002 residual):** the v4 filter's own passband ripple was
   measured (freqz sweep) and found flat (<0.01 dB) only up to ~80% of
   original Nyquist, degrading — always as *attenuation* (under-read),
   never gain, given the image-safety-driven cutoff-at-Nyquist placement —
   to ~0.02 dB at 85%, ~0.4 dB at 90%, ~1.5-2 dB at 94-95%, and ~5.9 dB at
   99.9%. Closing this fully (<0.01 dB to 0.999×) would need ~40,000+ FIR
   taps, verified computationally infeasible within the 5-minute NFR
   budget. §2/§7 now formalize a tiered ripple envelope matching this
   measured, already-implemented behavior instead of the prior single flat
   aspirational target. Note the comparison to `soxr` needs stating
   precisely, not generally: the v4 filter is a genuine, verified
   improvement over `soxr` specifically in the region that mattered for
   TC-022 (flat to <0.01-0.05 dB up to ~85% Nyquist, vs. `soxr`'s
   attenuation starting much earlier), but is *not* a strict improvement
   at every frequency in the extreme near-Nyquist tail — at ~94% Nyquist
   the v4 filter's own worst-case ripple (~1.5-2 dB) is larger than the
   single `soxr` VHQ droop figure previously measured at that point
   (~0.54 dB); these may reflect different measurement methods
   (filter-response ripple vs. one end-to-end reading) and have not been
   reconciled, but the honest framing is "materially better across the
   region that fixed the defect, not uniformly better everywhere," not an
   unqualified "improvement across the whole range" claim. The residual
   risk is accepted as bounded and narrow in practice (a real ceiling miss
   would require a track's *composite* peak to be dominated by energy
   above ~0.90-0.94× Nyquist — an edge case for this genre/generation
   pipeline, not the common case — see §2 for the full argument), with
   TC-024 (cross-validation against a known-good independent true-peak
   meter, still unresolved per defects.md's residual-validation-
   dependencies list) remaining the actual closure path and the single
   highest-stakes unresolved verification gap in the pipeline. A
   conditioned (measured-HF-energy-triggered) enforcement margin was
   considered as a cheap future mitigation but not implemented in this
   pass — see §2 for why.
4. **WAV chunk preservation is unverified against a real Suno export.** No
   actual Suno export file has been inspected yet to see what non-audio
   chunks (if any) it actually contains — `wav_chunks.py`'s design assumes
   a fairly standard RIFF layout. Recommend obtaining a real sample export
   early and validating against it; the chunk-splicer should fail
   *gracefully* (pass through with a logged warning, not abort the whole
   run) if it encounters an unrecognized/nonstandard chunk structure,
   rather than treating metadata-chunk oddities as fatal errors.
5. **Stereo-widened-element segmentation (§8 #2, revised in v3) is now a
   mathematically sound debounce (non-overlapping 500ms windows, 2-window
   /1000ms minimum), but it is still a fixed heuristic, not a solved
   problem.** The window length, 0.6 side/mid ratio, and 50ms crossfade
   parameters are defaults, not yet validated by ear; the known
   boundary-dilution edge case (documented in §8 #2) means genuinely
   sustained elements whose edges fall near a window boundary may be
   under-corrected at their very edges. This needs listening-based QA in
   addition to numeric correlation pass/fail and the single-transient
   rejection checks (TC-043-equivalent, now re-verifiable against the v3
   design), and may need parameter tuning after first listen. The
   mathematical flaw that made single transients *always* misclassify
   (DEF-003) is resolved; residual calibration/tuning risk on the
   corrected parameters is not new and was already flagged here in v2.
6. **The LUFS/true-peak/DR solver has three interacting constraints** and
   needs a well-defined "give up" path (report why -13.5 wasn't reached,
   per AC2) as well as a genuinely bounded, deterministic convergence
   (fixed iteration count, not wall-clock/tolerance-based) to satisfy
   AC10. This is the most algorithmically complex single piece of the
   pipeline and the one most likely to need iteration after first
   implementation. **Updated v4 (DEF-001 resolution):** the -16 LUFS value
   is no longer a hard solver constraint — python-developer numerically
   proved it is physically incompatible with the DR floor for some
   legitimate high-crest-factor long-form sources (the story's actual core
   use case), so §1 now specifies only two hard constraints (peak ceiling,
   DR floor), with LUFS fully soft and a new `below_documented_lufs_floor`
   report flag for the below-16 case. This is flagged in §11 as an
   assumption pending BA confirmation, since it changes what AC2
   guarantees. It also means "genuinely rare" is asserted, not yet
   empirically proven, beyond the two fixtures that motivated the fix
   (TC-015, TC-130) — recommend QA construct a wider sweep of
   crest-factor/source-DR combinations to confirm how often tracks
   actually land below -16 in practice; if it turns out to be common
   rather than rare, that itself is signal the BA should see before this
   ships.
7. **EQ/stereo-stage DR erosion vs. the AC4 comparison baseline** — see
   the note at the end of §1. Easy to get subtly wrong if the solver
   compares against its own stage-entry DR rather than the true
   pre-processing source DR.
8. **In-memory full-track float64 processing is assumed to comfortably fit
   the 5-minute budget and typical consumer-hardware RAM**, but this
   hasn't been benchmarked yet — flagging as an assumption rather than a
   verified fact, since the oversampling stages (true-peak metering,
   potentially called multiple times across pre/post analysis and solver
   iterations) are the most likely place for this to matter if it doesn't
   hold. The v4 true-peak filter change (a longer FIR convolution via
   `upfirdn` in place of `soxr`'s optimized C implementation) may shift
   this further — worth including in the eventual benchmark pass. **v5**:
   this unresolved benchmarking gap is now also the explicit reason a
   tap-count increase was rejected as a mitigation for the v5 residual
   above — see §2.
9. **`pydub` is present in the project's installed dependencies but
   deliberately excluded from the precision-critical signal path** (see
   §2). Flagging this explicitly since it's already installed and could
   otherwise look like the obvious/default choice to a developer picking
   up this story without reading this document closely.

## 10. Assumptions pending BA confirmation (v4) — CONFIRMED 2026-07-31

Both items below were confirmed by the BA/product owner on 2026-07-31; see
requirements.md v3, Section 8, Open Questions #11 and #12, for the
authoritative confirmation and rationale. Left in place below (unedited)
as the historical record of the reasoning that led to the confirmed
decisions. **v5 adds no new entry here** — see §2's "True-peak passband
ripple target — revised (v5...)" subsection for why: the target being
revised is architecture's own aspirational verification figure, not a
BA-specified number, and requirements.md v3 §8 Q12 (below) already covers
the relevant framing (zero-exceptions applies to the delivered-audio
ceiling, not metering-tool internal precision).

- **DEF-001 residual fix (§1): the -16 LUFS value in AC2 is now treated
  as a soft, reported threshold rather than a hard floor the solver must
  never cross.** requirements.md AC2 states the output "may land as low
  as -16 LUFS if reaching -13.5 LUFS would require dynamics-destroying
  limiting, in which case the report must explain why" — this language
  describes -16 as an expected landing point under adverse conditions,
  not explicitly as an inviolable lower bound that must trigger an error
  if unreachable. The prior (v1–v3) architecture read it as a hard floor;
  python-developer's numerical proof (defects.md DEF-001) shows that
  reading is physically incompatible with the also-BA-resolved DR floor
  for a class of legitimate, core-use-case long-form dynamic tracks (high
  body/transient crest factor). This revision assumes the BA's intent,
  given a genuine conflict between two of their own resolved numbers, is
  for the DR floor (tied to the story's explicit "don't flatten the
  build/payoff" creative intent) to win, with LUFS allowed to land below
  -16 in the cases this happens, clearly reported when it does. **This has
  not been confirmed by the BA/product owner** — recommend confirming
  before this reaches production use, since it changes AC2's guarantee
  from "we will always land at -16 or better" to "we will always protect
  DR and peak; LUFS may occasionally land below -16 for high-crest-factor
  sources, and we'll tell you when it does." If the BA instead wants -16
  preserved as an absolute floor even at the cost of DR, the correct
  alternative is option (c) from the DEF-001 fix notes (recalibrate the
  DR-floor rule for very-high-source-DR material) — not implemented here,
  flagged as the fallback if this assumption is wrong.
- **DEF-002 residual fix (§2): TC-022's monotonicity assertion is given a
  small documented tolerance rather than requiring strict increase with
  oversampling factor.** This assumes AC3's "zero exceptions" bar is about
  the -1 dBTP ceiling itself never being exceeded (a real safety
  requirement, still held exactly) rather than about a synthetic
  self-consistency check between oversampling factors (a metering-
  implementation test, not a delivered-audio safety property). Recommend
  BA/QA confirm this framing is acceptable; if AC3 is intended to also
  guarantee strict oversampling-factor monotonicity as a proxy for meter
  trustworthiness, the tolerance would need to be removed and true-peak's
  filter design tightened further (likely requiring the actual ITU-R
  BS.1770 Annex 2 published filter coefficients rather than a
  `scipy.signal.firwin`-designed approximation — see §9 risk #3).

  **Update 2026-07-31 (requirements.md v3):** both items above were
  confirmed by the BA/product owner — see requirements.md v3 §8 Open
  Questions #11 and #12 for the authoritative decision and rationale.
  Retained here unedited as the historical record of the reasoning that
  led to those confirmed decisions.

## 11. Downstream implementation note (v4)

Both changes in this revision touch code that has already been
implemented and partially fixed by python-developer against the v1–v3
contract:

- **`mastering/loudness_limit.py`** is stale against §1's v4 solver
  contract: the code-level DEF-001 fix (feasibility check requiring
  `achieved_lufs >= config.lufs_floor - tolerance`) must be **removed**,
  candidate selection changed to "highest achieved_lufs among DR/peak-
  feasible candidates, no lower bound," and `UnresolvableMasteringConstraintError`
  narrowed to fire only when no candidate is DR/peak-feasible at all. A
  new `below_documented_lufs_floor` field needs adding to whatever result
  type `loudness_limit.py` returns, and threading it through to
  `MasteringResult`/the report builder.
- **`analysis/true_peak.py`** is stale against §2's v4 filter design: the
  `soxr`-based oversampling call needs replacing with the
  `firwin`/`upfirdn`-based FIR interpolation described above, tuned and
  numerically verified per the new §7 frequency-sweep test. The existing
  DEF-002 guard-region trim and the `factor` floor fix (`max(1, ...)`) are
  unaffected and should be kept as-is on top of the new filter.
  `mastering/resample.py` (stage [3]) is **unaffected** — it keeps using
  `soxr` exactly as before.

**Note (2026-08-01): both items above were implemented and independently
verified against v4 by python-developer's verification pass (defects.md,
2026-08-01) — see defects.md DEF-001/DEF-002 for the full evidence. No
further action needed on these two items.**

**v5 addition: no code change required.** The v5 revision (§2, §7, §9 risk
#3) formalizes architecture's own aspirational verification target to
match `true_peak.py`'s already-implemented and already-verified filter
behavior — `numtaps=32×factor`, `beta=9.0`, `cutoff=0.5` (exactly original
Nyquist) are unchanged, and no tap-count increase or margin logic is being
requested. The only artifact that needs updating is the **test spec**:
`tests/test_smoke_true_peak_fir.py`'s existing single-tier check
(0.80×/0.01 dB) already conforms to §2's new tiered envelope's first tier
and needs no change to pass; extending it to assert the remaining tiers
(0.85/0.90/0.95/0.999×) explicitly is a recommended **test-case-writer/QA
task**, not a python-developer task — there is nothing stale in
`true_peak.py` itself for python-developer to pick up from this revision.

## 12. Revision history

- v1 (2026-07-31): Initial architecture, based on requirements.md v2 (all
  open questions resolved). No prior architecture.md or defects.md existed
  for this story.
- v2 (2026-07-31): Resolved both v1 architecture-level gaps flagged in §8:
  genre reference spectral curve now has concrete default values
  (-1.5/-3.0/-4.0 dB) plus a documented calibration mechanism
  (`scripts/build_reference_curve.py`); stereo-widened-element
  identification now has concrete parameters (500 ms/250 ms window/hop,
  0.6 side/mid ratio, 2-window debounce, 50 ms crossfade correction).
  Risks #1 and #5 in §9 updated to reflect resolved-defaults status
  (residual calibration/listening-QA risk remains, not a design gap).
  Unblocked for python-developer/test-case-writer.
- v3 (2026-07-31): Resolves DEF-003 (Architectural defect reported by
  qa-automation-engineer, TC-043). QA mathematically proved that v2's §8
  #2 debounce (500ms window / 250ms hop / 50% overlap / ≥2-consecutive-
  window debounce) could never filter a single brief transient, because
  under 50% overlap every interior time position — including an
  instantaneous event — necessarily falls inside exactly 2 overlapping
  windows, making the debounce threshold trivially always satisfied.
  **Change:** §8 #2 now specifies non-overlapping 500ms windows (hop =
  500ms, no overlap) with the same ≥2-consecutive-window debounce, which
  is now mathematically sound: 2 consecutive non-overlapping windows can
  only both flag if the widened content genuinely spans ≥1000ms of real,
  disjoint track time, so a single 20–200ms transient positioned away
  from a window boundary cannot qualify. §9 risk #5 updated to reflect
  that the mathematical flaw is resolved while flagging that
  listening-based calibration of the corrected parameters is still
  outstanding, plus a new documented boundary-dilution edge case (biases
  toward *under*-correction at region edges, never toward false-positive
  single-transient misclassification — the opposite, safer failure
  direction from the DEF-003 bug). §7 testability notes updated with
  concrete fixture guidance for `stereo_phase.py` (single-transient
  rejection test, sustained-pan positive test, boundary-straddling edge
  case test).

  **Downstream impact for python-developer:** the v2 implementation of
  `stereo_phase.py` (if already built against the 250ms-hop/50%-overlap
  spec) is now stale and must be updated to hop=500ms (no overlap) before
  TC-043 can pass; `stereo_correct.py` (stage [5]) is unaffected in its
  own logic, since it only consumes whatever contiguous flagged regions
  `stereo_phase.py` produces — no change needed there beyond however the
  region-boundary data structure is shaped. See defects.md DEF-003 for
  the QA-side status update.

- v4 (2026-07-31): Resolves the residual, Architectural portions of
  DEF-001 (TC-015, TC-130) and DEF-002 (TC-022) — both retagged
  Architectural by python-developer after numerically proving each was a
  genuine design-level gap, not a code bug, in their DEF-001/DEF-002 fix
  notes (defects.md).

  **DEF-001 residual — solver contract change (§1).** The v1–v3 solver
  treated -16 LUFS as a hard constraint alongside the DR floor and peak
  ceiling. python-developer proved this is physically unsatisfiable for
  some legitimate high-crest-factor long-form fixtures (TC-015: source
  DR=19; TC-130: source DR=20) under the single-broadband-gain-plus-
  limiter design, because BS.1770 gating makes integrated LUFS for this
  signal shape track the near-ceiling transients, so any gain increase
  large enough to move LUFS toward -16 erodes DR below the floor first.
  **Change:** the -16 LUFS value is now a soft, report-escalation
  threshold, not a hard solver constraint. Hard constraints are narrowed
  to exactly two: the -1 dBTP peak ceiling and the DR floor
  (max(DR8, source_DR-3dB)). The solver now selects the highest
  achieved-LUFS candidate that satisfies both hard constraints, with no
  lower LUFS bound; `UnresolvableMasteringConstraintError` is narrowed to
  fire only when no candidate satisfies the DR floor and peak ceiling at
  all. A new `MasteringResult.below_documented_lufs_floor` boolean and an
  escalated rationale-text requirement cover the case where the selected
  candidate lands under -16. Three options from python-developer's fix
  notes were evaluated (RMS/multiband leveler upstream of the limiter;
  soft LUFS floor; recalibrated DR-floor rule for high-source-DR
  material) — the soft-floor option was chosen; see the dedicated §1
  subsection for the full evaluation and rejection rationale for the
  other two. **This is flagged in the new §10 "Assumptions pending BA
  confirmation" as not yet BA-confirmed**, since it changes what AC2
  guarantees.

  **DEF-002 residual — true-peak oversampling filter change (§2).**
  python-developer confirmed `soxr` has real, unavoidable (via its Python
  binding) passband attenuation near Nyquist across all quality presets
  (~0.54 dB at ~94% Nyquist for VHQ), which inverted rather than
  preserved the expected monotonicity of true-peak readings across
  oversampling factors (TC-022), and is not a general resampler's correct
  optimization target for true-peak metering in the first place (general
  resamplers deliberately trade passband flatness near Nyquist for
  anti-aliasing margin, which true-peak oversampling doesn't need since
  the oversampled buffer is never played back). **Change:** `true_peak.py`
  now uses a purpose-built polyphase FIR interpolation filter
  (`scipy.signal.firwin` design + `scipy.signal.upfirdn` application,
  cutoff placed at exactly the original Nyquist) instead of `soxr` for
  its oversampling. `soxr` is unchanged and retained for stage [3]'s
  genuine format-rate conversion, where its anti-aliasing-margin bias is
  correct. A documented `true_peak_monotonicity_tolerance_db` (default
  0.05 dB) is introduced for TC-022-style cross-factor self-consistency
  test assertions specifically — never for actual -1 dBTP ceiling
  enforcement, which remains exact. This tolerance framing is also
  flagged in §10 as not yet BA-confirmed. §9 risk #3 updated to note the
  new filter is a `firwin`-designed approximation of BS.1770 Annex 2's
  intent, not the standard's literal published coefficients — residual
  cross-validation risk (TC-024) remains the top unresolved verification
  gap.

  **Downstream impact for python-developer (see new §11):**
  `mastering/loudness_limit.py`'s code-level DEF-001 fix (the
  `achieved_lufs >= lufs_floor - tolerance` feasibility clause) must be
  removed and candidate selection/error-scoping updated per §1;
  `analysis/true_peak.py`'s `soxr` oversampling call must be replaced
  with the `firwin`/`upfirdn` FIR design per §2, tuned and verified via
  the new §7 frequency-sweep test; `mastering/resample.py` is unaffected.
  See defects.md DEF-001 and DEF-002 for the corresponding status
  updates — both now "Architecturally resolved — awaiting
  implementation."

- v5 (2026-08-01): Resolves the second, newly-surfaced residual of DEF-002
  (defects.md, verification note 2026-08-01, qa-automation-engineer/
  python-developer re-verification pass): the v4 FIR true-peak
  oversampling filter's passband ripple was measured to hold the
  aspirational <0.01 dB target only up to ~80-85% of original Nyquist, not
  the full ~99.9%-of-Nyquist range architecture.md v4 §2/§7 implied, and
  closing that gap fully was verified computationally infeasible within
  the 5-minute NFR budget (~40,000+ FIR taps needed).

  **Change:** §2 and §7 now specify a tiered ripple-vs-frequency envelope
  (≤0.01 dB to 0.80×, ≤0.05 dB to 0.85×, ≤0.5 dB to 0.90×, ≤2.5 dB to
  0.95×, ≤6.5 dB to 0.999× of original Nyquist) matching the verified,
  already-implemented filter's real behavior, replacing the single flat
  aspirational figure. The error direction is explicitly documented as
  attenuation/under-read approaching Nyquist (never over-read, given the
  image-safety-driven cutoff-at-Nyquist placement) — the safety-relevant
  direction for a zero-exceptions ceiling — and the residual is accepted
  as bounded and narrow in practice via a composite-peak argument (a real
  ceiling miss requires the track's dominant peak content to sit above
  ~0.90-0.94× Nyquist, an edge case for this genre/generation pipeline),
  with TC-024's still-open external cross-validation as the actual closure
  path. A flat safety margin on ceiling enforcement was considered and
  rejected (too costly if large enough to matter, too weak to matter if
  kept cheap); a measured-HF-energy-conditioned margin was identified as a
  plausible cheap future mitigation but not implemented in this pass. §9
  risk #3 updated with the tiered figures, the corrected (narrower, more
  precise) comparison to `soxr`'s own droop figure, and the composite-peak
  risk framing. §11 updated to state explicitly that **no code change is
  required** for this revision — `true_peak.py`'s filter design
  (taps/beta/cutoff) is unchanged and already conforms; only
  `tests/test_smoke_true_peak_fir.py`'s asserted bounds need extending to
  the full tiered envelope (recommended test-case-writer/QA task). No new
  §10 assumption-pending-BA-confirmation entry was added, since the target
  being revised was architecture's own aspirational verification figure,
  not a BA-specified number — requirements.md v3 §8 Q12 already confirmed
  AC3's zero-exceptions bar applies to the delivered-audio ceiling
  (unchanged, still exact), not to the metering implementation's internal
  precision, which is exactly what this revision formalizes. Also
  corrected a stale cross-reference in the document header (was citing
  requirements.md v2; now correctly cites v3, which is what v4's own
  §10/§1 content already depended on).

- v6 (2026-08-13): Resolves DEF-009 (Architectural, triaged 2026-08-12).
  Two STORY-001 core acceptance criteria tests (TC-014[-9.0], TC-023[hot])
  failed with `UnresolvableMasteringConstraintError` following the STORY-006
  corrective-EQ changes. The python-developer's retriage confirmed the solver
  was behaving correctly per the existing §1/§7 contract: both fixtures used
  source DR3–5, below `config.dr_floor=8.0`, which is precisely the "source
  itself, essentially unprocessed, is already at or below its own DR floor"
  case that §1 point 4 mandates raises that exception. The old pipeline's
  uncapped EQ had been inadvertently rescuing these fixtures by boosting
  crest factor 3+ dB; the new `corrective_eq.py` cap of 2.0 dB correctly
  cannot replicate that side-effect.

  **Change:** §7 adds an explicit pipeline-level fixture feasibility
  requirement (source DR 10–11 for AC2/AC3 pass/result tests) with a
  derivation of the body_peak_amp constraint from the TT DR formula, and
  strengthens the §7-mandated positive `UnresolvableMasteringConstraintError`
  test requirement to require a hard assert (not `pytest.skip`) using
  confirmed DR3–5 fixture shapes. No pipeline code change. See defects.md
  DEF-009 for the full decision rationale.

  **Downstream impact for qa-automation-engineer:** TC-014[-9.0] and
  TC-023[hot] fixture parameters must be redesigned to
  `body_peak_amp ≤ 0.300` (for DR ≈ 10–11 with transient ≈ 0.95); the old
  DR3–5 shapes must be repurposed into a hard-assert positive test for
  `UnresolvableMasteringConstraintError`. No python-developer or pipeline
  changes needed.
