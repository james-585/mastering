# Defects Archive

Closed defects from completed stories (STORY-001 through STORY-006), archived 2026-08-12.
Active defects (Open, Fixed-Pending-Retest, Architectural) remain in each story's defects.md.

---

## STORY-001

*Active defects retained in stories/STORY-001/defects.md: DEF-006 (Fixed-Pending-Retest).*

## DEF-001
Status: Closed (2026-08-01, qa-automation-engineer full-suite re-verification)
Reported by: qa-automation-engineer
Linked test case: TC-015, TC-016 (boundary passed by luck), TC-130
Description: The loudness/true-peak/DR solver (`mastering/loudness_limit.py`,
`solve_loudness_and_limit`) can produce output **below the documented -16
LUFS floor** (AC2: "may land as low as -16 LUFS ... never going below -16
LUFS" per architecture.md Section 1). Root cause: `_render_candidate()`
computes `gain_db = target_lufs - current_lufs` and applies that broadband
gain, then runs the limiter. When the limiter subsequently has to apply
significant additional gain reduction to hold the true-peak ceiling (or,
separately, the DR-floor-driven bisection lands on a candidate far from its
own target), the **post-limiting achieved LUFS is not re-targeted / not
clamped to `>= config.lufs_floor`** -- the solver simply accepts whatever
LUFS resulted from the (target-gain + limiter) chain, even when that's well
under -16.

Reproduction (TC-015 fixture, `tests/test_ac2_loudness.py::
test_tc015_rationale_present_when_backing_off`): a 40s stereo track, body at
-30 dBFS RMS (220 Hz), sparse 5ms transients at amplitude 0.94, 44.1kHz.
- Expected: `-16.0 <= after.integrated_lufs <= -14.5` (backed off below the
  soft band, per AC2, but never below the hard -16 LUFS floor).
- Actual: `after.integrated_lufs = -19.79` LUFS (`achieved_true_peak_dbtp`
  correctly `-1.00 dBTP`, DR correctly protected at DR16). The solver's
  internal `target_lufs` for the winning candidate was `-13.54` (an
  earlier/higher bisection step marked "feasible" at the DR/TP check, but
  its **achieved** LUFS after limiting drifted far below what was checked).

A second, independent reproduction with a different fixture (TC-130,
`tests/test_solver_errors.py::test_tc130_peak_ceiling_wins_over_lufs_band`):
achieved LUFS = -20.86, again well under -16.0.

Impact: this violates AC2's explicit hard-floor guarantee ("may land as low
as -16 LUFS" implies -16 is the deepest permitted back-off) and directly
undermines the story's instruction not to over-limit a build-driven track
being read backwards -- here the track is arguably being **under-loudened**
well past the documented floor without the pipeline raising
`UnresolvableMasteringConstraintError` (which architecture.md says should
fire instead of silently violating a hard constraint -- see TC-016).
Triage: Code-level
Fix notes: (filled in by python-developer) -- likely fix: the bisection's
feasibility check compares `candidate.achieved_lufs <= config.lufs_ceiling`
but never checks `candidate.achieved_lufs >= config.lufs_floor - tolerance`;
add that check to the feasibility test, and/or have `_render_candidate`
iteratively re-solve gain against the *achieved* (post-limiting) LUFS rather
than accepting a single gain-then-limit pass, so `achieved_lufs` actually
converges near `target_lufs` (or the solver explicitly falls through to
`UnresolvableMasteringConstraintError` when even the floor candidate
undershoots by more than tolerance).

**Fix notes (2026-07-31, python-developer):** Implemented the literal
reported fix -- `mastering/loudness_limit.py`'s bisection `feasible` check
now also requires `candidate.achieved_lufs >= config.lufs_floor -
solver_lufs_tolerance`, so a candidate whose *achieved* LUFS has drifted far
below -16 (regardless of what its `target_lufs`/DR/TP looked like) can never
be selected as `best` over the `floor_candidate` fallback. This is a real,
confirmed bug fix: the exact symptom described above (a higher-target
candidate silently winning despite an achieved LUFS of -19.79/-20.86) is
gone -- the solver now only ever returns the floor-target render (or a
provably-better one) as `best`.

However, TC-015 and TC-130 still fail after this fix, and this second half
is **not** a code bug -- it is a genuine, numerically-verified physical
limitation of the v1 "single global broadband gain + brickwall lookahead
peak limiter" design (architecture.md Section 2 "Limiter design note",
explicitly flagged there as the "recommended for v1" simpler option) when
applied to a source with a very high crest factor (quiet sustained body,
brief near-ceiling transients). I bisected the actual achievable-gain space
by hand for both fixtures (script output retained below) and confirmed
**no gain value exists that satisfies both `achieved_dr >= dr_required` and
`achieved_lufs >= -16` simultaneously**:

- TC-015 fixture (source DR=19.0, `dr_required`=16.0): at the only gain
  where achieved DR still clears 16 (~6.9-7.5 dB of applied gain), achieved
  LUFS is ~-19.9 to -19.5. Pushing gain further to raise achieved LUFS
  toward -16 immediately drops DR to 15 and below (DR13 by the point
  achieved LUFS reaches -16.6). No intermediate gain satisfies both.
- TC-130 fixture (source DR=20.0, `dr_required`=17.0): identical shape --
  DR=17 only holds at ~7.8 dB gain (achieved LUFS ~-20.8); DR drops to 16 by
  8.8 dB gain (achieved LUFS still only ~-20.0).

Root physical cause: for this class of fixture, BS.1770 gating means
integrated loudness is dominated by the loud transient blocks (the quiet
body is gated out), so raising broadband gain to chase a louder integrated
LUFS mostly raises the *already-near-ceiling* transients, which the peak
limiter must then clamp back down -- eroding the very DR the DR-floor is
protecting, in near lock-step with any loudness gain, well before achieved
LUFS can climb back to -16. This is the same category of complexity
architecture.md Section 9 risk #6 already anticipated ("most algorithmically
complex...most likely to need iteration after first implementation") and
Section 2's limiter design note flags ("Possible future refinement" -- an
oversampled/more surgical limiter -- doesn't address this either, since the
problem isn't inter-sample-peak precision, it's that *any* broadband-only
gain strategy can't decouple "raise the quiet body" from "raise the
already-loud transient" for this signal shape). Resolving this for real
would need either (a) an RMS/multiband or program-dependent gain stage
upstream of the peak limiter that can raise quiet passages disproportionately
to loud ones (the kind of "smarter compressor" architecture.md explicitly
deferred past v1), or (b) a documented relaxation of the -16 LUFS floor to
be soft (not a hard `>=` requirement) for extreme-crest-factor sources, or
(c) recalibrating what `dr_max_reduction_db` means for very-high-source-DR
material. All three are architecture-level product/DSP-design decisions, not
something I can decide unilaterally as a code fix -- retagging this residual
portion of DEF-001 (TC-015, TC-130 specifically) back to
**Architectural** per the "don't silently work around a design gap" rule,
while leaving the code-level portion (the wrong-candidate-selection bug)
fixed. Recommend software-architect review of the three options above; happy
to implement whichever is chosen.

I also want to flag: TC-015's own in-code comment ("DR right at the DR8+3dB
margin") assumes source DR ~11 for that fixture's parameters, but the
implemented (and TC-030-calibrated -- see that test's passing status)
`dynamic_range.py` measures its actual source DR at 19.0, not ~11. I didn't
find evidence this is a `dynamic_range.py` bug (TC-030's own DR8-boundary
construction is measured correctly), so I believe the fixture's actual
crest-factor parameters (body -30 dBFS RMS, transient amplitude 0.94, i.e. a
~26 dB peak/body ratio) simply produce a much higher real DR than the
comment assumed -- worth a second look by test-case-writer/QA when
re-verifying, since a fixture tuned closer to the commented DR8+3dB intent
might turn out to be achievable with the current limiter and confirm the
code-level fix in isolation.

**Architectural resolution (2026-07-31, software-architect, architecture.md
v4):** Option (b) chosen (with (a) and (c) evaluated and rejected) -- the
-16 LUFS value moves from a hard solver constraint to a soft,
report-escalation threshold. The solver's only hard constraints are now the
-1 dBTP peak ceiling and the DR floor (max(DR8, source_DR-3dB)); LUFS is a
fully soft target with no lower bound, and the solver selects the highest
achieved-LUFS candidate that satisfies both hard constraints. A new
`MasteringResult.below_documented_lufs_floor` boolean plus an escalated
rationale-text requirement cover cases (like TC-015/TC-130) that land under
-16. `UnresolvableMasteringConstraintError` is narrowed to fire only when no
candidate can satisfy the DR floor and peak ceiling together at any gain --
genuinely rare/pathological sources, not ordinary high-crest-factor
long-form tracks. Full evaluation of options (a)/(b)/(c) and precise
algorithm changes (feasibility check, candidate-selection logic, error
scoping, new config/result fields) are in architecture.md §1 (the "Solver
resolution for high-crest-factor sources (v4, resolves DEF-001 residual)"
subsection) and §11 (downstream implementation note).

**Note for python-developer:** `mastering/loudness_limit.py` is now stale
against architecture.md v4 -- the code-level fix applied above (the
`achieved_lufs >= config.lufs_floor - tolerance` feasibility clause) must be
**removed**, candidate selection changed to "highest achieved_lufs among
DR/peak-feasible candidates, no lower bound," and the
`UnresolvableMasteringConstraintError` condition narrowed per architecture.md
§1. A new `below_documented_lufs_floor` field needs adding to the solver's
result type and threaded through to `MasteringResult`/the report. See
architecture.md §7 for the new test fixtures expected (a TC-015/TC-130-shaped
fixture asserting the below-floor path resolves cleanly with the flag set,
and a separate genuinely-unresolvable fixture asserting the narrowed
`UnresolvableMasteringConstraintError` condition still fires correctly).
**Also flagged in architecture.md §10 as an assumption pending BA
confirmation** -- this changes what AC2 guarantees (LUFS may now land below
-16 for some legitimate high-crest-factor sources, always reported when it
does), so the BA/product owner should confirm this reading of AC2 before
this ships to production, even though implementation should proceed against
it now to keep the story moving.

**See "Verification pass (2026-08-01, python-developer)" at the end of this
file for implementation verification (code confirmed correct against
architecture.md v4, zero code changes needed) and the TC-015/TC-130/TC-131
targeted test results — including a note that TC-015/TC-130's own
assertions are stale against v4 and need test-side rework.**

**Closure (2026-08-01, qa-automation-engineer, full-suite re-verification.)**
`tests/test_ac2_loudness.py::test_tc015_...` and
`tests/test_solver_errors.py::test_tc130_...` are, on disk, **already
reworked** to the v4 soft-floor contract (asserting
`below_documented_lufs_floor is True`, DR floor held exactly, true-peak
ceiling held, rationale names the DR floor with the correct figure) —
someone (test-case-writer and/or a prior QA pass) had already applied
exactly the rework python-developer's 2026-08-01 verification-pass note
recommended, before I picked this up; test-cases.md's own revision-history
section confirms the same TC-016/TC-130 rework and the new TC-025 addition.
Ran the full automated suite fresh (not just the prior targeted subset):
`TC-015`, `TC-016` (the new untested-middle-tier fixture), `TC-130`, and
`TC-131` (unresolvable-case, narrowed-error-condition check) **all PASS**.
No stale test assertions remain against this defect. Closing.

---

## DEF-002
Status: Closed (2026-08-01, qa-automation-engineer full-suite re-verification
-- both the original TC-020/TC-021/TC-022 defect and the second FIR
passband-flatness residual (TC-025) are confirmed fixed/resolved; see
closure notes below each).
Reported by: qa-automation-engineer
Linked test case: TC-020, TC-021, TC-022
Description: `analysis/true_peak.py`'s `measure_true_peak()` takes
`np.max(np.abs(oversampled_buffer))` over the **entire** oversampled buffer,
including the soxr resampling filter's transient/ringing at the very start
and end of the buffer. For short, isolated test buffers (and, more
importantly, for any real track's actual start/end -- which are exactly
where a raw Suno export is most likely to have hard-cut boundaries), this
edge ringing can read up to ~0.8 dB **higher** than the signal's true
steady-state inter-sample peak, causing false "true peak exceeds ceiling"
readings that don't reflect genuine programme content.

Reproduction (`tests/test_ac3_true_peak.py::
test_tc020_true_peak_reveals_intersample_peak`): quarter-Nyquist cosine,
`A = 10**(-1.0/20)` (true peak should read exactly -1.00 dBTP per the
closed-form construction in test-cases.md TC-020), 44.1kHz, 2s buffer,
oversampled 8x.
- Expected: oversampled true-peak reading ~= -1.00 dBTP (+-0.1 dB).
- Actual (full-buffer max): **-0.207 dBTP** (0.79 dB higher than expected).
- Diagnostic (manual verification, not part of the automated suite):
  restricting the max to the interior 80% of the same oversampled buffer
  (excluding the first/last 10%) gives **-1.0000000 dBTP**, i.e. exactly
  correct -- the discrepancy is entirely attributable to a filter-edge
  transient at sample index ~705580 of 705600 (soxr `VHQ` quality). The same
  ~0.24 dB-class overshoot (smaller but still present) reproduces with
  `scipy.signal.resample_poly` as an independent oversampler, confirming
  this is a generic oversampling-filter edge-transient effect, not specific
  to soxr.
- Same root cause reproduces TC-021 (off by the same ~0.79 dB) and breaks
  the intended 1x/2x/4x/8x monotonicity check in TC-022 (1x and 4x tie at
  the boundary sample instead of 4x being strictly higher).

Impact: safety-critical per AC3 (zero exceptions tolerated on the -1 dBTP
ceiling) -- but in the *opposite* direction from a missed violation: this
is a false-positive risk that could cause the limiter/solver to treat a
track as exceeding the true-peak ceiling near its very start/end when it
does not, in turn triggering unnecessary extra gain reduction right at the
track boundaries (audible as an intro/outro-specific level dip), or, in the
metering/reporting path, showing an inflated (misleadingly "worse")
true-peak figure in the pre/post report for perfectly compliant audio.
Triage: Code-level
Fix notes: (filled in by python-developer) -- likely fix: exclude a short
guard region (matched to the oversampling filter's known settling
length, or simply pad the buffer with a few ms of the boundary sample
value / zero before oversampling and trim the corresponding oversampled
edge before the max() scan) so filter edge transients aren't mistaken for
genuine inter-sample peaks. Needs to be resolved before TC-024's external
cross-validation (see residual risk below) can be considered meaningful,
since an independent meter would need matched edge handling to compare
against.

**Fix notes (2026-07-31, python-developer):** Tried the suggested
pad-then-trim approach first (replicate/reflect-pad the input before
oversampling, then trim the corresponding padded region off the
oversampled result) and rejected it -- it does not reliably converge to the
correct value, because any synthetic edge continuation (constant-replicate
or mirror-reflect) itself introduces a *different* discontinuity relative to
the real, unknown continuation of the signal past the buffer edge; on the
TC-020 construction, edge-replicate padding still read ~0.6 dB high and
reflect-padding ~0.95 dB high, regardless of how much padding was added (44
to 4410 samples tested -- no improvement with more padding, confirming this
is not a "not enough padding" problem).

What actually converges to the correct value (verified against TC-020's
closed-form expected value down to 6 decimal places): **simply excluding a
small guard region directly from the peak scan**, without any compensating
padding -- `measure_true_peak()` now takes `np.max(np.abs(.))` over
`oversampled[guard:-guard]` where `guard` is a fixed ~5ms (matched to
`limiter.py`'s own default lookahead window, for consistency) at the
oversampled rate, rather than over the whole buffer. This matches
architecture.md's own diagnostic (trimming the outer 10% of the short
synthetic TC-020 buffer read exactly the correct value) but uses a much
tighter ~5ms guard instead of a generous 10%, to minimize the documented,
accepted trade-off: a genuine inter-sample-over occurring within the first/
last ~5ms of a real track's true boundary would not be caught by this
metering call. `clipping.py`'s inter-sample-over scan still uses the full,
untrimmed oversampled buffer (returned unchanged via
`TruePeakResult.oversampled`) so that lower-stakes/non-ceiling detection
isn't affected by this trade-off.

While fixing this, I also found and fixed a **separate, previously-masked
bug** that TC-022 specifically was catching: `measure_true_peak()` was
silently clamping `factor = max(4, config.true_peak_oversample_factor)`,
so requesting `true_peak_oversample_factor=1` or `=2` (as TC-022 does, to
verify factor-sensitivity) was silently upgraded to `4` internally --
exactly matching the reported "1x and 4x tie" symptom. Removed the forced
floor (now `max(1, ...)`) so the config value is honestly respected;
production code is unaffected since `config.py`'s own default is already 8x
(comfortably above the >=4x BS.1770-4 Annex 2 floor).

Result: **TC-020 and TC-021 now pass** (both read within 0.1 dB of their
expected values). **TC-022 still fails**, but for a newly-exposed, distinct
reason that only became visible once the factor-clamp bug above was fixed:
TC-022's own test signal is constructed at `sr * 0.47` (~94% of Nyquist,
deliberately close to it to probe oversampling-factor sensitivity), and at
that frequency `soxr`'s actual resampling filter response (verified across
all five `soxr` quality presets: QQ/LQ/MQ/HQ/VHQ) shows real, physical
passband attenuation approaching Nyquist -- VHQ reads ~0.54 dB *lower* at
that frequency than a naive (no-filtering) 1x reading, which inverts (rather
than ties) the monotonicity the test expects. This is not fixable via more
guard/trim logic (verified: it reproduces identically on the untrimmed,
full buffer) and the `soxr` Python binding used here (`soxr` 1.1.0) does not
expose lower-level filter/passband-width tuning to correct it while staying
within architecture.md's specified library (`soxr`). This is the same
category of gap architecture.md Section 9 risk #3 already flags ("needs
cross-validation against a known-good external true-peak meter") --
retagging this residual piece of DEF-002 (TC-022 only) as **Architectural**:
resolving it would need either a lower-level `soxr` API/version with
passband control, a different oversampling approach for the small subset of
near-Nyquist content it affects, or an accepted-risk note in architecture.md
Section 9 alongside risk #3. TC-020/TC-021 (the safety-critical false-
positive-near-track-boundaries defect, which was DEF-002's primary impact
concern) are fully fixed.

**Architectural resolution (2026-07-31, software-architect, architecture.md
v4):** `true_peak.py`'s oversampling moves from `soxr` to a purpose-built
polyphase FIR interpolation filter (`scipy.signal.firwin` design +
`scipy.signal.upfirdn` application, cutoff placed at exactly the original
Nyquist rather than pulled in for anti-aliasing margin) for the true-peak
metering path specifically. Root-cause framing: general-purpose resamplers
like `soxr` are correctly optimized for anti-aliased playback-rate
conversion, which is not what true-peak oversampling needs (the oversampled
buffer is discarded after the peak search, never played back) -- a filter
purpose-built for flat passband response up to Nyquist is the right tool for
this specific job. `soxr` is unchanged and retained for `mastering/
resample.py` (stage [3]'s genuine format-rate conversion), where its
anti-aliasing bias is correct. A new `config.true_peak_monotonicity_
tolerance_db` (default 0.05 dB) is introduced so TC-022's cross-factor
monotonicity assertion allows a small, documented tolerance rather than
requiring bit-exact strict increase -- this applies only to that class of
test assertion, never to actual -1 dBTP ceiling enforcement, which remains
exact and must always treat the higher of any close readings as
authoritative. Full design detail (filter construction parameters, why a
general resampler is the wrong tool here, the tolerance rationale) is in
architecture.md §2 (the "True-peak oversampling filter, v4" and "Accepted
tolerance for TC-022's cross-factor monotonicity check" notes) and §9 risk
#3 (updated with residual verification risk -- this is a `firwin`-designed
approximation of BS.1770 Annex 2's intent, not the standard's literal
published coefficients).

**Note for python-developer:** `analysis/true_peak.py` is now stale against
architecture.md v4 -- the `soxr`-based oversampling call must be replaced
with the `firwin`/`upfirdn` FIR design per architecture.md §2, with
`numtaps`/`beta` tuned and numerically verified via the new §7 frequency-
sweep test (passband ripple < 0.01 dB across a sweep of frequencies from
~0.5x to ~0.999x of original Nyquist) before being accepted as the
production default. The existing DEF-002 guard-region trim (~5ms at the
oversampled rate) and the `factor` floor fix (`max(1, ...)`) are unaffected
and should be kept as-is on top of the new filter. `mastering/resample.py`
requires no change. **Also flagged in architecture.md §10 as an assumption
pending BA confirmation** regarding the TC-022 tolerance framing.

**See "Verification pass (2026-08-01, python-developer)" at the end of this
file for implementation verification (code confirmed correct against
architecture.md v4, zero code changes needed) and the TC-020/TC-021/TC-022
targeted test results (all pass) plus the full §7 frequency-sweep test
results — including a NEW Architectural residual (FIR passband flatness
above ~85% Nyquist, short of the full <0.01dB-to-0.999x-Nyquist aspirational
target) filed under this defect.**

**Architectural resolution of the second residual (2026-08-01,
software-architect, architecture.md v5):** The FIR passband-flatness gap
found in the 2026-08-01 verification pass (below) is resolved by
**formalizing a tiered ripple-vs-frequency envelope** (≤0.01 dB to 0.80x
Nyquist, ≤0.05 dB to 0.85x, ≤0.5 dB to 0.90x, ≤2.5 dB to 0.95x, ≤6.5 dB to
0.999x) that matches the *already-implemented, already-verified* filter's
real, measured behavior, replacing architecture.md v4's single flat <0.01dB-
to-0.999x-Nyquist aspirational target -- which two independent, documented
tuning attempts (see `true_peak.py`'s own tuning-note comment) proved
cannot be met within the 5-minute NFR budget (~40,000+ taps required) while
keeping the image-safe cutoff placement that a prior attempt showed is
non-negotiable (pushing cutoff past Nyquist to chase passband flatness
reintroduces 5-6 dB *time-domain* image-leakage errors, worse than the
gap being closed). The error direction (attenuation/under-read approaching
Nyquist, confirmed via the existing `test_fir_filter_image_rejection_
beyond_nyquist` test's own attenuation-sign check) is documented explicitly
as the safety-relevant direction for a zero-exceptions ceiling, and the
residual is accepted as bounded and narrow in practice on a **composite-peak
argument**: a real ceiling miss requires the track's own dominant peak
sample to be governed by energy above ~0.90-0.94x Nyquist (>19.8-20.7kHz at
44.1kHz), which is an edge case for this genre (124bpm melodic progressive
house/techno) and for Suno-generated/lossy-stage-passed source material (per
requirements.md §3's own caveat about generation-stage artifacts already
rolling off that region), not the common case. A flat safety margin on
ceiling enforcement (e.g. treating -1.1dBTP as the effective internal
ceiling) was considered and rejected as either too costly (if large enough
to matter) or too weak (if kept cheap) to be a real mitigation; a
measured-HF-energy-conditioned margin (leveraging stage [2]'s existing Welch
PSD computation) was identified as a plausible, near-zero-cost future
mitigation but is **not implemented in this pass** -- the composite-peak
argument already bounds the practical risk acceptably without it, and
TC-024 (external cross-validation against a known-good independent
true-peak meter, still an open residual-validation dependency below)
remains the actual closure path if this residual turns out to matter in
practice. Full detail, including the corrected (narrower, not-uniformly-
better) comparison against `soxr`'s original droop figure, is in
architecture.md §2 (new "True-peak passband ripple target — revised (v5,
resolves DEF-002 second residual)" subsection) and §9 risk #3 (updated).

**Status of this second residual: Architecturally resolved — awaiting
test-spec update (not awaiting implementation).** Per architecture.md v5
§11, **no code change is required** -- `true_peak.py`'s filter design
(numtaps=32x factor, beta=9.0, cutoff=0.5 at original Nyquist) is unchanged
and already conforms to the new tiered envelope (verified: the filter's own
measured figures, cited above, are exactly what the tiered envelope was
built to match, with headroom). The only remaining action is a
**test-case-writer/QA task**, not a python-developer task:
`tests/test_smoke_true_peak_fir.py`'s existing single-tier check
(0.80x/0.01dB) already passes against the new envelope's first tier
unchanged; recommend extending it with explicit assertions at the remaining
tiers (0.85x/0.90x/0.95x/0.999x) so the full documented envelope --
including the near-Nyquist degradation -- is regression-protected rather
than only described in this ledger and in `true_peak.py`'s tuning-note
comment. **python-developer: nothing to pick up here** -- flagging this
explicitly since the rest of this defect's history (above) does describe
staleness that needed code changes; this second residual does not.

**Closure (2026-08-01, qa-automation-engineer, full-suite re-verification.)**
The recommended test-spec extension is already done:
`tests/test_smoke_true_peak_fir.py` now contains a full "TC-025 leg 1"
(`test_fir_filter_matches_tiered_ripple_envelope_v5_freqz_leg`, densely
swept 0.50-0.999x Nyquist against the tiered envelope + an explicit
attenuation-only-direction check) and "TC-025 leg 2"
(`test_measure_true_peak_matches_tiered_ripple_envelope_v5_end_to_end_leg`,
the same envelope exercised end-to-end through `measure_true_peak()`),
matching test-cases.md's TC-025 (added in the same revision that reworked
TC-016/TC-130). Ran the full file fresh: **all 14 collected cases pass**
(TC-020/TC-021/TC-022 plus every parametrized instance of both TC-025 legs
and the pre-existing achievable-band/image-rejection/grid-alignment smoke
checks). Traceability note (not a defect): the TC-025 leg functions are
named descriptively rather than `test_tc025_...`; they are cross-referenced
to TC-025 by docstring/comment, so coverage is real and traced, just not
via the `test_tcNNN_` naming convention used elsewhere in this suite --
worth a cosmetic rename in a future pass for consistency, not blocking.
Both DEF-002 residuals closed.

---

## DEF-003
Status: Closed (2026-08-01, qa-automation-engineer full-suite re-verification)
Reported by: qa-automation-engineer
Linked test case: TC-043
Description: `analysis/stereo_phase.py`'s 2-consecutive-window debounce
(500ms window / 250ms hop / 50% overlap, architecture.md Section 8 item 2)
is stated to "exclude single-transient false positives (e.g. one
hard-panned drum hit) from being treated as an element" (architecture.md
Section 1, and again in Section 9 risk #5's framing). With 50% window
overlap (window length = 2x hop length), this design **cannot actually
achieve that stated goal for any transient occurring away from the very
first/last window of the track**: every interior sample position is, by
construction, covered by exactly 2 overlapping windows (the current window
and its immediate predecessor, since consecutive windows share a 250ms
overlap region). Empirically, a single ~20-200ms hard-panned transient
(tested at multiple durations and amplitudes) consistently registers as
`is_widened=True` in **exactly 2 consecutive windows**, because the two
windows that see the transient have effectively the same
side_energy/mid_energy ratio (the surrounding near-silent/narrow background
contributes negligible energy either way) -- which is exactly the debounce
threshold (`stereo_debounce_windows: int = 2`), so the "single transient"
is *always* misclassified as a sustained "element" and becomes subject to
stage [5]'s stereo-narrowing correction and the +0.3 correlation target,
contrary to the documented intent.

Reproduction (`tests/test_ac5_stereo_phase.py::
test_tc043_single_transient_not_sustained_debounce`): 3s stereo buffer,
narrow 0.05-amplitude 300Hz background, single 200ms hard-panned transient
(amplitude +-0.5) at t=1.5s. Result: 2 consecutive windows flagged
`is_widened=True`, forming a `StereoWidenedRegion` (`needs_correction=True`)
-- confirmed at transient durations 20/40/60/80/100/200ms and amplitudes
0.3/0.5/0.8, all giving the same 2-window result regardless of parameters.

Impact: any single drum hit, vocal ad-lib, or other brief hard-panned
element anywhere in the interior of a track will be treated as a sustained
"stereo-widened element" and corrected (narrowed) by stage [5], even though
architecture.md explicitly intends the debounce to protect exactly this
case. This is a design/parameter-choice problem (window length must be
> 2x hop length, or the debounce threshold must be > 2, for any debounce
value to filter out a genuinely single, brief event), not a coding
mistake -- the code correctly implements the window/hop/debounce
parameters as specified in architecture.md Section 8 item 2; the
parameters themselves cannot deliver the stated behavior.
Triage: Architectural
Fix notes: (filled in by software-architect) -- needs one of: (a) reduce
window overlap (e.g. hop >= window length, i.e. no overlap, so a brief
transient can fall within a single window), (b) raise
`stereo_debounce_windows` to 3 (so 2-window transient coverage is
insufficient to qualify), or (c) redefine "element" duration in terms of
wall-clock span rather than raw window count so a transient whose total
overlap span is < some minimum (e.g. 500ms) doesn't qualify even if it
touches 2 windows. Needs to be resolved together with the existing
architecture.md Section 9 risk #5 ("fixed heuristic, not a solved problem
... needs listening-based QA") since it changes the same parameter set.

**Architectural resolution (2026-07-31, software-architect, architecture.md
v3):** Option (a) chosen -- window overlap removed. `stereo_phase.py` now
specified with **non-overlapping** 500ms windows (hop = 500ms, same
0.6 side/mid ratio, same `stereo_debounce_windows = 2`). Because windows no
longer overlap, "2 consecutive flagged windows" now means the widened
content genuinely spans >=1000ms of real, disjoint track time -- a single
20-200ms transient positioned away from a window boundary can only ever
fall inside one window and cannot satisfy the debounce. See
architecture.md Section 8 item 2 (full rationale, including why options
(b)/(c) were not chosen) and Section 9 risk #5 (updated) and Section 12
Revision history (v3 entry).

**Note for python-developer:** if `stereo_phase.py` was already implemented
against the v2 spec (250ms hop / 50% overlap), that implementation is now
stale against architecture.md v3 and must be updated to hop=500ms (no
overlap) before TC-043 can pass. `stereo_correct.py` (stage [5]) requires
no logic change -- it only consumes whatever contiguous flagged regions
`stereo_phase.py` produces. Status will move to Closed once
python-developer implements the v3 windowing and qa-automation-engineer
re-runs TC-043 (and the related boundary-straddling case noted in
architecture.md Section 7) against it.

**Note (2026-07-31, software-architect):** This entry is unchanged by the
architecture.md v4 revision -- v4 only addresses DEF-001 and DEF-002
residuals. `stereo_phase.py`/`stereo_correct.py` were not touched in this
pass, per explicit scope instruction.

**See "Verification pass (2026-08-01, python-developer)" at the end of this
file for implementation verification (code confirmed correct against
architecture.md v3, zero code changes needed) and the TC-043 result
(pass).**

**Closure (2026-08-01, qa-automation-engineer, full-suite re-verification.)**
Ran `tests/test_ac5_stereo_phase.py` fresh: `test_tc043_single_transient_
not_sustained_debounce` **PASSES**, along with TC-041/TC-042/TC-044/TC-045/
TC-046/TC-047 (7/8 tests in the file pass). The file's 1 remaining failure
(`test_tc040_fully_out_of_phase_reads_minus1`) is an unrelated, newly-found
bug in the same module -- filed separately as **DEF-006** below, not a
DEF-003 regression (DEF-003 was specifically about the debounce/window-
overlap defeating the 2-consecutive-window filter; TC-040's failure is a
NaN-propagation bug in the region-summary math, triggered by a
fully-out-of-phase fixture, orthogonal to the windowing logic DEF-003
concerned). Closing DEF-003.

---

## DEF-004 (residual observation, not a failure)
Status: Closed
Reported by: qa-automation-engineer
Linked test case: TC-101
Description: `io/export.py`'s `resolve_output_path()` always derives
`<input_stem>_mastered.wav`. Because appending the literal suffix
`_mastered` to any stem necessarily changes the stem, **the output path can
never equal the input path through this derivation for any real input
filename** -- the documented "hard-fails if the resolved output path would
equal the input path" guard (architecture.md Section 4) is, in practice,
unreachable via `pipeline.master()`'s current public API (which only
exposes `output_dir`, not an explicit output-path override). This was
initially investigated as a possible defect (TC-101's precondition
describes forcing a "naming override" that collides, implying the guard
should be reachable in normal operation) but on inspection this is
actually a *stronger* guarantee (collision-proof by construction) rather
than a bug -- there is no currently-exposed code path that could trigger a
genuine collision. `tests/test_ac11_nondestructive.py::
test_tc101_output_equal_to_input_hard_rejected` exercises the guard's own
conditional logic directly (via a `Path.resolve` monkeypatch) and confirms
`OutputPathConflictError` fires correctly when the condition it checks for
is actually met.
Triage: Code-level (documentation/observation only)
Fix notes: No code fix required. Recommend a documentation note in
architecture.md clarifying that the guard is currently unreachable via the
public API by design, so a future contributor adding an explicit
output-path override parameter to `master()` knows this guard is the
enforcement point that must remain in front of it.

---

## DEF-005
Status: Closed (2026-08-01, qa-automation-engineer full-suite re-verification)
Reported by: qa-automation-engineer
Linked test case: TC-123
Description: `io/ingest.py` does not validate that the actual audio data
available in the file matches the `data` chunk's declared size / the
`fmt`-derived frame count. For a WAV file truncated mid-`data`-chunk (the
`data` chunk's declared size, per its own RIFF header field, exceeds the
bytes actually present in the file), `soundfile`/libsndfile silently reads
however many complete frames are actually present and returns them without
error -- `wav_chunks.py`'s chunk scanner correctly detects and logs a
warning about the truncation (`"chunk b'data' at offset 36 declares size
... which runs past end of file"`), but this warning is purely about
*non-audio chunk* preservation scanning, not about the audio payload
itself, and nothing in `ingest.py` surfaces this as an error or even a
warning against the returned `IngestResult`. The pipeline proceeds to
produce a full mastered output and a clean report from a shorter-than-
declared, truncated buffer, with no indication anywhere (report or logs)
that the input was truncated.

Reproduction (`tests/test_edge_cases_formats.py::
test_tc123_truncated_file_fails_gracefully`): a valid 5s/44.1kHz WAV,
truncated to 50% of its file size (data chunk cut off mid-stream).
- Expected (per test-cases.md TC-123): `InvalidWavError` raised with a
  clear message; no crash from reading past end-of-file.
- Actual: no exception raised at all -- `pipeline.master()` completes
  successfully, silently processing and delivering a master built from
  roughly half of the intended audio, with the report showing no mention
  that the input was truncated/incomplete.
Impact: this doesn't crash (satisfies the narrower "no crash" half of the
robustness NFR) but silently delivers a materially incomplete/corrupted
master without any indication to the user, which is arguably worse than a
clear rejection for a "final master, replaces the manual workflow entirely"
tool (requirements.md Section 2/Open Question #7) -- a truncated raw Suno
export should not silently become a truncated "final" delivered master.
Triage: Code-level
Fix notes: (filled in by python-developer) -- in `ingest()`, after reading
audio via `sf.read`, compare the number of frames actually read against
`info.frames` (from `sf.info()`, which reflects the declared header value);
if they differ, raise `InvalidWavError` with a message identifying the
expected vs. actual frame counts (or, if partial-file recovery is
considered acceptable behavior, at minimum surface a report-level warning
so a truncated master is never delivered silently).

**Fix notes (2026-07-31, python-developer):** The suggested fix
(`sf.read()`-actual-frames vs. `sf.info().frames`) does **not** work --
verified directly: for a truncated file, `soundfile`/libsndfile's own
`sf.info()` already reports the *clamped/truncated* frame count (it
recomputes the effective `data` chunk size from the actual file size, not
from the file's originally-declared header value), so `sf.read()`'s actual
frame count and `sf.info().frames` always agree trivially, even on a
truncated file -- that comparison can never detect this class of
truncation via `soundfile`'s API alone.

Implemented a different, working fix: added `_validate_data_chunk_not_
truncated()` in `io/ingest.py`, which does its own minimal, dependency-free
RIFF walk (stdlib `struct`, same approach as `wav_chunks.py`) to find the
`data` chunk's header-declared size directly and compare it against the
number of bytes actually remaining in the file after that header -- this is
checked against the file's own on-disk declaration, which is exactly the
value that gets silently "corrected" before either `sf.info()` or
`sf.read()` ever see it. Raises `InvalidWavError` (with the declared vs.
actual byte counts) before any audio is read, called at the very start of
`ingest()`, right after the existing exists/zero-length checks. Any other
RIFF-structure oddity (missing `data` chunk, non-RIFF file, etc.) is left
to the existing `sf.info()`/`sf.read()`/`wav_chunks.py` error paths, which
already handle those gracefully -- this fix only ever inspects the `data`
chunk's size field specifically, to stay narrowly scoped to the reported
defect.

Result: TC-123 now passes (`InvalidWavError` raised with a clear message,
no partial master produced), and the rest of `test_edge_cases_formats.py`
(15/15) plus the full non-slow suite pass with no regressions.

**Closure (2026-08-01, qa-automation-engineer, full-suite re-verification.)**
Ran `tests/test_edge_cases_formats.py` fresh, independently: **15/15
pass**, including `test_tc123_truncated_file_fails_gracefully`. No
regressions elsewhere in the full suite attributable to this fix. Closing.

---


---

## STORY-002

*Active defects retained in stories/STORY-002/defects.md: DEF-202 (Open/Architectural),*
*DEF-205 gate false positive (Open), DEF-206 TC-507 fixture (Architectural).*

*--- Section 1: DEF-101 through DEF-201 (all entries and updates) ---*

## DEF-101 (Architectural): mono-sum "~0 dB change" example contradicts BS.1770's channel-summed convention

**Status: Fixed.**

**Fix notes (python-developer, this pass)**: implemented architecture.md v2
Section 4.5 exactly, in `analysis/mono_sum.py`:
- Renamed `_CORRELATED_SUM_BASELINE_DB` to
  `_BROADBAND_DECORRELATED_FLOOR_DB = 10.0*math.log10(0.25)` (-6.0206 dB) and
  added `_PERBAND_DECORRELATED_FLOOR_DB = 10.0*math.log10(0.5)` (-3.0103 dB).
- `excess_cancellation_db` now references the broadband floor
  (`level_change_db - _BROADBAND_DECORRELATED_FLOOR_DB`).
- Added `excess_delta_db` per band (`delta_db - _PERBAND_DECORRELATED_FLOOR_DB`)
  and switched the `cancellation` flag to compare `excess_delta_db` against
  the renamed config field, rather than comparing raw `delta_db` against the
  old threshold.
- `analysis/reference_types.py`: added `excess_delta_db: float` to
  `BandCancellation`; updated `MonoSumResult.excess_cancellation_db`'s
  field comment to the corrected -6.0206 dB floor.
- `reference_analysis/config.py`: renamed `mono_cancellation_threshold_db`
  to `mono_band_cancellation_excess_db` (default unchanged, -3.0; comment
  updated to state it's now compared against excess-beyond-floor, not a raw
  dB reading).
- `report/reference_builder.py`: updated the `config_summary()` key to the
  renamed field; bumped `SCHEMA_VERSION` from `"1.0"` to `"1.1"` (additive
  field + renamed config field, per architecture.md Section 9's convention).
- Module docstring replaced with a pointer to architecture.md Section 4.5
  and this entry, per instruction 1.

**Verification (python-developer, this pass)** — synthetic fixtures, 44.1kHz
stereo, `ReferenceAnalysisConfig()` defaults:

1. Correlated stereo (L=R, 6s Gaussian noise, sigma=0.05):
   `level_change_db = -3.0103`, `excess_cancellation_db = +3.0103` (positive
   — further from the cancellation floor than ordinary wide stereo, as
   specified). Every band `delta_db ≈ 0`, `excess_delta_db ≈ +3.010`,
   `cancellation=False` for all 7 bands.
2. Healthy decorrelated stereo (independent Gaussian noise in L and R, equal
   power, sigma=0.05, no phase relationship): `level_change_db = -6.0111`,
   `excess_cancellation_db = +0.0095` (≈0, as specified — this is the direct
   regression test for the false-positive DEF-101 found). **Every one of the
   7 bands reads `cancellation=False`** (`excess_delta_db` ranged -0.26 to
   +0.32 across bands, all well above the -3.0 threshold) — confirms the
   false-positive is fixed; under the old code every one of these bands
   would have read `cancellation=True` since `delta_db≈-3.0..-3.3 <
   -3.0` was true by construction for every band.
3. Out-of-phase 1kHz tone (L=+0.2·sin, R=-0.2·sin, plus independent
   sigma=0.001 noise floor in both channels): `level_change_db = -45.94`,
   `excess_cancellation_db = -39.92` (large negative, clearly
   cancellation-driven, as expected — exact figure differs from
   architecture.md's illustrative `-43.42` because the fixture's specific
   tone/noise-floor amplitudes differ from the one used to produce that
   number, not a discrepancy in the fix). The `mid` band (500-2000 Hz,
   containing the 1kHz tone) reads `delta_db=-57.69`,
   `excess_delta_db=-54.68`, `cancellation=True`; all 6 other bands (noise
   floor only, genuinely decorrelated) read `cancellation=False` with
   `excess_delta_db` in the -0.29..+0.02 range — confirms no false
   positives ride along with the true positive.

No existing STORY-001 or STORY-002 test file referenced the renamed
`mono_cancellation_threshold_db` config field or `BandCancellation`'s shape,
so no other code needed updating. Recommend test-case-writer/QA add the
ordinary-decorrelated-stereo fixture (case 2 above) as a permanent
regression test, per architecture.md's own recommendation.

**Where**: architecture.md Section 4.5, "Mono-sum level change + band-specific
cancellation." Now fully rewritten in v2 — see architecture.md §4.5.

**What was found**: architecture.md states `mono_sum = (L+R)/2` and asserts
"a perfectly-correlated signal reads ~0 dB change (as expected: summing two
identical, in-phase signals to mono at half amplitude each preserves level
under BS.1770's convention)."

Measured directly (python-developer, this pass): a 6-second, -0.1..0.1
amplitude Gaussian-noise stereo pair with L=R exactly, passed through
`measure_integrated_lufs`, gives:

```
stereo LUFS (L=R): -13.905886656713594
mono_sum LUFS:      -16.916186613353403
delta:               -3.010299956639809
```

This is not measurement noise or an implementation bug -- it is the correct
mathematical consequence of BS.1770's channel-SUMMED (not averaged)
integrated-loudness convention. **Architect confirms this measured figure is
correct** (`level_change_db`'s formula was never the bug) -- but the
resolution python-developer applied on top of it (referencing
`excess_cancellation_db`, and implicitly the per-band cancellation
threshold, to this same `-3.0103` figure) was itself incomplete/incorrect,
for a reason more specific than either the original report or the
architect's first-pass review of it identified:

**The actual root cause, confirmed against `mono_sum.py`'s code**: the
broadband `level_change_db` formula and the per-band `delta_db` formula
divide by *different* denominators (BS.1770 channel-**summed** stereo power
vs. the **mean** of the two channels' own band power, respectively), so they
have two genuinely different "fully decorrelated, ordinary healthy stereo"
floors:

| ρ (correlation) | broadband `level_change_db` | per-band `delta_db` |
|---|---|---|
| +1 (correlated/mono-like) | -3.0103 dB | 0 dB |
| 0 (decorrelated — ordinary healthy wide stereo) | **-6.0206 dB** | **-3.0103 dB** |
| -1 (anti-correlated/cancelling) | -inf | -inf |

python-developer's `excess_cancellation_db` referenced the broadband field
to `-3.0103` (the *per-band* ρ=0 floor, not the broadband one) — meaning an
ordinary, healthy, fully-decorrelated wide-stereo track reads
`excess_cancellation_db ≈ -3 dB` under the v1 fix, which reads as
"3 dB of unexplained cancellation" for completely normal material. Separately
and more seriously, the **per-band cancellation flag itself** (`delta_db <
config.mono_cancellation_threshold_db`, threshold default `-3.0`) was
**not changed** by the v1 fix at all, and fires on essentially any healthy
decorrelated band, since `-3.0103 < -3.0` is true by construction -- this is
exactly the false-positive the task brief flagged ("normal wide-stereo
tracks could false-positive as cancelling"), confirmed real by reading the
code, not merely by test-case-writer's independent observation.

**Resolution (architect, this pass)**: both derived fields are now
referenced to their own metric's ρ=0 (fully-decorrelated) floor —
`-6.0206 dB` for `excess_cancellation_db` (broadband), `-3.0103 dB` for the
new `excess_delta_db` (per-band) — rather than to the ρ=+1 (correlated)
value either was previously (mis)anchored to. Full formulas, code, and
per-ρ worked table in architecture.md §4.5.

**Concrete changes required in the implementation (not yet made — this is
an instruction to python-developer, not a completed fix)**:
1. `analysis/mono_sum.py`: rename/redefine
   `_CORRELATED_SUM_BASELINE_DB` → `_BROADBAND_DECORRELATED_FLOOR_DB =
   10.0 * math.log10(0.25)` (**-6.0206**, not -3.0103); add
   `_PERBAND_DECORRELATED_FLOOR_DB = 10.0 * math.log10(0.5)` (**-3.0103**);
   `excess_cancellation_db` now uses the broadband floor; add
   `excess_delta_db` per band and switch the `cancellation` comparison to
   use it (`excess_delta_db < config.mono_band_cancellation_excess_db`);
   replace the module's v1 "DEVIATION NOTE" docstring with a pointer to
   architecture.md §4.5 and this entry.
2. `analysis/reference_types.py`: add `excess_delta_db: float` to
   `BandCancellation`; update `MonoSumResult.excess_cancellation_db`'s
   comment to reflect the corrected `-6.0206` floor.
3. `reference_analysis/config.py`: rename `mono_cancellation_threshold_db`
   → `mono_band_cancellation_excess_db` (default unchanged, `-3.0` —
   only its meaning is corrected: it's now compared against *excess beyond
   the decorrelated floor*, not a raw dB reading).
4. `report/reference_builder.py`: update the renamed config field reference
   (currently reads `config.mono_cancellation_threshold_db`).
5. Bump `ReferenceSetReport.schema_version` to `"1.1"` (additive field +
   renamed config field, per architecture.md §9's versioning convention).
6. Test coverage: re-verify the existing out-of-phase 1kHz fixture — its
   `excess_cancellation_db` will change from the reported `-46.43 dB` to
   approximately `-43.42 dB` (same floor-shift, still clearly
   cancellation-driven) — and **add a new required fixture**: ordinary
   decorrelated stereo (independent, equal-power noise in L/R), asserting
   `excess_cancellation_db ≈ 0` and no band flagged `cancellation=True`.
   This fixture's absence from v1's test coverage is exactly how the
   false-positive shipped undetected; recommend test-case-writer treat this
   as the first regression test added under the fix, not an afterthought.

**Not yet re-verified empirically by this architecture pass** (flagged,
architecture.md §14 risk #6): the corrected formula's algebra was checked
against the actual PSD/band-power code in `mono_sum.py`, and against the
one existing empirical measurement (`-3.0103` for L=R), but the new
decorrelated-stereo fixture has not yet been run against the corrected code
by anyone. Recommend python-developer run it as the first verification step
after making the changes above, before broader QA proceeds on top of it.

**Where**: architecture.md Section 4.5, "Mono-sum level change + band-specific
cancellation." Now fully rewritten in v2 — see architecture.md §4.5.

---

## DEF-102 (Architectural): whole-set time budget (Section 7, "under two minutes for 7 tracks") measured as not achievable at the specified fidelity

**Status: Architectural-Resolved (documentation/target correction only —
no code change required).**

**Where**: architecture.md Section 7 (now §7.2 in v2), whole-set time
budget.

**What was found**: after python-developer's own correctly-scoped
LRA-windowing performance fix (switching an O(n)-materializing fancy-index
construction to a cumulative-sum sliding-window computation — a genuine,
appropriately-handled implementation bug, not revisited here), a full
`analyze_track()` call measures 33.3s on a synthetic 7-minute stereo
44.1kHz fixture, extrapolating to ~3.9 minutes for a 7-track set — exceeding
architecture.md v1's "under two minutes" target by roughly 2x.

**Root cause, sharpened by the architect's own review**: `measure_all`
alone -- STORY-001's own code, which AC11 explicitly forbids optimizing in
this story (no lowering the true-peak oversample factor, no chunking) --
costs 16.39s/track on the same fixture. `7 × 16.39s ≈ 1.9 minutes` is
consumed by the reused, AC11-frozen path alone, before any of this story's
five new measurements run at all. **The v1 "under two minutes" target was
unachievable by construction once this figure was known precisely** -- it
was not that the new measurement code (the ~17s/track remainder) is poorly
optimized, it's that the v1 budget was set before the reused-path cost was
benchmarked closely enough to check the extrapolation against it.

**Resolution**: whole-set budget revised to **under 5 minutes for a
7-track set of 7-minute-average-duration tracks** (states the workload
assumption explicitly, ~25% headroom over the measured 3.9-minute figure),
with realistic 3-4 minute reference material noted separately as
extrapolating to **~2.3 minutes for a 7-track set** (comfortably inside
even the original v1 target) -- so the 5-minute figure is read as a
worst-case bound, not the typical case. Full reasoning in architecture.md
§7.2.

**No code change required.** Reducing PSD fidelity, Welch window size, or
consolidating the per-module Welch/CSD calls to force the number down
further would be exactly the kind of undocumented workaround this project's
standing convention prohibits, especially now that the actual bottleneck
(the AC11-frozen `measure_all`, roughly half the per-track cost, not the
new measurements) is identified precisely.

**Optional, explicitly non-blocking follow-up, not authorized/required
now**: a shared per-track PSD cache (`seven_band_balance.py`,
`hf_extension.py`, `per_band_stereo_width.py`, `mono_sum.py` currently each
independently call Welch/CSD) could reduce the ~17s/track these four
modules collectively cost, but its ceiling benefit is bounded by that same
~17s (it cannot touch the AC11-frozen `measure_all` half) -- at best
recovers something under 2 minutes off the 7-track/7-minute worst case, not
a multiple-x speedup. Given the revised budget is already met with
headroom, this remains optional future work, to be authorized separately
if pursued (it would change each module's independently-testable "plain
array in, typed result out" contract, per architecture.md §12).

---

## DEF-103 (Architectural): `Measurements.clipping` being a required field of `core` makes the Section 7 ~2.4 GB/track memory assumption an underestimate

**Status: Fixed.**

**Fix notes (python-developer, this pass)**: implemented both one-line
changes exactly as specified in architecture.md v2 Section 7.1:
- `analysis/true_peak.py`, peak-search line: replaced
  `float(np.max(np.abs(scan_region)))` with
  `float(max(scan_region.max(), -scan_region.min()))`.
- `analysis/clipping.py`, inter-sample-over line: replaced
  `np.abs(tp_result.oversampled) > 1.0` with
  `(tp_result.oversampled > 1.0) | (tp_result.oversampled < -1.0)`.

**Verification (python-developer, this pass)** — synthetic 7-minute stereo
44.1kHz Gaussian-noise track (sigma=0.2, seeded), `measure_all()`,
`tracemalloc` peak Python-heap bytes, before/after the two lines above
(measured by temporarily reverting the two lines, running, then restoring
the fix — same process, same fixture, same random seed, in the same
session):

```
BEFORE FIX (both allocations present): peak = 5,205,015,535 bytes (~4.85 GB)
AFTER FIX  (both allocations removed): peak = 4,741,647,835 bytes (~4.42 GB)
reduction: ~463 MB (~8.9%)
```

Output identity confirmed on the same run: `true_peak_dbtp`,
`clipping.sample_peak_clipped_count` (23), `clipping.inter_sample_over_count`
(114), and `clipping.severity` ("minor") were bit-identical before and
after the fix — confirms both rewrites are output-preserving, as specified.

**Note on the corrected estimate vs. this measurement, root-caused by
isolating each call**: architecture.md's ~2.7-3.3 GB corrected estimate
(down from the reported 5.5 GB) is **not** reproduced by the whole-
`measure_all()` figure above (4.85 GB before, 4.42 GB after, ~9% reduction)
-- both are higher than the estimate, and the reduction is smaller than
implied. Isolating `measure_true_peak()` and `detect_clipping()` separately
(same fixture, `tracemalloc` around each call individually, `tp_result`
computed outside the clipping-only timing window) explains why, precisely:

```
measure_true_peak() alone:  4,741,644,067 bytes (~4.42 GB) -- IDENTICAL before/after this fix
detect_clipping() alone:    2,833,872,095 bytes (~2.64 GB) before fix
                             1,055,757,099 bytes (~0.98 GB) after fix  (~1.65 GB reduction)
```

**Root cause of the gap, not fixture-dependent (an earlier draft of this
note incorrectly attributed it to the clip/inter-sample-over counts in the
fixture, which is wrong -- allocation size is a function of array shape,
not of how many samples exceed the threshold; corrected here)**:
`measure_true_peak()`'s own internal `upfirdn` oversampling machinery
(padded input copy + oversampled output buffer, both ~2.4 GB-class arrays
at 8x/7-minute/44.1kHz) already peaks at ~4.42 GB *before* the peak-search
line runs at all, and the fix does not touch that internal peak -- it only
removes a further, now-redundant `np.abs()` copy that, in this fixture, is
never the binding allocation (the isolated `measure_true_peak()` peak is
byte-identical before/after, confirming this directly). The `clipping.py`
fix, in contrast, delivers its full expected reduction in isolation (~2.64
GB -> ~0.98 GB, close to the architecture's own back-of-envelope
"replaces one float64 copy with ~1/8th-size boolean temporaries"
reasoning). In the full `measure_all()` sequence, **pre-fix the global
tracemalloc peak is set by clipping's abs()-copy stacked on the still-
retained oversampled buffer (~4.85 GB, i.e. `detect_clipping`'s own
isolated pre-fix peak), which exceeds true_peak's ~4.42 GB internal peak;
post-fix, clipping's peak drops to ~0.98 GB, below true_peak's ~4.42 GB
internal peak, so the new *global* peak for the whole `measure_all()` call
is set by `measure_true_peak`'s own unrelated internal upfirdn allocation,
not by either fixed line** -- which is exactly the observed 4.42 GB
post-fix `measure_all()` figure. Both fixes are correct, real,
output-preserving reductions in what their own lines allocate; the
`clipping.py` fix is the one visible in this fixture's whole-call peak
because it was (pre-fix) the binding constraint, while the `true_peak.py`
fix's benefit is masked here by a larger, unrelated internal allocation in
the same function that this DEF-103 fix was never scoped to touch (doing so
would mean chunking/optimizing the true-peak call itself, which
architecture.md's own memory note explicitly forbids for AC11 reasons).
Flagging this precisely, rather than reporting the architecture's 2.7-3.3
GB corrected estimate as confirmed, so a future architecture pass has the
right root cause if the `measure_true_peak` internal peak itself becomes
a target for a separate, properly-scoped optimization pass.

**Regression testing (required per architecture.md, STORY-001's own
regression surface since both touched files are STORY-001's)**:
`pytest tests/test_ac3_true_peak.py tests/test_ac6_clipping.py
tests/test_smoke_true_peak_fir.py tests/test_ac10_reproducibility.py` — **all
29 tests pass, 2 skipped, 0 failed, 0 regressions** (26 passed/1 skipped in
the first three files; 3 passed/1 skipped in the reproducibility/golden-file
suite).

**Where**: architecture.md Section 7 (now §7/§7.1 in v2).

**What was found**: `measure_all()` always calls `detect_clipping()`, which
does `np.abs(true_peak_result.oversampled) > 1.0` -- allocating a second
full-size array before the oversampled buffer is released. Measured peak
Python-heap memory (`tracemalloc`) for a single `measure_all()` call on a
synthetic 7-minute stereo 44.1kHz track: ~5.5 GB, not architecture.md
Section 7's assumed ~2.4 GB for the single oversampled buffer alone.

**Root cause, confirmed and found to be one line more than originally
reported**: reading `true_peak.py` directly (not just `clipping.py`) turns
up a **second, independent instance of the same anti-pattern inside
`measure_true_peak` itself**, at the peak-search line:
`peak_linear = float(np.max(np.abs(scan_region)))` -- this also allocates a
full-size float64 copy via `np.abs()`, *before* `detect_clipping` is even
called. Both this line and `clipping.py`'s
`np.abs(tp_result.oversampled) > 1.0` allocate a redundant full-size
float64 copy of an already-~2.4GB buffer, purely to compute a value
(a scalar max, and a boolean threshold comparison, respectively) that does
not actually require materializing the intermediate `abs()` array at all.
Both together, transiently stacked before either is freed, plausibly account
for the measured ~5.5GB figure.

**Resolution: both allocations are fixed, not accepted or documented
around.** Both rewrites are exactly output-preserving (including at NaN and
exactly ±1.0) for all real-valued float input, so neither changes
`measure_all()`'s public return value for any input and neither touches
AC11's code-path-identity guarantee:

1. `true_peak.py`, peak-search line: replace
   `float(np.max(np.abs(scan_region)))` with
   `float(max(scan_region.max(), -scan_region.min()))` -- allocates nothing.
2. `clipping.py`, inter-sample-over line: replace
   `np.abs(tp_result.oversampled) > 1.0` with
   `(tp_result.oversampled > 1.0) | (tp_result.oversampled < -1.0)` --
   replaces one full-size float64 copy with boolean temporaries roughly
   1/8th the byte size.

Expected peak after both fixes: approximately **2.7-3.3 GB/track**
(corrected estimate, not yet re-measured -- see below), versus the
documented v1 assumption of 2.4 GB (an undercount, now explained) and the
measured 5.5 GB (the bug, now fixed).

**This was judged the right call over the two alternatives on the table**
(accept 5.5 GB as documented reality, or skip clipping detection for
reference tracks specifically) because a genuinely better, low-risk,
behavior-preserving fix was available and specified precisely enough to
implement directly -- neither of the other two options should be taken when
that's true.

**Concrete changes required in the implementation**:
1. `true_peak.py` and `clipping.py` (both STORY-001 files) -- the two
   one-line changes above. This is a narrowly-scoped, explicitly-authorized
   exception to "don't modify STORY-001 files," on the same
   "extract/optimize, don't fork, no public-behavior change" basis as this
   story's other two internal refactors (the `dynamic_range.py` extraction,
   §5; the `frequency_balance.py` PSD extraction, §4.2).
2. **STORY-001's own existing clipping/true-peak regression and golden-file
   tests must be re-run and confirmed bit-identical** (dBTP values, clip
   counts, severity buckets, inter-sample-over counts) across STORY-001's
   existing fixture set -- this is STORY-001's regression surface, not just
   STORY-002's, since the two files being touched are STORY-001's own.
3. Re-run `tracemalloc` against the fixed code to confirm the ~2.7-3.3 GB
   corrected estimate empirically -- flagged in architecture.md §13 item 5
   as not yet re-measured by this architecture pass.

**Ask of python-developer, concretely**: make the two changes above, re-run
STORY-001's existing clipping/true-peak test suites (not just STORY-002's
new ones) to confirm no output change, and report the re-measured peak
memory figure so architecture.md's ~2.7-3.3 GB estimate can be confirmed or
corrected in a future pass if needed.

---

## DEF-104 (Code-level): `reference_render.py`'s human-readable mono-sum
text still states the pre-DEF-101 (-3.01 dB) baseline for
`excess_cancellation_db`, not the corrected (-6.02 dB) one

**Status: Fixed.**

**Fix notes (python-developer, this pass)**: updated the f-string in
`suno_mastering/report/reference_render.py::_track_section()` (the actual
on-disk path is `stories/STORY-001/implementation/suno_mastering/report/
reference_render.py` -- the module lives under STORY-001's implementation
tree per architecture.md's package layout, not a separate STORY-002 tree).
Changed:

```python
f"(excess cancellation beyond expected -3.01 dB correlated-sum baseline: "
```

to:

```python
f"(excess cancellation beyond the expected -6.02 dB ordinary-decorrelated-stereo "
f"floor (rho=0, broadband, per architecture.md Section 4.5 -- see DEF-101/DEF-104): "
```

Matches `MonoSumResult.excess_cancellation_db`'s own corrected field-comment
in `analysis/reference_types.py` and the DEF-101 fix's `_BROADBAND_
DECORRELATED_FLOOR_DB = -6.0206` constant in `analysis/mono_sum.py` -- both
the number and the description of what it represents (rho=0 decorrelated
floor, not a "correlated-sum" value) are now correct. No `schema_version`
bump (Markdown prose only, per the original fix-notes instruction).

**Verification (python-developer, this pass)**: `grep` of the shipped file
confirms the new text is in place and the old "-3.01 dB correlated-sum"
string is gone. No dedicated automated test exists for this prose string
specifically (per the original report, this was found by inspection, not by
a failing test) -- re-ran the full `test_ref_ac9_output.py`/`test_ref_
ac10_verification_bars.py` files (which exercise `report/reference_render.py`
indirectly via `render_markdown()`/`render_json()` calls) to confirm no
import/runtime breakage from the edit: both pass, see full-suite results
below.

---

**Status: Open.** (original report, preserved below for record)

**Reported by**: qa-automation-engineer.

**Linked test case**: none in test-cases.md v1 directly (v1 predates
DEF-101); found while writing this QA pass's own AC10/AC9 automation and
verifying the DEF-101 fix's "must appear in the report, not just this
document" requirement (architecture.md Section 4.5's `excess_cancellation_db`
description, and TC-310's "caveat is stated in the report" pattern applied
by inspection to the mono-sum section specifically).

**Description**: DEF-101's fix notes and architecture.md v2 Section 4.5 both
list the concrete files needing correction: `analysis/mono_sum.py`,
`analysis/reference_types.py`, `reference_analysis/config.py`, and
`report/reference_builder.py` (the renamed config-field reference). All four
were correctly updated. `report/reference_render.py` -- the module that
actually produces the human-readable text a producer reads -- was **not** on
that list and was **not** updated. Its `_track_section()` function still
renders:

```python
lines.append(
    f"- Mono-sum level change: {_fmt(m.mono_sum.level_change_db)} dB "
    f"(excess cancellation beyond expected -3.01 dB correlated-sum baseline: "
    f"{_fmt(m.mono_sum.excess_cancellation_db)} dB)"
)
```

(`report/reference_render.py`, `_track_section()`, in the non-mono branch.)

This text states `excess_cancellation_db` is measured against a "-3.01 dB
correlated-sum baseline" -- that was the **pre-DEF-101, incorrect** floor.
Per the DEF-101 fix, `excess_cancellation_db` is now correctly computed
against `_BROADBAND_DECORRELATED_FLOOR_DB = -6.0206 dB` (the rho=0 floor),
not -3.0103 dB (the rho=+1 floor) -- confirmed directly against the shipped
`analysis/mono_sum.py` code and `BandCancellation`/`MonoSumResult`'s own,
correctly-updated field-comment docstrings in `analysis/reference_types.py`.
The **numeric value** `excess_cancellation_db` shown in the report is
correct (computed by the fixed code); only the **prose describing what it's
measured against** is stale and now actively misleading -- a producer
reading this line would misunderstand what "0" vs. a negative
`excess_cancellation_db` value means relative to the baseline the text
itself names.

This is exactly the scenario architecture.md's own DEF-101 write-up warned
about: "conflating the two [floors] is exactly how a threshold tuned against
one formula's floor ends up firing on the other formula's ordinary, healthy
material output" -- here the analogous risk is a *reader*, not the code,
being misled by report text that names the wrong floor.

**Triage: Code-level.** This is a one-line text fix in an existing module,
directly analogous to the other four files DEF-101's own "what this changes
in the shipped code" list already itemized -- `report/reference_render.py`
was simply missed from that list, not a design question.

**Fix notes**: (for python-developer) Update the f-string in
`report/reference_render.py::_track_section()` to state the corrected
-6.0206 dB broadband decorrelated-floor baseline (matching
`MonoSumResult.excess_cancellation_db`'s own field-comment in
`analysis/reference_types.py`), and reconsider the phrase "correlated-sum
baseline" -- per architecture.md Section 4.5's table, -6.0206 dB is the
rho=0 (fully **decorrelated**) floor, not a "correlated-sum" value; the
existing phrase is doubly stale (wrong number *and* wrong description of
what the number represents). Recommend wording close to: "excess
cancellation beyond the expected -6.02 dB ordinary-decorrelated-stereo
floor." No `schema_version` bump needed (Markdown prose only, no schema/field
change).

---

## DEF-105 (Code-level): `reference_analysis/pipeline.py` never re-verifies
input file hashes at run completion -- the AC8 non-destructive guarantee's
actual enforcement mechanism is missing

**Status: Fixed.**

**Fix notes (python-developer, this pass)**: implemented the run-completion
re-hash step in `reference_analysis/pipeline.py::analyze_set()` (actual path
`stories/STORY-001/implementation/suno_mastering/reference_analysis/
pipeline.py`), following STORY-001's own `pipeline.master()` pre/post-hash
pattern as instructed:

- Imported `NonDestructiveIntegrityError` (reused, not duplicated) alongside
  the existing `EmptyReferenceSetError`/`MasteringError` imports.
- Added an `input_hashes: dict` collected during the existing per-file
  `[R1]`/`[R2]` loop in `analyze_set()`: immediately before each file's
  `analyze_track()` call, `reference_ingest.compute_file_hash(str(f))` is
  computed and stored under that file's path, but only committed to
  `input_hashes` once the track is confirmed successfully analyzed (i.e.
  inside the same success branch that appends to `per_track` -- a file that
  fails ingest/decode is never re-hash-checked, matching "every file that
  was successfully ingested," per architecture.md Section 10's own wording).
- After the per-track loop (and before `build_aggregates()`), a dedicated
  re-verification loop re-computes `compute_file_hash()` for every path in
  `input_hashes` and compares against the stored pre-analysis hash. On any
  mismatch, raises `NonDestructiveIntegrityError` with a message in the same
  format as STORY-001's own `pipeline.py::master()` ("Input file hash changed
  during processing: started with X, ended with Y. The original input must
  never be modified.").
- Deliberately did **not** add `input_hash` to `ReferenceMeasurements`/
  `ReferenceSetReport` (one of the two options architecture.md's fix notes
  offered) -- collecting `{track_path: input_hash}` locally inside
  `analyze_set()`'s own loop was the smaller-surface-area option (no schema
  change, no `schema_version` bump, no new field for report/reference_
  builder.py or reference_render.py to thread through), and is sufficient to
  satisfy AC8/Section 10's actual requirement (re-verify at run completion),
  which does not ask for the hash to appear in the report itself.

**Verification (python-developer, this pass)**:
```
pytest tests/test_ref_ac8_nondestructive.py -q
......                                                                   [100%]
6 passed in 5.22s
```
All 6 tests pass, including the previously-failing
`test_ref_hash_reverification_mechanism_present` (confirmed it now raises
`NonDestructiveIntegrityError` when a reference file is tampered with
mid-run, via the same mock-based tamper-after-ingest fixture the test already
used) and the four pre-existing "hash unchanged after a normal run" tests
(TC-280/281/282/284), confirming the new re-hash step does not fire a false
positive on an untampered run.

---

**Status: Open.** (original report, preserved below for record)

**Reported by**: qa-automation-engineer.

**Linked test case**: none in test-cases.md v1 by number (TC-280/281/282 as
literally specified only assert "hash unchanged after a normal run," which
passes trivially whether or not any re-verification code exists, since
nothing tampers with the file in those tests). Found by this QA pass's own
`test_ref_hash_reverification_mechanism_present` in
`tests/test_ref_ac8_nondestructive.py`, written specifically to exercise the
mechanism TC-280's own "no NonDestructiveIntegrityError raised" expected
result implies must exist to check against. **This test currently fails**
(`Failed: DID NOT RAISE NonDestructiveIntegrityError`), which is how this
defect was found -- not by inspection alone.

**Description**: architecture.md Section 10 states explicitly: "Every
reference file (WAV, FLAC, MP3) is opened read-only; `[R1]` computes its
input hash before decode, **`[R5]`'s run-completion step re-hashes every
file that was successfully ingested and asserts the set matches** -- a
`NonDestructiveIntegrityError` (reused from STORY-001's `errors.py`,
imported not duplicated) is raised if any mismatch is found."

Reading `reference_analysis/pipeline.py` directly: `ReferenceIngestResult.
input_hash` is computed at ingest time (`io/reference_ingest.py`,
`compute_file_hash()`), and is threaded through into
`ReferenceMeasurements`... but it is **never referenced again**. There is no
call to `compute_file_hash()` a second time anywhere in `analyze_track()` or
`analyze_set()`, and `errors.NonDestructiveIntegrityError` is never imported
or raised anywhere in `reference_analysis/pipeline.py`. This is a direct,
verifiable contrast with STORY-001's own `pipeline.py`, which does exactly
this re-hash-and-compare step (`suno_mastering/pipeline.py` lines ~146-156,
confirmed by inspection) -- the mechanism exists, was built once already for
STORY-001, and was simply not carried over to `reference_analysis/pipeline.py`.

**Concretely, what this means**: if a reference file were somehow modified
during a run (a real, if narrow, risk this project's own non-destructive
guarantee exists to catch -- e.g. a concurrent process, a disk error, a bug
elsewhere in this same run touching the wrong path), STORY-002's pipeline
would **not detect it and would not raise**, silently violating AC8/the NFR
despite `input_hash` being faithfully computed and carried in every
`ReferenceMeasurements` record. The data needed to catch this is present in
every record; the check that would use it to actually catch something is
simply never run.

**Triage: Code-level.** This is a missing implementation step against an
explicit, unambiguous architectural instruction (not a design judgment call
-- architecture.md Section 10 states concretely what must happen and cites
the exact exception type and error-raising trigger to reuse). No
architectural re-design is needed; STORY-001's own equivalent code
(`suno_mastering/pipeline.py`) is a direct, in-repo template for the fix.

**Fix notes**: (for python-developer) Add a run-completion re-hash step to
`reference_analysis/pipeline.py::analyze_set()` (most natural place: after
all tracks are analyzed, before/alongside aggregation, or at the very end
before returning `ReferenceSetResult`) that, for every successfully-ingested
track's `track_path`, re-computes `reference_ingest.compute_file_hash(path)`
and compares it against the `input_hash` recorded at ingest time (this needs
threading through -- currently `ReferenceIngestResult.input_hash` is
available at ingest time inside `analyze_track()` but is not currently
carried into the returned `ReferenceMeasurements`/`ReferenceSetResult`
shape; either add it to `ReferenceMeasurements` or collect
`{track_path: input_hash}` separately during the `[R1]`/`[R2]` loop in
`analyze_set()`). Raise `errors.NonDestructiveIntegrityError` (already
defined, already imported by STORY-001's own `pipeline.py` -- reuse, don't
duplicate) on any mismatch, matching STORY-001's existing message format.
Recommend also updating `test_ref_hash_reverification_mechanism_present` in
this QA pass's own `tests/test_ref_ac8_nondestructive.py` from a currently-
failing state to a confirmed-passing regression test once fixed (do not
delete or weaken it -- this is the concrete, automated form of AC8/the NFR
this story was missing).

---

## DEF-106 (documentation/test-spec, routed to test-case-writer, not
python-developer): four test-cases.md v1 expected values are stale against
architecture v2 / the DEF-101 and DEF-102 fixes

**Status: Closed.**

**Fix notes (test-case-writer, this pass)**: revised test-cases.md to v2,
correcting all four items this entry named, plus the same-class staleness
found while fixing them (not separately numbered in this entry's original
text, but the identical kind of drift, caught during the same pass per
this role's practice of grepping for the stale terms rather than
patching only the four named line numbers):

- **TC-292**: `schema_version` expected value corrected from `"1.0"` to
  `"1.1"`, matching the shipped `report/reference_builder.py::
  SCHEMA_VERSION`.
- **TC-311**: rewritten from an open-question framing to a direct
  assertion against the resolved single-channel convention
  (`level_change_db = -3.0103 ± 0.1 dB` for L=R, `excess_cancellation_db
  ≈ +3.0103 dB`, all bands `cancellation == False`), per architecture.md
  v2 §4.5 and this entry's own resolution — values traced to defects.md
  DEF-101's own verification case 1, not re-derived independently.
- **TC-313**: rewritten from an open-question/numeric-proximity-only
  framing (v1's "do not assert pass/fail on the boolean flag itself" was
  backwards) to a direct assertion of the `cancellation` boolean flag
  (`excess_cancellation_db ≈ 0`, all 7 bands `cancellation == False`),
  matching the shipped
  `test_tc313_def101_regression_ordinary_decorrelated_stereo_no_false_positive`
  regression guard this entry names. Kept the TC-313 ID (not split into a
  new TC) to match the shipped test's own name.
- **TC-381**: budget figure corrected from "under 120 seconds" to "under
  5 minutes (300s) worst-case, ~2.3 minutes typical for realistic
  material," per architecture.md v2 §7.2/DEF-102, with the measured
  per-stage basis (16.39s/track `measure_all` + ~17s/track new
  measurements ≈ 33.3s/track × 7 ≈ 3.9 min, 300s budget ≈ 25% headroom)
  stated inline so a future reader does not have to re-derive it.
- **Also corrected**, found while fixing the four named items above (same
  staleness class, not separately numbered in this entry's original
  text): the governing-rule paragraph's "mono-cancellation −3 dB"
  description (value unchanged, meaning corrected to "excess beyond the
  decorrelated floor, not a raw dB reading"); TC-312's cancellation-flag
  description (now references `excess_delta_db`, not raw `delta_db`,
  while explicitly not asserting an exact dB figure for the anti-phase
  fixture, since defects.md's own worked examples for a similar fixture
  produced different exact values, -39.92 dB and -43.42 dB, on different
  noise-floor amplitudes); the "Open questions" section's items 1/2
  (marked resolved, cross-referenced to architecture.md v2 §4.5 and this
  entry); the mandatory coverage checklist's TC-313 boundary-value
  description (TC-313 is no longer a threshold-boundary case, so its
  original checklist framing was misleading and is now corrected);
  TC-380/381's slow-test notes (recommend isolated pytest invocation, per
  architecture.md v3 §16/DEF-110); TC-382's note pointing to the
  corrected DEF-103 memory range; TC-390's note on `test_tc150` isolation
  (DEF-110 context, referenced for a future reader, not a new
  test-case-writer action item).

test-cases.md is now v2 (see its own "Revision history" section for the
full, itemized account). No production code change — this is a
test-spec-only fix per this entry's own triage; the shipped automated
suite already asserted the correct v2 values independently (per each
test's own inline docstring pointing back to this entry) and needed no
change.

---

**Status: Open** (original report, preserved below for record; routing
note, not a code defect -- flagged per this role's "test-cases.md itself
has a coverage gap / staleness -- note it, do not silently fix it"
instruction).

**Reported by**: qa-automation-engineer.

**Description**: `test-cases.md` is v1, written against architecture.md v1,
before DEF-101/DEF-102 were found and fixed (both landed in architecture.md
v2, in the same implementation pass whose output this QA pass is testing).
Four specific expected values in test-cases.md are now stale:

1. **TC-292** asserts `schema_version == "1.0"`. The DEF-101 fix's own fix
   notes and architecture.md v2 Section 9 explicitly bump this to `"1.1"`
   (additive `BandCancellation.excess_delta_db` field + renamed config
   field) -- confirmed directly against the shipped
   `report/reference_builder.py::SCHEMA_VERSION = "1.1"`. TC-292 needs its
   expected value updated to `"1.1"`.
2. **TC-311** is framed as an open question ("which channel convention --
   dual-mono or single-channel?") against architecture v1's ambiguous prose.
   This is resolved by the DEF-101 fix and architecture.md v2 Section 4.5's
   worked per-rho table: the shipped convention is confirmed (by reading
   `mono_sum.py` directly: `measure_integrated_lufs(mono_sum, sr)` is called
   on a genuinely single-channel 1-D array) to be the single-channel
   convention, giving `level_change_db = -3.0103` dB for L=R (not 0 dB).
   TC-311 should be rewritten as a direct assertion against this resolved
   value, not left as an open-question framing.
3. **TC-313** is framed as a "spec collision" open question (does the
   default -3.0 dB comparison need to be strict/lower to avoid flagging
   ordinary decorrelation as cancellation?). This is exactly DEF-101's own
   false-positive, now fixed: ordinary decorrelated stereo now reads
   `excess_delta_db ~= 0` and `cancellation == False` on every band
   (confirmed empirically by this QA pass, see `test_tc313_...` in
   `tests/test_ref_ac10_verification_bars.py`, which passes). TC-313's own
   instruction to "not assert pass/fail on the boolean flag itself" is now
   backwards -- the boolean is exactly what this test case should assert,
   since it is the direct DEF-101 regression guard.
4. **TC-381** asserts the whole-set budget is "under 120 seconds" for a
   7-track set. DEF-102 revised this target to **under 5 minutes** (300
   seconds) for a 7-track/7-minute-average-track worst case, with realistic
   3-4 minute material extrapolating to ~2.3 minutes -- architecture.md v2
   Section 7.2. TC-381's literal 120-second figure is the superseded v1
   target.

**Triage: this is a test-cases.md coverage/staleness issue, not a code
defect** -- routed to test-case-writer for a v2 revision of test-cases.md,
per this role's standing instruction not to silently patch spec gaps.
This QA pass's own automated suite
(`tests/test_ref_ac9_output.py::test_tc292_schema_version_matches_current_shipped_value`,
`tests/test_ref_ac10_verification_bars.py::test_tc311_...`/`test_tc313_...`,
`tests/test_ref_nfr.py::test_tc381_...`) asserts the **correct, current v2**
expected values directly, with an inline docstring pointing back to this
entry, so the suite is not blocked on test-cases.md's own revision -- but
test-cases.md itself should still be updated so a future reader of that
document alone (not this suite) isn't misled by the stale v1 figures.

---

## DEF-107 (documentation/test-spec, routed to test-case-writer): TC-302's
25 LU LRA gate-discrimination fixture does not actually discriminate a
correct -20 LU relative gate from an incorrectly-copied -10 LU gate

**Status: Closed.**

**Fix notes (test-case-writer, this pass)**: rewrote TC-302 with an 18 LU
separation (in the 14-22 LU derived-safe range this entry's own triage
recommended, and matching the exact figure the shipped regression test
already uses), and added the full derivation inline in the test case
itself — not just a corrected number, per this entry's own recommendation
to "note the mean-of-passing-blocks gate definition explicitly in the test
case's own rationale so a future reviewer understands why the number isn't
simply 'less than 20.'" The derivation states both boundaries explicitly
(`loud_level − 23.01` for the correct -20 LU gate, `loud_level − 13.01`
for the incorrect -10 LU gate) and why 18 LU sits cleanly between them,
and why v1's 25 LU did not (25 > 23.01, so it was excluded even under the
correct gate). Matches the shipped
`test_tc302_lra_gate_discriminates_correct_vs_incorrect_relative_gate`
fixture exactly. Also re-checked TC-301's 12 LU baseline claim against the
corrected gate math (12 < 13.01 and well under 23.01, so it still survives
either gate as originally claimed) — confirmed still valid, no change
needed there.

test-cases.md is now v2. No production code change — the LRA
implementation itself was already confirmed correct by this entry's own
investigation (ships the -20 LU gate, not a miscopied -10 LU one); this
was entirely a test-fixture-design correction.

---

**Status: Open.** (original report, preserved below for record)

**Reported by**: qa-automation-engineer.

**Description**: test-cases.md's TC-302 is explicitly designed as "the
regression guard" for the single most common LRA implementation bug
(miscopying the -20 LU relative gate as -10 LU). Its fixture: 30s at level
A, 30s at level B, |A-B| ~= 25 LU, asserting the quiet cluster survives the
correct -20 LU gate (LRA reads ~25 LU) but would collapse toward ~0 LU under
an incorrectly-copied -10 LU gate.

Measured directly against the shipped `analysis/loudness_range.py` code,
using both the correct default config (`lra_relative_gate_lu=-20.0`) and a
config forced to `-10.0`, on a 25 LU two-level fixture built exactly per
TC-302's own construction: **both configurations produce `lra_lu` close to
   maximized by a full-scale square wave (every sample at exactly
   `+/-1.0`), giving mean-square `= 1.0` — 3 dB higher than a full-scale
   sine's mean-square of `0.5`. This is the correct worst case to bound
   against, not the sine DEF-206's own reproduction happened to use
   (which is why the derived ceiling below sits comfortably above
   DEF-206's own measured `+3.297 dB`, not merely equal to it).
3. **K-weighting's total filter gain is bounded above across the
   ENTIRE frequency response, not only the 2-8 kHz range verified
   during DEF-206's own reproduction.** Derivation against this
   codebase's own public `k_weight` implementation
   (`analysis/loudness_range.py::_high_shelf_coeffs`/
   `_high_pass_coeffs`; see the filter-identity caveat below for why
   this, not `pyloudnorm`, is the filter actually derived against):
   - **High-shelf stage.** Evaluating the shelf's transfer function
     exactly at Nyquist (`z = -1`) algebraically, using the shipped
     coefficient formulas (`b0,b1,b2,a1,a2` in terms of `Vh, Vb, k, Q`):
     numerator `b0 - b1 + b2` reduces to `4*Vh/a0_`, denominator
     `1 - a1 + a2` reduces to `4/a0_`, so `H_shelf(-1) = Vh` **exactly**
     — the shelf's gain reaches its high-frequency asymptote precisely
     at Nyquist, with `g_db = 3.99984385397` (`Vh = 10**(g_db/20) ≈
     1.5849`, i.e. ≈+4.0 dB). The `Q ≈ 0.7072` / `Vb ≈ Vh**0.4997`
     parametrization is the standard no-resonance ("maximally flat")
     shelf design, which by construction does not peak above `Vh`
     anywhere between DC and Nyquist.
   - **High-pass stage — the correction this revision makes to the
     figure QA's own reproduction cited.** The RLB high-pass stage's
     `b = [1, -2, 1]` coefficients are **unnormalized** (faithful to
     BS.1770's own published Annex 1 stage-2 constants), so its gain at
     Nyquist is not exactly `1.0`. Evaluating the same way: numerator
     `b0 - b1 + b2 = 4`, denominator `1 - a1 + a2 = 4/a0_hp`, so
     `H_hp(-1) = a0_hp = 1 + k/Q + k²` where `k = tan(π·f0/sr)`. At
     `sr=44100`, `f0=38.13547`, `Q=0.50033`: `k ≈ 0.0027168`, giving
     `a0_hp ≈ 1.005437`, i.e. **≈+0.047 dB at Nyquist**, not `0 dB`.
     (Cross-checked against the published 48 kHz ITU coefficients
     directly, `a1=-1.99004745`, `a2=0.99007225`: `4/(1-a1+a2) =
     1.004995`, ≈+0.043 dB — consistent, and the ratio between the two
     figures tracks the `48/44.1` sample-rate ratio as expected.) This
     excess is small but nonzero, and — since it stacks additively in
     dB with the shelf's own `+4.0 dB` — is not negligible at the
     precision this ceiling needs. **The excess is sample-rate
     dependent**: it *shrinks* at higher sample rates (`k` shrinks as
     `sr` grows for fixed `f0`) and *grows* at lower ones (e.g.
     `~+0.095 dB` at 22050 Hz) — the shipped constant below is padded
     to remain valid across this codebase's supported sample rates, not
     tuned to exactly one.

   Combined: `|H_total(f)| <= Vh · a0_hp` for every `f` in `[0,
   Nyquist]` (the high-pass stage's own gain is `<= a0_hp` everywhere,
   being non-resonant and monotonically approaching its own Nyquist
   value from below), so **K-weighted mean-square power `<= (Vh ·
   a0_hp)² · (pre-weighting mean-square power)` for ANY input signal**,
   by Parseval's theorem.

**Combining all three facts**:

```
LUFS_max = -0.691 + 10*log10(N_max * (Vh * a0_hp)**2 * 1.0)
         = -0.691 + 10*log10(2) + 20*log10(Vh * a0_hp)
         = -0.691 + 3.0103 + g_db + 20*log10(a0_hp)
         = -0.691 + 3.0103 + 3.99984 + 0.04710      (at sr=44100)
         ~= 6.366 dB
```

**This corrects the `+6.32 dB` figure QA's own DEF-206-adjacent
reproduction implied** (which used only the shelf's own `g_db ≈
3.99984` and omitted the high-pass stage's own small excess gain at
Nyquist) **to `≈ +6.37 dB` at 44.1 kHz**, and the bound is mildly
sample-rate dependent (slightly higher at lower supported sample
rates). **The shipped constant is set to `_LUFS_CEILING_DB = 6.5`** —
above the tightest computed bound at every sample rate this codebase
supports, so the check is never made stricter than the true
mathematical maximum (the failure mode a too-tight, unpadded ceiling
would risk), while remaining far below any plausible real audio
(DEF-206's own measured worst case, `+3.297 dB` on a genuinely
non-clipping sine, sits more than 3 dB inside this bound).

**Filter-identity caveat, stated explicitly rather than assumed away**:
`check_lufs_plausible` guards `Measurements.integrated_lufs`, which is
computed by `analysis/loudness.py::measure_integrated_lufs` via
**pyloudnorm**'s `Meter.integrated_loudness`, not via this codebase's
own `k_weight` (`loudness_range.py`), which this derivation is
performed against. `loudness_range.py`'s own module docstring states
explicitly that `pyloudnorm.Meter._filters` is "a private
implementation detail that must not be relied on" — i.e. this
codebase's own `k_weight` was written as an independent, from-the-
published-standard reimplementation specifically because pyloudnorm's
internal filter is not something to import or introspect directly. The
`f0`/`G`/`Q` constants in `k_weight` are the well-known, independently-
reproduced ITU-R BS.1770-4 Annex 1 published values (the same constants
widely used across independent implementations of this standard,
including — by strong circumstantial evidence, not confirmed by reading
its source in this environment — pyloudnorm's own), so the two
implementations are extremely likely to share the same frequency
response. **Partial empirical cross-check performed this pass** (not a
substitute for reading pyloudnorm's source): predicting the DEF-206
reproduction's 8 kHz dual-mono/amplitude-0.999 sine case using this
derivation's own `Vh`/`a0_hp` gain figures gives a predicted LUFS of
`≈+3.35 dB`, against the actually-measured (via `measure_all()`, i.e.
via pyloudnorm) `+3.297 dB` — a `~0.05 dB` gap, consistent with the
shelf not yet being fully at its Nyquist asymptote at 8 kHz (this
derivation's `Vh` bound is reached only at Nyquist itself, per the
exact algebra above) rather than evidence of a differing filter. This
supports, but does not prove, that the bound derived here applies to
the actually-measured quantity. **Flagged as an open verification item
for QA, not resolved by this document**: confirm pyloudnorm's actual
internal K-weighting response is bounded the same way — either via
`scipy.signal.freqz` against `pyln.Meter._filters`'s own coefficients,
or empirically, by feeding calibrated tones through
`measure_integrated_lufs` directly at frequencies approaching Nyquist
and confirming the reading does not exceed this derivation's bound —
before this ceiling is treated as certain to the same rigor as the
`-70` floor.

**Second flagged gap, also not resolved here**: the "no overshoot
between DC and Nyquist" property relied on for both filter stages (the
`Q≈0.707`/`Vb≈Vh**0.5` no-resonance shelf parametrization, and the
`Q≈0.5` non-resonant high-pass) is asserted from standard filter-design
theory, not numerically swept — this document cannot execute code.
**Concrete ask for QA**: run `scipy.signal.freqz` (or equivalent) on a
dense frequency grid for both `_high_shelf_coeffs`/`_high_pass_coeffs`
at this codebase's supported sample rates and confirm `|H(f)|` never
exceeds the Nyquist-value bound derived above anywhere in `[0,
Nyquist]`, before this constant is treated as final.

```python
_LUFS_CEILING_DB = 6.5
# Derived, not an arbitrary "matches 0 dBFS" guess -- see architecture.md
# Section 4.2 for the full derivation (DEF-206). Summary: for any
# non-clipping (|x|<=1), <=2-channel (this codebase's own
# _SUPPORTED_CHANNELS={1,2} ingest limit), standard-weighted (G_i=1.0)
# signal, BS.1770's own channel-summed integrated-loudness formula
# cannot mathematically exceed roughly +6.37 dB at this codebase's
# supported sample rates (a full-scale dual-mono square wave at the
# K-weighting shelf's own peak-gain frequency is the theoretical worst
# case) -- 6.5 is that bound with margin, not tightened below it.

def check_correlation_range(correlation: float) -> Optional[SanityWarning]:
    # Correlation is a normalized cross-correlation; [-1, 1] by definition.
    # correlation_coefficient() computes num/denom from two independently
    # rounded floating-point sums (analysis/stereo_phase.py lines 34-38);
    # for genuinely identical channels this can read fractionally over
    # 1.0 (e.g. 1.0000000000000002) as a pure floating-point artifact of
    # computing sqrt(sum(L**2)*sum(R**2)) vs sum(L*R) via different
    # operation sequences on bit-identical inputs -- an epsilon is
    # required or this check false-positives on the single MOST correct
    # possible input (L identical to R). math.isnan is checked first:
    # NaN compares False against every bound below, so a NaN would
    # otherwise sail through silently.
    if math.isnan(correlation):
        return SanityWarning("correlation_range", "fail", "correlation is NaN")
    if correlation < -1.0 - 1e-6 or correlation > 1.0 + 1e-6:
        return SanityWarning("correlation_range", "fail",
            f"correlation {correlation:.6f} outside [-1.0, 1.0]")
    return None

def check_lufs_plausible(lufs: float) -> Optional[SanityWarning]:
    # -inf is the documented, legitimate BS.1770-gated result for
    # silence/near-silence (loudness.py's own docstring;
    # test_silence_dynamics.py already exercises this) -- exempt exactly
    # -inf, not any "looks quiet" heuristic.
    #
    # A FINITE value below -70 is not merely "suspicious", it is
    # mathematically impossible for a correct implementation: BS.1770's
    # integrated loudness is a power-mean (not a plain average) of
    # per-block mean-squares that individually passed the -70 LUFS
    # absolute gate. Each surviving block's mean-square x_i satisfies
    # -0.691 + 10*log10(x_i) > -70, i.e. x_i > 10**((-70+0.691)/10).
    # The arithmetic mean of positive values is >= any individual value's
    # own floor, so mean(x_i) has that same floor, and therefore
    # -0.691 + 10*log10(mean(x_i)) > -70 whenever the gate let anything
    # through at all. A finite value < -70 can only mean a bug (e.g. an
    # ungated computation), not real audio -- this resolves
    # requirements.md's own flagged ambiguity about "silent vs.
    # non-silent" without needing a heuristic: the invariant is exact.
    #
    # The upper bound, _LUFS_CEILING_DB (DEF-206, see the module-level
    # comment and architecture.md Section 4.2 for the full derivation),
    # is a genuine hard bound, not the story.md-literal "> 0.0" figure
    # this check originally shipped with -- 0.0 false-positived on
    # legitimate, non-clipping, K-weighting-shelf-boosted /
    # channel-summed audio (DEF-206).
    if math.isnan(lufs):
        return SanityWarning("integrated_lufs_range", "fail", "LUFS is NaN")
    if lufs == float("-inf"):
        return None  # legitimate gated-silence result, not a failure
    if lufs < -70.0 or lufs > _LUFS_CEILING_DB:
        return SanityWarning("integrated_lufs_range", "fail",
            f"integrated LUFS {lufs:.2f} outside (-70, {_LUFS_CEILING_DB}] and not -inf")
    return None

def check_hf_rolloff_vs_air_band(
    rolloff_hz: Optional[float], insufficient_duration: bool,
    air_relative_db: Optional[float],
) -> Optional[SanityWarning]:
    # Uses the SAME quantity already surfaced in every seven-band report
    # (SevenBandMeasurement.relative_db for band="air") -- see
    # architecture.md Section 2.4 for why no density-domain conversion is
    # performed here. air_relative_db is Optional: a caller with a
    # non-default seven_bands_hz config that omits "air" entirely passes
    # None, in which case this check is skipped rather than raising.
    if rolloff_hz is None or insufficient_duration or air_relative_db is None:
        return None
    if rolloff_hz < 5000.0 and air_relative_db > -40.0:
        return SanityWarning("hf_rolloff_vs_air_band", "fail",
            f"rolloff reported at {rolloff_hz:.0f} Hz but air band "
            f"(10-24 kHz) reads {air_relative_db:.1f} dB relative "
            f"(> -40 dB) -- physically inconsistent, a real {rolloff_hz:.0f} Hz "
            f"cutoff would show air-band energy far below this")
    return None

def check_seven_band_adjacent_deltas(
    bands: List[SevenBandMeasurement],
    threshold_db: float = 25.0, air_threshold_db: float = 40.0,
) -> List[SanityWarning]:
    # `bands` iterated in config.seven_bands_hz's own insertion order
    # (sub, low, low_mid, mid, high_mid, high, air) -- already the
    # correct frequency ordering, no re-sort needed.
    # Two thresholds, not one: the air band legitimately sits far below
    # the mid-band reference on ordinary commercial masters (the existing
    # DEF-201 report data shows ~-20 dB there on real tracks with no
    # HF problem at all) -- a single threshold tight enough to catch a
    # genuine sign/computation bug (which tends to produce +/-40-60 dB
    # excursions) would false-positive on that ordinary case. Every other
    # adjacent pair uses the tighter figure, since natural -3 to -6
    # dB/octave tilt over the ~1-3 octave gaps between non-air adjacent
    # seven-band edges rarely exceeds ~15-20 dB even on atypical mixes.
    out = []
    for a, b in zip(bands, bands[1:]):
        limit = air_threshold_db if "air" in (a.band, b.band) else threshold_db
        delta = abs(a.relative_db - b.relative_db)
        if delta > limit:
            out.append(SanityWarning(
                f"seven_band_adjacent_delta.{a.band}_{b.band}", "warn",
                f"{a.band} ({a.relative_db:.1f} dB) vs {b.band} "
                f"({b.relative_db:.1f} dB): {delta:.1f} dB gap exceeds "
                f"{limit:.1f} dB plausibility threshold"))
    return out
```

**`25.0`/`40.0` dB are stated here as an explicit, provisional
architectural decision, not left as an unresolved open question** (per
requirements.md's own routing of this to the architect) — but they are
a judgment call, not a derived invariant like the LUFS bound, and
should be calibrated against real data. **Instruction to
qa-automation-engineer**: when this suite runs against the existing
five reference tracks (`test_ref_*` fixtures / real reference set, if
available in this environment), report the observed maximum
adjacent-band delta for every pair, including air, across all five
tracks, so these two numbers can be tightened or loosened in a future
pass without another architecture round-trip.

### 4.3 Integration points — two call sites, one field name, no exceptions propagate

**`analysis/__init__.py::measure_all()`**: after computing
`integrated_lufs` and `stereo_phase`, run
`check_lufs_plausible(integrated_lufs)` and
`check_correlation_range(stereo_phase.overall_correlation)`, collect
non-`None` results into a list, pass as
`Measurements(..., sanity_warnings=warnings)`. This covers both the
mastering pipeline (pre/post) and the reference pipeline (`core`),
since both call this same function — no duplicated logic.

**`reference_analysis/pipeline.py::analyze_track()`**: after `core`,
`hf_ext`, and `seven_band` are computed, build
`air_relative_db = next((b.relative_db for b in seven_band.bands if b.band == "air"), None)`
(explicit default, so a non-default band config that omits "air"
degrades to "check skipped," not a `StopIteration` crash), then
`reference_warnings = list(core.sanity_warnings) +
[check_hf_rolloff_vs_air_band(hf_ext.rolloff_hz, hf_ext.insufficient_duration, air_relative_db)] +
check_seven_band_adjacent_deltas(seven_band.bands)` (filtering `None`),
assign to `ReferenceMeasurements(..., sanity_warnings=reference_warnings)`.
**One field, one list, per result type** — `ReferenceMeasurements.sanity_warnings`
is a superset of `core.sanity_warnings`, not a second, separately-consulted
list. This is deliberate: it gives `report/reference_render.py` exactly
one place to read from, avoiding a renderer bug where only one of two
scattered lists gets rendered.

### 4.4 Schema/report consequences (AC13)

Two additive dataclass fields:
- `analysis/types.py::Measurements`: `sanity_warnings: List[SanityWarning] = field(default_factory=list)`.
- `analysis/reference_types.py::ReferenceMeasurements`: `sanity_warnings: List[SanityWarning] = field(default_factory=list)`.

`report/reference_builder.py::SCHEMA_VERSION`: bump `"1.1"` → `"1.2"`
(additive field, same convention DEF-101 established for `"1.0"` →
`"1.1"`).

**Both renderers, per AC13's own requirement, updated consistently:**
- `report/reference_render.py::_track_section()`: render each
  `sanity_warnings` entry as a bullet, `[FAIL]`/`[WARN]` prefix by
  severity.
- `report/render.py` (STORY-001's mastering pre/post renderer):
  `ReportData.before`/`.after` are `Measurements` objects directly, so
  the new field flows through `build_report()` with zero changes there
  — only `render.py` needs a new rendering block for
  `before.sanity_warnings`/`after.sanity_warnings`, same
  `[FAIL]`/`[WARN]` convention, for consistency across both report
  formats.

**Verification required before assuming this is sufficient, not
performed by this architecture pass**: this document has not read
`report/reference_builder.py::build_reference_set_report()` in full.
If that function constructs its own per-track output structure rather
than embedding/threading the `ReferenceMeasurements` object (or a
field-for-field copy of it) directly, the new `sanity_warnings` field
can silently fail to reach either renderer even though the dataclass
change is correct and `analyze_track()` populates it correctly —
every test in §7.6 that only checks population, not rendered output,
would still pass in that scenario. **§7.6 accordingly requires a
rendered-output assertion, not just a population assertion** — this is
the concrete test design that catches exactly this risk; whoever
implements this must additionally confirm by direct reading that
`reference_builder.py` threads the field before considering AC13 done.

**Golden-file / reproducibility risk, flagged explicitly**:
`test_ac10_reproducibility.py` is referenced in DEF-103's fix notes as
part of a "reproducibility/golden-file suite." Before adding
`sanity_warnings` to `Measurements`, check whether that file (or any
other) does an exact stored-JSON/report-text diff — if so, adding a
new field changes the serialized shape, and golden-file regeneration
must be a deliberate, reviewed step (confirm the new content is
correct, then regenerate), not a silent overwrite that could mask an
unrelated regression.

---

## 5. Ground-truth subset selection mechanism (open question 7)

**Decision: both a filename convention and a pytest marker, matching
this project's own precedent of using both simultaneously** (`test_ref_*.py`
filename convention for STORY-002's domain, `@pytest.mark.slow`/
`@pytest.mark.isolated` marker convention for wall-clock-sensitive NFR
tests, per DEF-110).

- New files: `test_ground_truth_loudness.py`,
  `test_ground_truth_true_peak.py`, `test_ground_truth_hf_extension.py`,
  `test_ground_truth_dynamic_range.py`, `test_ground_truth_spectral_balance.py`,
  `test_ground_truth_stereo_width.py`, `test_ground_truth_sanity_assertions.py`,
  `test_ground_truth_kweight_oversample.py` — all under
  `stories/STORY-001/implementation/tests/`.
- Each file sets `pytestmark = pytest.mark.ground_truth` at module
  level.
- Register the marker in `pyproject.toml`:
  `"ground_truth: STORY-003 ground-truth signal tests, analytically-derived expected values, selectable independently for the AC5/AC12 <30s runtime budget."`
- Timed invocation: `pytest -m ground_truth`. No isolation marker
  needed (unlike `test_tc150`/`test_tc381`, DEF-110) — these fixtures
  are all sub-second per test; there is no expectation of
  session-position sensitivity here, but if QA's actual measurement
  disagrees, that itself is a finding to record, not something this
  architecture should assume away.

---

## 6. AC6 sequencing protocol — ordered, owner-assigned

For **DEF-201** (the only one requiring the failing-test-first
sequence, per §3.4):

1. **python-developer or test-case-writer** (whoever writes
   `test_ground_truth_hf_extension.py`) writes the AC6d pink-noise
   ground-truth test against the **unmodified** code
   (`hf_rolloff_threshold_db=6.0` still in place).
2. Run it. Record the exact failure in `stories/STORY-002/defects.md`'s
   DEF-201 entry: the test name, the failing assertion, and the
   **numeric actual-vs-expected values** — not "it failed." (e.g.
   "`test_ground_truth_hf_extension.py::test_ac6d_pink_noise_no_cutoff`
   failed: `rolloff_hz` reported `2143 Hz`, expected `>= 0.9 * Nyquist
   (19845 Hz)`" — tie the recorded number to the same style of finding
   that opened DEF-201 in the first place, e.g. GusGus's reported
   1979 Hz.)
3. **python-developer** makes the one-line config change (§2.2, now
   `6.0` → `20.0`), and the `test_tc304`/`test_tc305` re-fixture onto
   `brickwall_lowpass_noise_mono` (§2.5).
4. Re-run the same test; confirm it passes; record the post-fix value
   in the same defects.md entry.
5. Re-run the full HF-extension-adjacent regression surface named in
   §2.5, plus the full `test_ref_*.py`/`test_ac*.py` suites, per this
   project's standing no-regression convention; record pass counts in
   the same entry.
6. Mark DEF-201 **Fixed** in `stories/STORY-002/defects.md`, following
   the existing DEF-101/DEF-103 fix-notes format (what changed, what
   was verified, exact numbers).

For **DEF-203**: no code change (§3.4). The sequence is: derive (§3,
already done in this document) → write the ground-truth test, which
passes immediately against unmodified code → record the derivation and
the "why AC6's ordering doesn't apply here" note in
`stories/STORY-002/defects.md`'s DEF-203 entry, closing it
**not-a-defect**.

---

## 7. Per-measurement ground-truth test specifications

Brief per AC item — full derivations for HF extension and mono-sum are
in §2/§3; this section covers the rest concretely enough that no
further design decision is needed.

### 7.1 Loudness (AC4a/4b) — `test_ground_truth_loudness.py`

**AC4a is already satisfied** by the existing `test_tc010`
(`tests/test_ac2_loudness.py`): 1 kHz sine, -20 dBFS RMS, mono,
asserts `abs(lufs - (-20.0)) < 0.1`. Recommend one small addition to
that test's docstring (not a new test) stating the AC3 "why" derivation
explicitly: 1 kHz is BS.1770's own calibration-neutral frequency — the
K-weighting high-shelf's partial boost already present at 1 kHz (shelf
center `f0≈1682 Hz`, `Q≈0.707` per `loudness_range.py`'s coefficients,
so the shelf's rise begins measurably below its own center) combines
with the standard's `-0.691 dB` fixed offset to net ≈0 dB total at
1 kHz — this is the standard, widely-documented reason 1 kHz is used
as the BS.1770 calibration tone, not a coincidence specific to this
implementation.

**AC4b is new** (no existing test): construct two calibrated
1 kHz sines at an exact 6.000 dB linear ratio
(`amplitude2 = amplitude1 * 10**(6/20)`, not `2.0`, which is 6.0206 dB
— use the exact ratio so the expected delta is exactly 6.000, not an
approximation), measure both, assert
`abs((lufs2 - lufs1) - 6.0) < 0.1`. 3-5 s each is sufficient (no
block/window minimum applies to plain integrated LUFS beyond
pyloudnorm's own ~400 ms internal minimum).

### 7.2 True peak (AC5a/5b) — `test_ground_truth_true_peak.py`

**Fixture: `nyquist_adjacent_sine(sr, duration_s=2.0)`** — `x[n] =
sin(πn/2 + π/4)`, i.e. exactly `sr/4` Hz with a 45° phase offset. Every
sample lands at exactly `±1/√2` (sample peak = `-3.0103 dBFS`
exactly), while the continuous-time signal's true peak is `1.0`
(`0 dBTP` exactly) at `t` values that fall exactly halfway between
consecutive samples — the classic, exact inter-sample-overshoot
construction. This gives an exact, analytically-known margin of
`3.0103 dB`, not an approximation, and serves both AC5a and AC5b from
one fixture:

- **AC5a**: `measure_true_peak(to_stereo(fixture), sr, config).dbtp`
  should read `≈ -3.0103 + margin` where the FIR's own passband
  behavior near this frequency (well below Nyquist at any
  `true_peak_oversample_factor >= 4`, since this is exactly the
  original signal's Nyquist, not the oversampled Nyquist) is flat —
  assert `dbtp` is within `0.05 dB` of `0.0` (the true value), and
  separately assert `dbtp - sample_peak_dbfs >= 2.9` (comfortably
  inside the exact 3.0103 dB margin, loose enough to absorb FIR ripple
  at this frequency).
- **AC5b**: assert `measure_true_peak(...).dbtp != pytest.approx(sample_peak_dbfs, abs=0.5)`
  — i.e. a test asserting true peak equals sample peak on this fixture
  **must fail**; write it as the direct regression guard AC5b asks
  for.

**Explicitly do not use a near-Nyquist frequency for this fixture** —
`true_peak.py`'s own documented FIR droop (`~1.5 dB at 94% Nyquist`,
per its module docstring's tuning notes) would corrupt the expected
value at a near-Nyquist frequency and produce a failure that is about
FIR passband ripple, not about true-peak correctness. `sr/4` sits
comfortably inside the FIR's flat region regardless of oversample
factor.

### 7.3 HF extension / rolloff (AC6a-e) — `test_ground_truth_hf_extension.py`

**Every test in this file uses `ref_config(hf_min_duration_s=2.0)`**
(§1.3), the established override pattern, so 2-5 s fixtures reach the
real scan path instead of the `insufficient_duration` fallback.

- **AC6a**: `brickwall_lowpass_noise_mono(sr, duration_s=3.0, cutoff_hz=15000.0, seed=1, amplitude=0.3)`
  (§1.2 — genuine spectral-zero brickwall, **not**
  `lowpassed_white_noise`, per §2.5). Assert `rolloff_hz ==
  pytest.approx(15000.0, abs=config.hf_rolloff_test_tolerance_hz)`
  (reuses the existing `500.0 Hz` config tolerance directly — a true
  brickwall's threshold-crossing frequency is independent of the
  absolute threshold's depth to within a few Welch-PSD bins of leakage
  smear, so no new tolerance figure is needed regardless of the exact
  `hf_rolloff_threshold_db` value in effect) and `stable is True`.
- **AC6b**: same construction, `cutoff_hz=8000.0`, same assertions
  against `8000.0`.
- **AC6c**: `white_noise_mono(sr, duration_s=3.0, seed=1, amplitude=0.2)`
  (full-band, no filtering). Assert `rolloff_hz >= 0.9 * (sr/2)` and
  `insufficient_duration is False` (§2.3 — no new sentinel needed).
- **AC6d — the literal DEF-201 regression fixture**:
  `pink_noise_mono(sr, duration_s=3.0, seed=1)` (existing helper,
  reused as-is — its own docstring's "good enough for non-degenerate
  energy, not precision spectral assertions" caveat does not apply
  here, since this test's assertion is directional, not precision-numeric).
  Assert `rolloff_hz >= 0.9 * (sr/2)`, matching AC6c's assertion — this
  is the test that would have caught DEF-201 (see §6 for the
  failing-test-first sequence this specific test must go through).
- **AC6e**: `brickwall_lowpass_noise_with_drift(sr, first_s=2.0, second_s=2.0, cutoff1_hz=15000.0, cutoff2_hz=8000.0, seed=1, amplitude=0.3)`
  (4 s total, `hf_stability_segment_count=5` default gives 5 segments
  of ~0.8 s each — segments 1-2 fall entirely in the first half,
  segments 4-5 entirely in the second, segment 3 straddles the
  transition). Assert `stable is False` (spread between 15000 Hz and
  8000 Hz segments, `≈7000 Hz`, exceeds `hf_stability_tolerance_hz=2000`)
  and `rolloff_hz is not None` (median still reported, not withheld —
  matches the existing `test_tc308`'s own assertion pattern for the
  same scenario).

**Migration of existing tests, per §2.5**: `test_tc304`
(`cutoff_hz=16000.0`) and `test_tc305` (`cutoff_hz=12000.0`) in
`test_ref_ac10_verification_bars.py` must be re-fixtured from
`lowpassed_white_noise` onto `brickwall_lowpass_noise_mono`, keeping
their existing expected values and tolerance unchanged. `test_tc307`
and `test_tc308` are unaffected and need no change (§2.5).

### 7.4 Spectral balance (AC8a/8b/8c) — `test_ground_truth_spectral_balance.py`

Covers both `frequency_balance.py` (STORY-001's three-band scheme) and
`seven_band_balance.py` (STORY-002's seven-band scheme) — both share
the identical `_psd.py` boundary convention.

**AC8a**: `band_limited_noise_mono(sr, duration_s=4.0, band_hz=(2000,5000), seed=1, amplitude=0.2, floor_amplitude=0.005)`
(§1.2) — energy concentrated in `high_mid` plus a low broadband floor
everywhere. Assert `high_mid.relative_db` is the maximum among all
seven bands, and exceeds every other band's `relative_db` by at least
`20 dB` (a directional, by-construction assertion — the bandpass
confines the dominant component to one band; the exact numeric gap
depends on filter order/floor amplitude choices made at
implementation time, so a relational assertion is the honest ground
truth here, not a fabricated precise number). **Not yet empirically
verified that `floor_amplitude=0.005` keeps every other band's power
away from the `_MIN_POWER=1e-20` floor** — flagged in §10 risk #2;
confirm before finalizing.

**AC8b — exact, closed-form, no filtering needed**: for genuinely flat
white noise, `_psd.band_power`'s trapezoidal integral of a constant
density over `[lo, hi]` is `density * (hi - lo)` to a very good
approximation (band widths here are all far larger than the PSD bin
spacing), so `relative_db(band) = 10*log10(width_band / width_ref)`
**independent of the actual noise realization** — a purely geometric
prediction. Reference band width is `1500 Hz` (500-2000). Worked table
(44.1 kHz, Nyquist=22050 for the air band's open upper edge):

| band | range (Hz) | width (Hz) | predicted `relative_db` |
|---|---|---|---|
| sub | 20-60 | 40 | `10*log10(40/1500) = -15.74` |
| low | 60-120 | 60 | `10*log10(60/1500) = -13.98` |
| low_mid | 120-500 | 380 | `10*log10(380/1500) = -5.96` |
| mid | 500-2000 | 1500 | `0.00` (this is the reference band itself) |
| high_mid | 2000-5000 | 3000 | `10*log10(3000/1500) = +3.01` |
| high | 5000-10000 | 5000 | `10*log10(5000/1500) = +5.23` |
| air | 10000-22050 | 12050 | `10*log10(12050/1500) = +9.05` |

(For 48 kHz sources, air's upper edge is 24000, width 14000,
`relative_db = +9.70` — compute per actual sample rate, do not
hardcode the 44.1 kHz figure for a 48 kHz fixture.) Use
`white_noise_mono(sr, duration_s=5.0, seed=1, amplitude=0.1)`,
tolerance `±1.0 dB` per band (generous relative to finite-length Welch
estimation variance; QA may tighten empirically).

**AC8c — revised design: unit-test `_psd.band_power` directly, not
through a synthesized tone.** A tone-based approach (e.g. a pure sine
at exactly 120 Hz, fed through the full measurement pipeline) does
**not** actually isolate the mask's inclusive/exclusive convention: a
real Welch PSD spreads a single tone's energy across several
neighboring bins via the analysis window's own spectral leakage
regardless of whether `band_power`'s mask is `>=`/`<=`,
`>`/`<`, or any other combination — "both adjacent bands show
elevated energy" would pass under every possible boundary convention,
proving nothing about which one is actually implemented. The correct
ground truth is a direct, hand-built-array unit test of the function
itself:

```python
def test_ac8c_boundary_frequency_attributed_to_both_adjacent_bands():
    """_psd.band_power's mask is (freqs>=lo)&(freqs<=hi) -- confirmed
    inclusive on BOTH ends by reading _psd.py directly (not assumed).
    A synthesized-tone test cannot actually distinguish this from an
    exclusive convention (Welch spectral leakage spreads a tone's
    energy across several bins regardless of the mask), so this test
    hand-builds a freqs/psd pair with all the energy in exactly one bin
    at the shared low/low_mid boundary (120 Hz) and calls band_power
    directly."""
    freqs = np.array([100.0, 120.0, 140.0])
    psd = np.array([1e-20, 1.0, 1e-20])  # all energy at exactly the boundary bin
    power_low = _psd.band_power(freqs, psd, (60.0, 120.0))
    power_low_mid = _psd.band_power(freqs, psd, (120.0, 500.0))
    assert power_low > 1e-10        # boundary bin's energy included...
    assert power_low_mid > 1e-10    # ...in BOTH adjacent bands
```

No new signal generator is needed for this test — it does not go
through audio synthesis at all.

### 7.5 Stereo width / correlation / mono-sum (AC9a-9d) — `test_ground_truth_stereo_width.py`

**AC9a**: `to_stereo(pink_noise_mono(sr, 3.0, seed=1))` (identical
L=R). `correlation_coefficient(left, right) == pytest.approx(1.0, abs=1e-6)`
(epsilon required — see §4.2's note on floating-point artifacts for
this exact function). `measure_per_band_stereo_width`: derive from the
CSD formula directly — for `L=R`, `S_LR = S_LL = S_RR` exactly (real,
in-phase), so `width = 1 - |S_LL| / sqrt(S_LL * S_LL) = 1 - 1 = 0` in
every band. Assert every band's `width < 0.05`.

**AC9b**: `inverted_stereo(pink_noise_mono(sr, 3.0, seed=1))`
(L=-R). `correlation_coefficient == pytest.approx(-1.0, abs=1e-6)`.
`mono_sum`: pure L=-R with no noise floor gives `mono_sum` identically
zero — `measure_integrated_lufs` on all-zero returns `-inf`
(confirmed by `test_tc017`'s existing coverage of that behavior), so
`level_change_db == float("-inf")` and `excess_cancellation_db ==
float("-inf")` — assert these exactly, not approximately. **Note,
stated explicitly to avoid a future false "regression" report**:
`per_band_stereo_width` is a magnitude-based (phase-blind) metric by
design (`width` uses `|Re{S_LR}|`) — it reads `≈0` for **both** ρ=+1
and ρ=-1 (both are "fully correlated in magnitude," just opposite
sign), unlike `correlation_coefficient`, which is signed and
distinguishes them. AC9a/AC9b's "per_band_stereo_width ≈0" framing in
story.md is literally only stated for the identical-L/R case; do not
add an assertion claiming `per_band_stereo_width ≈0` is somehow wrong
or different for the inverted case — it is expected to read the same
as AC9a, by construction of the formula, and that is correct behavior,
not a bug.

**AC9c**: `independent_noise_stereo(sr, 5.0, sigma=0.05, seed=3)`
(existing `ref_helpers.py` function — the DEF-101 case-2 fixture).
`correlation_coefficient` near `0.0` (tolerance `±0.05`, reflecting
finite-sample noise, not a tight bound). `per_band_stereo_width`:
independent equal-power noise drives `S_LR → 0` in expectation, so
`width → 1`; assert `width >= 0.8` in every band (generous starting
tolerance, flagged for QA to tighten empirically once the real Welch
averaging depth at this fixture length is measured).

**AC9d / DEF-203 resolution — the dedicated derivation test**: three
sub-cases, reusing `test_tc311`'s and `test_tc313`'s existing fixtures
plus one new rho=-1 fixture, **extended with explicit per-band
`delta_db` assertions and an inline derivation comment stating which
denominator each field uses** (requirements.md's own explicit
requirement, not previously satisfied by `test_tc311`/`test_tc313`,
which asserted `excess_cancellation_db`/`cancellation` but not the raw
`delta_db`/`level_change_db` values with the denominator called out):

```python
def test_ac9d_def203_monosum_floors_derived_from_first_principles():
    """DEF-203 resolution (see architecture.md Section 3 for the full
    variance-based derivation). level_change_db uses BS.1770's
    channel-SUMMED denominator (2*sigma^2 for stereo); delta_db uses the
    per-band channel-MEAN denominator (sigma^2) -- these are different
    formulas with genuinely different rho=0 floors, -6.0206 dB and
    -3.0103 dB respectively, not two candidate answers to one question.
    """
    sr = 44100
    # rho = +1
    mono = pink_noise_mono(sr, 5.0, seed=1)
    result = measure_mono_sum(to_stereo(mono), sr, ref_config())
    assert result.level_change_db == pytest.approx(-3.0103, abs=0.1)
    for b in result.band_cancellations:
        assert b.delta_db == pytest.approx(0.0, abs=1.0)

    # rho = 0
    result = measure_mono_sum(independent_noise_stereo(sr, 8.0, sigma=0.05, seed=1), sr, ref_config())
    assert result.level_change_db == pytest.approx(-6.0206, abs=0.1)
    for b in result.band_cancellations:
        assert b.delta_db == pytest.approx(-3.0103, abs=1.0)

    # rho = -1
    result = measure_mono_sum(inverted_stereo(pink_noise_mono(sr, 5.0, seed=1)), sr, ref_config())
    assert result.level_change_db == float("-inf")
```

### 7.6 Sanity assertions (AC10) — `test_ground_truth_sanity_assertions.py`

**Two layers, not one — a population-only test suite is not sufficient
to satisfy AC10, per §4.4's flagged risk that the report-builder layer
might not thread the new field even if the dataclass change is
correct:**

1. **Unit level** against the four pure functions in §4.2 directly
   (plain float/list inputs, no audio needed — e.g.
   `check_correlation_range(1.0000000000000002)` returns `None`;
   `check_correlation_range(1.5)` returns a `fail`;
   `check_lufs_plausible(float("-inf"))` returns `None`;
   `check_lufs_plausible(-75.0)` returns a `fail`;
   `check_lufs_plausible(float("nan"))` returns a `fail`;
   `check_lufs_plausible(3.297)` (DEF-206's own reproduced value) returns
   `None`, confirming the corrected ceiling no longer false-positives on
   it; `check_lufs_plausible(6.6)` returns a `fail` (just above the
   derived `6.5` ceiling)).
2. **Rendered-output level, following `test_tc310`'s existing
   pattern** (`render_markdown(...)` → `assert "..." in md`) — for
   **both** renderers, using a fixture engineered to deliberately trip
   a real check, not merely to populate the field:
   - Reference path: hand-construct a `ReferenceMeasurements` the same
     way `ref_helpers.make_stub_measurements` already does (extend
     that helper to accept a `sanity_warnings` override, or
     hand-construct directly), with `hf_rolloff_hz=2000.0`,
     `hf_insufficient_duration=False`, and a seven-band `air`
     `relative_db` forced above `-40.0` — the exact DEF-201-shaped
     scenario. Call `build_reference_set_report()` then
     `render_markdown()` (and `render_json()`), and assert the FAIL
     text (or the `sanity_warnings` field) appears in the output. This
     directly exercises whatever `reference_builder.py` actually does
     with the field, closing §4.4's flagged risk rather than assuming
     it away.
   - Mastering path: hand-construct a `Measurements` (or `ReportData`)
     object with a manufactured `sanity_warnings` list (e.g. a
     correlation-out-of-range warning) and call `report/render.py`'s
     `render_markdown()` directly; assert the warning text appears.
3. **Integration level**: confirm `measure_all()` and `analyze_track()`
   actually populate `sanity_warnings` end-to-end on a real (if tiny)
   buffer — this is necessary but, per the above, not sufficient on
   its own.

Also covers the "known degenerate case" from requirements.md
explicitly: `correlation_coefficient` on both-silent stereo returns
exactly `1.0` (by design, per its own code comment) — assert this
specific behavior directly, `pytest.approx(1.0)`, so a future change to
the null-handling doesn't silently drift without a test noticing.

### 7.7 `k_weight` / `oversample` (recommended additional coverage) — `test_ground_truth_kweight_oversample.py`

Confirming requirements.md's own flagged recommendation as in-scope
for this story: both are load-bearing internal machinery (every LRA
measurement depends on `k_weight`; every true-peak measurement depends
on `oversample`) where a silent bug would corrupt every downstream
measurement that calls them, and both have cheap ground truth
available.

- **`oversample`**: apply `oversample(nyquist_adjacent_sine(sr, 2.0), sr, factor=8)`
  directly (no guard-region trimming — that is `measure_true_peak`'s
  own addition, not `oversample`'s) and assert
  `max(abs(oversampled)) ≈ 1.0` (within `0.05`) — the same fs/4
  construction as §7.2, ground-truthing the interpolation filter in
  isolation from the peak-search/guard-region logic layered on top of
  it in `measure_true_peak`.
- **`k_weight`**: apply to sines at a small set of anchor frequencies
  and compare the input/output RMS ratio (in dB) against BS.1770's
  published magnitude-response anchor points: approximately `0 dB` at
  1 kHz (per §7.1's derivation), approximately `+4 dB` on the
  high-shelf's plateau (well above `~2 kHz`, e.g. at `10 kHz`), and a
  clearly measurable attenuation below the high-pass corner (e.g. at
  `20 Hz`, well below the `~38 Hz` corner). **Note, added this
  revision, per §4.2's DEF-206 derivation**: at exactly Nyquist itself,
  `k_weight`'s own gain reaches `Vh ≈ +4.0 dB` on the shelf stage
  exactly (algebraically, not just "approximately," per §4.2) and
  `a0_hp` (`≈+0.047 dB` at 44.1 kHz) on the high-pass stage — a useful
  additional anchor point if this test is extended to cover the exact
  boundary case §4.2's ceiling derivation relies on, though not
  required to satisfy this AC's own "anchor points" framing on its own.
  **Exact literature figures for the specific attenuation at 20 Hz are
  not pinned down by this architecture** — flagged as something
  whoever implements this test should pull directly from BS.1770-4
  Annex 1's published response curve or a known-good independent
  implementation (e.g. libebur128's own test vectors) rather than an
  invented number, with a generous tolerance (`±1 dB` on the shelf
  plateau, `±0.5 dB` at 1 kHz) since published figures vary slightly by
  source/rounding.

---

## 8. Testability notes

- **Session-scoped fixtures**, per the NFR, for signals genuinely
  reused byte-for-byte across multiple test functions — not for every
  parametrized variant. Recommend: `calibration_tone_1khz_neg20dbfs`,
  `standard_pink_noise_3s`, `standard_white_noise_3s`,
  `identical_stereo_pair_3s`, `inverted_stereo_pair_3s`,
  `uncorrelated_stereo_pair_5s`. **Mutation hazard, stated explicitly**:
  pytest session scope returns the *same array object* to every
  requesting test. A test that mutates a session-scoped array in place
  (e.g. `audio *= 2.0` or a slice-assignment dropout like §7.3's AC7c
  construction) will corrupt it for every other test in the session
  that runs afterward — the fix is `audio.copy()` at the top of any
  test that needs a modified variant, stated here as a concrete
  implementation rule, not left implicit.
- **Fixed seeds everywhere** (per the NFR's reproducibility
  requirement) — every noise-based generator in §1.2 takes an explicit
  `seed` parameter; no bare `np.random` calls without a seed.
- **Injectable config, not hardcoded defaults**, is what makes the
  `hf_min_duration_s` override (§1.3) possible at all — this is an
  existing property of the codebase (`ReferenceAnalysisConfig` and
  `MasteringConfig` are both plain dataclasses passed explicitly to
  every measurement function), not something this story needs to add;
  it only needs to be *used* correctly, per the `ref_config(**overrides)`
  pattern already established.
- **Runtime**: see §1.3's reasoning for why longer-than-2-5s fixtures
  (DR, LRA) do not threaten the 30 s budget. qa-automation-engineer
  should still measure `pytest -m ground_truth` wall time directly and
  record the actual figure, not rely on this architecture's estimate.

---

## 9. Assumptions pending BA confirmation

1. **The `25.0`/`40.0` dB seven-band adjacent-delta sanity thresholds
   (§4.2)** are this architecture's own provisional judgment call,
   explicitly flagged as such per requirements.md's open question 3 —
   not a BA-specified figure. Proceeding with these values so the
   sanity check has a concrete implementation now; recommend
   calibrating against the five existing reference tracks' actual
   adjacent-band deltas (§4.2's instruction to QA) before treating them
   as final.
2. **`hf_rolloff_threshold_db = 20.0`** (§2.2, revised this pass from
   the original `40.0`) is no longer a point chosen from DEF-201's
   suggested "-30 to -40 dB" range by architectural judgment alone —
   it is the midpoint of an empirically validated window (`[18, 21]
   dB`), derived from both this project's real five-track reference set
   and a realistic synthetic negative control (§2.2, §2.5). **This is a
   narrower and more fragile empirical result than a simple "chose the
   deep end for safety margin" framing would suggest** — see §2.6 for
   the fragility statement and the protocol for what to do if a future
   reference track or fixture invalidates it, and §2.7 for the reasoned
   answer on whether a fixed threshold is durably the right mechanism.
   This is not a simple tuning question for "a later pass" the way v1's
   equivalent assumption framed it — a future pass finding the window
   closed or inverted is a structural finding, not a minor recalibration
   (§2.6 item 3).
3. **`k_weight`/`oversample` ground-truth coverage (§7.7)** is
   confirmed in-scope, per requirements.md's own explicit recommendation
   — stated here as a confirmed architectural decision, not left open,
## DEF-201 -- QA ground-truth verification (qa-automation-engineer, STORY-003 pass)

**Status: still Open** (Code-level -- unchanged triage; the fix itself is
a one-line numeric config change, but the specific number architecture.md
Section 2.2 names, 40.0, is empirically wrong and must be corrected before
python-developer applies it -- see recommendation below). Not closed by this
entry; this records the required AC6/AC11 "failing-test-first" evidence plus
new evidence bearing on the fix's exact target value.

**AC6/AC11 evidence -- failing test recorded BEFORE any production code
change, per architecture.md Section 6 / requirements.md AC11**:

Test: `stories/STORY-001/implementation/tests/test_ground_truth_hf_extension.py::test_tc024_pink_noise_no_cutoff`
(STORY-003 test-cases.md TC-024, the literal DEF-201 regression fixture:
`pink_noise_mono(sr=44100, duration_s=3.0, seed=1)`, `ref_config(hf_min_duration_s=2.0)`,
run against the shipped, UNMODIFIED `hf_rolloff_threshold_db=6.0`).

Failing assertion: `assert result.rolloff_hz >= 0.9 * (SR / 2.0)`.

Actual vs. expected: **`rolloff_hz = 12960.296630859375 Hz`** (per-segment
values: `[12960.30, 13652.05, 10747.76, 12858.01, 16136.44]`), expected
`>= 19845.0 Hz` (0.9 x Nyquist at 44.1kHz). `insufficient_duration=False`
(the `hf_min_duration_s=2.0` override correctly reaches the real scan path,
not the fallback branch).

Note for the record: this is a real, reproducible false "cutoff" on pure
pink noise (no real cutoff exists by construction) -- structurally the same
defect DEF-201's original report found on GusGus (1979 Hz), though the exact
numeric value differs (12960 Hz here vs. 1979 Hz there), because this
synthetic 1/f-shaped pink-noise fixture's spectral tilt is not identical to
real commercial-master spectral shape. Architecture.md's own "~2143 Hz"
figure for this test was explicitly an illustrative placeholder, not a
prediction, per test-cases.md's own instruction -- the actual measured value
above is what's recorded, not that placeholder.

**TC-023 (new, finite-stopband-floor negative control) -- run against the
SAME unmodified code (threshold=6.0)**:

Test: `test_ground_truth_hf_extension.py::test_tc023_finite_stopband_floor_probes_whether_deepened_threshold_is_too_deep`,
fixture `brickwall_lowpass_noise_with_floor_mono(sr=44100, duration_s=3.0, cutoff_hz=16000.0, floor_below_db=27.0, seed=1, passband_sigma=0.15)`
(a real 16000 Hz cutoff with a 27 dB-down, non-silent stopband floor, matching a
realistic mid-quality lossy-encoder anti-aliasing floor -- see test-cases.md
TC-023 for the full construction/derivation).

**Result at threshold=6.0 (current shipped default): PASSES.**
`rolloff_hz = 15999.17 Hz` (expected `16000 +/- 500 Hz`). This is the direct,
concrete confirmation of the trade-off test-cases.md TC-023 was written to
probe: the CURRENT shipped 6.0 dB threshold gets TC-023 right (finds the
real cutoff) and TC-024 wrong (false-positives on pink-noise tilt) --
DEF-201's proposed 40.0 dB fix inverts exactly that (see sweep below), i.e.
it would trade one false positive for a different false negative, not
simply fix the bug.

**Threshold sweep -- run to answer the orchestrator's specific question
("does 40.0 need to go back to the architect as a separate Architectural
defect from DEF-201's direction-of-fix being correct")**. All five HF
ground-truth fixtures (TC-020 brickwall@15kHz, TC-021 brickwall@8kHz, TC-022
full-band white noise, TC-023 finite-floor@16kHz/-27dB, TC-024 pink noise),
measured `rolloff_hz` at `hf_rolloff_threshold_db` in `{6,7,8,9,10,...,22,...,40}`,
via `ref_config(hf_min_duration_s=2.0, hf_rolloff_threshold_db=X)`:

```
fixture                        6       9      10      15      18      20      21      22      26      30      40
TC020_brickwall_15k        14998   ~15001  15001   15001   15001   15001   15003   15003   15003   15003   15006
TC021_brickwall_8k          8000   ~8000    8000    8002    8002    8002    8002    8002    8002    8002    8005
TC022_white                22047   22050   22050   22050   22050   22050   22050   22050   22050   22050   22050
TC023_floor27db_16k        15999   15999   15999   16002   16002   16002   16002   18516   22031   22045   22050
TC024_pink (seed1)         12960   21181   21921   22045   22047   22047   22047   22047   22047   22050   22050
TC024_pink (seed2)         11300   21504   21880   22047   22047   22047   22047   22050   22050   22050   22050
TC024_pink (seed3)         12481   21259   21732   22037   22047   22047   22050   22050   22050   22050   22050
```

(Nyquist=22050 Hz; TC024's pass bound is `>=19845`; TC023's pass bound is
`[15500,16500]`.)

**Finding (synthetic fixtures only, superseded below by real-track data):**
initially, a window of threshold values -- approximately `[9, 21] dB` --
appeared to satisfy BOTH TC-023 and TC-024 simultaneously across three
synthetic pink-noise seeds. TC-020/021/022/025 (brickwall/white-noise/drift
fixtures) are threshold-independent or pass everywhere in this range, per
architecture.md Section 2.5's own derivation. TC-023 fails once threshold
exceeds ~21-22 dB (jumps to 18516 Hz, then to Nyquist); synthetic TC-024
(pink) needs threshold >= ~9-10 dB to clear `0.9*Nyquist` across seeds.

**Real-track validation, performed this pass** (this project's own real
five-track reference set, `Reference Tracks/*.wav` at the project root --
the exact tracks DEF-201's original report was written against, including
GusGus which DEF-201 quoted directly): the synthetic-only window above is
**too optimistic**. Sweeping `hf_rolloff_threshold_db` against all five real
tracks and cross-checking each against `check_hf_rolloff_vs_air_band`
(i.e. "does this threshold value make the DEF-201-motivated sanity check
stop firing on this real track's own rolloff-vs-air-band numbers"):

```
Black_Flute_Remastered.wav      (air=-11.44 dB): clears at t>=6  (never fires)
GusGus (DEF-201's own example)  (air=-20.05 dB): clears at t>=15 (t=6: rolloff=1979, FIRES; t=15: rolloff=6740, clear)
Leftfield_-_Melt_Audio.wav      (air=-25.10 dB): clears at t>=18 (t=15: rolloff=3768, STILL FIRES; t=17: rolloff=4965, STILL FIRES; t=18: rolloff=8142, clear)
Chemical_Brothers...            (air=-16.01 dB): clears at t>=15 (t=6: rolloff=4954, FIRES; t=15: rolloff=10618, clear)
Wavy_Gravy.wav                  (air=-13.15 dB): clears at t>=6  (never fires)
```

Leftfield is the binding real-world constraint: **the sanity check
(rolloff<5000 AND air>-40) keeps firing on this real track all the way up
through threshold=17 dB**, only clearing at threshold>=18 dB. This is
materially tighter than the synthetic-fixture-only estimate suggested
(which implied 9-10 dB was already "safe").

**Re-checking TC-023's own upper boundary against this tightened lower
bound**: TC-023 (16000 Hz cutoff, 27 dB-down realistic floor) remains within
tolerance (`rolloff_hz=16002`, `|16002-16000|<=500`) for every threshold
from 15 through 21 dB, and fails hard at 22 dB (`rolloff_hz=18516`, outside
tolerance).

**Revised finding: a real, but much narrower, safe window exists --
approximately `[18, 21] dB`** -- validated against BOTH the real five-track
reference set (Leftfield's own binding constraint, threshold>=18) AND the
synthetic realistic-lossy-floor fixture (TC-023's own binding constraint,
threshold<=21). Synthetic TC-024 (pink, all 3 seeds) and TC-022 (white
noise) both clear comfortably by threshold=18-20 (per the earlier synthetic
sweep table above, both fixtures reach `>=21900 Hz`, well past the
`19845 Hz` bound, at threshold>=18).

**Answer to the orchestrator's question, revised with real-track evidence**:
still NO, this does not need to become a separate Architectural defect
distinct from DEF-201 -- a real, non-empty window of single numeric
threshold values satisfies both the real-track and synthetic-realistic-floor
constraints, so the fix remains Code-level (the AC11-approved directional
decision -- deepen the absolute threshold, not a slope-based primary
detector -- is not invalidated). **The window is materially narrower than
first estimated from synthetic fixtures alone (`[18,21]`, not `[9,21]`)** --
this is exactly why the real-track validation this entry initially flagged
as "not yet done, time-boxed out" was performed as a follow-up within this
same pass once the synthetic-only estimate's fragility became apparent; a
production fix based on the synthetic-only estimate (e.g. the originally
drafted 15.0 dB recommendation) would NOT have fixed DEF-201 on the real
Leftfield track (still firing at 15/16/17 dB) while appearing safe against
every synthetic fixture in this suite.

**Revised recommendation for python-developer (Code-level fix)**: set
`hf_rolloff_threshold_db` to **20.0 dB** (centered in the validated `[18,21]`
window, 2 dB margin on both sides against the two binding real/synthetic
constraints found). Architecture.md Section 2.2's "Decision: change
`hf_rolloff_threshold_db` default from 6.0 to 40.0" text should be corrected
to 20.0 and reference this entry -- recommend a short architect
confirm-and-update pass on that one paragraph (not a redesign; the chosen
detection METHOD remains correct and is not reopened by this finding).

**Caveats on this narrower recommendation, stated explicitly**:
- Still only one real five-track set and one synthetic floor depth
  (27 dB down) were tested. The margin (18-21, i.e. 2 dB either side of 20)
  is real but not large -- a sixth reference track with an even more
  gradual real-world tilt than Leftfield's, or a shallower realistic lossy
  floor than 27 dB down, could plausibly narrow this further or close the
  window entirely. This is measured evidence of a real, currently-viable
  fix, not a proof the window is permanently stable as more reference
  material is added.
- `Leftfield_-_Melt_Audio.wav` and `The_Chemical_Brothers...wav` both show
  `stable=False` at every threshold tested (segment-to-segment rolloff
  variance on real material, a separate concern from the absolute-threshold
  depth question this entry addresses) -- worth a follow-up look at
  `hf_stability_tolerance_hz`/`hf_stability_segment_count` calibration
  against real material in a future pass, not addressed here.

**Post-fix verification, still to be performed once python-developer
applies the corrected threshold** (not yet done -- no production code
change has been applied in this QA pass): re-run
`test_ground_truth_hf_extension.py::test_tc024_pink_noise_no_cutoff` and
`::test_tc023_finite_stopband_floor_probes_whether_deepened_threshold_is_too_deep`,
confirm both pass, record the post-fix `rolloff_hz` values in this entry,
re-fixture `test_tc304`/`test_tc305` in `test_ref_ac10_verification_bars.py`
onto `brickwall_lowpass_noise_mono` per architecture.md Section 2.5 (TC-026/
TC-027, currently skipped placeholders in
`test_ground_truth_hf_extension.py` pending this), re-run the full
`test_ref_*.py`/`test_ac*.py` suites, then mark DEF-201 **Fixed**.

**Sanity-check cross-reference**: `analysis/sanity.py::check_hf_rolloff_vs_air_band`
was unit-tested directly against DEF-201's own literal reported numbers
(GusGus: 1979 Hz rolloff, -20.05 dB air-band) in
`test_ground_truth_sanity_assertions.py::test_tc062_check_hf_rolloff_vs_air_band_def201_literal_numbers`
and correctly fires a `fail`-severity warning on those exact values --
confirms the sanity layer (already shipped, python-developer's prior pass)
would have caught DEF-201's original real-world report immediately without
knowing the "correct" rolloff value, as AC10 intends. Note: this specific
synthetic TC-024 pink-noise fixture's own rolloff (12960 Hz at threshold=6.0)
does NOT itself trip `check_hf_rolloff_vs_air_band` (its air-band
`relative_db=-2.37 dB`, and its rolloff of 12960 Hz is not `<5000 Hz`) --
this is a property of this particular synthetic fixture's milder spectral
tilt relative to real commercial material, not a defect in the sanity
check's own logic (confirmed correct directly against the literal DEF-201
numbers above).

**Architect update (software-architect, STORY-003 v2 revision), addressing
this entry's own recommendation directly**: architecture.md Section 2.2
corrected, `hf_rolloff_threshold_db` decision changed from `40.0` to
**`20.0`** (the midpoint of this entry's own validated `[18, 21] dB`
window), with Section 2.5's blast-radius analysis fully reworked for the
corrected value (the Butterworth-fixture crossing-frequency table
recomputed at 20 dB; the Nyquist-exceed trap boundary recomputed; the
`suspected_transcode` prediction corrected from "will start firing" to
"most likely remains dormant on the current reference set," per this
entry's own real-track rolloff figures 6740/8142/10618 Hz, all well below
the 15.5-20.5 kHz suspect bands). Two new subsections added: Section 2.6
states the `[18, 21]` window's fragility explicitly (a 4 dB window, each
edge set by exactly one data point -- this entry's own Leftfield finding on
one side, TC-023's 27 dB floor assumption on the other) and gives a
concrete protocol for what to do if a future reference track or fixture
invalidates it (re-sweep, record the new binding evidence, do not silently
retune a third time; if the window closes or inverts, that is treated as
decisive evidence for escalating to hybrid detection, not as grounds for a
fourth point-value guess). Section 2.7 answers, on the record, whether a
fixed absolute-dB threshold is the right detection mechanism at all: yes,
for the current fix (the AC11-approved direction is not reopened), but the
slope-based/hybrid follow-up this entry's own `_transcode_slope_check`
cross-reference gestures at is now recorded as recommended, not optional,
given the demonstrated narrowness of the validated window and the
observation (new in this pass) that the window's own lower edge is partly
set by a second, uninvestigated tunable (`check_hf_rolloff_vs_air_band`'s
fixed `5000 Hz`/`-40 dB` figures), not by a clean, independent physical
measurement of Leftfield's true cutoff.

**Status update: still Open, Code-level** (unchanged triage, per this
entry's own note that the fix is a one-line numeric config change) --
architecture.md now specifies the corrected value; the config change itself
(`reference_analysis/config.py`, `hf_rolloff_threshold_db: 6.0 -> 20.0`),
the `test_tc304`/`test_tc305` re-fixture onto `brickwall_lowpass_noise_mono`,
and the post-fix verification this entry's own "Post-fix verification, still
to be performed" section already lists remain python-developer's/
qa-automation-engineer's outstanding work, not completed by this
architecture update. Do not close this entry until that work lands and is
recorded here, per this entry's own existing instruction.

**Fix notes (python-developer, this pass) -- Status: Fixed-Pending-Retest.**
Applied the exact one-line production change architecture.md Section 2.2
specifies: `stories/STORY-001/implementation/suno_mastering/
reference_analysis/config.py` line 52,
`hf_rolloff_threshold_db: float = 6.0` -> `float = 20.0` (an explanatory
comment was added inline, pointing to architecture.md Section 2.2/2.5/2.6/
2.7 and this entry, per this project's convention of not leaving a bare
magic-number change unexplained at its call site -- no logic in
`hf_extension.py` itself was touched, matching architecture.md's explicit
"no change to `hf_extension.py`'s scan logic itself" instruction).

**Deliberately NOT done in this pass, per explicit routing to
qa-automation-engineer/test-case-writer (this project's tests/ ownership
convention, and this pass's own task instructions)**: the
`test_tc304`/`test_tc305` re-fixture onto `brickwall_lowpass_noise_mono`
(architecture.md Section 2.5/Section 6 step 3). These two tests remain
skipped placeholders (`test_ground_truth_hf_extension.py::test_tc026_...`/
`test_tc027_...`) exactly as this entry's own "Post-fix verification, still
to be performed" section anticipated -- this is qa-automation-engineer's
outstanding half of this entry's own work list, not overlooked.

**Verification performed this pass** (narrow, targeted re-run per this
role's standing instruction not to run the full suite):
`pytest tests/test_ground_truth_hf_extension.py -q -m "not isolated"` ->
**7 passed, 3 skipped** (the 3 skips are exactly TC-026/TC-027/TC-029,
already anticipated above as QA's outstanding work; no unexpected
failures). Specifically confirmed, by name:
- `test_tc024_pink_noise_no_cutoff` **PASSED** -- this is the literal AC6/
  AC11 evidence loop closing: the failing-test-first record above showed
  `rolloff_hz=12960.30 Hz` (expected `>=19845 Hz`) against the unmodified
  `threshold_db=6.0`; with the fix applied, this same test now passes
  (post-fix `rolloff_hz` not independently re-printed by this run beyond
  pass/fail, consistent with this entry's own pre-recorded sweep-table value
  of `22047 Hz` at `threshold_db=20` for this exact seed).
- `test_tc023_finite_stopband_floor_probes_whether_deepened_threshold_is_too_deep`
  **PASSED** -- confirms the negative control that ruled out the earlier,
  now-superseded 40.0 dB target still passes at the corrected 20.0 dB value,
  consistent with this entry's own sweep table (`rolloff_hz=16002 Hz` at
  `threshold_db=20`, well inside the `[15500, 16500]` tolerance).
- `test_tc020_brickwall_15k_detected_within_tolerance`,
  `test_tc021_brickwall_8k_detected_within_tolerance`,
  `test_tc022_full_band_white_noise_reports_near_nyquist_not_midband`,
  `test_tc025_drift_detection_fires_on_changing_cutoff`,
  `test_tc028_tc307_tc308_unaffected_by_threshold_depth_baseline` all
  **PASSED** -- the threshold-independent/unaffected fixtures architecture.md
  Section 2.5 predicted remain unaffected are confirmed unaffected.

Also confirmed via a direct `measure_all()` smoke check (not a `pytest`
invocation) that `ReferenceAnalysisConfig().hf_rolloff_threshold_db == 20.0`
at runtime, i.e. the new default actually takes effect through the
dataclass, not just as a literal in the source file.

**Not re-run this pass** (explicitly deferred, per this role's standing
instruction to run narrow tests only, not the full suite): the broader
regression surface architecture.md Section 2.5 lists (`grep` for
`rolloff_hz`/`suspected_transcode` beyond the HF-extension file,
`suspected_transcode` real-track values, the full `test_ref_*.py`/
`test_ac*.py` suites) -- this is qa-automation-engineer's next step per
architecture.md Section 6 steps 4-5, not this pass's.

**Status: Fixed-Pending-Retest.** Config change applied and narrowly
verified as above. Not marking Fixed/Closed -- per this role's standing
rule, only QA closes a defect, and the `test_tc304`/`test_tc305`
re-fixture plus the full-suite regression re-run are still outstanding
(qa-automation-engineer's territory, not withheld by oversight).

**QA retest (qa-automation-engineer, this pass) -- Status: Closed.**
Completed the two outstanding items this entry's own "Fixed-Pending-Retest"
note left open.

1. **Confirmed the pre-migration failure directly, before touching
   anything** (per this role's own standing discipline of not softening a
   result): ran the UNMODIFIED `test_tc304`/`test_tc305`
   (`stories/STORY-001/implementation/tests/test_ref_ac10_verification_bars.py`,
   still on `lowpassed_white_noise`) against the current shipped
   `hf_rolloff_threshold_db=20.0`. **Both fail**, exactly as architecture.md
   Section 2.5's blast-radius analysis predicted:
   `test_tc304` (16 kHz design cutoff): `rolloff_hz=16747.4 Hz` (expected
   `16000 +/- 500 Hz`); `test_tc305` (12 kHz): `rolloff_hz=13010.1 Hz`
   (expected `12000 +/- 500 Hz`). (Measured values, not the asymptotic
   `fc*10**(20/320)` prediction of ~18477/~16010 Hz -- real Welch-PSD
   estimation differs somewhat from the idealized formula, but the
   conclusion -- both fail, migration required, not a wider tolerance --
   is unaffected either way, matching architecture.md's own caveat.)
2. **Re-fixtured both onto `brickwall_lowpass_noise_mono`** (already
   present in `ref_helpers.py`, added by a prior pass), keeping the
   existing expected values (16000.0/12000.0 Hz) and tolerance (500.0 Hz)
   unchanged, per architecture.md Section 2.5/test-cases.md TC-026/TC-027.
   Both now pass: `test_tc304` measures `rolloff_hz=16000.52 Hz`,
   `stable=True`; `test_tc305` measures `rolloff_hz=12000.72 Hz` -- both
   comfortably inside tolerance, confirming a genuine spectral-zero edge's
   crossing frequency is independent of threshold depth, as designed.
   (`test_tc026`/`test_tc027`/`test_tc029` in
   `test_ground_truth_hf_extension.py` remain deliberately-skipped
   process/documentation placeholders, per that file's own comment that
   the actual re-fixturing work item lives in
   `test_ref_ac10_verification_bars.py`, not in the ground-truth suite
   itself -- left as-is, not converted, consistent with the file's
   existing scope statement.)
3. **Full ground-truth suite** (`test_ground_truth_*.py`, the 8 files):
   **73 passed, 3 skipped (TC-026/TC-027/TC-029, the deliberate migration/
   due-diligence placeholders named above), 0 failed, in 5.87s** --
   comfortably under AC12's 30s budget. `test_tc024_pink_noise_no_cutoff`
   (the literal DEF-201 regression guard) now **passes**;
   `test_tc023_finite_stopband_floor_probes_whether_deepened_threshold_is_too_deep`
   (the finite-floor negative control that ruled out the earlier,
   superseded 40.0 dB target) also **passes** at the corrected 20.0 dB
   value.
4. **Full existing regression suite**, one combined run
   (`python -m pytest -q -m "not isolated"` from
   `stories/STORY-001/implementation/`, covering all of `test_ac*.py`,
   `test_ref_*.py`, and `test_ground_truth_*.py` in one process, excluding
   only `test_tc150`/`test_ref_nfr.py`'s isolated NFR tests per this
   project's own `stories/STORY-001/automation/README.md` isolation rule):
   **277 passed, 9 skipped, 2 deselected, 0 failed, in 1325.37s (22:05)**.
   The 9 skips and 2 deselections were enumerated against the suite's own
   static skip/isolated markers and match exactly (no unexpected skip);
   zero failures anywhere in the combined run, confirming the threshold
   change, the `test_tc304`/`test_tc305` re-fixture, and the DEF-206 LUFS-
   ceiling change (see that entry) together introduce no regression beyond
   the intentionally-migrated fixtures themselves.
5. **Real five-track reference-set re-run**, regenerated fresh against the
   current shipped code (`python -m suno_mastering.reference_analysis
   "Reference Tracks"`, default config, `hf_rolloff_threshold_db=20.0`):

   ```
   Black_Flute_Remastered.wav        rolloff=14652.8 Hz  air=-11.44 dB  suspected_transcode=False  sanity_warnings=[]
   GusGus_...Arabian_Horse_Album.wav rolloff=12065.9 Hz  air=-20.05 dB  suspected_transcode=False  sanity_warnings=[]
   Leftfield_-_Melt_Audio.wav        rolloff= 8170.2 Hz  air=-25.10 dB  suspected_transcode=False  sanity_warnings=[]
   Chemical_Brothers_...Halo_Maud.wav rolloff=12774.9 Hz air=-16.01 dB  suspected_transcode=False  sanity_warnings=[]
   Wavy_Gravy.wav                     rolloff=17781.0 Hz air=-13.15 dB  suspected_transcode=False  sanity_warnings=[]
   ```

   **Plausibility cross-check (the actual point of this story)**: GusGus,
   the track DEF-201's original report was written against, now reads
   12065.9 Hz -- not the physically-impossible 1979 Hz the original bug
   reported alongside a -20.05 dB air band. Every one of the five tracks
   now reports a rolloff comfortably above the 5 kHz sanity-check
   threshold, consistent with each track's own air-band energy (darker air
   band correlates with a lower-but-still-plausible rolloff -- Leftfield,
   the darkest air band at -25.10 dB, reads the lowest rolloff at 8170 Hz;
   Black_Flute, the brightest at -11.44 dB, reads the highest at
   14652.8 Hz -- an internally coherent, monotonic-in-the-right-direction
   picture, not five arbitrary numbers), and `check_hf_rolloff_vs_air_band`
   correctly stays silent on all five (no rolloff `<5000 Hz` exists in this
   set). `suspected_transcode=False` on all five, consistent with
   architecture.md Section 2.5 item 2's "most likely remains dormant"
   prediction (not proven permanently, but not contradicted either). No
   `1979 Hz`-style impossible value anywhere in this set.

   **One new observation, not previously on record at this scope, flagged
   but not filed as a new defect**: all five real tracks now show
   `stable=False` (previously only 2 of 5 -- Leftfield and Chemical
   Brothers -- were recorded showing this at the sweep-tool's own
   `hf_min_duration_s=2.0`-truncated configuration; this run used the
   production pipeline's actual default `hf_min_duration_s=30.0` config
   against full-length real tracks). This is exactly the "separate,
   uninvestigated concern about `hf_stability_tolerance_hz`/
   `hf_stability_segment_count` calibration against real material" that
   architecture.md Sections 2.5/2.6/2.7 already flag explicitly as a known,
   deliberately-out-of-scope follow-up item for this story -- not a new
   blind spot, but the real-material evidence for it is now broader (5/5,
   not 2/5) than previously recorded. Does not affect `rolloff_hz` value
   correctness or block any of this story's 6 acceptance criteria (the
   `stable` field is informational; AC6e's own ground-truth test, TC-025,
   exercises the True->False transition correctly on a synthetic
   construction and is unaffected). Recorded here as updated evidence for
   whichever future pass picks up architecture.md's own flagged
   `hf_stability_*` calibration follow-up, per this role's standing
   instruction to record, not silently fix, an out-of-scope observation.

**DEF-201: Status: Closed.** Both outstanding items (`test_tc304`/
`test_tc305` re-fixture, full-suite regression re-run) are complete, zero
unexpected regressions, and the real-track evidence confirms the fix
resolves the original physically-impossible-value defect this story exists
to catch.

---

DEF-201

Status: Open Reported by: james (report review) Linked test case: (none — coverage gap, see DEF-204) Triage: Code-level

Description: HF extension detection returns physically impossible values. Measured rolloff points: GusGus 1979 Hz, Leftfield 2208 Hz, Chemical Brothers 4954 Hz. Commercial releases do not roll off at 2 kHz — these tracks extend to 16-20 kHz.

The report's own data contradicts the result: GusGus measures -20.05 dB in the air band (10-24 kHz). A track genuinely cut at 1979 Hz would show roughly -60 dB or lower there. Meaningful energy at 10-24 kHz and a 2 kHz rolloff cannot both be true.

Suspected cause: hf_rolloff_threshold_db: 6.0. Music has a naturally declining spectrum (~-3 to -6 dB/octave). A 6 dB threshold is crossed in the low mids on almost any programme material, so the detector is finding normal spectral tilt rather than a codec or generation cutoff.

Expected behaviour: detect the near-vertical cliff a lossy encoder or generative model leaves behind — not a gentle slope. Either a much deeper threshold (-30 to -40 dB relative to the passband) or, better, slope-based cliff detection (dB/octave exceeding a steep threshold sustained across adjacent bins).

Why this matters: HF rolloff is the metric specifically added to catch the Suno generation problem. As implemented, a Suno track cutting at 15 kHz would be reported as better than four of the five references.


*--- Section 2: DEF-203 closed, DEF-204, DEF-205 schema, DEF-206 LUFS, DEF-207, DEF-208,*
*DEF-201 reopened/investigation/resolution, STORY-004 passes ---*

---

## DEF-203 -- CLOSED as not-a-defect (qa-automation-engineer, STORY-003 ground-truth pass)

**Status: Closed (not-a-defect).** The derivation below (already worked out
independently by software-architect in architecture.md Section 3, and
re-confirmed here by an independently-written and independently-run
ground-truth test against the CURRENT, unmodified shipped code) confirms the
shipped `-6.0206 dB` broadband floor and `-3.0103 dB` per-band floor were
already correct. No code change applied or required.

**Test**: `stories/STORY-001/implementation/tests/test_ground_truth_stereo_width.py::test_tc054_def203_monosum_floors_derived_from_first_principles`
(STORY-003 test-cases.md TC-054), run against the unmodified
`analysis/mono_sum.py`. **Result: PASSED on first run** (no fix applied,
none needed).

**Derivation (first principles, restated here per requirements.md's own
requirement that the full derivation -- not just a status change -- be
recorded in this entry)**: let L, R be zero-mean, equal-power
(`Var(L)=Var(R)=sigma^2`) stereo channels with correlation rho.
`mono_sum=(L+R)/2`, so `Var(mono_sum)=sigma^2*(1+rho)/2`.

- **Broadband `level_change_db`** uses BS.1770's channel-**SUMMED**
  convention (both `stereo_lufs` and `mono_lufs` come from
  `measure_integrated_lufs`, confirmed by reading `mono_sum.py` directly):
  `LUFS_stereo = -0.691 + 10*log10(2*sigma^2)`,
  `LUFS_mono = -0.691 + 10*log10(sigma^2*(1+rho)/2)`, so
  `level_change_db = 10*log10((1+rho)/4)`.
- **Per-band `delta_db`** uses the **per-channel-mean** band-power
  denominator (`power_channel_mean=(P_L+P_R)/2=sigma^2`), numerator
  `power_sum=Var(mono_sum)=sigma^2*(1+rho)/2`:
  `delta_db = 10*log10((1+rho)/2)`.

These are genuinely DIFFERENT formulas with genuinely different
denominators (channel-summed BS.1770 convention vs. channel-mean band
power) -- not two candidate answers to the same question, which is exactly
what DEF-203's original report did not distinguish. Worked table, all three
rho values:

| rho | `level_change_db` (broadband, `(1+rho)/4`) | `delta_db` (per-band, `(1+rho)/2`) |
|---|---|---|
| +1 (identical L=R) | `10*log10(0.5) = -3.0103 dB` | `10*log10(1.0) = 0.0000 dB` |
| 0 (uncorrelated, equal power) | `10*log10(0.25) = -6.0206 dB` | `10*log10(0.5) = -3.0103 dB` |
| -1 (inverted, L=-R) | `10*log10(0) = -inf` | `10*log10(0) = -inf` |

**Empirical confirmation, this pass, against the shipped code, three
synthetic fixtures with known-by-construction correlation**:

```
rho=+1 (to_stereo(pink_noise_mono(sr,5.0,seed=1))):
  level_change_db measured within 0.1 dB of -3.0103  -- PASS
  every band's delta_db measured within 1.0 dB of 0.0 -- PASS

rho=0 (independent_noise_stereo(sr,8.0,sigma=0.05,seed=1)):
  level_change_db measured within 0.1 dB of -6.0206  -- PASS
  every band's delta_db measured within 1.0 dB of -3.0103 -- PASS

rho=-1 (inverted_stereo(pink_noise_mono(sr,5.0,seed=1))):
  level_change_db == float("-inf") exactly -- PASS
```

**DEF-203's original report is wrong, quantified**: it states "-3.01 dB is
correct" without specifying which formula it means, and treats "-6.02 dB"
and "-3.01 dB" as competing answers to the SAME question. The derivation
above shows they are the correct rho=0 floor for two DIFFERENT fields
(broadband `excess_cancellation_db` vs. per-band `excess_delta_db`).
Separately, DEF-203's own measured evidence (level changes of -3.47 to
-4.03 dB across five references) is itself more consistent with the
-6.0206 dB broadband floor than with -3.0103, once correlation is
back-solved (`rho = 4*10^(level_change_db/10) - 1`): -3.47 dB -> rho~=0.80;
-4.03 dB -> rho~=0.58. Both land inside an ordinary, plausible
"moderately-high inter-channel correlation for center-heavy commercial
stereo mixes" range -- the "narrow spread across five references" DEF-203's
report flagged as suspicious is adequately explained by the reference
material's own consistent mix character, not a wrong constant.

**AC6 branch, applied as architecture.md Section 3.4 specifies**: this
derivation confirms the shipped constant was already correct, so there is
no fix, and therefore AC6's "write a failing test first" ordering
requirement does NOT apply to DEF-203 -- this is the deliberate, documented
exception architecture.md Section 3.4 and requirements.md's own DEF-203
section state explicitly, not a silent gap in this pass's process. (AC6/
AC11's failing-test-first sequence WAS followed for DEF-201 -- see that
entry above.)

**Ground-truth test is retained as the permanent derivation-of-record**
for this metric (`test_tc054_...`), per story.md's own core principle,
regardless of this closure.

---

DEF-203

Status: Open (ORIGINAL REPORT, closed above -- preserved for record per
this project's standing convention of never deleting a resolved entry)
Reported by: james (report review) Triage: Code-level

Description: Mono-sum "excess cancellation" reports 1.995-2.548 dB across all five references — a suspiciously narrow spread for five structurally different records. Near-identical results on a metric across dissimilar inputs usually indicates the calculation is being measured, not the audio.

Suspected cause: the -6.02 dB baseline in architecture.md Section 4.5 appears incorrect. Summing (L+R)/2 with uncorrelated, equal-power channels yields approximately -3.01 dB, not -6.02 dB. Measured level changes (-3.47 to -4.03 dB) sit close to -3.01, consistent with these tracks summing normally and the reported "excess" being an artifact of a wrong reference point.

Expected behaviour: re-derive the expected mono-sum floor from first principles, verify against synthetic signals with known correlation (rho = 1.0, 0.0, -1.0), and correct the baseline.

Note: DEF-101/DEF-104 apparently examined this area previously and closed on the current value. Re-examine rather than assuming the prior conclusion holds.

---

## DEF-204 -- CLOSED (qa-automation-engineer, STORY-003 ground-truth pass)

**Status: Closed.** Per requirements.md's own explicit out-of-scope note
("DEF-204 itself is closed by virtue of this story's completion... but that
closure should be recorded explicitly... once the suite lands, not
assumed") -- the ground-truth suite has now landed:
`stories/STORY-001/implementation/tests/test_ground_truth_loudness.py`,
`test_ground_truth_true_peak.py`, `test_ground_truth_hf_extension.py`,
`test_ground_truth_dynamic_range.py`, `test_ground_truth_spectral_balance.py`,
`test_ground_truth_stereo_width.py`, `test_ground_truth_sanity_assertions.py`,
`test_ground_truth_kweight_oversample.py` -- 74 test functions total (71
passed + 1 expected-fail (TC-024/DEF-201, by design) + 2 skipped placeholders
pending the DEF-201 fix landing on this baseline run), each with an
analytically-derived expected value stated inline (AC1/AC3), covering all 11
measurement functions plus `k_weight`/`oversample`. Full suite runtime
6.35s (`pytest -m ground_truth`), comfortably under AC12's 30s budget. This
is the concrete coverage-gap closure DEF-204 named -- the same class of
signal (pink noise vs. genuine cutoff, correlated vs. decorrelated stereo,
etc.) that let DEF-201/DEF-202/DEF-203 ship undetected now has a test that
would catch it, demonstrated directly by TC-024 catching DEF-201's own
defect class on this exact run (see DEF-201 entry above). Note DEF-202
(mastering stage not consuming reference measurements) is explicitly a
separate, still-open, architectural pipeline-wiring defect, NOT closed by
this suite -- requirements.md is explicit that DEF-204's closure must not be
read as implying DEF-202 is also closed.

---

DEF-204

Status: Closed (see above; original report preserved below for record)
Reported by: james (report review) Triage: Code-level (test coverage)

Description: DEF-201, DEF-202 and DEF-203 all passed the existing test suite. Three measurable defects — one producing physically impossible output — were not caught. This is a coverage failure, not a speed failure.

Root cause: tests appear to verify that functions execute and return plausibly-typed values, not that they return correct values against signals with known ground truth.

Expected behaviour: every measurement function must have at least one test against a synthetic signal whose correct answer is known by construction. See STORY-003 for the full ground-truth test approach.

---

## DEF-205 QA update (qa-automation-engineer, STORY-003 ground-truth pass)

**Status: still Open overall, but the automated-suite half is now Fixed.**
Per this entry's own instruction ("qa-automation-engineer update both stale
spots in `tests/test_ref_ac9_output.py`"): fixed both. The assertion
(`assert report.schema_version == "1.2"`, was `"1.1"`) and the module
docstring (updated to state the `"1.1"` -> `"1.2"` history, both bumps, and
point back to this entry) in
`stories/STORY-001/implementation/tests/test_ref_ac9_output.py`. Verified:
`pytest tests/test_ref_ac9_output.py tests/test_ref_ac10_verification_bars.py -q -m "not isolated"`
-> **19 passed, 1 skipped, 0 failed** (16.63s).

**Remaining open action, NOT done here (test-case-writer's territory per
this entry's own routing and this role's standing rule not to silently
patch test-cases.md)**: test-cases.md's own TC-292 (STORY-002 v2, line
~629) still states the stale `"1.1"` expected value and needs the same
`"1.1"` -> `"1.2"` correction. Leaving Status: **Open** (not Closed) until
that spec-side update lands, per the DEF-106/107/108 precedent of not
closing a documentation-routed entry until the routed party's half is also
done.

**Spec-side update, done (STORY-003 pipeline coordinator, this session)**:
test-case-writer's STORY-003 re-invocation confirmed the STORY-003
test-cases.md document itself already stated `"1.2"` everywhere (it was
authored after the bump), so the actual stale spot was STORY-002's own
`test-cases.md` TC-292 (line ~622), outside that agent's assigned scope for
its STORY-003-only revision pass. Corrected directly: TC-292's expected
value `"1.1"` -> `"1.2"`, with a v3 note explaining the bump traces to
STORY-003's AC13 `sanity_warnings` addition (DEF-205), preserving the prior
DEF-106 `"1.0"` -> `"1.1"` history inline rather than deleting it.

**Status: Closed.** Both halves (automated suite, test-cases.md) now agree
on `"1.2"`.

**STORY-004 re-occurrence (qa-automation-engineer, STORY-004 closure pass):**
STORY-004 bumped `SCHEMA_VERSION` from `"1.2"` to `"2.0"` (MAJOR bump: removes
`HfExtensionResult.rolloff_hz` and `MonoSumResult.excess_cancellation_db`).
TC-292 was stale again asserting `"1.2"`. Fixed directly: updated assertion to
`"2.0"`. Same class of fix as above; no new defect entry created.

Also resolved in this pass: TC-252 (`test_tc252_mp3_clean_cbr_reports_lossy_with_bitrate`)
and TC-254 (`test_tc254_format_label_renders_inline_per_track`) failed because
`mutagen==1.47.0` (declared in `pyproject.toml` dependencies) was not installed
in the environment. `bitrate_kbps` returns `None` from `_mutagen_bitrate_kbps`
when mutagen is absent (silent-fallback per resolved open question #9), so the
MP3 provenance bitrate field was always `None`. Fixed by installing mutagen.
Not a code defect — the production code handles the absent-dependency case
correctly; the environment was missing the declared dependency.

**Status: Still Closed.**

---

DEF-205 (documentation/test-spec, routed to test-case-writer, not
python-developer): `test_ref_ac9_output.py::test_tc292_schema_version_matches_current_shipped_value`
(and test-cases.md v2's TC-292) now assert a stale `schema_version == "1.1"`,
superseded by STORY-003's additive `sanity_warnings` schema change

Status: Open (found by python-developer, this pass; not fixed here -- same triage class as DEF-106/108, a test-spec staleness issue, not a production-code defect)

Reported by: python-developer (STORY-003 implementation pass).

Description: per STORY-003 architecture.md Section 4.4/AC13, adding `ReferenceMeasurements.sanity_warnings` (and `Measurements.sanity_warnings`) is an additive schema change, and `report/reference_builder.py::SCHEMA_VERSION` is correctly bumped from `"1.1"` to `"1.2"` as part of this same implementation pass (per the DEF-101 versioning precedent: MINOR bump for an additive field). `tests/test_ref_ac9_output.py::test_tc292_schema_version_matches_current_shipped_value` still asserts the pre-STORY-003 value:

```
assert report.schema_version == "1.1"
```

Ran narrowly (`pytest tests/test_ref_ac9_output.py tests/test_ref_ac10_verification_bars.py -q`) after making the STORY-003 sanity-assertion/schema changes: 18 passed, 1 skipped, **1 failed** -- exactly this test, with `AssertionError: assert '1.2' == '1.1'`. This is the expected, anticipated consequence of the schema bump the architecture explicitly calls for, not a regression introduced by an unrelated code change -- the same class of staleness DEF-106 already established a precedent for (test-cases.md/automated-test expected values lagging a schema-version bump made in the same pass that produced them).

test-cases.md (STORY-002 v2, TC-292, line ~629) also states the `"1.1"` expected value explicitly and needs the same correction.

Triage: documentation/test-spec, routed to test-case-writer -- not a code defect. `report/reference_builder.py::SCHEMA_VERSION = "1.2"` is correct and intentional (STORY-003 architecture.md Section 4.4). Recommend test-case-writer update TC-292's expected value to `"1.1"` -> `"1.2"` in test-cases.md, and qa-automation-engineer update **both** stale spots in `tests/test_ref_ac9_output.py`: the assertion at line 54 (`assert report.schema_version == "1.1"`) AND the module docstring at line 4 (`schema_version is "1.1" in the shipped code`), which states the same stale figure one line above the test and would otherwise be left inconsistent with a fixed assertion -- per the DEF-106 precedent (test-case-writer revises the spec; the automated suite is brought into line with it, not silently patched by whoever happens to notice the failure first).

Not fixed by python-developer in this pass: per this role's standing instruction not to write or modify executable test files (that is test-case-writer's/qa-automation-engineer's territory), and per this project's DEF-106/108 precedent of routing test-spec staleness rather than patching it directly.

---

## DEF-206 QA confirmation (qa-automation-engineer, STORY-003 ground-truth pass)

**Status: still Open, Architectural** (triage confirmed, not changed --
python-developer's own routing to software-architect is correct; this is
a genuine, undocumented-in-architecture.md ceiling-derivation gap, not a
code-level fix). Reproduction re-run independently this pass, confirmed
byte-for-byte against python-developer's reported numbers:

```
1000 Hz -> integrated_lufs=  -0.044  warnings=[]
2000 Hz -> integrated_lufs=   2.331  warnings=['integrated_lufs_range']
3000 Hz -> integrated_lufs=   3.067  warnings=['integrated_lufs_range']
4000 Hz -> integrated_lufs=   3.227  warnings=['integrated_lufs_range']
6000 Hz -> integrated_lufs=   3.287  warnings=['integrated_lufs_range']
8000 Hz -> integrated_lufs=   3.297  warnings=['integrated_lufs_range']
```

(dual-mono stereo sine, amplitude=0.999, 2s, 44.1kHz, through `measure_all()`
unmodified.) No further action taken -- left for software-architect to
choose between the three candidate resolutions python-developer's own entry
already lays out. Not re-triaged.

**Architect resolution (software-architect, STORY-003 v2 revision)**:
architecture.md Section 4.2 revised, choosing candidate resolution (a) from
this entry's own three options -- derive a real ceiling accounting for
K-weighting-shelf-boost + BS.1770 channel-sum stacking, rather than (b)
dropping the check entirely or (c) keeping the un-derived literal `0.0`
figure. The derivation (full detail in architecture.md Section 4.2) rests on
three verified facts: this codebase's own `_SUPPORTED_CHANNELS = {1, 2}`
ingest constraint (`io/ingest.py` line 24, `io/reference_ingest.py` line 31 --
no surround/LFE channel is ever reachable, so BS.1770's channel gain `G_i` is
always `1.0` and channel count never exceeds 2); a non-clipping signal's
maximum possible mean-square power (`1.0`, a full-scale square wave, not the
`0.999`-amplitude sine this entry's own reproduction used, which is why the
derived bound sits comfortably above this entry's own measured `+3.297 dB`
worst case); and K-weighting's total filter gain bounded across the entire
frequency response (not only the 2-8 kHz range this entry's own reproduction
tested), derived exactly against this codebase's own `k_weight`
implementation (`analysis/loudness_range.py`) -- the high-shelf stage's gain
reaches its asymptote `Vh` exactly at Nyquist (proven algebraically from the
shipped biquad coefficients, `H_shelf(-1) = Vh` exactly), and the RLB
high-pass stage, previously assumed unity-gain, was found this pass to carry
its own small excess gain at Nyquist (`a0_hp ~= 1.005437`, `~+0.047 dB` at
44.1 kHz, since its `b=[1,-2,1]` coefficients are unnormalized, matching
BS.1770's own published stage-2 constants) -- a genuine correction this
architecture pass made to a `+6.32 dB` figure that had been informally
floated for this bound (which used only the shelf's own `~+4.0 dB` and
omitted the high-pass stage's contribution). Combined:
`LUFS_max = -0.691 + 10*log10(2) + g_db + 20*log10(a0_hp) ~= +6.366 dB` at
44.1 kHz. **Shipped constant: `_LUFS_CEILING_DB = 6.5`** (padded above the
tightest computed bound, valid across this codebase's supported sample
rates, never tightened below the derived figure).

**Two gaps flagged, not resolved, by this derivation** (architecture.md
Section 4.2's own "concrete ask" callouts, also recorded in Section 10 risk
#8): (1) the derivation is performed against this codebase's own `k_weight`
reimplementation, not against pyloudnorm's actual internal filter, which is
literally what `measure_integrated_lufs`/this check's guarded quantity uses
-- a partial empirical cross-check this pass (predicting this entry's own
8 kHz/amplitude-0.999 case via the derived gain figures gives `~+3.35 dB`
against the actually-measured `+3.297 dB`, a `~0.05 dB` gap consistent with
the shelf not yet being at its Nyquist asymptote at 8 kHz) supports but does
not prove the two filters share the same bound; QA should confirm via
`scipy.signal.freqz` against `pyln.Meter._filters` or direct calibrated-tone
measurement near Nyquist before this is treated as certain to the same rigor
as the `-70` floor. (2) the "no overshoot between DC and Nyquist" property
both filter stages rely on is asserted from standard no-resonance
shelf/high-pass filter-design theory (`Q~=0.707`/`Vb~=Vh**0.5` for the
shelf, `Q~=0.5` for the high-pass), not numerically swept -- this
architecture pass cannot execute code; QA should confirm via `scipy.signal.freqz`
on a dense frequency grid.

**Status update: still Open, Architectural-Resolved (derivation and target
value now specified)** -- the concrete implementation change (replace the
literal `lufs > 0.0` comparison in `analysis/sanity.py::check_lufs_plausible`
with `lufs > _LUFS_CEILING_DB`, add the module-level constant and derivation
comment, both given in full in architecture.md Section 4.2) is now
python-developer's outstanding work, not completed by this architecture
update. Downstream note: any existing test asserting the old `0.0`-based
false-positive behavior as "known/expected" (as opposed to a test that will
now correctly pass once the ceiling is corrected) needs re-examination --
`test_tc304`/`test_tc305`-style re-fixturing for this check specifically
(e.g. `test_tc062`/any test built around this entry's own `+3.297 dB`
reproduction case, if one exists) is qa-automation-engineer's/
test-case-writer's task, not performed here.

**Fix notes (python-developer, this pass) -- Status: Fixed-Pending-Retest.**
Implemented `analysis/sanity.py::check_lufs_plausible` exactly as
architecture.md Section 4.2 now specifies:
- Replaced the module-level `_LUFS_CEILING = 0.0` constant with
  `_LUFS_CEILING_DB = 6.5`, and added the module-level derivation comment
  architecture.md Section 4.2 gives verbatim (the `_SUPPORTED_CHANNELS={1,2}`
  ingest-enforced channel bound, the full-scale-square-wave mean-square=1.0
  worst case, and the K-weighting total-filter-gain bound at Nyquist,
  combining to `LUFS_max ~= +6.366 dB` at 44.1 kHz, padded to `6.5` with
  margin and never tightened below the derived figure).
- Replaced the `lufs < _LUFS_ABSOLUTE_FLOOR or lufs > _LUFS_CEILING`
  comparison with `lufs < _LUFS_ABSOLUTE_FLOOR or lufs > _LUFS_CEILING_DB`,
  and updated the warning message to report the actual configured ceiling
  (`f"...outside (-70, {_LUFS_CEILING_DB}] and not -inf"`) rather than a
  hardcoded `0`, so the message stays correct if the constant is ever
  revised.
- Added the derivation-summary paragraph to `check_lufs_plausible`'s own
  docstring (the "`_LUFS_CEILING_DB`... is a genuine hard bound, not the
  story.md-literal '> 0.0' figure this check originally shipped with" text
  architecture.md Section 4.2 specifies), pointing back to this entry and
  architecture.md Section 4.2 for the full proof, not just restating the
  number.

**Verification performed this pass**:
1. Direct unit check: `check_lufs_plausible(6.3)` -> `None` (no warning;
   below the derived ceiling), `check_lufs_plausible(6.6)` -> `SanityWarning`
   (above it), `check_lufs_plausible(float("-inf"))` -> `None` (silence
   exemption unaffected), `check_lufs_plausible(-71.0)` -> `SanityWarning`
   (floor unaffected) -- confirms the floor logic is untouched and only the
   ceiling changed.
2. **Direct re-run of this entry's own false-positive reproduction**, byte-
   for-byte the same construction QA's confirmation used (dual-mono stereo
   sine, amplitude 0.999, 2s, 44.1kHz, through the shipped, otherwise-
   unmodified `measure_all()`): at 8 kHz, `integrated_lufs = 3.2969029...`
   (matches the previously-recorded `+3.297 dB` exactly),
   `sanity_warnings = []` -- **the false positive is gone**, confirming the
   fix resolves the exact case this defect was opened against, not merely a
   synthetic boundary value.
3. Ran `pytest tests/test_ground_truth_sanity_assertions.py -q -m "not
   isolated"` (narrow, targeted re-run per this role's standing instruction):
   **24 passed, 1 failed** -- the single failure,
   `test_tc061_check_lufs_plausible_boundaries[0.01-False]`, asserts the
   *old* `> 0.0` ceiling behavior (`0.01` expected to warn) and is exactly
   the "existing test asserting the old 0.0-based false-positive behavior as
   known/expected" case the architect's own status-update paragraph above
   flagged as needing re-examination. **This is the anticipated,
   architecture-documented consequence of the fix, not a regression** --
   left unmodified per this pass's explicit routing (tests/ is
   qa-automation-engineer's/test-case-writer's territory, not
   python-developer's, per this project's established test-ownership
   convention) and per the architect's own note above naming this exact
   test class as their outstanding work, not mine.

**Status: Fixed-Pending-Retest.** Implemented exactly as architecture.md
Section 4.2 specifies, verified against both the derived boundary values and
the original reproduction case. Not marking Fixed/Closed -- only QA closes a
defect, and `test_tc061`'s boundary-value re-fixture (plus the two open
verification items architecture.md Section 4.2 itself flags: confirming
pyloudnorm's actual internal K-weighting response shares this codebase's own
`k_weight` bound, and sweeping `scipy.signal.freqz` to confirm no
between-DC-and-Nyquist overshoot) remain outstanding QA work, not performed
in this pass.

**QA retest (qa-automation-engineer, this pass) -- Status: Closed.**
Completed all three items this entry's own "Fixed-Pending-Retest" note left
open, plus one additional end-to-end regression test.

1. **`test_tc061_check_lufs_plausible_boundaries` re-fixtured**
   (`stories/STORY-001/implementation/tests/test_ground_truth_sanity_assertions.py`):
   replaced the stale `(0.0, True)`/`(0.01, False)` rows (the old,
   un-derived literal ceiling) with `(_LUFS_CEILING_DB, True)`/
   `(_LUFS_CEILING_DB + 0.01, False)`, importing `_LUFS_CEILING_DB` directly
   from `analysis/sanity.py` rather than hardcoding `6.5` -- so the
   boundary test tracks the shipped constant automatically if it is ever
   re-padded, per this project's own "don't lock in a number, derive it"
   discipline. **Independently re-derived the bound before trusting
   python-developer's `6.5` figure** (not copied uncritically, per this
   pass's own instruction): `-0.691 + 10*log10(2) + 3.99984 +
   20*log10(1.005437) = -0.691 + 3.0103 + 3.99984 + 0.04712 ~= 6.366 dB` --
   matches architecture.md Section 4.2's own figure to the same precision,
   confirming no arithmetic slip in the fix notes. `_LUFS_CEILING_DB=6.5`
   sits ~0.13 dB above this bound, consistent with "padded, never tightened
   below the derived figure."
2. **The two open verification items architecture.md Section 4.2 itself
   flagged (not previously closed by anyone) -- both closed this pass**:
   - **No-overshoot-between-DC-and-Nyquist sweep** (`scipy.signal.freqz`,
     200,000-point grid, the shipped `_high_shelf_coeffs`/
     `_high_pass_coeffs` cascade, at 44100/48000/22050 Hz): confirms the
     combined filter's maximum gain anywhere in `[0, Nyquist]` occurs
     *exactly at* Nyquist itself, with zero overshoot before it, at all
     three sample rates tested (`overshoot-beyond-Nyquist=0.000000 dB` in
     every case) -- the "maximally-flat, no-resonance" shelf/high-pass
     design theory architecture.md's derivation relies on is now
     numerically confirmed, not merely asserted from filter-design theory.
   - **pyloudnorm's actual internal filter vs. this codebase's own
     `k_weight` reimplementation**: introspected `pyln.Meter(44100)
     ._filters` directly (for verification purposes only, not production
     code -- `loudness_range.py`'s own docstring correctly says not to rely
     on this as a production import) and ran the same `freqz` sweep against
     pyloudnorm's actual coefficients. Result: pyloudnorm's own combined
     filter response also shows **zero overshoot** (max gain occurs exactly
     at Nyquist, `4.00000 dB` there) and its peak gain is `4.00000 dB`,
     slightly *below* the shipped `k_weight`'s own `4.04694 dB` at 44.1kHz
     (max difference between the two responses across `[0, Nyquist]`:
     `0.107 dB`). This means pyloudnorm's actual worst-case LUFS bound is
     if anything *tighter* than the one this codebase's own `k_weight`
     derivation used -- the `_LUFS_CEILING_DB=6.5` figure is safe against
     the quantity actually measured (`measure_integrated_lufs` via
     pyloudnorm), not just against the codebase's own from-spec
     reimplementation. Both of architecture.md Section 4.2's flagged gaps
     are now closed with direct evidence, not merely "supports but does not
     prove."
3. **Empirical near-worst-case stress test** (not previously performed):
   full-scale (amplitude 0.999, genuinely non-clipping), dual-mono square
   waves -- closer to the theoretical worst case (mean-square=1.0) than
   DEF-206's own original sine-wave reproduction -- at five frequencies
   inside/near the K-weighting shelf plateau (6000/8000/10000/15000/20000
   Hz), through the shipped, unmodified `measure_all()`:
   ```
      6000 Hz square: integrated_lufs=6.2798  warnings=[]
      8000 Hz square: integrated_lufs=6.2830  warnings=[]
     10000 Hz square: integrated_lufs=6.2910  warnings=[]
     15000 Hz square: integrated_lufs=6.0794  warnings=[]
     20000 Hz square: integrated_lufs=6.2881  warnings=[]
   ```
   All five read comfortably below the `6.5` ceiling (max observed
   `6.291 dB`, ~0.21 dB of real margin against a near-worst-case
   construction) with zero false positives -- consistent with, and further
   corroborating, the derived `~6.366 dB` theoretical bound (pyloudnorm's
   own slightly-lower peak gain explains why the empirical worst case sits
   a little under the from-`k_weight`-derived figure).
4. **New end-to-end regression guard added**:
   `test_def206_regression_hot_dual_mono_sine_no_false_positive`
   (`test_ground_truth_sanity_assertions.py`) reproduces DEF-206's original
   reproduction case byte-for-byte (dual-mono sine, amplitude 0.999, 2s,
   44.1kHz, swept across the same six frequencies recorded in this entry's
   earlier confirmation) through the full `measure_all()` pipeline and
   asserts `sanity_warnings == []` at every frequency -- the permanent
   regression guard for this exact defect class, not just a boundary-value
   unit test on the pure function in isolation.
5. **Full ground-truth suite and full existing-regression-suite results**:
   same combined run recorded in the DEF-201 closure entry above (both
   fixes landed together) -- ground-truth suite: 73 passed, 3 skipped
   (unrelated DEF-201 placeholders), 0 failed, 5.87s; full regression suite:
   277 passed, 9 skipped, 2 deselected, 0 failed, 1325.37s -- zero
   regressions traceable to the LUFS-ceiling change.

**DEF-206: Status: Closed.** All three candidate-resolution open items
(the boundary-value test re-fixture, and both of architecture.md's own
flagged verification gaps) are now closed with direct empirical evidence,
not merely asserted; the original false-positive reproduction case is fixed
and permanently regression-guarded.

---

DEF-206 (Architectural): `check_lufs_plausible`'s `> 0.0` ceiling, implemented exactly as architecture.md Section 4.2 specifies, false-positives ("fail") on legitimate, non-clipping audio -- the ceiling has no derivation behind it, unlike the -70 floor

Status: Open (found by python-developer, this pass, during pre-handoff verification; implemented exactly as specified, not silently altered -- routed back per this role's standing instruction not to make an undocumented design call)

Reported by: python-developer (STORY-003 implementation pass).

Description: `analysis/sanity.py::check_lufs_plausible` is implemented verbatim against architecture.md Section 4.2's code and derivation: `-inf` is exempted (gated silence), any finite value `< -70.0` is a `fail` (with a rigorous, exact proof of why that floor cannot legitimately be crossed by a correctly-gated BS.1770 computation), and any finite value `> 0.0` is also a `fail`. **The `> 0.0` half of this rule has no derivation offered anywhere in architecture.md, requirements.md, or story.md** -- story.md states the figure ("LUFS above 0 ... -> fail") but requirements.md's own AC10 discussion of false-positive risk addresses only the `-inf`/silence exemption, not the ceiling.

Verified empirically this pass, against the shipped `measure_all()` (unmodified `loudness.py`/`stereo_phase.py`), a dual-mono (identical L=R) stereo sine at `amplitude=0.999` (i.e. genuinely non-clipping, sample values never exceed +-1.0), 44.1kHz, 2s, at several frequencies inside K-weighting's high-shelf boost region:

```
1000 Hz -> integrated_lufs = -0.044   (no warning -- correct, near BS.1770's own calibration-neutral point)
2000 Hz -> integrated_lufs = +2.331   (FAIL warning fires)
3000 Hz -> integrated_lufs = +3.067   (FAIL warning fires)
4000 Hz -> integrated_lufs = +3.227   (FAIL warning fires)
6000 Hz -> integrated_lufs = +3.287   (FAIL warning fires)
8000 Hz -> integrated_lufs = +3.297   (FAIL warning fires)
```

This is not a computation bug and not physically impossible: it is the correct, expected consequence of two real, already-documented properties of this codebase's own BS.1770 implementation stacking -- (1) K-weighting's high-shelf boost (~+4 dB in the 2-10 kHz region, per this same story's own §7.1/§7.7 derivation notes) and (2) BS.1770's channel-**summed** convention adding another ~+3.01 dB for genuinely dual-mono stereo (the same convention DEF-101's own derivation and STORY-001's existing `test_tc010b` already establish as correct, not a bug). A hot, narrow-band-content, dual/multi-channel-summed source sitting close to full scale is exactly the kind of real (if extreme) pre-master input this tool exists to measure and correct -- not a value "a correct implementation cannot produce," which is the standard the -70 floor's own derivation explicitly relies on and the ceiling does not have an equivalent for.

Concretely, what this means in production: any pre-master or reference-track measurement of hot, high-frequency-weighted, multi-channel-summed content will carry a spurious `[FAIL] integrated_lufs_range` annotation in the report even though nothing is wrong with the measurement or the audio -- degrading trust in the sanity-warning mechanism exactly the way a false positive on `suspected_transcode` or `cancellation` would (this project's own established false-positive-avoidance standard, e.g. DEF-101's core finding).

**Why this is routed to the architect, not resolved here**: architecture.md Section 4.2 states this exact `> 0.0` comparison as the specified implementation, with the -70 floor's derivation presented as if it justified the whole range check; it does not derive the ceiling separately, and this python-developer pass has implemented the check exactly as specified rather than narrowing/removing the ceiling unilaterally (which would be an undocumented product/design call this role is not authorized to make). Candidate resolutions for the architect to choose between, not decided here: (a) raise the ceiling to account for K-weighting-shelf-boost + channel-sum stacking (e.g. some data-derived headroom above 0.0, akin to how the -70 floor's own margin was derived from the gate arithmetic rather than picked arbitrarily), (b) drop the ceiling check entirely and rely on `clipping.py`'s existing, purpose-built sample-peak/inter-sample-peak detection to catch genuinely invalid (out-of-range) audio, since LUFS is not designed to be a peak/clipping detector, or (c) keep the literal `> 0.0` rule and accept the false-positive rate as a documented, known limitation (matching option (c) chosen for DEF-102's budget rather than optimizing further) -- explicitly not this implementer's call.

**Action taken this pass**: `check_lufs_plausible` ships exactly as architecture.md Section 4.2 specifies (no unilateral change to the `> 0.0` threshold or logic). This entry records the concrete, reproducible false-positive evidence for the architect's next pass. Not blocking STORY-003's own AC10/AC13 acceptance criteria (the check exists, runs in production code, never raises, and surfaces correctly in both renderers, all independently verified this pass) -- but it is a real, demonstrated false-positive risk that should not ship silently unacknowledged.

---

## DEF-207 (documentation/test-spec, routed to test-case-writer): three STORY-003 test-cases.md derivations contradict each other or their own stated preconditions, found while writing the ground-truth automation this document specifies

Status: Open (found by qa-automation-engineer, STORY-003 ground-truth automation pass; not fixed in test-cases.md here, per this role's standing instruction not to silently patch test-case-writer's document -- the automated suite itself asserts the corrected values directly, with inline docstrings pointing back to this entry, so the suite is not blocked on test-cases.md's own revision)

Reported by: qa-automation-engineer.

Description: while writing `stories/STORY-001/implementation/tests/test_ground_truth_loudness.py` and `test_ground_truth_kweight_oversample.py` directly against test-cases.md's own stated derivations, three internal-consistency problems were found (this is exactly the "cross-check results for internal consistency" discipline this role is required to apply, applied to the SPEC document itself, not only to measured output):

1. **TC-003/TC-004 contradict TC-001, in the same document.** TC-001's own derivation states: "1 kHz is BS.1770's calibration-neutral frequency -- the K-weighting high-shelf's gain at 1 kHz... combines with the standard's fixed -0.691 dB offset to net ~=0 dB total, so LUFS ~= input dBFS RMS directly." TC-003 and TC-004, in the SAME document, instead compute their expected values as `dbfs - 0.691` (e.g. TC-004: "-68 dBFS RMS... above the -70 LUFS absolute gate by ~=1.3 dB once the -0.691 dB offset is applied... Expected result: ... abs(lufs - (-68.69)) < 0.1"), treating the -0.691 dB offset as UNCANCELLED at 1 kHz -- directly contradicting TC-001's own stated reasoning one section earlier. Measured directly against the shipped `measure_integrated_lufs` (this pass), across seven RMS levels from -80 to -20 dBFS, all at 1 kHz: the net offset is a FIXED, level-independent `-0.0354 dB` (not `-0.691 dB`) at every level tested -- confirming TC-001's framing is the correct one and TC-003/TC-004's arithmetic is the error. The correct expected value for TC-004 (-68 dBFS RMS) is `~-68.04 LUFS`, not `-68.69 LUFS`; the correct absolute-gate boundary is `~-69.96 dBFS RMS`, not TC-004's implied `~-71.3 dBFS`. (TC-003's own -80 dBFS fixture is far enough below the gate either way that its "returns exactly -inf" conclusion is unaffected -- only the intermediate derivation number in TC-003's own prose is imprecise, not its pass/fail outcome.)

2. **TC-071's "1 kHz: ~=0dB" figure is for the wrong quantity.** TC-071 (`k_weight` ground-truth) states the K-WEIGHTING FILTER's own gain at 1 kHz should read "~=0 dB (+/-0.5 dB)". Measured directly this pass: `k_weight`'s own gain at 1 kHz (input/output RMS ratio, filter applied in isolation, no BS.1770 offset involved) is `~+0.70 dB`, not `~0 dB` -- outside TC-071's own stated 0.5 dB tolerance. This is the same class of error as item 1: "1 kHz is calibration-neutral" is a true statement about the COMBINED system (K-weighting filter gain + the separate -0.691 dB BS.1770 fixed offset applied later in the loudness formula), not about the K-weighting filter's gain in isolation. The two findings cross-check each other exactly: `0.691 - 0.0354 ~= 0.656 dB` (the K-weighting gain implied by item 1's finding) is consistent with `~0.70 dB` (item 2's direct filter-only measurement) to within ordinary measurement-method differences (short-fixture RMS ratio vs. full BS.1770 pipeline), not a separate, unrelated error.

3. **TC-023's own text states an internally-contradictory "current shipped config" value.** TC-023's "Analytically predicted outcome" paragraph opens with "against the current shipped config (`hf_rolloff_threshold_db=40.0`)" -- but this document's own Section 0 states explicitly, two pages earlier: "What is confirmed not yet done: `hf_rolloff_threshold_db` is still `6.0` (DEF-201 unfixed)." The two statements are mutually exclusive within the same document. (This did not block writing or running TC-023's automated test -- the automated test does not hardcode either value, it asserts against whatever `hf_rolloff_threshold_db` the config actually carries at run time, and was run against the real current value, 6.0, per DEF-201's own entry above -- but the prose itself needs reconciling for a future reader of test-cases.md alone.)

Where these were found and fixed for the purposes of the automated suite (test-cases.md itself NOT touched, per this role's routing convention): `stories/STORY-001/implementation/tests/test_ground_truth_loudness.py::test_tc004_just_above_absolute_gate_reads_finite_negative_control` and `test_tc003_below_absolute_gate_reads_exactly_minus_inf` (item 1); `test_ground_truth_kweight_oversample.py::test_tc071_k_weight_matches_bs1770_anchor_points` (item 2) -- each has an inline docstring stating the correction and the measured evidence, pointing back to this entry. Item 3 required no code correction (the automated test was already written value-agnostic).

Triage: documentation/test-spec, routed to test-case-writer -- not a code defect (measure_integrated_lufs's and k_weight's actual behavior is correct and self-consistent; this is entirely a test-cases.md derivation-arithmetic and internal-consistency issue, the same class as DEF-106/107/108). Recommend test-case-writer: (a) correct TC-003/TC-004's expected-value derivation to match TC-001's own stated reasoning (net offset ~=0 dB at 1 kHz, not -0.691 dB), (b) correct TC-071's 1 kHz expected figure from "~=0dB" to "~=+0.66 to +0.70 dB" (or reframe the whole point using the SAME frequency table already used elsewhere, to avoid re-deriving it a third time), and (c) reconcile TC-023's "current shipped config" sentence with the document's own Section 0 statement (simplest fix: drop the specific `hf_rolloff_threshold_db=40.0` parenthetical from that sentence, since the prediction that follows only needs to say "against whatever hf_rolloff_threshold_db the config carries at run time," which is what the automated test already asserts against).

**QA verification (qa-automation-engineer, this pass) -- Status: Closed.**
Read `stories/STORY-003/test-cases.md` in full this pass (v1.3, its
"Revision history" section item v1.3) and confirmed test-case-writer's own
half of this entry's routing is done, matching all three of this entry's
own asks exactly:
(a) TC-003's derivation now reads "≈-80.04 LUFS" (not the old -80.69) and
TC-004's expected value is now `-68.04` (not -68.69), with the corrected
"≈1.96 dB above the gate" figure and an explicit derivation paragraph --
matches item 1's fix exactly.
(b) TC-071's 1 kHz row is now framed as a derived cross-check bound,
`[0.5, 0.9] dB` (not "≈0 dB"), explicitly labelled as a bound rather than a
re-pinned ground-truth figure -- matches item 2's fix (a reframed band
rather than the single point figure this entry's own recommendation
suggested, which is an equally valid, arguably more honest, resolution
given the underlying number is itself derived, not independently
published).
(c) TC-023's "Analytically predicted outcome" paragraph no longer hardcodes
`hf_rolloff_threshold_db=40.0` -- it is now stated as "a function of
whatever `hf_rolloff_threshold_db` the config carries at run time," exactly
matching item 3's fix and the automated test's own (already-correct)
value-agnostic assertion.
The automated suite (`test_ground_truth_loudness.py::test_tc003_...`/
`test_tc004_...`, `test_ground_truth_kweight_oversample.py::test_tc071_...`)
already asserted the corrected values, confirmed still passing in this
pass's full ground-truth suite run (73 passed, 0 failed, see DEF-201/
DEF-206 closure entries above). Both halves (test-cases.md, automated
suite) now agree -- closing per the DEF-106/107/205 precedent of closing a
documentation-routed entry once the routed party's half lands.

---

## Minor finding, not filed as a defect: `measure_mono_sum` on a fully-silent (both-channels-zero) stereo buffer returns `NaN`, not a guarded value

Found while running `test_ground_truth_stereo_width.py::test_tc057_mono_sum_both_silent_degenerate_case_does_not_crash` (STORY-003 test-cases.md TC-057, which explicitly flagged this as an open question, not a pre-assumed pass/fail). Measured: `level_change_db=nan`, `excess_cancellation_db=nan` -- the function does NOT crash/raise (satisfying TC-057's actual pass condition), but the double `-inf - (-inf)` arithmetic (`mono_lufs=-inf`, `stereo_lufs=-inf`, `level_change_db = mono_lufs - stereo_lufs`) produces Python float `NaN` rather than a guarded sentinel. `analysis/sanity.py` has no check covering `MonoSumResult` fields (`check_lufs_plausible`/`check_correlation_range` only cover `Measurements`' own `integrated_lufs`/`stereo_phase.overall_correlation`), so this `NaN` would currently pass through to a report un-flagged if it ever occurred on a real (degenerate, fully-silent) reference/pre-master track. Not filed as a numbered defect because: (a) fully-silent stereo input is an extreme edge case unlikely on real material, (b) it does not crash the pipeline (the primary risk this story's AC10 hard rule cares about), and (c) this is a genuinely new scope item (a `check_mono_sum_plausible`-style function does not exist and was not specified by story.md/architecture.md) rather than a fix to something already specified -- recommend the architect consider it as a small, optional follow-up to AC10's sanity-check inventory if worth the additional surface area, not an oversight in the current implementation.

---

## DEF-208 (Code-level/test-spec, fixed): `test_ref_story001_nonregression.py::test_tc391_measurements_dataclass_shape_unchanged` asserted a stale `Measurements` field list, superseded by STORY-003's own additive `sanity_warnings` field

Status: Fixed (qa-automation-engineer, STORY-003 full-regression-suite pass, this session).

Reported by: qa-automation-engineer, found during the required-once full `test_ref_*.py`/STORY-001 `tests/` regression run after this pass's `analysis/sanity.py` wiring and new `test_ground_truth_*.py` files landed.

Description: `test_tc391_measurements_dataclass_shape_unchanged` (STORY-002's own non-regression guard, written to confirm architecture.md's "compose, don't extend" rule -- STORY-002 must not add fields directly to STORY-001's shared `Measurements` dataclass) asserted the field list was exactly STORY-001's original ten fields. STORY-003's architecture.md Section 4.4/AC13 explicitly and correctly adds an eleventh, additive field (`sanity_warnings`) directly to `Measurements` -- a DIFFERENT story's sanctioned addition, not a violation of the original STORY-002-scoped rule this test was written to guard. Running the full `test_ref_*.py` suite this pass surfaced exactly one failure:

```
FAILED tests/test_ref_story001_nonregression.py::test_tc391_measurements_dataclass_shape_unchanged
AssertionError: Left contains one more item: 'sanity_warnings'
```

This is the expected, anticipated consequence of STORY-003's own architecture-approved additive schema change, not a regression -- same class as DEF-106/DEF-205.

Triage: Code-level/test-spec (a stale test assertion in an executable test file, this role's own territory to fix directly, same as DEF-205's `test_ref_ac9_output.py` fix -- not a design question, since architecture.md Section 4.4 already explicitly authorizes this exact field addition).

Fix notes (qa-automation-engineer, this pass): updated `test_tc391_measurements_dataclass_shape_unchanged` in `stories/STORY-001/implementation/tests/test_ref_story001_nonregression.py` to assert the field list including `sanity_warnings` as the eleventh field, with an inline docstring explaining why this is still a correct "compose, don't extend" check (guards against STORY-002-specific additions, not against a later story's own explicitly-approved one) and pointing back to this entry.

Verification: the failure was caught by this pass's combined `test_ref_*.py` invocation (16 files, `-m "not isolated"`, includes `test_ref_story001_nonregression.py`): **90 passed, 2 skipped, 1 deselected, 1 failed** -- this test was the single failure in that run. The fix was then verified with a standalone re-run of the single file: `pytest tests/test_ref_story001_nonregression.py -q -m "not isolated"` -> **4 passed, 1 skipped, 0 failed**. Note precisely: this standalone re-run confirms the fix in isolation; it was NOT re-validated inside a second full combined `test_ref_*.py` run (that would have been a third full-suite invocation, outside this pass's run-budget discipline). Separately, this pass's STORY-001-file-tree invocation (`tests/` excluding all `test_ref_*.py` files and excluding `test_tc150`) explicitly `--ignore`'d this file, so its 184-passed count does not include this test at all -- the two counts are non-overlapping, not double confirmation.

---

## DEF-201 -- REOPENED (james, review of `Reference Tracks/reference_set_report.md` after the DEF-201/DEF-206 retest pass)

Status: **Open** (was: Closed). Reported by: james. Triage: Architectural (was: Code-level).

Description: the fix that closed DEF-201 (`hf_rolloff_threshold_db` 6.0 -> 20.0) changed the numbers but not the method. It is still detecting spectral tilt, not a cutoff.

Evidence it is still wrong:

1. All five reference tracks now report **UNSTABLE** across segments (previously two were stable, per the same pass's own report). A genuine cutoff -- a codec cliff or a generation band limit -- is a FIXED property of the file. It cannot vary segment to segment as the music changes. Universal instability is the signature of a detector tracking programme material.
2. **Leftfield - Melt reports 8170 Hz.** It is a 1995 CD master extending to roughly 20 kHz. No commercial CD master cuts at 8 kHz.
3. Threshold-based detection cannot work on music. Programme material has a naturally declining spectrum (~-3 to -6 dB/octave). ANY fixed dB threshold will be crossed somewhere in the upper mids on a dark record, regardless of where the real band limit is.

Required change -- replace threshold detection with slope-based cliff detection:

- Look for a sustained steep slope (24+ dB/octave, the value already in config as `transcode_suspect_slope_db_per_octave`) across adjacent spectral bins, followed by a floor. That is a filter. A gentle decline is not.
- If no cliff is found, report NO CUTOFF or Nyquist. Do not fall back to returning the point where some threshold was crossed.
- Reconsider whether stability checking is meaningful once detection is correct -- a real cutoff should be stable by definition, so instability after the fix likely indicates the detection is still wrong rather than that the file genuinely varies.

Write these tests FIRST and confirm each fails before changing the detector:

- Full-band pink noise, no cutoff -> must report NO CUTOFF. This is the critical negative control. A 20 dB threshold detector will falsely find a cutoff in pink noise. If this test already exists and passes, it is not wired to the function that produced these reference measurements -- investigate that as a separate finding.
- White noise brickwalled at 15 kHz -> ~15 kHz
- White noise brickwalled at 8 kHz -> ~8 kHz
- Pink noise brickwalled at 15 kHz -> ~15 kHz (declining spectrum AND a real cutoff -- must find the cutoff, not the tilt)

Process note: both DEF-201 and DEF-203 (below) were previously reported as resolved. Before closing either again, cross-check the output values for internal consistency and physical plausibility, not just for passing assertions -- specifically: does a reported HF cutoff contradict the measured air-band energy; is a result plausible for the material (a commercial CD master does not cut at 8 kHz); is the spread across dissimilar inputs suspiciously narrow. Also investigate why STORY-003's ground-truth tests did not catch this, and report that as a finding -- `test_tc024_pink_noise_no_cutoff` reportedly passes at the current threshold on synthetic pink noise, while real tracks with declining spectra are getting mid-band cutoffs from the same detector; both cannot be true unless the synthetic fixture doesn't exercise the same code path real reference tracks go through (candidate causes to check: `extract_active_audio` silence-gating changing what reaches the PSD on real material but not on continuous synthetic noise; the multi-segment split in `hf_stability_segment_count` giving real per-segment PSDs far fewer Welch averages than the synthetic single-segment case; `freq_reference_band_hz` anchoring the threshold to a band whose energy differs hugely between flat noise and a dark mix).

---

## DEF-203 -- REOPENED (james, review of `Reference Tracks/reference_set_report.md` after the DEF-201/DEF-206 retest pass)

Status: **Open** (was: Closed, not-a-defect). Reported by: james. Triage: Architectural.

Description: completely unchanged from the previous run -- same measured values (1.995-2.548 dB excess across all five tracks), same `mono_band_cancellation_excess_db: -3.0` in config, same -6.02 dB baseline referenced in architecture.md Section 4.5.

The -6.02 dB baseline is suspected wrong. Summing (L+R)/2 with uncorrelated, equal-power channels yields approximately -3.01 dB, not -6.02 dB. The measured level changes (-3.47 to -4.03 dB) sit close to -3.01, which is consistent with these tracks summing NORMALLY and the reported "excess" being an artifact of comparing against a wrong reference point.

Required:

- Re-derive the expected mono-sum floor from first principles. Show the derivation in architecture.md, do not just change the constant.
- Verify against synthetic stereo signals with known correlation: rho = 1.0 (identical channels), rho = 0.0 (uncorrelated), rho = -1.0 (inverted). Each has an analytically known expected mono-sum level change -- assert against those.
- Correct the baseline and re-run the reference set.
- DEF-101/DEF-104 previously examined this and closed on the current value; the STORY-003 pass re-examined it again and also closed not-a-defect. Re-examine from scratch a third time; do not assume either prior conclusion holds.

Existing evidence on file, for whoever re-examines this (pointer, not a pre-emptive closure -- this defect is reopened and the re-examination should reach its own conclusion): the STORY-003 architecture.md Section 3 derivation, cross-checked independently twice this project (once by the architect agent, once directly against the shipped `mono_sum.py`/`loudness.py` code by the pipeline coordinator), found `level_change_db = mono_lufs - stereo_lufs` where `stereo_lufs`/`mono_lufs` both come from `measure_integrated_lufs`, which implements BS.1770's channel-**summed** convention (`Loudness = -0.691 + 10*log10(sum_i G_i * z_i)`, G=1.0 per channel for L/R -- this is standard ITU-R BS.1770 behaviour, not specific to this codebase). Worked from that formula, the rho=0 floor for `level_change_db` is `10*log10((1+0)/4) = -6.0206 dB`, and this matched DEF-101's own empirical measurement (-6.0111 dB measured vs -6.0206 predicted) to ~0.01 dB. If re-examination confirms this derivation, the open question is NOT the constant but the metric itself: `excess_cancellation_db = level_change_db - (-6.0206)` runs +3.01 at rho=1 (best case, perfect mono compatibility) down to -infinity at rho=-1 (full cancellation) -- i.e. a HIGHER value means BETTER mono compatibility, opposite to what "excess cancellation" sounds like it means, and opposite to the per-band `excess_delta_db` sign convention (where more-negative flags cancellation). Under that reading, +1.995 to +2.548 dB would indicate healthy, better-than-worst-case sums, not a problem -- which would mean this is the same correct number being reported as a bug for the third time (DEF-101, DEF-104, DEF-203) because of a confusing name/sign convention, not a wrong constant. This is a pointer to investigate, not an instruction to close the defect on that basis -- re-derive independently per the instructions above and reach your own conclusion, including on whether the metric's naming/sign convention itself is the actual defect here.

---

## DEF-201 wiring-gap investigation (qa-automation-engineer)

**Status: investigation only -- DEF-201 remains Open (Architectural), not
closed or re-triaged by this entry.** Scope, per the task this entry
answers: trace precisely why
`test_ground_truth_hf_extension.py::test_tc024_pink_noise_no_cutoff`
passes against synthetic pink noise at `hf_rolloff_threshold_db=20.0`
while `measure_hf_extension()` reports an implausible 8170 Hz cutoff on
the real Leftfield track under the same config, and report which of the
three candidate hypotheses in the REOPENED report explains the gap. No
production code (`hf_extension.py`, `config.py`, or any other file under
`suno_mastering/`) was modified for this investigation -- all diagnostics
were produced by a standalone script that imports and calls the shipped,
unmodified functions directly (`_psd.compute_psd`, `_psd.band_mean_density`,
`silence.extract_active_audio`, `hf_extension._segment_rolloff_hz`,
`hf_extension.measure_hf_extension`), never by editing source.

**Zeroth finding, checked first and important framing for everything
below: there is no separate/duplicate code path.** Read
`reference_analysis/pipeline.py::analyze_track()` line 85:
`hf_ext = hf_extension_mod.measure_hf_extension(audio, sr, config)` -- this
is the literal, single `measure_hf_extension` function in
`analysis/hf_extension.py`, imported once (`from ..analysis import
hf_extension as hf_extension_mod`), the exact same function
`test_tc024_pink_noise_no_cutoff` imports and calls
(`from suno_mastering.analysis.hf_extension import measure_hf_extension`).
Both call sites also construct their config the same way: the real pipeline
uses a `ReferenceAnalysisConfig()` (defaults, no override needed since
Leftfield's 313.8s duration exceeds `hf_min_duration_s=30.0` on its own);
`test_tc024` uses `ref_config(hf_min_duration_s=2.0)` i.e.
`dataclasses.replace(ReferenceAnalysisConfig(), hf_min_duration_s=2.0)` --
same class, same defaults, only the one duration field overridden (and that
override only affects which branch is taken for a 3s vs 313.8s buffer, not
the scan logic itself once the real-scan branch is reached in both cases).
**"Wiring gap" is therefore not a code-routing bug** (the real pipeline is
not silently calling a stale copy, a different function, or skipping a step
the test exercises) -- the gap is entirely in what statistical properties
the two inputs (3s of stationary synthetic pink noise vs. 313.8s of real,
dynamically-varying music) have, and in how `measure_hf_extension`'s
segment-relative threshold logic responds to that difference. Confirmed by
running the actual shipped `measure_hf_extension()` end-to-end against both
inputs in the same script/session (numbers below) -- not inferred.

**Reproduction (script:
`C:\Users\james\AppData\Local\Temp\claude\C--Users-james-Documents-suno-mastering\bde517b1-446d-41f4-ae0d-d11fb1420701\scratchpad\def201_wiring_investigation.py`,
run via the project's own `venv` at `C:\Users\james\Documents\suno-mastering\venv`,
`ReferenceAnalysisConfig()` defaults,
`hf_rolloff_threshold_db=20.0`, `hf_stability_segment_count=5`,
`freq_reference_band_hz=(500.0, 2000.0)`, `silence_gate_threshold_db=-60.0`)**:

```
TC024-style synthetic pink noise (3.00s @ 44100Hz):
  active audio after silence-gating: 123480 samples (2.80s, 93.3% of raw)
  n_segments=5, seg_len=24696 samples (0.56s/segment)
  welch nperseg/segment = 16384, ~2 Welch windows averaged per segment
  per-segment reference-band (500-2000Hz) density_db: -73.81, -73.48, -73.46, -73.83, -73.65
    (spread across 5 segments: 0.37 dB)
  per-segment rolloff_hz: 22047.3, 22047.3, 22047.3, 22047.3, 22050.0
  measure_hf_extension(): rolloff_hz=22047.3, stable=True   -- TC024 PASSES (>=19845 Hz required)

Real track: Leftfield - Melt Audio.wav (313.83s @ 48000Hz, default config):
  active audio after silence-gating: 14745600 samples (307.20s, 97.9% of raw)
  n_segments=5, seg_len=2949120 samples (61.44s/segment)
  welch nperseg/segment = 65536, ~89 Welch windows averaged per segment
  per-segment reference-band (500-2000Hz) density_db: -62.73, -55.70, -55.96, -58.39, -54.51
    (spread across 5 segments: 8.22 dB)
  per-segment rolloff_hz: 14291.7, 8170.2, 8143.1, 8997.1, 5131.3
  measure_hf_extension(): rolloff_hz=8170.2 (median), stable=False (spread=9160.4 Hz)
    -- reproduces the exact 8170 Hz figure in reference_set_report.md
```

**Hypothesis 1 (`extract_active_audio` silence-gating) -- checked,
NOT the driver.** Both cases show the silence gate removing only a small,
comparable fraction of audio: 93.3% of the synthetic clip survives (and
that loss is entirely the block-truncation remainder, `usable = audio[:
n_blocks*block_len]` -- every one of the 7 blocks was already above
-60dB, so the RMS gate itself removed nothing from the synthetic fixture);
97.9% of Leftfield survives (98.0% of blocks pass the RMS gate; the ~2%
removed is consistent with digital silence at the file's very start/end --
`block_rms_db` minimum measured at exactly -240.0 dB, the function's own
`max(rms, 1e-12)` floor, i.e. true digital-zero blocks, not quiet passages
mid-track). Silence-gating changes what reaches the PSD by a similar, small
amount in both cases and is not differential in a way that explains the
9160 Hz vs. 2.7 Hz spread difference.

**Hypothesis 2 (segmentation reduces Welch averages on real material) --
checked, REFUTED, and refuted in the OPPOSITE direction from what the
hypothesis predicted.** `_psd.welch_nperseg()` caps at 65536 samples and
floors at 1024; because a real track's active audio (307s / 5 =
61.44s/segment) is vastly longer than the synthetic fixture's active audio
(2.80s / 5 = 0.56s/segment), each real segment hits the 65536-sample cap
and gets roughly **89 averaged Welch windows**, while each synthetic
segment (24696 samples, well under the cap) gets only **~2 averaged Welch
windows** per segment. The real per-segment PSD estimates are therefore
*more* statistically averaged/smoother than the synthetic ones, not less --
this hypothesis, as stated in the REOPENED report (real segments getting
"far fewer Welch averages... much noisier per-segment spectral estimates"),
does not hold; if anything the direction is reversed. This does not mean
segmentation is irrelevant (see Hypothesis 3) -- only that "fewer Welch
averages -> noisier estimate" is not the mechanism.

**Hypothesis 3 (`freq_reference_band_hz` anchoring) -- CONFIRMED as the
dominant mechanical driver of the segment-to-segment INSTABILITY
specifically, with a direct empirical isolation.** `_segment_rolloff_hz()`
recomputes its own reference-band (500-2000Hz) mean density **independently
per segment** (`ref_density = _psd.band_mean_density(freqs, psd,
config.freq_reference_band_hz)`, called fresh inside the per-segment loop,
not once for the whole track) and derives that segment's absolute
`threshold_level_db` from it. On stationary synthetic pink noise, this is
harmless: the 500-2000Hz density is time-invariant by construction (1/f
shaping applied once to the whole 3s buffer), so all 5 segments' local
reference anchors agree to within 0.37 dB and the reported rolloff is
identical across segments (a 2.7 Hz spread). On real, dynamically-arranged
music, the 500-2000Hz band's energy genuinely changes between different
61-second stretches of the song -- measured 8.22 dB of spread in Leftfield's
own per-segment reference-band density, a 23x larger swing than the
synthetic fixture's 0.37 dB. Because each segment's threshold floats with
its own local reference-band loudness, the reported "crossing frequency"
swings with programme dynamics rather than with any fixed property of the
file.

**Refinement, checked directly rather than assumed**: `band_mean_density`
is an *absolute* density, so it moves with a segment's overall broadband
level, not only with its spectral *balance* -- the 8.22 dB reference-band
spread could in principle be mostly a level artifact (e.g. one segment
happening to land on a quiet intro) rather than genuine EQ/arrangement
variation. Checked directly (script
`C:\Users\james\AppData\Local\Temp\claude\C--Users-james-Documents-suno-mastering\bde517b1-446d-41f4-ae0d-d11fb1420701\scratchpad\def201_probe_level.py`): per-segment broadband RMS on
Leftfield is `[-22.86, -17.63, -15.97, -17.03, -17.56]` dBFS (segment 0,
which contains the file's leading near-silence per the block-RMS trace
below, is 5-7 dB quieter than segments 1-4) -- broadband RMS spread 6.88 dB.
Normalizing the reference-band density by each segment's own broadband RMS
(`ref_density_db - rms_db`, a level-invariant balance measure) still leaves
a 4.41 dB spread across segments (down from 8.22 dB unnormalized). **So
roughly half of the measured reference-band swing is a level artifact
(segment 0's quieter intro passage) and roughly half is genuine
spectral-balance variation independent of level** -- both components feed
Hypothesis 3's per-segment re-anchoring mechanism identically (the code
does not distinguish level-driven from balance-driven density changes), so
this refines but does not change the conclusion: level changes across a
real track's structure are exactly the kind of ordinary, expected variation
(a quiet intro is not a defect) that a per-segment-reanchored absolute
threshold has no way to be robust against, which is itself an argument for
a level/tilt-invariant (slope-shape-based) detector rather than a fix that
merely tries to hold the reference anchor's absolute value more stable.

**Threshold-sensitivity quantification (Hz reported per dB of reference
anchor shift), the direct, affirmative evidence that this is a shelf/tilt
being measured and not a cliff**: comparing each segment's own-local-anchor
rolloff (shipped behavior) against its fixed-global-anchor rolloff (the H3
isolation experiment above) gives the local, empirical slope of "reported
rolloff_hz" as a function of anchor level near the ~8kHz crossing region:
segment 0 moved 14291.7 Hz -> 8143.1 Hz (-6148.6 Hz) for a 6.07 dB anchor
shift, ~1013 Hz per dB; segment 4 moved 5131.3 Hz -> 8142.3 Hz (+3011.0 Hz)
for a 2.15 dB anchor shift, ~1401 Hz per dB. **A reported "cutoff" that
moves roughly 1000-1400 Hz for every 1 dB the reference anchor moves is not
a cliff -- it is the scan finding the point where a shallow, continuously
declining shelf happens to cross whatever absolute threshold line it is
given.** This is the direct, quantitative contrast with `test_tc020`/
`test_tc021`'s own fixture design and docstring claim (`brickwall_lowpass_noise_mono`,
`ref_helpers.py`: "the detector's reported rolloff coincides with cutoff_hz
REGARDLESS OF WHICH dB THRESHOLD `hf_rolloff_threshold_db` uses... A finite-
slope filter's threshold-crossing frequency moves when the threshold moves;
a true brickwall's does not"): a genuine brickwall/codec cliff is, by
construction, threshold-depth-independent (the DEF-201 threshold-sweep
table in the entry above confirms TC-020/021 move by only a handful of Hz
across the entire 6-40 dB sweep); Leftfield's ~8kHz reading moves by
thousands of Hz for single-digit dB anchor perturbations -- direct,
affirmative evidence there is no cliff at 8kHz on this track, not just an
absence of evidence for one.

**Isolation experiment (script:
`C:\Users\james\AppData\Local\Temp\claude\C--Users-james-Documents-suno-mastering\bde517b1-446d-41f4-ae0d-d11fb1420701\scratchpad\def201_probe_h3.py`)**: re-ran the identical
per-segment scan against Leftfield, but pinned the reference density to a
single value computed ONCE from the whole 307.2s active-audio track
(global anchor: -56.67 dB, `threshold_level_db=-76.67 dB`), instead of
recomputing it per segment:

```
segment 0: local_ref_density_db=-62.73 (global delta -6.07 dB), rolloff_hz(FIXED global anchor)=8143.1
segment 1: local_ref_density_db=-55.70 (global delta +0.97 dB), rolloff_hz(FIXED global anchor)=8216.3
segment 2: local_ref_density_db=-55.96 (global delta +0.70 dB), rolloff_hz(FIXED global anchor)=8170.2
segment 3: local_ref_density_db=-58.39 (global delta -1.72 dB), rolloff_hz(FIXED global anchor)=8848.4
segment 4: local_ref_density_db=-54.51 (global delta +2.15 dB), rolloff_hz(FIXED global anchor)=8142.3

spread with FIXED global anchor: 706.1 Hz  (vs. 9160.4 Hz with the shipped PER-SEGMENT re-anchoring)
median with FIXED global anchor: 8170.2 Hz  (IDENTICAL to the shipped per-segment-anchored median)
```

Pinning the anchor collapses the spread from 9160.4 Hz to 706.1 Hz -- well
inside `hf_stability_tolerance_hz=2000.0` -- confirming per-segment
re-anchoring (Hypothesis 3) is the concrete, isolable mechanical cause of
the reported instability (finding #1 in the REOPENED report: "all five
reference tracks now report UNSTABLE").

**Critical second half of this finding, and the reason this is NOT simply
"fix the anchor and DEF-201 is done": the median rolloff under the FIXED,
stable anchor is STILL 8170.2 Hz** -- numerically identical to the shipped
per-segment-anchored result. Removing the instability does not remove the
implausible absolute number. This directly confirms the REOPENED report's
central claim (finding #2/#3: "Leftfield reports 8170 Hz... no commercial
CD master cuts at 8kHz... ANY fixed dB threshold will be crossed somewhere
in the upper mids on a dark record, regardless of where the real band limit
is") on its own terms, independent of the instability question: the
detection METHOD -- a fixed relative-dB threshold-crossing scan against a
naturally-declining real-music spectrum -- reports a physically implausible
mid-band "cutoff" on Leftfield **even when the reference anchor is held
perfectly stable**. Instability (Hypothesis 3's mechanism) and the wrong
absolute number (the threshold-vs-tilt confound) are two independently
reproducible symptoms of the same underlying design flaw, not two separate
bugs -- a narrow fix that only stabilizes the reference anchor (e.g.
computing it once per track instead of once per segment) would make
`stable=True` but would NOT fix the reported cutoff frequency, and should
not be mistaken for a fix of DEF-201 itself. This is consistent with (and
independently confirms, from the mechanical/code level rather than from
report-level cross-checking) the REOPENED report's own required-change
direction: replace threshold-crossing with slope-based cliff detection,
not patch the anchor.

**Why the ground-truth suite didn't catch this -- direct answer to the
task's question.** `test_tc024_pink_noise_no_cutoff`'s fixture
(`pink_noise_mono`, `ref_helpers.py`) is a single, stationary 1/f-shaped
noise realization applied uniformly across its whole 3s duration -- it has
no time-varying loudness or spectral-balance envelope at all. This is
exactly the property that makes Hypothesis 3's mechanism invisible: with a
stationary source, "recompute the reference anchor per segment" and
"compute the reference anchor once for the whole signal" are numerically
equivalent (confirmed above: 0.37 dB spread, i.e. effectively the same
value every time), so the test cannot expose the anchor's segment-to-segment
sensitivity, and pink noise's gentle -3dB/octave tilt also happens not to
cross a 20dB-relative threshold until near Nyquist, so the test also cannot
expose the threshold-vs-tilt confound on this particular fixture's tilt
depth. Both of DEF-201's reopened symptoms require a fixture with (a) a
realistic, declining-but-not-infinite spectral tilt AND (b) genuine
segment-to-segment variation in the reference-band's energy (i.e.
non-stationary dynamics, the way a real mix's arrangement changes over
time) to be exposed at all -- **no fixture in
`test_ground_truth_hf_extension.py` currently has both properties
together**: TC-024 (pink noise) has (a) but not (b) [stationary];
TC-025 (`brickwall_lowpass_noise_with_drift`) has a form of (b) but as a
genuine, instantaneous real-cutoff-frequency change (15kHz->8kHz), not a
declining-spectrum loudness-envelope change with NO real cutoff at all, so
it does not test the specific "false instability on dark, dynamic, but
cutoff-free material" failure mode either. This is a genuine coverage gap
in test-cases.md's HF-extension suite (TC-020 through TC-029), not a
wiring/routing defect and not something this pass fixes, per the task's
explicit instruction -- **flagged here for test-case-writer**: a fixture
combining (a) and (b) (e.g. a multi-segment concatenation of differently-EQ'd
pink/brown noise stretches, all sharing the same near-Nyquist true absence
of any real cutoff, but with deliberately different per-segment 500-2000Hz
energy, similar in spirit to `mono_low_decorrelated_high_stereo`'s
crossover-based construction pattern already used elsewhere in
`ref_helpers.py`) is the missing ground-truth negative control that would
have caught both reopened symptoms before they reached the real reference
set.

**A second, separate coverage gap, also worth flagging for test-case-writer
while it was noticed during this investigation**: every fixture in
`test_ground_truth_hf_extension.py` is built at `SR = 44100` (the file's own
module constant), but all five real reference tracks are 48000 Hz
(confirmed: `reference_set_report.md` lists Leftfield, and every other
track, as `48000 Hz`). This is not itself shown to be the cause of the
8170 Hz finding above (the mechanism was isolated directly against the
real 48kHz file, and Hypothesis 3's anchor-instability/threshold-tilt
mechanism reproduces identically in principle at either rate), but it is a
real, concrete regime the ground-truth suite never exercises: Nyquist
differs (24000 Hz vs. 22050 Hz, so the `air` band's open upper edge and the
`0.9 * Nyquist` pass bound in TC-022/TC-024 both shift), and
`_psd.welch_nperseg()`'s 65536-sample cap is reached at a different
wall-clock duration per segment at 48kHz vs. 44.1kHz, changing the
Hz-per-bin resolution and therefore the fixed-`kernel_size=5` `medfilt`
smoothing's *effective bandwidth in Hz* (a 5-bin median filter smooths a
wider or narrower Hz window depending on bin spacing, which is sample-rate-
and segment-length-dependent) between the two paths -- a concrete numeric
difference in the two code paths' operating regime that no fixture in this
suite currently exercises at all, worth a dedicated 48kHz ground-truth
fixture in the same test-case-writer pass that adds the tilt+non-stationary
negative control above.

**Summary answer to the task's three-hypothesis ranking**: Hypothesis 3
(reference-band anchoring) is confirmed as the mechanical cause of the
reported *instability*; Hypothesis 2 (segmentation reducing Welch averages)
is refuted, and refuted in the opposite direction from predicted (real
segments get ~89 Welch windows vs. synthetic's ~2); Hypothesis 1 (silence
gating) is checked and found to have a small, symmetric, non-differential
effect that does not explain the gap. Separately, and more importantly for
the architect's redesign: even with Hypothesis 3's instability mechanism
fully isolated and neutralized (fixed anchor), the reported cutoff on
Leftfield does not change (8170.2 Hz either way) -- confirming the REOPENED
report's diagnosis that this is a detection-method defect (threshold-crossing
vs. real spectral tilt), not merely an anchor-stability defect, and that the
architect's planned slope-based cliff-detection redesign is the right target
for the fix, not a narrower anchor-computation patch.

**Not yet done / left for the redesign and next retest pass (explicitly out
of scope for this investigation, per the task)**: no production code was
changed; `hf_extension.py`'s detection method itself was not modified;
`test-cases.md`'s coverage gap (no fixture combining declining tilt with
non-stationary per-segment loudness) was not fixed, only flagged above for
test-case-writer; DEF-201 remains **Open (Architectural)**, unchanged by
this entry.

---

> **Recovery note (pipeline coordinator, 2026-08-03).** A `software-architect`
> agent's Write accidentally overwrote this file with a placeholder, destroying the
> DEF-101..DEF-208 history above (and the DEF-201/DEF-203 REOPENED entries and the
> QA wiring-gap investigation). That history has been restored **verbatim** from the
> same agent's own pre-overwrite read of this file (recovered from its task
> transcript). Two separator lines between the DEF-203 REOPENED entry and the
> wiring-gap entry were reconstructed to match this file's formatting. The two
> architect **v3 resolution** entries that follow are the only content that write
> intended to add, preserved exactly as written.

## DEF-201 -- Architect resolution (software-architect, v3 pass), addressing the reopened defect

**Status: Architectural-Resolved (redesign specified; not yet
implemented).** Full design lives in `stories/STORY-003/architecture.md`
§2.8-§2.13 (v3 revision) -- not restated in full here, per this project's
pointer convention.

**Summary of what changed and why**: the v2 fix (`hf_rolloff_threshold_db`
6.0→20.0) changed the numeric target but not the detection method, and
remained a threshold-crossing scan -- structurally unable to distinguish a
real filter cliff from a naturally declining spectrum crossing an absolute
line, at any threshold depth. This was confirmed decisively by
qa-automation-engineer's own wiring-gap investigation (see that entry,
above/preceding in this file): pinning Leftfield's per-segment reference
anchor to a single whole-track value collapsed the reported instability
(spread 9160.4 Hz → 706.1 Hz) but left the reported rolloff figure
unchanged at 8170.2 Hz, and the empirical sensitivity (~1000-1400 Hz of
reported "rolloff" per 1 dB of anchor perturbation) is the direct,
quantitative signature of a tilt crossing a threshold, not a cliff.

**Resolution**: replaced threshold-crossing with a two-stage detector.
Stage 1 (`_cliff_exists`) is an existence gate requiring, on the WHOLE
(silence-gated) active-audio PSD: (a) a passband precondition (the
candidate window must start within `hf_cliff_passband_max_deviation_db`
= 6.0 dB of the reference-band level -- this is what prevents an
already-declined-region window from being mistaken for a cliff, the exact
failure mode a naive slope+floor check without this precondition would
still reproduce on Leftfield); (b) a sustained slope ≥
`hf_cliff_slope_db_per_octave` = 24.0 dB/octave (renamed from
`transcode_suspect_slope_db_per_octave`, same value, promoted from
secondary corroborator to primary mechanism, per this defect's own
explicit suggestion) across a `hf_cliff_min_span_octaves` = 1/3-octave
window (8 dB minimum total drop); (c) a floor -- ≥
`hf_cliff_floor_min_fraction` = 0.8 of the remaining spectrum at/below
`ref_density_db - hf_rolloff_threshold_db` (20.0, reused, role changed
from primary threshold to floor depth). Stage 2 reuses the existing,
already-validated scan-down localization logic, now gated behind Stage
1's confirmation rather than run unconditionally.

**Structural fix for the "detector tracks programme material" finding**:
the primary existence/localization decision is now made ONCE on the
whole-track PSD (matching the precedent `_transcode_slope_check` already
set for exactly this reason), not per-segment. Per-segment analysis is
retained but repurposed as drift/stability corroboration only, using the
SAME Stage 1+2 test per segment -- `stable` is redefined as agreement
between per-segment INDEPENDENT cliff confirmations and the whole-track
result, not the spread of raw per-segment threshold crossings.

**Return-contract change**: `HfExtensionResult` gains `cutoff_detected:
bool` and `per_segment_cutoff_detected: List[bool]`. `rolloff_hz` is now
always concrete once `insufficient_duration=False`: the localized cliff
frequency when `cutoff_detected=True`, Nyquist when `cutoff_detected=False`
("no cutoff", not a mid-band value). Schema bump combined with DEF-203's
own change into a single `SCHEMA_VERSION` bump, `"1.2"`→`"1.3"`.

**Not yet done (python-developer's outstanding work, per architecture.md
§12's downstream-impact list)**: implement `_cliff_exists`/
`_probe_band_levels_db`/`_localize_crossing_hz`/`_segment_result`/
`_compute_stability` in `analysis/hf_extension.py`; restructure
`measure_hf_extension`; delete `_transcode_slope_check`; rename the config
field and add the four new config fields in `reference_analysis/config.py`;
update `report/reference_builder.py::config_summary()`'s renamed key.

**Not yet done (qa-automation-engineer's/test-case-writer's outstanding
work)**: this architecture pass's predictions (TC-020/021/023/024/025's
expected pass/fail outcomes, TC-020's `stable is True`) are reasoned but
NOT confirmed by execution -- architecture.md §2.13 lists each prediction
explicitly and requires empirical confirmation, not assumption, before
DEF-201 is closed a second time. The real five-track set must be re-run
and `rolloff_hz`/`cutoff_detected`/`stable`/`suspected_transcode` recorded
per track (Leftfield is *expected* to report `cutoff_detected=False`;
GusGus's outcome is genuinely unknown, not predicted). Test-case-writer
should also pick up the two coverage gaps QA's wiring-gap investigation
flagged: (1) no existing fixture combines a realistic declining tilt with
genuine per-segment non-stationarity (the negative control that would have
caught both reopened symptoms before they reached the real reference set);
(2) no HF-extension ground-truth fixture runs at 48000 Hz, the real
reference tracks' actual sample rate.

**Status: still Open, Architectural-Resolved** -- design specified, not
yet implemented or verified. Do not mark Fixed/Closed until the
implementation lands and the empirical predictions above are confirmed
against both the ground-truth suite and the real five-track set, per this
project's standing "only QA closes a defect" rule.

---

## DEF-203 -- Architect resolution (software-architect, v3 pass), addressing the reopened defect

**Status: Architectural-Resolved (metric-semantics fix specified; not yet
implemented). The underlying `-6.0206 dB`/`-3.0103 dB` constants are
CONFIRMED CORRECT for a third time -- this was never the actual defect.**
Full derivation and fix design in `stories/STORY-003/architecture.md`
§3.5-§3.6 (v3 revision).

**Independent re-derivation (§3.5), generalized beyond the prior
equal-channel-power derivation**: letting channel power be unequal
(`Var(L)=σ_L²`, `Var(R)=σ_R²`, not assumed equal), both the broadband
`level_change_db` and per-band `delta_db` formulas reduce to the identical
closed form `10·log10(1 + effective correlation)`, where "effective
correlation" is `kρ` (broadband, `k=2σ_Lσ_R/(σ_L²+σ_R²)≤1`) or `k_band·ρ_band`
(per-band, same form computed from that band's own power). Both ρ=0
floors (-6.0206 dB broadband, -3.0103 dB per-band) are exact REGARDLESS of
channel-power imbalance -- the shipped constants were never wrong, at any
channel balance. Cross-checked against the reopened report's own quoted
figures ("1.995-2.548 dB... across all five references"): back-solving
under near-equal power gives `ρ≈0.58-0.80`, matching the prior
investigation's own independent back-solve from different quoted figures
almost exactly -- two independently-quoted five-track figure sets,
through two related-but-different formulas, converge on the same range,
consistent with the reference material's own consistent mix character,
not a wrong constant.

**The actual defect, identified by tracing why the same correct number has
now been reported as a bug three times (DEF-101, DEF-104, DEF-203)**:
`excess_cancellation_db`'s NAME and SIGN CONVENTION invite the opposite of
its actual meaning. The metric runs `+3.0103 dB` at ρ=+1 (best case) down
to `-inf` at ρ=-1 (full cancellation) -- higher is better. A field named
"excess cancellation" reading a positive number reads, to any plain-English
interpretation, as "this much excess (bad) cancellation is present" -- the
opposite of the truth. The per-band sibling (`BandCancellation.excess_delta_db`)
has the identical sign polarity but is far less confusing in practice
because it is never the primary reader-facing signal -- the correctly-signed
boolean `BandCancellation.cancellation` is. The broadband field has no
equivalent flag.

**Resolution, both halves of the reopened report's proposed options
adopted**: (1) RENAME `MonoSumResult.excess_cancellation_db` →
`MonoSumResult.headroom_db` (same formula, same sign, only the name
changes -- deliberately not `mono_sum_headroom_db`, since
`reference_analysis/aggregate.py` already prefixes the aggregate key with
`"mono_sum."`, which would double it). (2) ADD
`MonoSumResult.broadband_cancellation: bool`, computed as
`headroom_db < config.mono_broadband_cancellation_headroom_db`, mirroring
the existing per-band flag exactly. New config field
`mono_broadband_cancellation_headroom_db: float = -3.0` -- DERIVED, not a
fresh guess: the existing per-band default corresponds to flagging
`k_band·ρ_band < -0.5`; since the broadband metric reduces to the
identical closed form, reusing `-3.0` flags the SAME physical criterion.

**Not yet done (python-developer's outstanding work)**: `analysis/mono_sum.py`
(rename the computed field, add `broadband_cancellation`); `analysis/
reference_types.py` (rename `MonoSumResult.excess_cancellation_db` →
`headroom_db` with a corrected sign-convention docstring, add
`broadband_cancellation: bool`); `reference_analysis/config.py` (add
`mono_broadband_cancellation_headroom_db=-3.0` with the derivation
comment); `report/reference_render.py::_track_section()` (update the field
reference and prose, add a `broadband_cancellation` render line);
`reference_analysis/aggregate.py` (update the aggregate key to
`"mono_sum.headroom_db"`); `SCHEMA_VERSION` bump `"1.2"`→`"1.3"`, combined
with DEF-201's own additive `HfExtensionResult` fields into a single bump.

**Not yet done (qa-automation-engineer's/test-case-writer's outstanding
work)**: `tests/ref_helpers.py::make_stub_measurements`'s
`mono_sum_excess_cancellation_db` kwarg and `MonoSumResult(...)`
construction need updating to the renamed field; existing tests
referencing the old name (`test_tc311`, `test_tc313`) need updating to
`result.headroom_db`.

**AC6 branch, stated explicitly**: the constant's own correctness needed
no failing-test-first sequence a third time (§3.4's already-recorded
exception, reconfirmed by this independent re-derivation) -- the
metric-semantics fix is an ordinary code change, not a defect-in-a-
computed-value fix, and is not gated by AC6/AC11's failing-test-first rule.

**Status: still Open, Architectural-Resolved** -- design specified
(rename + new flag + derived threshold), not yet implemented or verified.
Do not mark Fixed/Closed until the implementation lands and both renamed
fields are confirmed correctly threaded through both renderers and the
schema bump, per this project's standing "only QA closes a defect" rule.

---

## Pointer: STORY-004 supersedes the two v3 "Architect resolution" entries above for DEF-201/DEF-203

`stories/STORY-004/architecture.md` (v1.3, post-Gate-1) is the current,
authoritative design for DEF-201 and DEF-203 -- **not** the two v3 entries
directly above. `stories/STORY-004/story.md`'s coordinator notes state this
explicitly: v3's DEF-203 proposal (rename `excess_cancellation_db` ->
`headroom_db`, keep the -6.0206 dB channel-summed constant) is CONTESTED
and was NOT adopted -- it conflicts with DOMAIN.md Section 3 / CLAUDE.md's
precedence rule. STORY-004 instead changes the mono-sum comparator itself
(channel-mean, not channel-summed; field `mono_sum_level_change_db`,
rho=0 floor -3.0103 dB) and replaces `excess_cancellation_db` with a
boolean, `mono_sum_excess_cancellation`, per architecture.md Section 2.3.
v3's DEF-201 HF design is a partial starting point but its return-contract
names (`cutoff_detected`/`rolloff_hz`-as-Nyquist-sentinel) are superseded by
`hf_band_limit_hz` (nullable, never a sentinel) + `hf_band_limit_confidence`,
and its detection method is replaced with a log-frequency-grid two-stage
cliff detector (architecture.md Section 3). See `stories/STORY-004/
architecture.md` Sections 2-3 for the current binding design and Section 10
for the full revision history including the Gate 1 blocker resolution
(v1.3).

---

## STORY-004 QA baseline (confirmed-failing-first pass, qa-automation-engineer)

**Status of this note: evidence record only. No STORY-004 defect is opened,
closed, or retriaged by this entry -- STORY-004 does not yet have its own
`defects.md`; this baseline is recorded here per the coordinating prompt's
explicit instruction, against the existing DEF-201/DEF-203/DEF-204 line
items, since those are the defects this baseline evidences.**

Per HANDOFF.md H7 step 2 ("the failing test... was written before the fix
and confirmed failing"), this pass ran STORY-004's new negative-control and
mono-sum ground-truth fixtures against the CURRENT, UNMODIFIED shipped code
(pre-architecture.md-v1.3 implementation -- `hf_extension.py` still
threshold-crossing with `hf_rolloff_threshold_db=20.0`; `mono_sum.py` still
comparing against BS.1770 channel-SUMMED stereo LUFS) **before** any
STORY-004 code change is applied. No fix has been made or is pending this
pass; all findings below are pre-implementation baseline evidence.

New test file: `stories/STORY-001/implementation/tests/test_story004_baseline.py`
(imports new fixture helpers added to `stories/STORY-001/implementation/
tests/ref_helpers.py`: `tilted_noise_mono`, `tilted_then_brickwall_mono`,
`tilt_nonstationary_no_cutoff_mono`, `silent_stereo`). Run via
`pytest -q -s tests/test_story004_baseline.py` from
`stories/STORY-001/implementation/`. Result: **6 passed, 2 failed** (0
errors, no collection issues) -- full numbers below.

### DEF-201 -- HF band-limit negative controls (pre-fix)

| Test | Fixture | Result (old schema: `rolloff_hz`, `stable`) | Pass/Fail against "no cutoff" expectation |
|---|---|---|---|
| `test_tc406_pink_noise_no_cutoff_baseline` | Stationary pink noise (-3 dB/oct), no filter, 44.1kHz | `rolloff_hz=22047.3 Hz` (>=0.9*Nyquist), `stable=True`, `per_segment_rolloff_hz=[22047.3, 22047.3, 22047.3, 22047.3, 22050.0]` | **PASS, but for the WRONG reason -- not clean agreement about an absent cliff.** Every one of the 5 segments returns a value at or immediately below Nyquist (`scan_freqs[-1]`/near-top bin) -- per `_segment_rolloff_hz`'s top-down loop, this means the very TOPMOST scanned bin already cleared the threshold line on (essentially) every segment, i.e. the scan terminated at its first candidate rather than genuinely searching down and independently confirming no crossing exists lower in the spectrum. This is structurally different from what the corrected detector's `hf_band_limit_confidence==1.0` no-cliff branch (architecture.md Section 3.7) is meant to represent -- "every segment independently found no cliff" after a real search, not "every segment's scan degenerated to its starting point." Already passed before this pass, as architecture.md Section 5.1/9 predicts; its passing is NOT evidence DEF-204 is closed, and must not be read as evidence the current method correctly handles the no-cliff case. |
| `test_tc407_tilted_no_cutoff_48k_baseline` (NEW fixture) | Full-band, constant -6 dB/octave tilt, NO filter anywhere, 48kHz. **Fixture verified, not assumed**: band-averaged density (`_psd.band_mean_density`, same multi-bin quantity the detector's own reference-band anchor uses) confirms a genuine, constant ~6 dB/octave tilt across 500Hz-16kHz (per-octave measurements: ~6.1, ~5.9, ~6.1, ~6.0 dB/oct) -- this is a correctly-constructed fixture, not a construction defect. | `rolloff_hz=19532.2 Hz` (< 21600.0 = 0.9*24000 Nyquist bound), `stable=False`, `per_segment_rolloff_hz=[19331.5, 19532.2, 23869.6, 22176.3, 18476.1]` (spread 5393.5 Hz) | **FAIL (confirmed failing, H7 evidence).** A value inside the near-Nyquist problem region (close to architecture.md Section 3.5's derived ~20774 Hz truncation ceiling at 48kHz), not near-Nyquist-enough/None, and unstable across segments -- on a signal engineered to have NO real cutoff anywhere. **H5 spread-check finding, not predicted in advance**: the naive prediction ("20 dB / 6 dB-per-octave = 3.33 octaves above the ~1000 Hz reference band -> an 8-13 kHz mid-band crossing") did NOT hold; the crossing lands near-Nyquist instead. Plausible mechanism, NOT independently discriminated from an equally-consistent alternative (flagged, not asserted as settled): the detector's raw per-bin threshold-crossing scan (unlike the band-averaged density used to verify the fixture) has substantial single-realization Welch-estimate variance (`_psd.compute_psd` averages only ~4 segments at this fixture length), so the reported crossing may track scan-noise near Nyquist rather than the mean tilt. An equally consistent alternative, NOT ruled out here: at the fixture's top-octave density (~-114 to -118 dB), the reference-band-minus-20dB threshold line may sit within a few dB of the spectrum across a wide near-Nyquist span, so the top-down scan's stopping point is ill-conditioned by construction (a near-parallel line/spectrum crossing) rather than purely noise-driven. The discriminating check (comparing `ref_density_db - 20` against the 16-22kHz band-averaged density for this exact fixture) was not run this pass -- left as an open item for whoever next investigates this fixture in detail, not fabricated here. This is itself an additional, independent H5 spread-check anomaly: TC-407 is fully STATIONARY by construction yet its per-segment spread (5393.5 Hz) EXCEEDS TC-408's spread (3732.0 Hz) below, even though TC-408 is deliberately non-stationary -- a stationary fixture producing more instability than a non-stationary one is itself evidence the measured instability is an artifact of the detector's noise-sensitivity, not of genuine programme variation, reinforcing (not merely restating) DEF-201's "detector tracks programme content, not a fixed property" diagnosis. This is the primary near-Nyquist confirmed-failing-first evidence the Gate 1 Blocker fixture requires. |
| `test_tc408_tilt_nonstationary_no_cutoff_baseline` (NEW fixture) | Concatenation of 4 segments, differing tilt (4/6/8/5 dB/oct) and gain, NO filter, no real cutoff, 44.1kHz | `rolloff_hz=22020.4 Hz` (clears the naive near-Nyquist threshold), but `stable=False`, `per_segment_rolloff_hz=[22047.3, 22044.6, 18315.3, 22020.4, 21961.2]` (spread 3732.0 Hz > `hf_stability_tolerance_hz`=2000.0) | **FAIL (confirmed failing, H7 evidence) -- actual failure mode differs from the predicted mid-band-value shape.** The absolute `rolloff_hz` value itself is near-Nyquist here (does NOT reproduce a GusGus-1979-Hz/Leftfield-8170-Hz-style mid-band number on this specific fixture), but the detector is UNSTABLE on a signal with no real (fixed or otherwise) band limit anywhere -- DOMAIN.md Section 2: "a band limit is a fixed property of a file... a detector reporting it as unstable is measuring programme content." Recorded honestly as a sibling failure mode of the same threshold-crossing method, not forced to match the GusGus/Leftfield shape. |
| `test_tc404_tilt_then_brickwall_20k_48k_fixture_construction` (NEW fixture, fixture-construction record only) | Tilt (-6 dB/oct) then brickwall at 20000 Hz, 48kHz -- a GENUINE cliff, not a negative control | `rolloff_hz=18769.0 Hz`, `stable=True` | Not a pass/fail assertion against the old method (the corrected near-Nyquist adaptive-truncation method this fixture is designed to exercise does not exist in the current code); no H7 evidence claimed for this fixture -- unlike TC-407/TC-408/TC-453, there is no pre-fix "expected failing" outcome asserted here to point to. Recorded purely as a pre-fix data point for contrast once architecture.md v1.3's detector is implemented and this fixture is re-run expecting ~20000 +/- 1000 Hz. **Worth flagging for that future re-run**: the old method already undershoots a REAL cliff here by ~1231 Hz (18769 vs the true 20000 Hz construction), landing just outside the corrected method's own +-1000 Hz tolerance. If the post-fix log-grid detector reports a similarly low value again, that would suggest the localization bias is inherited by the redesign rather than being specific to the old threshold-crossing method -- worth checking explicitly, not assuming the redesign automatically fixes it. |

### DEF-203 -- mono-sum ground truth (pre-fix)

| Test | rho (by construction) | `level_change_db` (old comparator: channel-SUMMED stereo denominator) | Post-fix (architecture.md v1.3 Section 2.1) expected value | Pass/Fail against post-fix expectation |
|---|---|---|---|---|
| `test_tc450_rho1_identical_channels_baseline` | 1.0 (L=R exactly) | **-3.0103 dB** (`excess_cancellation_db=+3.0103`) | 0.0 dB | Test asserts and confirms the PRE-FIX value (-3.0103, not 0.0) -- this passing IS the confirmed-failing-vs-post-fix-spec evidence: the current comparator's rho=1 reading is 3.01 dB away from the corrected contract's required 0 dB. |
| `test_tc451_rho0_independent_noise_baseline` | 0.0 (independent, equal-power noise) | **-6.0225 dB** (`excess_cancellation_db=-0.0019`, i.e. ~exactly at the old, wrong -6.0206 dB floor CLAUDE.md Section 5 names explicitly) | -3.0103 dB | Test asserts and confirms the PRE-FIX value (-6.0225, not -3.0103) -- direct, textbook DEF-203 evidence: this is the exact "-6.02 dB is wrong" figure CLAUDE.md's own known-wrong-patterns table calls out by name. |
| `test_tc452_rho_neg1_inverted_baseline` | -1.0 (R = -L exactly) | -inf dB | -inf dB | **Already matches post-fix expectation under the CURRENT code too** -- this specific point does not discriminate the DEF-203 defect (mono_sum is identically zero regardless of which stereo-LUFS denominator is used as the comparator). Included for AC4 completeness, not new failing evidence. |
| `test_tc453_both_channels_silent_baseline` | N/A -- all-zero stereo buffer, both channels exact digital silence | **NaN** (`math.isnan(level_change_db) is True`) | 0.0 dB (the defined rho=1 limit) + `mono_sum_both_channels_silent=True` | **FAIL (confirmed failing, Gate 1 advisory H7 evidence).** Directly confirms the Gate 1 review's identified hazard: `(-inf) - (-inf)` evaluates to NaN in IEEE arithmetic under the current, unguarded code; `NaN < -4.5` is `False` in Python, so a completely silent stereo file would silently fail to flag rather than reporting a defined, plausibility-visible result. No guard branch exists yet in `mono_sum.py`. |

### H7 step 2 status, explicit per-fixture (do not generalize "6 passed, 2
failed" into "H7 is satisfied for this pass" -- it is only satisfied for
the fixtures that actually failed)

- **H7 step 2 SATISFIED** (confirmed-failing pre-fix evidence exists,
  recorded above): TC-407 (near-Nyquist tilted negative control), TC-408
  (tilt+non-stationarity negative control), TC-453 (both-channels-silent
  guard).
- **H7 step 2 NOT SATISFIED / not applicable** (no pre-fix failure to
  point to for these): TC-406 (already passed pre-fix, for the wrong
  reason -- see its row's caveat above, not new failing evidence), TC-404
  (fixture-construction record only, no pre-fix expectation asserted),
  TC-450/TC-451 (these DO fail against the post-fix spec, but the
  assertions in this baseline file deliberately assert the PRE-FIX value
  and therefore currently PASS -- they are H4/ground-truth evidence of the
  wrong constant, not H7 "confirmed failing" test bodies; a future pass's
  corrected-schema suite is what will fail-then-pass against these points),
  TC-452 (matches post-fix expectation already, does not discriminate the
  defect).

### Suite health

- Collection: clean, no errors. `pytest -q -s tests/test_story004_baseline.py` -> `6 passed, 2 failed` as itemized above; both failures are the intended confirmed-failing-first evidence, not accidental breakage.
- Regression check: `pytest -q tests/test_ground_truth_hf_extension.py` (existing STORY-003 HF suite, unmodified) still passes unchanged after the `ref_helpers.py` additions (`7 passed, 3 skipped`) -- the new fixture helpers are additive and do not disturb existing fixtures/tests.
- Full STORY-001/STORY-002 regression suite was deliberately NOT run this pass (out of the stated budget for a baseline pass); `test_tc150_processing_time_budget`'s isolation rule (`stories/STORY-001/automation/README.md`) was respected -- not invoked at all this pass.

### What this baseline does NOT do

- Does not implement architecture.md v1.3's corrected detectors.
- Does not write the full v1.3-corrected test-cases.md automation (new
  field names `hf_band_limit_hz`/`hf_band_limit_confidence`/
  `mono_sum_level_change_db`/`mono_sum_excess_cancellation`/
  `mono_sum_both_channels_silent` do not exist on the current dataclasses;
  asserting against them now would raise `AttributeError`, which
  architecture.md Section 5.1's own process note states explicitly is "not
  meaningful evidence of failure," not real H7 evidence). That corrected
  suite is the next qa-automation-engineer pass's job, once python-developer
  implements architecture.md v1.3.
- Does not close, retriage, or otherwise change the status of DEF-201,
  DEF-203, or DEF-204. All three remain as currently stated in this file
  (DEF-201/DEF-203: Open/REOPENED above, with the v3 entries superseded per
  the pointer note preceding this one; DEF-204 has no dedicated entry in
  this file -- see `stories/STORY-004/story.md`/`requirements.md` for its
  scope, which this baseline's TC-407/TC-408 results directly evidence).

---

## STORY-004 implementation pass (python-developer) -- DEF-201 and DEF-203

Implements `stories/STORY-004/architecture.md` v1.3 (the Gate-1-resolved
design) against `stories/STORY-001/implementation/suno_mastering/analysis/*`
and the downstream files architecture.md Section 4's "downstream-impact
list" names. Per this pass's own task brief, test files (`tests/*`,
`ref_helpers.py`, `test_story004_baseline.py`) were deliberately NOT
modified -- that is qa-automation-engineer's/test-case-writer's territory,
not python-developer's, notwithstanding architecture.md Section 4 item 11
nominally listing them. Those files still reference the pre-fix field names
(`rolloff_hz`, `level_change_db`, `excess_cancellation_db`) and will raise
`AttributeError`/`TypeError` against the corrected dataclasses until the
next QA pass updates them -- this is expected, not a regression introduced
here (`test_story004_baseline.py`'s own docstring already says it is
"disposable evidence... retire this whole file").

### DEF-201 -- Status: Fixed-Pending-Retest.

**AC2 NOT MET on Leftfield (8125.5 Hz, below the 10 kHz DOMAIN.md Section 2
bar) under the literal v1.3 algorithm as implemented -- see the
Architectural finding below for the full root cause (confirmed, not
speculative: the real ~20 kHz wall IS found by this same detector at a
later candidate, but is masked by "first-qualifying-candidate-wins"
stopping at an earlier, shallower false candidate) and two specific,
checkable design points for the architect's Gate 2 review.**

**Test files broken by the field renames, for QA's discovery pass** (not
found by inspection alone -- confirmed by `grep` of the pre-change field
names across `tests/`, listed here so QA does not have to re-derive it):
`tests/ref_helpers.py` (`make_stub_measurements`'s `HfExtensionResult`/
`MonoSumResult` construction), `tests/test_story004_baseline.py`
(deliberately left broken per its own docstring -- disposable evidence),
`tests/test_ref_ac10_verification_bars.py`, `tests/test_ref_ac5_hf_exclusion.py`,
`tests/test_ref_ac1_per_track.py`, `tests/test_ref_ac2_aggregate.py`,
`tests/test_ref_ac12_aggregate_n.py`, `tests/test_ref_edge_cases.py`,
`tests/test_ground_truth_hf_extension.py`, `tests/test_ground_truth_stereo_width.py`.
All raise `AttributeError`/`TypeError` against the corrected dataclasses
until updated to the new field names -- none of this is a code regression,
it is the expected consequence of the field-name/type changes architecture.md
Section 4 specifies.

**H6: METHOD change, not a parameter change.** The threshold-crossing
scan (`_segment_rolloff_hz`, an absolute relative-dB line against a
per-segment-re-anchored reference band) is deleted entirely, along with
`_transcode_slope_check`. Replaced with the two-stage log-frequency-grid
cliff detector architecture.md Section 3 specifies: a candidate window
must pass (1) a passband precondition (local pre-candidate slope <=
`hf_cliff_passband_max_slope_db_per_octave`, 12 dB/octave) so a candidate
partway down an ordinary declining spectrum is rejected before the drop
test even runs, (2) a sustained-drop test (>= `hf_cliff_required_drop_db`,
a FIXED 8.0 dB regardless of near-Nyquist window truncation -- the Gate 1
fix), and (3) a floor-confirmation test (coverage + no-recovery, Section
3.5). No threshold-crossing mechanism of any kind remains; `None` is
returned, never a fallback value, when no candidate satisfies all three
tests anywhere in the search range.

**Files changed** (per architecture.md Section 4's downstream-impact list):
- `suno_mastering/analysis/_psd.py`: added `log_band_levels_db()` (Section
  3.2) -- the log-frequency (1/24-octave, configurable via
  `hf_cliff_log_band_octave_fraction`) rebinning helper. Existing functions
  unchanged.
- `suno_mastering/analysis/hf_extension.py`: full rewrite. `_detect_cliff()`
  implements the three-test candidate search (Sections 3.3-3.5), used
  identically for the whole-track PSD and every per-segment PSD (Section
  3.7 -- decided ONCE on the whole-track active-audio PSD, corroborated,
  never re-decided, per segment). `_compute_confidence()` implements
  Section 3.7's fraction-of-segments-agreeing formula, defined for both the
  found-cliff and no-cliff branches. `suspected_transcode` is now a direct
  classification against the confirmed `hf_band_limit_hz` (Section 3.6),
  the separate `_transcode_slope_check` function deleted.
- `suno_mastering/analysis/reference_types.py`: `HfExtensionResult`
  reshaped to the Section 3.8 contract -- `rolloff_hz` -> `hf_band_limit_hz`
  (nullable, never a fallback), added `hf_band_limit_confidence: float`,
  `per_segment_rolloff_hz` -> `per_segment_hf_band_limit_hz: List[Optional[float]]`.
- `suno_mastering/reference_analysis/config.py`: removed
  `hf_rolloff_threshold_db` and `transcode_suspect_slope_db_per_octave`
  (the mechanisms they served no longer exist); added the eleven
  `hf_cliff_*` fields architecture.md Section 3.3's table specifies, each
  with the derivation/judgment-call comment from that table
  (`hf_cliff_log_band_octave_fraction`, `hf_cliff_target_window_octaves`,
  `hf_cliff_required_drop_db=8.0` [derived, fixed -- the Gate 1 resolution],
  `hf_cliff_min_window_bands=3`, `hf_cliff_min_floor_bands=2`,
  `hf_cliff_slope_db_per_octave=24.0`,
  `hf_cliff_passband_max_slope_db_per_octave=12.0`,
  `hf_cliff_floor_min_fraction=0.8`, `hf_cliff_floor_noise_margin_db=3.0`,
  `hf_cliff_search_min_hz=3000.0`, `hf_cliff_confidence_stable_floor=0.6`).
  `hf_stability_tolerance_hz` kept, repurposed as the confidence-agreement
  tolerance (Section 3.7), not a raw spread-of-crossings figure.
- `suno_mastering/reference_analysis/pipeline.py`: `analyze_track()`'s
  `check_hf_rolloff_vs_air_band` call site updated to
  `hf_ext.hf_band_limit_hz`.
- `suno_mastering/analysis/sanity.py`: `check_hf_rolloff_vs_air_band`'s
  first parameter renamed `rolloff_hz` -> `hf_band_limit_hz` (behavior
  unchanged -- `None` still means "skip the check," now covering three
  legitimate cases instead of one). `_HF_ROLLOFF_SUSPECT_HZ` raised
  `5000.0` -> `10000.0` (architecture.md Section 4 item 7b -- a doc-derived
  correction from DOMAIN.md Section 2's explicit "any reported cutoff below
  ~10 kHz on a commercial release is a measurement error," not parameter
  tuning of the detector under test).
- `suno_mastering/reference_analysis/aggregate.py`:
  `_hf_extension_aggregates` renamed `rolloff_hz` -> `hf_band_limit_hz` and,
  per architecture.md Section 4 item 8, now distinguishes "insufficient
  duration" from "no band limit detected -- legitimate, not a defect" in
  the exclusion-reason string (previously conflated under one reason).
  **Also renamed the machine-readable aggregate metric key itself**,
  `hf_extension_rolloff_hz.{sr}hz` -> `hf_extension_hf_band_limit_hz.{sr}hz`
  -- this key is schema-2.0 surface STORY-005 consumes; leaving it as
  `rolloff_hz` after the field itself is renamed would be exactly the
  incomplete-rename pattern this same architecture.md Section 4 opens by
  warning about (DEF-104/DEF-106).
- `suno_mastering/report/reference_builder.py`: `SCHEMA_VERSION` `"1.2"` ->
  `"2.0"` (MAJOR bump, architecture.md Section 8 -- removes/reshapes
  fields, not additive). `_config_summary()` drops the two removed config
  keys, adds the eleven new `hf_cliff_*` keys.
- `suno_mastering/report/reference_render.py`: `_track_section()`'s HF
  branch now renders three distinct cases -- insufficient duration, no band
  limit detected (with the Section 3.5 near-Nyquist-ambiguity caveat inline
  and `hf_band_limit_confidence` shown), and a confirmed band limit (Hz +
  confidence + stable/unstable), per architecture.md Section 4 item 10.

**Verification performed this pass** (targeted, not the full suite --
qa-automation-engineer owns the corrected-schema automated suite):
1. `python -c "import ..."` on every changed module -- imports cleanly, no
   syntax/reference errors.
2. Synthetic fixtures (via `tests/ref_helpers.py`'s existing helper
   functions, called directly, NOT via pytest -- consistent with "leave
   test files alone"):
   - `brickwall_lowpass_noise_mono` @ 15 kHz, 8 kHz, 44.1 kHz: correctly
     found a cliff (not `None`), `stable=True`, `confidence=1.0`.
   - `brickwall_lowpass_noise_with_floor_mono` @ 16 kHz, 27 dB floor: cliff
     found, `stable=True`.
   - `tilted_noise_mono` (-6 dB/octave, NO cutoff, 48 kHz -- the Gate-1
     Blocker's required negative control): `hf_band_limit_hz is None`,
     `confidence=1.0`, `stable=True`. **Confirms the Gate 1 Blocker fix
     (fixed 8.0 dB drop bar, not window-scaled) holds** -- this exact
     fixture is what exposed the pre-v1.3 near-vacuous scaled bar.
   - `pink_noise_mono` (no cutoff, 44.1 kHz, the TC-024/TC-406 pattern):
     `hf_band_limit_hz is None`.
   - `tilt_nonstationary_no_cutoff_mono` (the primary DEF-204 negative
     control -- differing per-segment tilt/gain, no real cutoff, 44.1 kHz):
     `hf_band_limit_hz is None`, `confidence=1.0`, `stable=True`. **This is
     the fixture whose absence let DEF-201 ship undetected** (per
     requirements.md's DEF-204 scope) -- confirmed it now correctly reports
     no cliff, not the pre-fix instability failure recorded in the
     STORY-004 QA baseline section above (TC-408).
   - `tilted_then_brickwall_mono` (-6 dB/octave tilt then a genuine 20 kHz
     brickwall, 48 kHz): a cliff WAS found (not `None`).
3. Real five-track reference set (`Reference Tracks/*.wav`, all 48 kHz):
   see the Architectural finding immediately below -- one track
   (Leftfield) still produces an AC2-violating result.

**Architectural finding (flagged, not silently worked around) -- ONE root
cause, two consequences, both confirmed by direct data, not speculation.**

Running the corrected detector (implemented exactly per architecture.md
v1.3, no deviation) against the real reference set:

| Track | `hf_band_limit_hz` | `confidence` | `stable` |
|---|---|---|---|
| Black Flute (Remastered) | 12531.3 Hz | 1.0 | True |
| GusGus -- Over (Arabian Horse) | 13276.4 Hz | 1.0 | True |
| **Leftfield -- Melt** | **8125.5 Hz** | 0.8 | True |
| Chemical Brothers -- Live Again | 16727.3 Hz | 0.2 | False |
| Wavy Gravy | 18775.7 Hz | 0.6 | True (suspected_transcode=True) |

**Leftfield reports 8125.5 Hz** -- DOMAIN.md Section 2: "any reported
cutoff below ~10 kHz on a commercial release is a measurement error," and
this is a near-exact reproduction of DEF-201's own original report figure
for this same track (8170 Hz). AC2 requires "no value below 10 kHz is
reported for a commercial master." **`confidence=0.8`** (4 of 5
independently-analysed per-segment PSDs agree on this same ~8.1 kHz
result) is itself corroborating evidence for the corrected root cause
below, not against it: a noise/estimator-variance artifact would not be
expected to reproduce consistently across four independent segment-level
PSD estimates -- only a genuine, stable spectral feature would.

**Root cause, confirmed by direct trace, corrected from an earlier draft
of this note -- this is NOT noise/estimator variance.** The candidate at
`i` (center 8125.5 Hz, `w=8`) is a REAL, smooth, monotonic feature: Welch
levels decline from -80.25 dB to -89.55 dB across the window (steps
`[-1.41, -2.13, -0.08, -1.66, -1.48, -2.16, +0.86]` dB, every step within
the +-1 dB wiggle tolerance -- this is ordinary programme HF content
decaying smoothly into the recording's own noise floor, not a spurious
run), followed by a genuinely flat plateau from ~8.1 to ~19.9 kHz (levels
consistently -89 to -94 dB across a full octave) before the file's REAL
wall at ~20.5 kHz (level drops to -125.7 dB, then -147 dB). Below 8 kHz
the same data oscillates +-5 dB band-to-band (noisy); from 8.1 kHz onward
it does not -- this is a real transition, just the WRONG one: the design's
8.0 dB bar over a 1/3-octave window is the minimum evidence consistent
with a genuine 24 dB/octave cliff, and a programme-decaying-into-floor
transition of only 9.29 dB clears it just as easily as a true wall would.
**Directly confirmed the real wall is independently detectable by this
SAME detector**: the candidate at `i` (center 16251.1 Hz) passes all three
tests on its own -- passband precondition 10.89 dB/octave (<=12 dB/octave
gate), drop `levels_db[i]-levels_db[i+8]` = 34.5 dB (>> 8.0 dB bar), every
step in `[+0.53, -0.22, +0.42, -1.23, -0.95, -0.60, -1.47]` within the +-1
dB tolerance, floor coverage 1.0 with a comfortable no-recovery margin.
**The true 20 kHz wall is already inside this detector's reach and is
masked, not missed** -- "first (lowest-frequency) qualifying candidate
wins" (architecture.md Section 3.5) stops the scan at the earlier, shallow
8.1 kHz candidate before it ever reaches the real one at 16.3 kHz. This
reframes the finding precisely: **the design's own two specified
choices -- an 8 dB bar that does not discriminate a shallow decline-into-
floor from a genuine wall's depth, combined with first-candidate-wins
ordering -- are together what suppress a correct, reachable answer**, not
a broken detector or noise-driven false positive.

**Separately confirmed, and now understood as the SAME root cause, not a
second, independent finding: `hf_band_limit_hz`'s reported value
(`centers[i]`, the window START, per architecture.md Section 3.5) is
systematically ~0.3 octaves BELOW the true cutoff on every genuine,
verified synthetic cliff -- but `centers[i+w]` (the window's FAR end,
already computed and compared inside the drop test, just not the reported
quantity) lands within architecture.md's own +-500 Hz tolerance in every
case:**

| Fixture (true cutoff, by construction) | Reported `centers[i]` | `centers[i+w]` | Within +-500 Hz of true cutoff? |
|---|---|---|---|
| Brickwall @ 15000 Hz, 44.1 kHz | 12174.5 Hz (-2825.5 Hz) | **15339.0 Hz** | `centers[i+w]`: yes (+339.0) |
| Brickwall @ 8000 Hz, 44.1 kHz | 6449.2 Hz (-1550.8 Hz) | **8125.5 Hz** | `centers[i+w]`: yes (+125.5) |
| Finite-floor brickwall @ 16000 Hz, 44.1 kHz | 12898.5 Hz (-3101.5 Hz) | **16251.1 Hz** | `centers[i+w]`: yes (+251.1) |
| Tilt-then-brickwall @ 20000 Hz, 48 kHz | 16251.1 Hz (-3748.9 Hz) | **20475.1 Hz** | `centers[i+w]`: yes (+475.1) |

This is a direct, internal contradiction inside architecture.md itself,
not merely "the design may not localize well": Section 3.5 mandates
reporting `centers[i]` ("the center frequency of log band `i`... **not
`i+w`, the bottom of the cliff**" -- v1.2 revision-history note explicitly
rejecting `i+w`), while Section 5.1's own ground-truth fixture table
asserts `hf_band_limit_hz ~= cutoff +/- 500 Hz` for exactly these
fixtures. Both cannot hold simultaneously against a genuinely near-
vertical (single-band) real edge -- the data above shows `centers[i+w]`
is what actually satisfies Section 5.1's own tolerance claim.

**Named crisply, since it is the mechanism behind both consequences**: the
drop test spans `i -> i+w` (checks two points `w` bands apart), but the
monotonicity/"sustained" test only checks the INTERIOR `[i, i+w)` (`w-1`
steps). A single-band-wide real wall sitting exactly at the `i+w` boundary
satisfies "sustained decline" vacuously -- the entire checked interior is
flat/gently declining, and the one real step (into the wall) is the one
step the monotonicity test never examines. This is also why the reported
`i` sits a full window-width before the wall: `i` is not an independent
measurement of where the wall begins, it is "wherever the far end of some
admissible window first reaches the wall."

**Neither finding was corrected in code by this pass.** Per H6, a
python-developer does not have standing to silently redesign a specified
algorithm's window semantics or candidate-selection rule without a
derivation -- both consequences trace to two specific, named design
choices in architecture.md Section 3.5 (the reported point is `centers[i]`
not `centers[i+w]`; and "first qualifying candidate wins" with no
depth-relative-to-noise-floor discriminator on the 8.0 dB bar), not to a
missing derivation this role could supply. **Raised here as Architectural
for the software-architect/mastering-engineer's Gate 2 review**, with two
concrete, narrow, checkable candidate fixes (not prescribed, and
deliberately NOT "tighten the wiggle tolerance" -- that was an earlier,
incorrect draft of this note's recommendation, discarded once the root
cause above was confirmed empirically, since it would only reject
Leftfield's specific +0.86 dB step by luck and would not address the
underlying depth-discrimination gap): (a) report `centers[i+w]` (or
equivalent, e.g. the last interior band) instead of `centers[i]` --
confirmed above to bring all four synthetic ground-truth fixtures within
Section 5.1's own +-500 Hz tolerance; (b) among all qualifying candidates
in a track (not just the first), prefer the one with the LARGEST total
drop, or add an explicit depth-relative-to-the-passband-level
discriminator to the drop test, so a genuine wall (Leftfield: 34.5 dB) is
not masked by an earlier, shallower decline-into-floor transition
(Leftfield: 9.29 dB) that merely happens to occur at a lower frequency.
Both are narrow, targeted revisions to Section 3.5's own stated rules, not
a request to redesign the detector; verified empirically against real
data in this note, not asserted.

**Consequence of adopting (a), stated so the architect does not carry
forward stale numbers**: Section 3.5's near-Nyquist reachability ceiling
(`Nyquist / 2^(5/24)` ~= 20774 Hz at 48 kHz, ~= 19087 Hz at 44.1 kHz,
derived specifically for the `centers[i]` report point with 5 bands
reserved above `i`), Section 6 risk 4's discussion built on that ceiling,
and Section 5.1's +-1000 Hz widened-tolerance rationale for the 20 kHz/
48 kHz fixture would all become stale if (a) is adopted -- they would need
re-deriving for `centers[i+w]`, not carried over. Re-derived here for the
architect's convenience (verified by direct arithmetic, not asserted): at
the highest admitted `i` (`n_bands-5`), `bands_remaining=5` so
`w = min(8, 5-2) = 3`, placing `i+w` at `n_bands-2` -- two bands below the
top of the grid, giving a NEW ceiling of `Nyquist / 2^(2/24)`: **~=22637
Hz at 48 kHz** (was ~=20774 Hz) and **~=20812 Hz at 44.1 kHz** (was
~=19087 Hz). Both are HIGHER, not lower, than the current figures -- the
48 kHz ceiling would then cover DOMAIN.md Section 2's full 20-22 kHz
CD/lossless row, and the 44.1 kHz ceiling would reach the ~20 kHz MP3-320
row Section 3.5 currently states explicitly is unreachable at 44.1 kHz.
Adopting (a) therefore extends reach past the current documented limits
rather than shrinking it, incidentally narrowing Section 6 risk 4's
`None`-ambiguity gap as a side effect, not a cost of the fix.

**This does NOT mean DEF-201's method change failed on its own terms.**
The four synthetic negative controls (tilted-no-cutoff, pink-noise,
tilt+non-stationarity) and the passband/drop-bar arithmetic all confirm
the core DEF-201 defect -- a fixed relative-dB threshold crossed by
ordinary programme tilt regardless of whether a cliff exists -- is closed:
no negative-control fixture produces a spurious result, and the real
20 kHz wall on Leftfield IS inside this detector's reach (confirmed
above), just masked by an ordering/depth-discrimination gap in two named
rules, not absent. This is a narrower, more specific, and more actionable
finding than "the method may not work on real material" -- recommend
qa-automation-engineer raise it as a new, distinct defect (not a DEF-201
reopen, since the mechanism is different from DEF-201's original
threshold-crossing-on-tilt failure) once independently confirmed against
the corrected-schema automated suite.

**This does NOT mean DEF-201's method change failed on its own terms.**
The four synthetic negative controls (tilted-no-cutoff, pink-noise,
tilt+non-stationarity, and by direct inspection the passband/drop-bar
arithmetic itself) all confirm the core DEF-201 defect -- a fixed
relative-dB threshold crossed by ordinary programme tilt regardless of
whether a cliff exists -- is closed: none of the negative-control fixtures
produce a spurious result any more, and 4/5 real reference tracks report
plausible (>=10 kHz) values, an unambiguous improvement over "all five
report UNSTABLE" and "GusGus at 1979 Hz" (the original DEF-201 evidence).
The remaining Leftfield false positive is real, but is a DIFFERENT
mechanism (noise-driven spurious monotonicity in a fixed-tolerance
per-band test on real Welch estimates) from the ORIGINAL DEF-201 mechanism
(threshold-crossing on a smoothly declining, noise-averaged spectrum) --
conflating the two would misdiagnose a genuinely new, narrower finding as
"DEF-201 unfixed." Recommend a NEW defect number (not a DEF-201 reopen) be
raised by qa-automation-engineer once this is independently confirmed
against the corrected-schema automated suite, so the two mechanisms are
tracked distinctly.

### DEF-203 -- Status: Fixed.

**Retest (qa-automation-engineer):** TC-311/312/313 updated to the
channel-mean schema (`mono_sum_level_change_db`, `mono_sum_excess_cancellation`)
and corrected expected values (rho=+1→0 dB, rho=0→−3.0103 dB, anti-phase
< −15 dB). `test_ground_truth_stereo_width.py` TC-051/053/054/057 likewise
updated. `test_story004_baseline.py` retired (per its own instructions).
All three target tests pass; full edited-file suite 24 passed, 1 skipped.

### DEF-203 -- Status (prior): Fixed-Pending-Retest.

**H6: METHOD change, not a parameter change.** The broadband comparator no
longer divides `LUFS(mono_sum)` by BS.1770's channel-SUMMED stereo LUFS
(the mechanism that produced the -6.0206 dB rho=0 floor, correct for that
comparator but the wrong comparator per DOMAIN.md Section 3/CLAUDE.md's
precedence rule). It now divides by the CHANNEL-MEAN reference, computed in
the linear-power domain from each channel's own independent BS.1770-gated
measurement (architecture.md Section 2.1-2.2) -- giving the DOMAIN.md-
specified rho=0 floor of -3.0103 dB. The comparator itself changed, not
just the constant it is checked against.

**Files changed**:
- `suno_mastering/analysis/mono_sum.py`: full rewrite. `_lufs_to_linear`/
  `_linear_to_lufs`/`_channel_mean_lufs` implement the linear-power-domain
  averaging (Section 2.2); `_lufs_to_linear` raises `InvalidWavError`
  (reused, not duplicated) on a NaN LUFS input rather than silently
  propagating it. `measure_mono_sum` now calls `measure_integrated_lufs`
  independently on `left`, `right`, AND `mono_sum` (three independent
  BS.1770 gate decisions, the "open risk" architecture.md Section 2.2
  states explicitly, not formally bounded here). The both-channels-silent
  guard (Gate 1 advisory) is evaluated BEFORE any subtraction, exactly as
  Section 2.2 specifies -- confirmed empirically (see Verification below)
  that it correctly avoids the `(-inf)-(-inf) = NaN` hazard. Single shared
  `_DECORRELATED_FLOOR_DB = -3.0103 dB` constant now used by BOTH the
  broadband and per-band comparators (previously two different constants,
  `_BROADBAND_DECORRELATED_FLOOR_DB=-6.0206` and
  `_PERBAND_DECORRELATED_FLOOR_DB=-3.0103` -- the broadband one is deleted,
  not renamed; no reference to -6.0206 dB survives anywhere in the module).
- `suno_mastering/analysis/reference_types.py`: `MonoSumResult.level_change_db`
  -> `mono_sum_level_change_db`. `excess_cancellation_db` (a numeric field
  whose sign convention had already caused the same correct number to be
  reported as a bug three times -- DEF-101, DEF-104, DEF-203, per
  architecture.md Section 2.3) is REMOVED, not renamed -- replaced with a
  directly-named boolean, `mono_sum_excess_cancellation`. Added
  `mono_sum_both_channels_silent: bool = False` (Gate 1 advisory).
  `BandCancellation`'s constant reference renamed to the shared
  `_DECORRELATED_FLOOR_DB` -- no method change needed there (the per-band
  formula was already correct, per architecture.md Section 2.1's own
  observation).
- `suno_mastering/reference_analysis/config.py`: added
  `mono_sum_excess_cancellation_threshold_db: float = -4.5` (DOMAIN.md
  Section 3, one-sided trigger, architecture.md Section 2.3).
- `suno_mastering/reference_analysis/aggregate.py`:
  `mono_sum.level_change_db` -> `mono_sum.mono_sum_level_change_db` in the
  stereo-only aggregate. The `mono_sum.excess_cancellation_db` aggregate
  line is REMOVED (architecture.md Section 4 item 8 -- the corrected field
  is a boolean, not a median-appropriate metric); documented as a
  deliberate simplification in the aggregate line's own comment, not a
  silent loss -- the per-track boolean remains visible in
  `report/reference_render.py`'s per-track section.
- `suno_mastering/report/reference_builder.py`: `config_summary()` adds
  `mono_sum_excess_cancellation_threshold_db`; `SCHEMA_VERSION` bump shared
  with DEF-201 above (`"1.2"` -> `"2.0"`, one combined bump per
  architecture.md Section 8, not two separate ones).
- `suno_mastering/report/reference_render.py`: `_track_section()`'s
  mono-sum branch replaced the stale `excess_cancellation_db` f-string
  (which, after DEF-104's partial fix, correctly stated the NOW-REMOVED
  -6.02 dB floor -- doubly stale after this pass) with
  `mono_sum_level_change_db` and the `mono_sum_excess_cancellation`
  boolean, referencing the corrected -3.01 dB DOMAIN.md Section 3 floor.
  Added a distinct branch for `mono_sum_both_channels_silent = True`
  (Gate 1 advisory, architecture.md Section 4 item 10) rendering "both
  channels digitally silent -- mono-sum comparison not meaningful,"
  verified NOT to fall through to the normal-reading branch.

**Verification performed this pass** (synthetic signals, direct function
calls, matching architecture.md Section 2.2's own "verify by hand" table
exactly):

| rho (by construction) | `mono_sum_level_change_db` (measured) | `mono_sum_excess_cancellation` | Architecture.md Section 2.1 prediction |
|---|---|---|---|
| +1.0 (L=R exactly) | **0.0** | False | 0 dB |
| 0.0 (independent, equal-power noise, sigma=0.05) | **-3.0098** | False | -3.0103 dB |
| -1.0 (R=-L exactly) | **-inf** | True | -inf dB |
| N/A (both channels exact digital silence) | **0.0** (`mono_sum_both_channels_silent=True`) | False | 0 dB (the defined rho=1 limit) |

All four match the architecture.md Section 2.1 derivation to within
floating-point/finite-sample noise (-3.0098 vs. -3.0103 predicted, 0.0005
dB, well inside the DEF-101 precedent's own ~0.01 dB empirical tolerance).
No -6.0206 dB reference of any kind remains in `mono_sum.py` or
`reference_types.py` (grepped directly, confirmed).

**Real five-track reference set** (`Reference Tracks/*.wav`, 48 kHz):

| Track | `mono_sum_level_change_db` | `mono_sum_excess_cancellation` |
|---|---|---|
| Black Flute (Remastered) | -0.796 dB | False |
| GusGus -- Over (Arabian Horse) | -0.462 dB | False |
| Leftfield -- Melt | -0.521 dB | False |
| Chemical Brothers -- Live Again | -1.023 dB | False |
| Wavy Gravy | -0.946 dB | False |

**Matches requirements.md AC5's stated expectation exactly**: no track
shows excess cancellation, and every value is well above the old
-3.0...-4.5 dB "normal decorrelated" band the superseded comparator would
have predicted for correlated commercial material -- consistent with
DOMAIN.md Section 3's 0.5-0.9 correlation-plausibility range for
commercial electronic material (correlated content reads CLOSER to 0 dB
under the corrected channel-mean comparator, exactly as requirements.md's
DEF-203 section predicted: "correlated commercial references may
legitimately read closer to 0 dB"). No Architectural concern found for
DEF-203 on the real reference set -- unlike DEF-201 above, this fix's
real-world behavior matches its own design predictions without a residual
finding.

---

## STORY-004 v1.4 implementation pass (python-developer) -- DEF-201 candidate-selection/report-point refinement

Implements `stories/STORY-004/architecture.md` v1.4 Section 3.5 (and its
Section 4 item 12 / revision-history downstream-impact notes) against
`suno_mastering/analysis/hf_extension.py`. Per this pass's own task brief,
test files were again deliberately NOT modified (`tests/test_story004_baseline.py`
in particular -- QA's territory). No config field changed: v1.4 explicitly
introduces no new `ReferenceAnalysisConfig` field (a code change to
candidate selection/reporting, not a new tunable constant).

**Architect's pointer (v1.4 revision-history note, recorded verbatim as
instructed, since the architect agent could not edit this file directly):**

> Resolved in architecture.md v1.4 -- candidate selection is now
> max-total-drop across the full scan (not first-qualifying), and the
> reported point is the winning candidate's `centers[i+w]` (floor-onset
> band, not window start). Both changes are necessary jointly (Section
> 3.5's derivation). Recommend qa-automation-engineer raise this as a
> distinct defect from DEF-201 (different mechanism -- see the finding's
> own "This does NOT mean DEF-201's method change failed on its own
> terms" paragraph), track it through H7 closure once python-developer
> implements v1.4 and the new masked-wall fixture (Section 5.1) is
> confirmed failing against v1.3 and passing against v1.4.

### DEF-201 -- Status: Fixed-Pending-Retest (unchanged -- this pass does NOT close it).

**H6: METHOD change, not a parameter change.** `_detect_cliff`'s scan no
longer early-exits at the first qualifying candidate window; it now
collects every `(i, w, drop_db)` triple that passes all three tests
(slope, passband, floor) across the entire admissible range, selects the
entry with the largest `drop_db` (ties broken by lowest `i`), and returns
`centers[best_i + best_w]` -- the onset of the *winning* candidate's own
confirmed floor region -- instead of `centers[i]` of the first candidate
found. This is a genuine control-flow change (no early exit is possible
any more), not a threshold retune. Nothing else in `_detect_cliff` (the
passband gate, Section 3.4; the fixed 8.0 dB drop bar and monotonicity
test, Section 3.3) was touched. `mono_sum.py`/DEF-203 is untouched by this
pass.

**Criterion (a) -- Leftfield no longer reports a sub-10 kHz value --
HOLDS.** Re-run against the real five-track set (`Reference Tracks/*.wav`,
all 48 kHz), superseding the stale v1.3 table above in full:

| Track | `hf_band_limit_hz` | `confidence` | `stable` | `suspected_transcode` |
|---|---|---|---|---|
| Black Flute (Remastered) | 16727.3 Hz | 1.0 | True | False |
| GusGus -- Over (Arabian Horse) | 16727.3 Hz | 1.0 | True | False |
| **Leftfield -- Melt** | **22328.2 Hz** | 1.0 | True | False |
| Chemical Brothers -- Live Again | 21075.0 Hz | 0.4 | **False** | False |
| Wavy Gravy | 22982.5 Hz | 0.6 | True | False |

Leftfield's original AC2 violation (8125.5 Hz) is gone -- it now reports
22328.2 Hz, comfortably above the 10 kHz floor and inside DOMAIN.md
Section 2's CD/lossless range. No track reports `suspected_transcode=True`
under this re-run (a reclassification from the stale table's Wavy Gravy
entry, per architecture.md Section 3.6's v1.4 note -- confirmed, not
assumed).

**Criterion (c) -- synthetic positive fixtures localize within the v1.4
derived tolerance -- DOES NOT HOLD for two of the four required fixtures.
Stopping here per this pass's own task brief rather than forcing it.**

Direct calls to `measure_hf_extension` against the existing
`tests/ref_helpers.py` fixtures (not via pytest -- consistent with
"leave test files alone"):

| Fixture | True cutoff | Derived tolerance (Section 3.5) | Reported `hf_band_limit_hz` | Holds? |
|---|---|---|---|---|
| `brickwall_lowpass_noise_mono` @ 15000 Hz, 44.1 kHz (TC-020) | 15000 Hz | +-659.3 Hz | 15339.0 Hz | **yes** (but see caveat below) |
| `brickwall_lowpass_noise_mono` @ 8000 Hz, 44.1 kHz (TC-021) | 8000 Hz | +-351.6 Hz | **9387.9 Hz** | **NO** (+1387.9 Hz, ~4x the derived tolerance) |
| `brickwall_lowpass_noise_with_floor_mono` @ 16000 Hz, 27 dB floor, 44.1 kHz (TC-023) | 16000 Hz | +-703.3 Hz | **18241.2 Hz** | **NO** (+2241.2 Hz, ~3.2x the derived tolerance) |
| `tilted_then_brickwall_mono` @ 20000 Hz, -6 dB/oct tilt, 48 kHz (required v1.4 fixture) | 20000 Hz | +-879.1 Hz | 20475.1 Hz | yes |

Negative controls (criterion (b)) all hold, verified directly: `pink_noise_mono`
(44.1 kHz), `tilted_noise_mono` (-6 dB/oct, 48 kHz, no cutoff), and
`tilt_nonstationary_no_cutoff_mono` (44.1 kHz) all report `hf_band_limit_hz
is None`, `stable=True`, `confidence=1.0` -- unaffected by v1.4, as
Section 3.5 itself argued (an empty qualifying-candidate set cannot be
changed by a selection/report rule over a non-empty set).

**Root cause, confirmed by direct trace, NOT the previously-flagged Section
6 risk 12 (a genuine deeper secondary feature in real material) -- this is
a different, narrower, and stronger mechanism: estimator-noise-driven
argmax over near-tied candidates once `levels_db[i+w]` saturates at
`_MIN_POWER`.** On `brickwall_lowpass_noise_mono` (a hard FFT-zeroed
stopband -- literal digital silence above the cutoff, not a synthetic
approximation of a real floor), every candidate window whose far edge
`i+w` lands past the cutoff has `levels_db[i+w]` clamped to the exact same
`_MIN_POWER` floor value. Total drop for such a window is then
`levels_db[i] - _MIN_POWER`, so the argmax is decided entirely by which
passband band `i` drew the highest Welch-estimator noise realization --
not by which window is closest to the true edge. Traced directly on the
8 kHz fixture (`_detect_cliff`'s full candidate list, band index / window
size / drop dB / `centers[i]` / `centers[i+w]`):

```
i=50 w=8 drop=99.53  center_i=6449.2  center_i+w=8125.5   <- true edge (drop still partial: i+w=58 sits in the transition band, not yet fully clamped)
i=51 w=8 drop=134.04 center_i=6638.2  center_i+w=8363.6
i=52 w=8 drop=134.09 center_i=6832.7  center_i+w=8608.7
i=53 w=8 drop=133.99 center_i=7032.9  center_i+w=8861.0
i=54 w=8 drop=133.96 center_i=7239.0  center_i+w=9120.6
i=55 w=8 drop=134.10 center_i=7451.1  center_i+w=9387.9   <- WINNER (max drop, by 0.01 dB over i=52)
i=56 w=8 drop=133.90 center_i=7669.5  center_i+w=9662.9
i=57 w=8 drop=133.90 center_i=7894.2  center_i+w=9946.1
```

Candidates i=51..57 all sit within 0.2 dB of each other's total drop --
below Welch-estimator noise -- yet the selection rule (correctly
implemented per Section 3.5: strict max, ties broken by lowest `i`) picks
whichever is fractionally largest, `i=55`, reporting a value 1387.9 Hz
past the true edge rather than `i=50`'s `centers[i+w]=8125.5` (the figure
architecture.md's own Section 3.5 table cites as the "+125.5 Hz" observed
error for this exact fixture -- that number is the FIRST-qualifying
candidate's `i+w`, not the max-drop-selected one; the two rules diverge
here even though the fixture has only one real wall and no second
feature). The same mechanism reproduces on TC-023 (a real, non-clamped,
27 dB-deep floor -- so this is not purely a `_MIN_POWER`-clamp artifact;
a sufficiently flat real floor produces the identical near-tied-argmax
problem) and on the real reference set: Black Flute's winning candidate
(9.28 dB @ `i=75`) is tied to two decimal places with its immediate
predecessor (9.28 dB @ `i=74`, `centers[i+w]=16251.1` vs the selected
`16727.3`); Chemical Brothers has two candidates 0.58 dB apart (42.92 dB
@ `i=83` -> 21075.0 Hz vs 42.34 dB @ `i=85` -> 22328.2 Hz) and reports
`confidence=0.40`, `stable=False` -- **independent corroborating evidence
from the per-segment mechanism itself**: CLAUDE.md Section 5's own named
pattern ("reporting a fixed property as varying... instability means the
method is wrong") applies directly here, since a near-tied whole-track
argmax is exactly the condition under which different segments' own
Welch-noise realizations can select different winners.

**Leftfield's own full candidate list**, included per architecture.md
Section 5.3's explicit requirement (record every qualifying candidate, not
just the winner) and because it shows the architect's own Section 5.3
orientation estimate (~20475 Hz) is NOT what max-drop selection reports:

```
i=58 w=8 drop=9.29  center_i=8125.5   center_i+w=10237.5   (the old masking candidate -- correctly out-ranked)
i=82 w=8 drop=34.51 center_i=16251.1  center_i+w=20475.1   <- architecture.md Section 5.3's own predicted true wall
i=83 w=8 drop=56.48 center_i=16727.3  center_i+w=21075.0
i=84 w=8 drop=56.99 center_i=17217.4  center_i+w=21692.6
i=85 w=8 drop=57.49 center_i=17721.9  center_i+w=22328.2   <- WINNER (max drop)
i=86 w=8 drop=56.26 center_i=18241.2  center_i+w=22982.5
i=87 w=7 drop=55.31 center_i=18775.7  center_i+w=22982.5
i=88 w=6 drop=54.70 center_i=19325.9  center_i+w=22982.5
i=89 w=5 drop=53.23 center_i=19892.2  center_i+w=22982.5
```

`i=82` (the candidate matching the architect's own orientation estimate)
is correctly out-ranking the old masking candidate at `i=58` -- the v1.4
fix's core purpose IS working, the masking-by-shallow-decline defect is
closed. But `i=82` is itself out-ranked by `i=83`/`i=84`/`i=85`, all of
which start WITHIN what should be classified as the real wall's own floor
(`centers[i]` from 16727 to 17722 Hz, past the 16251 Hz onset of the true
wall at `i=82`) and whose drop keeps climbing before falling off again at
`i=86`. This is structurally the Section 6 risk-12 pattern (a deeper
feature inside an already-established floor winning over an earlier
genuine wall) but manifesting on the SAME wall's own floor structure, not
a second, independently-real feature -- confirming risk 12's predicted
failure mode was materializing on Leftfield itself, the very track this
v1.4 revision was written to fix, not only on the Black Flute/GusGus cases
Section 6 risk 12 named as the ones to watch. (Black Flute and GusGus were
checked directly too, per Section 5.3's explicit instruction: GusGus's
winner, 21.68 dB @ `i=75`, is unambiguous -- next-best is 20.11 dB, a real
3.3x-noise-floor margin, not a near-tie; Black Flute's winner IS a
near-tie, as shown above.)

**Not adopted here, per H6 and this pass's own scope**: no fix is applied
in code. A python-developer does not have standing to redesign a
specified selection rule without a derivation (same standing this file's
own prior DEF-201 finding took). This is empirically a DIFFERENT, further
gap from the one v1.4 closed -- v1.4's fix (report `centers[i+w]` of the
max-drop winner; scan the full range, no early exit) is faithfully
implemented exactly as Section 3.5 specifies and correctly closes the
masking-by-shallow-decline mechanism it targeted (confirmed on Leftfield's
own `i=58` vs `i=82` comparison above, and on all three negative
controls). What remains open is a second, narrower mechanism: near-tied
argmax over multiple overlapping windows whose far edge lands in a flat
(clamped or genuinely quiet) floor region, where the winner is decided by
sub-noise differences in Welch estimation rather than by which window is
closest to the true edge. Recommend the same disposition the architect's
pointer above already anticipates for this class of finding: raised here
as **Architectural** for Gate 2 review, distinct from both the original
DEF-201 mechanism (threshold-crossing on ordinary tilt) and the v1.3->v1.4
masking mechanism (first-candidate-wins stopping short of a real wall) --
this is a third, distinct mechanism (near-tied max-drop argmax under a
flat/clamped floor), not a reopening of either prior fix, and not
resolvable by retuning `hf_cliff_floor_noise_margin_db` or
`hf_cliff_floor_min_fraction` (per H6, tuning a judgment-call constant
against a method-level argmax-stability gap would repeat the exact
"numbers changed, method still wrong" pattern CLAUDE.md Section 5 names).
Two directions worth the architect's consideration, not prescribed:
(i) a depth-relative-to-passband discriminator that scores candidates by
how far their window's start sits below the passband reference level,
rather than raw endpoint-to-endpoint drop, so windows whose start is
already deep inside a prior floor cannot out-rank the window at the
genuine passband-to-floor transition; (ii) requiring the winning
candidate's own passband precondition to be evaluated at a point
demonstrably still in the ordinary passband (not itself already past a
prior qualifying candidate's floor onset). Section 6 risk 12's own
proposed remedy (a depth-relative-to-passband discriminator) is consistent
with (i) above and was not adopted here for the same reason: no standing
to redesign the specified rule without a derivation.

**Verification performed this pass** (targeted, direct function calls per
`tests/ref_helpers.py`'s existing fixtures, not via pytest): `python -c
"import suno_mastering.analysis.hf_extension"` and the full package import
both succeed cleanly, no syntax/reference errors. All numbers in the
tables above were measured directly against the current code, not
estimated or carried forward.

### DEF-201 -- Architect resolution (STORY-004 v1.5)

Resolved in architecture.md v1.5. The third, distinct mechanism this
pass raised as Architectural (near-tied max-drop argmax under a
flat/clamped floor) is fixed by removing candidate selection entirely:
localization is now a single-pass floor-onset rule (track a passband
baseline left-to-right with a terminal freeze on the first sustained
trailing-octave break, then find the unique first band, scanning
right-to-left via suffix-max, whose remaining spectrum never recovers
above passband_level - required_drop). The existence gate (Section
3.3/3.4) is unmodified. There is no candidate list and no argmax
anywhere in the new design, so the near-tied-argmax mechanism this
finding identified cannot recur by construction (architecture.md
Section 3.5's up-set/suffix-max argument). This is a further METHOD
change on top of v1.4 (H6), not a parameter change and not a
reopening of v1.4's own masking fix, which remains correct and is
carried forward unmodified (v1.4's Step-0/gate design is now Step 0 of
the v1.5 procedure). python-developer's hf_extension.py candidate-
collection-and-argmax code (the block implementing v1.4's Section 3.5)
is now stale in full and must be deleted, not patched. The v1.4
five-track table above is stale for a second time and must be
re-measured under v1.5; architecture.md Section 5.3 requires a
per-band trace dump (freeze index, j*, suffix_max near j*) as the
verification artifact this time, not just the winning value. Recommend
qa-automation-engineer track this as a distinct H7 closure item from
both DEF-201's original mechanism and the v1.4 masking-fix mechanism,
requiring the new required risk-12-closing fixture (architecture.md
Section 5.1) to be confirmed passing before closure.

---

### DEF-201 -- Gate 2 review and closure (STORY-004 v1.5a)

**Verdict: CLOSED.** Gate 2 mastering-engineer review (`stories/STORY-004/
gate2-review-v1.5a.md`, 2026-08-08) verdict PASS-WITH-FINDINGS. Whole-track
localization is physically plausible and correctly implemented for all five
reference tracks. DEF-201's root cause (wrong method producing 1979 Hz on a
CD master) is confirmed resolved.

**Gate 2 per-track summary (v1.5a measured values):**

| Track | v1.4 Hz | v1.5a Hz | stable | conf | margin_dB | plausible |
|---|---|---|---|---|---|---|
| Black_Flute | 16727.3 | 15788.4 | True | 1.0 | 0.39 (min 0.08) | Yes — mid-bitrate lossy source |
| GusGus | 16727.3 | 16251.1 | True | 1.0 | 7.35 | Yes — lossy source |
| Leftfield | 22328.2 | 20475.1 | True | 1.0 | 22.99 | Yes — architecture prediction confirmed exactly |
| Chemical_Bros | 21075.0 | 20475.1 | False | 0.4 | 25.79 | Yes — honest report on variable material |
| Wavy_Gravy | 22982.5 | 20475.1 | True | 0.6 | 19.48 | Yes — stable=True by 0.0 margin |

**Architecture prediction failure (Chemical Brothers) — documented, not reopening DEF-201.**
Architecture.md §3.7 predicted v1.5a would fix Chemical Brothers stable=False/confidence=0.4.
It did not. The mechanism changed (v1.4: argmax saturation; v1.5a: segments 2+5 returned
None via honest gate abstention; segment 1 fired at i_max=71≈12502 Hz and localized to
14066 Hz — a gate false positive on programme content). The whole-track output is
correct (20475.1 Hz, 25.79 dB margin). stable=False is the correct, honest report
for a track where only 2/5 segments find the wall unambiguously. This is not a DEF-201
defect — the system is reporting what it can measure. The segment 1 false positive on real
programme material is raised as a separate defect (DEF-205 below).

**SRC vs. transcode question — flagged for STORY-005, not a DEF-201 blocker.**
All three ~20475 Hz tracks (Leftfield, Chemical Brothers, Wavy Gravy) fall in
transcode_suspect_bands (19500–20500 Hz). The mastering-engineer notes two competing
hypotheses: (A) high-bitrate lossy files with 20 kHz lowpass, or (B) 44.1 kHz sources
SRC'd to 48 kHz by this project (anti-alias passband ending at 0.929 × 22050 = 20484 Hz).
Three tracks landing at the same grid band is stronger evidence for Hypothesis B.
STORY-005 must resolve this before deriving HF extension targets.

**Open items raised by Gate 2 (not DEF-201 blockers):**
- DEF-205: segment 1 gate false positive on Chemical Brothers real material
- DEF-206: Black Flute confidence=1.0 with 0.08 dB per-segment margin (confidence
  metric blind to adjacent-band uncertainty at current 2000 Hz tolerance)
- STORY-005 prerequisite: determine whether the three 48 kHz / 20475 Hz tracks
  were SRC'd from 44.1 kHz originals (Hypothesis B) or are genuinely lossy-sourced

---

### DEF-201 -- Architect resolution (STORY-004 v1.5a)

Gate 1 v1.5 Blocker resolved. The mastering-engineer Gate 1 review of
v1.5 (stories/STORY-004/gate1-review-v1.5.md, Finding 1) identified a
Blocker: architecture.md Section 3.5 Step 1 re-used
`hf_cliff_passband_max_slope_db_per_octave` (12 dB/oct) as a positive
detection trigger (the passband tracker froze when the trailing-octave
slope exceeded this value), but its derivation in Section 3.4 supports
only a rejection criterion (gate rejects candidates whose pre-slope
already exceeds this value → outcome is None; safe). On real
CD-sourced material with ordinary steep air-band roll-off — conceded as
plausible in Section 3.4 horn (a) itself — the tracker froze mid-air-
band, anchored `passband_level` in the 8–12 kHz region, and produced a
wrong number (not None). Same structural failure as DEF-201, transposed
to the top end of the spectrum.

Resolution (v1.5a): the passband tracker loop is eliminated entirely.
`freeze_index = i_max`, where i_max is the highest-frequency gate-
qualifying candidate start returned by `_gate_scan` (renamed from
`_gate_admits_any`; signature now Optional[int] instead of bool). The
gate scan already runs the three-test cliff criterion (slope, passband,
floor); using its highest-qualifying start as the freeze point means
the localization anchors exactly at the gate's own highest-confidence
candidate, not at a 12 dB/oct trailing-octave trip that fires
independently of gate admission. The 12 dB/oct constant remains confined
to its original derived role: rejecting gate candidates whose pre-slope
is already indistinguishable from a cliff.

Implementation: python-developer has replaced the v1.5 trailing-octave
tracker loop with `freeze_index = i_max; passband_level =
levels_db[freeze_index]` in `hf_extension.py::_detect_cliff`. The
function `_track_passband_level` was never implemented (eliminated at
architecture stage). `_gate_scan` returns Optional[int] (i_max or None)
instead of bool. `_floor_onset_index` is unchanged. A new required
fixture (steep air-band pre-slope, 10-11 dB/oct, brickwall at 20 kHz,
SR=48000) is specified in architecture.md Section 5.1 and must be added
to the test suite (test-case-writer scope) before closure. All existing
positive ground-truth fixtures (TC-020, TC-021, TC-023) pass under
v1.5a; TC-022 and TC-024 now correctly return None (fixed from stale
threshold-era assertions). The drift-stability fixtures (TC-025, TC-028,
TC-308) required richer drift construction (three-step or 5s+20s splits)
to maintain stable=False under v1.5a's highest-frequency-first whole-
track selection.

**Steep-air-band fixture closure (2026-08-09, test-case-writer):**
`steep_air_band_brickwall_mono` helper added to
`stories/STORY-001/implementation/tests/ref_helpers.py`; test
`test_steep_air_band_brickwall_20k_48k` added to
`test_ground_truth_hf_extension.py`. Signal: flat noise below 4 kHz,
A(f) = (f/4000)^(-a) above it where a = 10.5/(20*log10(2)) ≈ 1.7441,
brickwalled at 20 kHz, SR=48000. Construction-time slope verification
confirms 10–11 dB/oct (target 10.5 dB/oct ± 0.5 dB Welch noise, upper
bound 11.5 dB/oct, firmly below the 12 dB/oct gate-rejection ceiling) in
octave windows whose upper band center falls in 10 kHz to 19714 Hz (band
top edge strictly below 20 kHz). Measured: hf_band_limit_hz passes
pytest.approx(20000.0, abs=879.1), stable=True,
hf_band_limit_robustness_db is not None. Full suite: 11 passed, 3 skipped
(pre-existing placeholders).

---


*--- Section 3: DEF-206 Gate 2 review (Confidence metric, Black Flute) ---*

## DEF-206 — Confidence metric blind to adjacent-band uncertainty (Black Flute)

**Status**: Closed  
**Triage**: Code-level  
**Raised by**: mastering-engineer Gate 2 review (2026-08-08), `stories/STORY-004/gate2-review-v1.5a.md`

On Black_Flute_Remastered.wav, segment 2 has a j* margin of 0.08 dB — within Welch
estimator noise. The adjacent band (band 82, 16251 Hz) is 463 Hz away. On re-measurement,
segment 2 could shift from band 81 (15788 Hz) to band 82 (16251 Hz). However, because
`hf_stability_tolerance_hz = 2000 Hz` is too coarse to see a 463 Hz adjacent-band
shift, `confidence = 1.0` in both cases. `confidence = 1.0` does not bound localization
robustness here — it indicates the metric cannot see this quantization risk.

The whole-track measurement is robust (0.39 dB margin, same grid band on all five
segments in actual observation). The defect is in what confidence claims: it reports
"maximum agreement" when a neighbouring segment's agreement is below Welch noise and
could flip on re-measurement.

**Required**: Either (a) confidence metric incorporates a per-segment margin as a
secondary factor to discount thin-margin agreements, (b) hf_stability_tolerance_hz is
documented as deliberately coarse with an explicit caveat that adjacent-band uncertainty
(< tolerance) is not captured, or (c) a separate `hf_band_limit_robustness_db` field
reports the minimum per-segment margin, allowing callers to gate on it independently.

**Resolution (STORY-004 closure pass, 2026-08-09):** Option (c) selected. Additive field
`hf_band_limit_robustness_db: Optional[float] = None` added to `HfExtensionResult`.
Populated as `min(L_seg - suffix_max_seg[j*_seg], levels_db_seg[j*_seg - 1] - L_seg)` —
two-sided minimum (rightward and leftward j* margin) across all per-segment cliff
detections. Two-sided formula chosen over rightward-only after mastering-engineer review
showed leftward fragility is equally real on gradual-cliff material; the clean-brickwall
derivation confirms leftward_margin ≈ `hf_cliff_required_drop_db` (8.0 dB) for any
gate-confirming cliff (structural upper bound, not an empirical constant). Architecture
§11 updated with revised fixture 2 assertion (`≈ 8.0 ± 1.0 dB`, replacing misleading
`> 50 dB`). `SCHEMA_VERSION` `"2.0"` → `"2.1"` (MINOR). Three new tests: TC-430
(rightward-dominated, ≈ 2.0 ± 0.5 dB), TC-431 (leftward-dominated, ≈ 8.0 ± 1.0 dB),
TC-432 (None-branch, negative controls). H5 real-output check: Black Flute 90 s →
`hf_band_limit_robustness_db = 0.013 dB` (physically plausible — minimum of ten two-sided
margins across five segments on a gradual-cliff track). Suite: 282 passed, 0 failures.
Mastering-engineer H5 review: no blocker; renderer functionally correct (cosmetic markdown
precision gap `_fmt(0.013, 2)` → "0.01 dB" vs JSON 0.013 noted, not a defect).

**Status: Closed.**

---


---

## STORY-006

*Active defects retained in stories/STORY-006/defects.md: DEF-605 (Fixed-Pending-Retest),*
*DEF-609 (Open/Architectural).*

## DEF-601

**Status:** Closed  
**Reported by:** qa-automation-engineer  
**Linked test cases:** TC-612, TC-613, TC-614, TC-617, TC-620, TC-622, TC-623, TC-625, TC-627, TC-647

**Description:**

`SpectralCorrectiveAction` dataclass (in `suno_mastering/mastering/corrective_eq.py`) is missing two required fields defined by architecture §7.1:

- `source_db` (float) — the measured pre-correction band level passed in via `pre_band_levels`
- `aim_point_db` (float) — the correction aim point (range_min/range_max for range_compliance, or `de_mud.correction_aim_point_db` for de_mud trigger)

Current dataclass fields: `band`, `trigger`, `applied_db`, `resulting_db`, `cap_reached` (5 fields).  
Architecture §7.1 requires: `band`, `trigger`, `source_db`, `aim_point_db`, `applied_db`, `cap_reached`, `resulting_db` (7 fields).

The absence of `aim_point_db` is the most critical gap. At source levels where both aim points (+2.0 dB and +3.394 dB) produce the same `applied_db` (capped at -2.0 dB), `aim_point_db` is the **only** log-field discriminator for AC19 (TC-623). Without it, an incorrect implementation using aim +3.394 cannot be detected at high source levels.

Measured: `SpectralCorrectiveAction(band='sub', trigger='range_compliance', applied_db=2.0, resulting_db=-4.247, cap_reached=True)` — no `source_db` or `aim_point_db` attributes.

**Triage:** Code-level  
**Fix notes:** **Parameter change: No. Method change: No. Field addition to dataclass.**  
Added `source_db: float` and `aim_point_db: float` to `SpectralCorrectiveAction` in `mastering/corrective_eq.py` in the order specified by architecture §7.1 (`band`, `trigger`, `source_db`, `aim_point_db`, `applied_db`, `cap_reached`, `resulting_db`). Populated in `apply_corrective_eq`: `source_db = src_sub` (or `src_lm`), `aim_point_db = aim_sub` (nearest range edge for range_compliance) or `de_mud_aim` (for de_mud trigger). Smoke check confirmed: `SpectralCorrectiveAction` with `source_db=-5.0` and `aim_point_db=-3.7467` emitted for sub band below range. Also removed the `.get()` fallback literals for correction_cap_db and de_mud thresholds (using direct dict indexing since DEF-604 guarantees the keys exist). Fixed simultaneously with DEF-601 in `corrective_eq.py` rewrite.

**QA closure (2026-08-12):** TC-612 to TC-627 pass. All 7 required `SpectralCorrectiveAction` fields verified present with correct values (source_db, aim_point_db, applied_db, cap_reached, resulting_db, band, trigger). H5 plausibility: applied_db values are in [-2.0, +2.0] range; resulting_db = source_db + applied_db arithmetic identity holds. H6: field addition, no parameter change. Closed.

---

## DEF-602

**Status:** Closed  
**Reported by:** qa-automation-engineer  
**Linked test cases:** TC-630, TC-632, TC-634, TC-637, TC-647

**Description:**

`WidthCorrectiveAction` dataclass (in `suno_mastering/mastering/stereo_width_corrector.py`) is missing three required fields defined by architecture §7.2:

- `trigger` (str) — must be `"width_above_threshold"` when width > near_mono_threshold
- `source_value` (float) — the measured pre-correction band width from `pre_widths`
- `resulting_value` (float) — the predicted post-correction width = `source_value + applied`

Current dataclass fields: `band`, `aim_point`, `applied`, `cap_reached` (4 fields).  
Architecture §7.2 requires: `band`, `trigger`, `source_value`, `aim_point`, `applied`, `cap_reached`, `resulting_value` (7 fields).

Measured on TC-632 (sub=0.20, cap not binding): `WidthCorrectiveAction(band='sub', aim_point=0.15, applied=-0.05, cap_reached=False)` — no `trigger`, `source_value`, `resulting_value`.

`resulting_value` is critical for the floor assertion: architecture §6.4 requires `resulting_value >= 0.10` (correction_floor), and without this field the constraint cannot be programmatically verified.

**Triage:** Code-level  
**Fix notes:** **Parameter change: No. Method change: Yes (fields added, algorithm replaced simultaneously with DEF-603).**  
Rewrote `stereo_width_corrector.py` to add `trigger: str`, `source_value: float`, `resulting_value: float` to `WidthCorrectiveAction` in the order specified by architecture §7.2. Set `trigger = "width_above_threshold"`, `source_value = w_src` (pre-correction per-band width), `resulting_value = w_src + applied` (arithmetic = w_target). The `resulting_value` is now checked by post-condition assertion `assert resulting_value >= floor` (§6.4). Smoke check confirmed: AC20 case (sub=0.60) produces `aim_point=0.15`, `applied=-0.15`, `resulting_value=0.45`, `cap_reached=True`. Fixed simultaneously with DEF-603.

**QA closure (2026-08-12):** TC-630 to TC-637 pass. All 7 required `WidthCorrectiveAction` fields present with correct values. resulting_value >= correction_floor (0.10) verified. H6: field addition + algorithm replacement, not a parameter change. Closed.

---

## DEF-603

**Status:** Closed  
**Reported by:** qa-automation-engineer  
**Linked test cases:** TC-630, TC-634, TC-637, TC-638

**Description:**

The stereo width correction algorithm in `suno_mastering/mastering/stereo_width_corrector.py` has three independent departures from architecture §6.3, §6.5:

**1. Wrong gain formula.** The implementation uses a broadband linear side-channel scale:
```
scale = 1 - (applied / max(src, 1e-6))
```
Architecture §6.3 requires:
```
g = sqrt(w_target * (2 - w_src) / (w_src * (2 - w_target)))
```
where `w_target = max(aim_point, w_src - max_step)`.

For the canonical TC-630 case (w_src=0.60, cap applies → w_target=0.45):
- Architecture formula: `g = sqrt(0.45 * 1.40 / (0.60 * 1.55)) = sqrt(0.677) = 0.823`
- Implementation formula: `scale = 1 - 0.15/0.60 = 0.75`

These are different filter gains that produce different resulting widths.

**2. No per-band bandpass filtering.** Architecture §6.5 requires an 8th-order Butterworth bandpass filter isolating the target band before applying the M/S gain operation. The implementation applies M/S narrowing to the full broadband signal. When both sub and low bands trigger, the entire signal is narrowed twice, affecting mid-band stereo image — which requirements §8 explicitly puts out of scope.

**3. Hardcoded correction parameters; targets dict not consulted.** The implementation hardcodes `aim_point = 0.15` and `cap = 0.15` (lines 29-30 of `stereo_width_corrector.py`), ignoring the `targets` argument. The `stereo_width` block (near_mono_threshold, correction_aim_point, correction_floor, max_correction_step) is never read. This violates AC13.

**Critical distinction (H6):** Items 2 and 3 are method-level errors. Adding the correct per-band bandpass cannot be achieved by adjusting the linear scale coefficient. A parameter change fixing `scale` cannot close this defect — the filter design must be replaced.

TC-638 confirms the method defect: `stereo_width_corrector.py` does not import `measure_per_band_stereo_width`, which is required by architecture §6.2 for consistency of pre- and post-correction measurement.

**Triage:** Code-level  
**Fix notes:** **Parameter change: No. Method change: Yes on all three points (H6).**  
(1) Gain formula: replaced `scale = 1 - (applied / max(src, 1e-6))` with the architecture §6.3 formula `g = sqrt(w_target * (2 - w_src) / (w_src * (2 - w_target)))`, where `w_target = max(aim_point, w_src - max_step)` (cap in width units, not in g). (2) Per-band bandpass filter: added `_apply_band_narrowing(audio, sr, band_hz, g)` helper using `scipy.signal.butter(order=8, btype='bandpass', output='sos')` + `sosfiltfilt` per architecture §6.5; delta-add approach avoids full-reconstruct artefacts. (3) Targets read from `targets["stereo_width"][band]`: reads `near_mono_threshold`, `correction_aim_point`, `correction_floor`, `max_correction_step` per band (no hardcoded literals). All three are method changes; none can be fixed by parameter tuning. Regarding TC-638 (asserts import of `measure_per_band_stereo_width`): architecture §6.2 explicitly prohibits a second width estimator inside `stereo_width_corrector.py`; the module does not import that function and uses `pre_widths` from Stage [2] as specified. TC-638's import assertion conflicts with §6.2. Raised as DEF-611 against test-cases.md; test updated to assert correct §6.2 behavior.

**QA closure (2026-08-12):** TC-630 audio measurement passes with engineered width-060 fixture (sub-band width ≈ 0.60 → corrects to 0.45 ± 0.05). TC-637 passes with width-080 fixture (0.80 → 0.65 ± 0.07). Width formula verified: g = sqrt(w_target*(2-w_src)/(w_src*(2-w_target))). H5 plausibility: g values in [0.82, 0.85]; resulting widths within ±0.07 of target (Welch variance for narrow 20-60 Hz band). H6: method change confirmed. Closed.

---

## DEF-604

**Status:** Closed  
**Reported by:** qa-automation-engineer  
**Linked test cases:** TC-602, TC-603, TC-604, TC-605, TC-611

**Description:**

`suno_mastering/targets/targets_generator.py` produces a `targets.json` that diverges from the schema defined in architecture §7/§8 in five distinct ways:

**1. `dynamic_range_db` wrong key names (TC-602):**
Generator emits `{"min": ..., "max": ..., "median": ...}`.  
Architecture §7.3 requires `{"target_median": ..., "range_min": ..., "range_max": ...}`.

**2. `spectral_bands[band]` missing `classification` and `correction_cap_db` (TC-603):**
Generator emits only `freq_hz`, `range_db_re_mid`, `median_db_re_mid`.  
Architecture requires `classification` (e.g., "soft" for sub/low_mid, "informational" for others) and `correction_cap_db` (2.0 for corrected bands).

**3. `de_mud` missing `applies_to_band` (TC-604):**
Generator emits only `flag_threshold_db_above_mid` and `correction_aim_point_db`.  
Architecture §7.4 requires `applies_to_band: "low_mid"`.

**4. Air band lower edge formula wrong (TC-605):**
Generator uses `int(air_upper * 0.6)` as the high/air boundary: for air_upper=22050 this gives 13230 Hz; for air_upper=24000 gives 14400 Hz.  
Architecture §8.1 and the seven-band analysis scheme (`reference_analysis/config.py` SEVEN_BANDS_HZ) define the boundary at 10000 Hz (fixed).

**5. `stereo_width` block absent; wrong key name (TC-611):**
Generator emits `per_band_stereo_width` (with only `min`, `max`, `median` per band).  
Architecture §7.5 requires a `stereo_width` block with `near_mono_threshold`, `correction_aim_point`, `correction_floor`, `max_correction_step` per band (in addition to the statistical data).

Note on real track sample rates: all five reference tracks are at 48000 Hz (Nyquist=24000 Hz), so the actual generated `air_upper_edge_hz` is 24000 Hz — consistent with the formula but inconsistent with the architecture's assumption of 44100 Hz tracks. Architecture §4.3 states "All three contributing tracks are expected to be at 44100 Hz." This is factually incorrect; the architecture document should be updated to reflect 48000 Hz tracks. The generator formula is correct; the architecture's stated expected value is wrong.

**Triage:** Code-level  
**Fix notes:** **Parameter change: No. Method change: No (schema additions and key renames).**  
Five fixes applied to `targets/targets_generator.py`: (1) `dynamic_range_db` keys renamed: `min`→`range_min`, `max`→`range_max`, `median`→`target_median`; (2) Added `classification` (`"soft"` for sub/low_mid, `"informational"` for others) and `correction_cap_db` (2.0 for sub/low_mid only) to each `spectral_bands` entry; (3) Added `"applies_to_band": "low_mid"` to `de_mud`; (4) Replaced `int(air_upper * 0.6)` formula with fixed 10000 Hz boundary for both high (5000–10000 Hz) and air (10000–air_upper) bands; (5) Renamed `per_band_stereo_width` to `stereo_width` and added per-band correction params (`near_mono_threshold=0.15`, `correction_aim_point=0.15`, `correction_floor=0.10`, `max_correction_step=0.15`). Updated `targets/schema.py`: added `stereo_width: Dict[str, Any]` field, added `"stereo_width"` to required keys, raises `TargetsLoadError` instead of `ValueError`. Updated `TargetsDocument.to_dict()` to include `stereo_width`. Regenerated `targets.json` from the actual reference set — all five schema issues confirmed resolved in the new file. Architecture §4.3 states 44100 Hz sample rate; actual tracks are 48000 Hz — noted in generator docstring as factually incorrect in the architecture; generator formula is correct (produces 24000 Hz from actual tracks).

**QA closure (2026-08-12):** TC-601 to TC-611 all pass. Key verifications: dynamic_range_db keys = {range_min, range_max, target_median}; spectral_bands.sub has classification='soft' and correction_cap_db=2.0; de_mud.applies_to_band='low_mid'; air band freq_hz=[10000, 24000] from 48000 Hz tracks; stereo_width block has near_mono_threshold, correction_aim_point, correction_floor, max_correction_step per band. H5 plausibility: air upper edge 24000 Hz matches min(24000, Nyquist=24000) formula. Closed.

---
## DEF-606

**Status:** Closed  
**Reported by:** qa-automation-engineer  
**Linked test cases:** TC-648, TC-649

**Description:**

`suno_mastering/errors.py` does not define `TargetsLoadError`. AC22 and TC-648/TC-649 require that missing or malformed `targets.json` raises `TargetsLoadError` (a named error subclass of `MasteringError`) so callers can handle this case distinctly from audio format errors.

Current behavior:
- Missing file: `loader.py` raises bare `FileNotFoundError` (not a `MasteringError` subclass)
- Missing schema key: `schema.py` raises bare `ValueError` (not a `MasteringError` subclass)
- Neither raises an error before Stage [1] — the pipeline fails when loading the file, not before ingest

**Triage:** Code-level  
**Fix notes:** **Parameter change: No. Method change: No (error type addition and wrapping).**  
(1) Added `TargetsLoadError(MasteringError)` to `errors.py` with `path: str` attribute per architecture §7.3 contract. (2) Updated `loader.py`: checks `path is None` → `TargetsLoadError`; wraps `FileNotFoundError` → `TargetsLoadError(message, path=path)`; wraps `json.JSONDecodeError` → `TargetsLoadError`. (3) Updated `schema.py` `from_dict()`: raises `TargetsLoadError` instead of `ValueError` on missing required keys; added `"stereo_width"` to required list. (4) Updated `pipeline.py`: `load_targets()` called before Stage [1] unconditionally — `TargetsLoadError` propagates immediately (no audio processing). `config.targets_json_path = None` (the current default) is a hard failure; tests must set it explicitly. Default kept as `None` since architecture §14's stated default path (`implementation/targets.json`) does not match the actual committed location (project root `targets.json`).

**QA closure (2026-08-12):** TC-648 (missing file → TargetsLoadError with path attribute) and TC-649 (malformed JSON / missing key → TargetsLoadError) both pass. `TargetsLoadError` confirmed subclass of `MasteringError`. `path` attribute present and matches the supplied path. H5 plausibility: error raised before any Stage [1] audio processing (confirmed by TC-648 measuring zero audio reads before the exception). H6: error type addition, not a parameter change. Closed.

---

## DEF-607

**Status:** Closed  
**Reported by:** qa-automation-engineer  
**Linked test cases:** TC-618, TC-624, TC-629 (indirectly — band mapping affects Stage [9] derivations); TC-645, TC-646 (blocked — require `seven_band` data in mastering report, which is unavailable because `Measurements` has no `seven_band` field)

**Description:**

`pipeline.py` constructs `pre_band_levels` for the targets-based corrective EQ using incorrect frequency band measurements:

```python
# pipeline.py lines ~144-148
pre_band_levels = {
    "sub": before.frequency_balance.low_end.relative_db,      # measures (20, 120) Hz
    "low_mid": before.frequency_balance.low_mid_mud.relative_db,  # measures (200, 500) Hz
    "mid": 0.0,
}
```

Architecture §5.1 and the corrective EQ design require measurements from the **seven-band** analysis:
- `sub` should come from `before.seven_band.sub` (20–60 Hz)
- `low_mid` should come from `before.seven_band.low_mid` (120–500 Hz)

The substituted bands are:
- `before.frequency_balance.low_end` measures 20–120 Hz (double the sub band's range, includes the "low" band 60–120 Hz)
- `before.frequency_balance.low_mid_mud` measures 200–500 Hz (excludes 120–200 Hz, which is architecturally part of low_mid)

This means the correction decision is made on a different frequency range than what the corrective filter is designed to operate on. Stage [9] measurements after correction will not match the analytical derivations in test-cases.md because the correction strength was determined by the wrong input measurement.

**Triage:** Code-level  
**Fix notes:** The `Measurements` dataclass (in `suno_mastering/analysis/types.py`) has NO `seven_band` attribute. The seven-band result exists only on `ReferenceTrackResult` (in `suno_mastering/analysis/reference_types.py`), which is produced by the reference analysis pipeline, not by the mastering pipeline's `measure_all()` call.

Two viable fix paths:

(a) Add `seven_band: SevenBandResult` to `Measurements` and have `measure_all()` compute it via `seven_band_balance.measure_seven_band_balance()`, then access `before.seven_band.bands` in `pipeline.py`.

(b) Have `pipeline.py` call `seven_band_balance.measure_seven_band_balance(audio, sr, ref_cfg)` directly before Stage [5.1] to obtain a fresh seven-band reading, independent of the `Measurements` object.

Either path requires: `seven_band_map = {b.band: b.relative_db for b in seven_band.bands}`, then:
```python
pre_band_levels = {
    "sub":    seven_band_map.get("sub", 0.0),    # 20–60 Hz
    "low_mid": seven_band_map.get("low_mid", 0.0), # 120–500 Hz
    "mid":    seven_band_map.get("mid", 0.0),
}
```

Note: TC-618/624/629/645/646 cannot be written as meaningful automated tests until this defect is resolved:
- TC-618/624/629: attribute Stage [9] measurements to the corrective EQ decision, which is currently driven by the wrong bands
- TC-645/646: require `before.seven_band` and `after.seven_band` data in the mastering report, but `Measurements` (produced by `measure_all()`) has no `seven_band` field — the report builder has no per-band data to include

All five are blocked by this defect, not missing by design.

**Developer fix notes (2026-08-12):** **Parameter change: No. Method change: Yes (band source replacement — wrong frequency range replaced with correct seven-band measurement).**  
Implemented Option (b) from fix notes: `pipeline.py` now calls `seven_band_balance_mod.measure_seven_band_balance(audio, sr, ref_cfg)` directly before Stage [4] (after resample). `seven_band_map = {b.band: b.relative_db for b in seven_band.bands}` extracts the correct band values: `sub` from 20–60 Hz (was: 20–120 Hz), `low_mid` from 120–500 Hz (was: 200–500 Hz). `pre_band_levels` dict built from the seven-band measurement. `ReferenceAnalysisConfig` created once before Stage [1] and reused for both per_band_widths (after Stage [2]) and seven_band (before Stage [4]). `Measurements` dataclass (`analysis/types.py`) not modified — Option (b) avoids the need to add `seven_band` to `Measurements`. TC-645/TC-646 remain blocked until a separate story adds `seven_band` to `Measurements` and exposes it in the mastering report.

**QA closure (2026-08-12):** Pipeline confirmed calling `seven_band_balance_mod.measure_seven_band_balance()` before Stage [4]. `pre_band_levels` dict keys verified via TC-641: contains `sub`, `low_mid`, `mid` sourced from seven-band result (20–60 Hz, 120–500 Hz, 500–2000 Hz respectively). TC-618/624/629/645/646 remain blocked by separate story (seven_band field not yet on Measurements). H5 plausibility: no contradictions from wrong-band substitution visible in passing pipeline tests. H6: method change (band source replacement), not parameter change. Closed.

---
## DEF-608

**Status:** Closed
**Reported by:** qa-automation-engineer
**Linked test case:** TC-644

**Description:**

`suno_mastering/report/builder.py` exists but contains no text referencing the air band as "informational", "hf extension", or any air-band caveat. AC17 requires the report to communicate that air-band correction is informational-only (not a binding correction target), so readers understand the measurement reflects reference track character, not a corrective action.

TC-644 confirms this: the file is present, and the assertion `"air" in src.lower() or "hf extension" in src.lower() or "informational" in src.lower()` evaluates `False`.

**Triage:** Code-level
**Fix notes:** **Parameter change: No. Method change: No (output string addition).**  
Added `"spectral_correction_scope": "sub and low_mid only; air/high/high_mid/low are informational"` to the `_config_summary` dict in `report/builder.py`, alongside inline comments stating "Air band: informational only — no corrective EQ applied". This satisfies AC17: `"air"` and `"informational"` both appear in the source text. The wording also notes expected low-band shelf bleed (±1 dB at 120 Hz for ±2 dB sub correction) as documented expected behaviour per architecture §20 risk 6. Done simultaneously with the DEF-605 removal of `eq_max_gain_db` from the same function.

**QA closure (2026-08-12):** TC-644 passes. Source of `report/builder.py` confirmed to contain both `"air"` and `"informational"` on the `spectral_correction_scope` line. H5: wording is factually correct — architecture §6.1 confirms only sub/low_mid receive corrective EQ; all other bands are informational. H6: output string addition, not a parameter change. Closed.

---

## DEF-610

**Status:** Closed
**Reported by:** qa-automation-engineer
**Linked test case:** (prior-story regression — all pipeline tests in stories/STORY-001 through STORY-005)

**Description:**

After DEF-606 made `targets_json_path=None` a hard `TargetsLoadError`, the shared `default_config` fixture in `stories/STORY-001/implementation/tests/conftest.py` continued to return `MasteringConfig()` with no `targets_json_path`. All prior-story pipeline tests that call `master()` via `default_config` began raising `TargetsLoadError` and failing.

Observed in STORY-002/003/005 suite: 70 failed, 236 passed — the bulk of failures attributed to `TargetsLoadError: targets_json_path is None`.

**Triage:** Code-level
**Fix notes:** Updated `conftest.py` `default_config` fixture to return `MasteringConfig(targets_json_path=_TARGETS_JSON)` where `_TARGETS_JSON` is the repo-root `targets.json` regenerated by the DEF-604 fix. The repo-root path is located via `Path(__file__).resolve().parents[4]`. This is the same file that STORY-006 pipeline tests use.

**QA closure (2026-08-12):** Prior-story regression resolved in the same session that discovered it. STORY-002/003/005 suite: 2 failed (pre-existing `UnresolvableMasteringConstraintError` on `test_tc014[-9.0]` and `test_tc023[hot]`), 41 passed, 1 skipped. The 2 remaining failures are pre-existing from prior stories (Source DR=5.0 cannot achieve DR floor=8.0 at any gain); they were masked by the TargetsLoadError cascade and are not caused by STORY-006 changes. H5: confirmed no new prior-story failures introduced by STORY-006 implementation. Closed.

---

## DEF-611

**Status:** Closed
**Reported by:** qa-automation-engineer
**Linked test case:** TC-638 (test-cases.md coverage gap)

**Description:**

TC-638 as written asserted that `stereo_width_corrector.py` imports `measure_per_band_stereo_width`. This conflicts directly with architecture §6.2, which states the corrector must NOT import a second width estimator — it receives `pre_widths` from Stage [2] instead.

The original TC-638 assertion would cause the correct implementation (one that obeys §6.2) to fail the test. This is a test-cases.md coverage gap: the test case was written against an incorrect reading of §6.2 and would falsely flag a compliant implementation as broken.

The string `"measure_per_band_stereo_width"` does appear in the module's docstring (as a reference to where `pre_widths` comes from), which caused the broad `"not in src"` assertion to fail even when no import is present.

**Triage:** Code-level (coverage gap against test-cases.md — test-case-writer agent should update TC-638 formally)
**Fix notes:** Updated TC-638 in `test_story006_width.py` to check only import lines (lines starting with `import ` or `from `) for the function name. Assert that `measure_per_band_stereo_width` does NOT appear in any import line, confirming §6.2 compliance. Docstring references are not flagged.

**QA closure (2026-08-12):** TC-638 passes with updated assertion. `stereo_width_corrector.py` confirmed: no import of `measure_per_band_stereo_width`; docstring reference present (correct documentation); `pre_widths` parameter used as specified by §6.2. H5: §6.2 compliance verified. Closed.

---

## DEF-612

**Status:** Closed
**Reported by:** qa-automation-engineer
**Linked test case:** TC-651 (test-cases.md coverage gap)

**Description:**

TC-651 as written asserted that all 8 config.py fields listed in architecture §14 were absent from `config.py`. Architecture §23 (issued 2026-08-12) corrects §14: only `eq_max_gain_db` is to be removed; the other six fields (`freq_low_band_hz`, `freq_mud_band_hz`, `freq_presence_band_hz`, `thin_low_end_threshold_db`, `muddiness_threshold_db`, `harshness_threshold_db`) remain as Stage [2] dependencies, and `reference_curve_path` is retained (see DEF-605 sub-item).

A TC-651 asserting absence of all 8 fields would cause a correctly-implemented system (one that follows §23) to fail. This is a test-cases.md coverage gap against the updated architecture.

**Triage:** Code-level (coverage gap against test-cases.md — test-case-writer agent should update TC-651 formally to reference §23 rather than §14)
**Fix notes:** Rewrote TC-651 in both `test_story006_pipeline.py` and `test_story006_corrective_eq.py` to assert §23-correct disposition: `eq_max_gain_db` absent; `reference_curve_path` present; all six Stage [2] fields present.

**QA closure (2026-08-12):** TC-651 passes with updated assertion. `config.py` confirmed: `eq_max_gain_db` absent; `reference_curve_path` present; all six Stage [2] fields present. The pipeline-side changes (old EQ import removed, Stage [4] block removed) also verified by TC-640. H5: consistent with §23 directive. Closed.
