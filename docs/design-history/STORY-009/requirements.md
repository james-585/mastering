# STORY-009 — Requirements: Wire `suno_dsp` C++ DSP extension into the mastering chain

## Contract
```
Consumes:  src_cpp/spectral_repair.cpp (suno_dsp pybind11 module, built via
           CMakeLists.txt/scikit-build), STORY-007 artifact-detector output
           (Measurements.artifact_detection.artifact_flags — for
           repair_whistles only, filtered to artifact_type ==
           "STATIONARY_WHISTLE")
Produces:  three new/extended pipeline stages in pipeline.py calling into
           suno_dsp, each config-gated and default-off, with every
           invocation (or deliberate non-invocation) logged to the
           returned actions payload and the mastering report
Consumed by: mastering pipeline (pipeline.py). Terminal — no further
           downstream consumer of this story's output.
```

## Restated intent
Three DSP functions exist in a compiled, tested-at-the-C++-level extension
but are not reachable from the Python pipeline. This story specifies how
each is exposed as an explicit, off-by-default pipeline stage, what data
each is allowed to consume, and what a Gate 1 domain reviewer must sign off
on before any of the three defaults to on. It does not design the wiring
(architect's job) and does not implement anything.

---

## Source-grounding: what the code actually does

Read directly from `src_cpp/spectral_repair.cpp`. Two of these facts
correct assumptions in the originating BACKLOG.md draft and the task brief
— both are flagged as findings below, not silently reconciled.

### `repair_whistles(input_audio, sample_rate, target_frequencies)`
- STFT notch: 4096-sample frame, 2048 hop (50% overlap), Hann analysis
  **and** synthesis window.
- Per target frequency: attenuates bins `target_bin ± 2` (5 bins) and the
  mirror bin by ×0.01 (−40 dB), not to zero.
- Bin width at 44.1 kHz/4096 ≈ 10.77 Hz; 5 bins ≈ 54 Hz notch width at
  6.4 kHz → Q ≈ 120. Genuinely surgical — supports the CLAUDE.md §4.2a
  characterisation of this as artifact removal at known coordinates, not
  a tonal EQ move. Note: bin width in Hz scales with `sample_rate`, so the
  notch is proportionally wider at 48 kHz than at 44.1 kHz for the same
  bin count.
- Notches the **entire file duration**, uniformly, for every frame. It
  takes no time-window argument. STORY-007's `ArtifactFlag` carries
  `timestamp_start_s`/`timestamp_end_s` for a detected whistle — that
  information cannot currently be passed to `repair_whistles`. A whistle
  detected in a 4-second window becomes a whole-track notch at that
  frequency. **This is a contract mismatch between the two components,
  not a requirements decision I am resolving here** — see Open Questions.
- L and R (or all channels) are notched **independently**, frame by frame.
  No mid/side or linked-channel processing. Unlinked notching can shift
  inter-channel phase/level relationship at the notch frequency.
- **Finding — OLA gain risk requiring verification, not asserted as fact**:
  the code windows the signal on analysis (line ~121) and again on
  synthesis (line ~163), so the numerator carries `hann²`, but
  `overlap_weights` (used as the OLA normalisation divisor) accumulates
  plain `hann`, not `hann²`. For a 50%-hop Hann window, mean(hann²) over
  a period ≈ 3/8, and with two overlapping frames per sample that gives an
  expected reconstruction gain around 0.75 (~−2.5 dB) — even with an
  **empty** `target_frequencies` list, i.e. even when nothing is notched.
  This must be measured (bit-diff / level-diff test), not assumed correct
  or assumed broken.
- **Finding — short input**: if `n_samples < frame_size` (4096 samples,
  ~93 ms at 44.1 kHz), neither the main loop (`start + frame_size <=
  n_samples`) nor the tail-frame branch (`n_samples > frame_size`)
  executes. Output is uninitialised zeros — silence — for any input
  shorter than one frame.

### `shape_transients(input_audio, sample_rate, attack_boost_db, sustain_cut_db)`
- Fast (2 ms) / slow (50 ms) envelope followers per channel, independently
  per channel (no stereo linking).
- **Finding — gain law is not proportional to transient strength.** The
  gain interpolation uses `diff / (|diff| + 1e-6)`, where `diff = fast_env
  − slow_env`. For any audio-scale envelope difference this ratio is
  effectively ±1 (the epsilon only matters at ~1e-6 amplitude). The
  function is therefore a **near-binary switch** between
  `attack_multiplier` and `sustain_multiplier`, smoothed only by a single
  5 ms one-pole (`smooth_alpha`) — not a graduated response to how
  transient or sustained the material is. This reads as a design risk
  (potential zipper/pumping artifacts on continuous material) for the
  mastering-engineer to rule on at Gate 1, not something resolved here.
- The 2 ms / 50 ms / 5 ms time constants are hardcoded in C++, asserted
  not derived — CLAUDE.md §5 requires derivation or synthetic-signal
  justification for any such constant.

### `collapse_swish(input_audio, sample_rate, cutoff_freq)`
- Requires exactly 2-channel stereo input; raises otherwise.
- Mid/side split. `filtered_side` is computed via a standard RBJ
  **lowpass** biquad (`b0=(1−cosω)/2, b1=1−cosω, b2=(1−cosω)/2` — textbook
  RBJ lowpass coefficients) applied to the side channel, then
  `left_out = mid + filtered_side`, `right_out = mid − filtered_side`.
- **Finding — this is the inverse of the BACKLOG.md and task-brief
  description.** A lowpass on the side channel means side content **below**
  the cutoff is preserved (stays stereo) and side content **above** the
  cutoff is discarded from the output (becomes mono). BACKLOG.md describes
  this as "mono-sum the side channel below a cutoff frequency"; the task
  brief calls it "mono-izes bass below the crossover." Both describe a
  highpass-collapse (or equivalently, a lowpass on mid width), which is
  not what the coefficients implement. What the code actually implements
  — collapsing **high-frequency** side content to mono while preserving
  low-frequency stereo width — is consistent with the function's name and
  with STORY-007's `PHASE_SWISH` detector, which flags **HF** inter-channel
  decorrelation (architecture.md §5.4, "L and R independent above 8 kHz").
  This reads as the function doing exactly what a `PHASE_SWISH` remediation
  should do, and the BACKLOG wording being the drafting error — but that is
  a plausible read, not a confirmed one. **The architect must confirm this
  before treating either description as ground truth**; I have not amended
  BACKLOG.md.
- Because the intended semantics is "collapse the HF swish, not the bass,"
  a sensible default cutoff is in the low-kHz range (matching where
  PHASE_SWISH typically fires, e.g. the ~8 kHz region referenced in
  STORY-007's positive control), **not** the 100–150 Hz bass-mono figure
  that would apply under the BACKLOG's literal wording. I am not asserting
  either number as the requirement — see Open Questions. Per CLAUDE.md,
  I will not invent an unstated engineering target.

---

## STORY-007 grounding for `repair_whistles`' input contract

Confirmed from `stories/STORY-007/architecture.md`:
- `Measurements.artifact_detection: ArtifactDetectionResult | None`, with
  `artifact_flags: list[ArtifactFlag]`.
- `ArtifactFlag.artifact_type` includes `"STATIONARY_WHISTLE"`.
- `ArtifactFlag.details` for a whistle flag contains
  `{"frequency_hz": float, "prominence_db": float, "q_factor": float}`.
- `ArtifactFlag.confidence_score`, 0.0–1.0.
- Existing threshold: `CONFIDENCE_THRESHOLD_TO_WARN = 0.8`, already used to
  decide whether a flag is surfaced in `plausibility_warnings`. Proposing
  this as the default gate for feeding a frequency into `repair_whistles`
  is reuse of an existing, already-reviewed number, not a new invented
  target — but it is a proposal for Gate 1 to confirm, not a settled
  requirement.
- Already computed in the pipeline at Stage [2] (`before =
  analysis.measure_all(...)`, `pipeline.py` line ~156), so the frequency
  list is available without a new call to the detector.

**Conflict to flag, not resolve**: `stories/STORY-007/architecture.md`
§7.3 states in the report template: *"This analysis is report-only.
Flagged artifacts cannot be corrected at the master stage (DOMAIN.md
§4)."* CLAUDE.md §4.2a (added 2026-08-16, same day as this story) creates
a narrow, explicit exception for `repair_whistles`/`STATIONARY_WHISTLE`
only. STORY-007's architecture doc and DOMAIN.md §4's "Cannot" table have
not been updated to reflect this exception. I am not rewriting either
document here. This is a documentation-reconciliation item for the project
owner/architect, and the exception must not be read as extending to
`SMEARED_TRANSIENT`, `DIGITAL_HAZE`, or `PHASE_SWISH`.

---

## Rejected as out of scope

**Using `shape_transients` to repair `SMEARED_TRANSIENT` detections.**
DOMAIN.md §4 "Cannot" table: transient smearing is unfixable at master
stage because the fast-attack information was never rendered — it is
absent, not masked. BACKLOG.md's "Deliberately not on this backlog" table
lists "transient repair" as impossible. `shape_transients` as a *general
dynamics/glue tool applied to the sum* is legitimate — DOMAIN.md §4 "Can"
explicitly lists "dynamics control and glue" — but it must not be
positioned, parameterised, or reported as fixing smearing.

Acceptance criteria below make this an enforceable boundary: `
shape_transients` must not be driven by, gated on, or take parameters
derived from STORY-007's `SMEARED_TRANSIENT` flags (the mirror-image rule
of "repair_whistles only from STORY-007 STATIONARY_WHISTLE flags"), and
must not be described in config, logs, or the report as artifact repair.

**Using `repair_whistles` or `collapse_swish` on frequencies/artifact
types outside their CLAUDE.md §4.2a-granted scope** is rejected for the
same reason — the exception is narrow and dated, and this story must not
broaden it.

---

## Acceptance criteria

### General (applies to all three functions)
1. Given the config flag for a function is off (the default), when the
   pipeline runs, then that function is never called and no related action
   appears in the report.
2. Given a config flag is on, when the pipeline runs, then every
   invocation of that function — including calls made with an empty or
   degenerate argument set — is recorded in the returned `actions` payload
   and the human-readable report, with before/after measurements sufficient
   to see what changed (at minimum: peak/RMS delta for the processed
   region, and for `repair_whistles`, the frequency list actually notched).
3. Given `suno_dsp` fails to import, when any of the three flags is
   enabled, then the pipeline fails loudly with a clear error before
   processing begins (same failure posture as missing `targets.json`,
   `pipeline.py` line ~141). Given all three flags are off, an import
   failure must not affect the run.
4. Given identical input audio and identical config, when the pipeline is
   run twice, then output is bit-identical (all three C++ functions are
   deterministic, single-threaded, no dependency on wall-clock or thread
   scheduling — assert this, don't assume it).
5. No default may be flipped to "on" without a recorded Gate 1 clearance
   for that specific function. Shipping any of the three enabled by
   default without that record is a defect.
6. With any subset of the three flags enabled, the final master must still
   meet the existing standing targets (CLAUDE.md §4.2): −13.5 LUFS
   integrated, −1.0 dBTP ceiling, DR within the 6.6–8.7 reference range,
   loudness measured after limiting, not before. The report must show the
   before/after delta introduced by each newly-enabled stage so a
   regression is attributable to a specific stage.

### `repair_whistles`
7. Given `config.repair_whistles.enabled = True` and a track with zero
   `STATIONARY_WHISTLE` flags at or above the confidence gate, when the
   pipeline runs, then `repair_whistles` is either not invoked, or invoked
   with an empty frequency list and produces a result the test suite
   verifies is a no-op (see Finding above — bit-identical, or within a
   tight, explicitly stated tolerance, not assumed silently "close
   enough"). This is the negative control (BACKLOG.md AC4).
8. Given one or more `STATIONARY_WHISTLE` flags at or above the confidence
   gate, when the pipeline runs, then `repair_whistles` receives exactly
   the `frequency_hz` values of those flags — sourced only from
   `Measurements.artifact_detection.artifact_flags`, never from a
   user-supplied, config-file, or hardcoded frequency list. This must be
   enforced in code (e.g. the function is only ever called from one
   call-site that reads the detector output), not left as a convention
   (BACKLOG.md AC2, CLAUDE.md §4.2a).
9. Given input shorter than one STFT frame (4096 samples), when
   `repair_whistles` is invoked, then the pipeline must not silently
   accept a silent/zeroed result — either detect and refuse the call for
   sub-frame audio, or the architect must specify required handling.
   Flagged as an open question below; not resolved here.
10. The OLA gain-risk finding above must be closed by a measured test
    (empty-frequency-list run vs. unmodified input, level and null-test
    diff) before this stage's default may move to "on."

### `shape_transients`
11. Given the flag is enabled, `shape_transients` parameters
    (`attack_boost_db`, `sustain_cut_db`) must be config-supplied
    constants, never derived from or gated on `SMEARED_TRANSIENT`
    detections (see Rejected as out of scope).
12. Report/log text for this stage must describe it as dynamics
    shaping/glue, never as artifact repair or smearing correction.
13. Gate 1 must explicitly rule on the near-binary gain law and the
    hardcoded 2 ms/50 ms/5 ms constants (see Findings) before this stage's
    default may move to "on."

### `collapse_swish`
14. Given non-stereo (mono or >2-channel) input, `collapse_swish` must not
    be called — the pipeline must check channel count before invoking it
    (the C++ function raises on non-stereo input; the pipeline must not
    rely on catching that exception as its control flow).
15. The semantic discrepancy between BACKLOG.md's description and the
    measured RBJ-lowpass-on-side behaviour (see Finding above) must be
    resolved and recorded by the architect/mastering-engineer before a
    default cutoff frequency is chosen. This requirements document does
    not assert a cutoff value.
16. Whatever cutoff is chosen, its interaction with the existing [5a]
    per-band stereo width correction and [5b] broadband stereo/mono
    correction stages (`pipeline.py` ~lines 239–256) must be addressed —
    two stages independently altering side-channel content is a
    double-correction risk. CLAUDE.md §4.2 states stereo width is
    "guidance only... do not correct without explicit requirement"; if
    this story is being treated as that explicit requirement, the
    architect must say so explicitly rather than let the stages silently
    stack.

---

## Audio quality targets
No new loudness/dynamics/spectral targets are introduced by this story.
All three stages must operate within the existing standing targets set in
CLAUDE.md §4.2 (−13.5 LUFS integrated, −1.0 dBTP, DR 6.6–8.7 hard target,
spectral soft-nudge ±2 dB) and must not be a route to reintroducing
hardcoded spectral/dynamics constants (CLAUDE.md §5, "known-wrong
patterns"). No numeric cutoff, boost/cut dB default, or notch-depth value
is specified in this document beyond what already exists in the C++ source
— defaults for `shape_transients`' dB parameters and `collapse_swish`'s
cutoff are explicitly open questions for Gate 1, not assumed here.

## Input/output assumptions
- Input to all three stages is the pipeline's in-flight `AudioBuffer`/plain
  `np.ndarray` (per the current plain-array convention noted in
  `stories/STORY-007/architecture.md` §7.2, pending SPRINT-007-01
  resolution) at whatever sample rate the pipeline has reached by the
  relevant stage — not raw file input.
- `repair_whistles` additionally consumes
  `Measurements.artifact_detection.artifact_flags` from Stage [2]
  pre-master analysis, already computed and available in `pipeline.py`.
- All three functions return `float32` NumPy arrays matching the input
  shape (1D mono or 2D stereo, except `collapse_swish` which requires 2D
  stereo).
- Output of this story is the modified in-pipeline audio buffer plus
  logged actions — no new file artifact type is produced.

## Explicit out-of-scope
- Any change to STORY-007's detector, its thresholds, or its report text.
- Repair of `SMEARED_TRANSIENT`, `DIGITAL_HAZE`, or `PHASE_SWISH` flags
  using these functions beyond `collapse_swish`'s plausible (but
  architect-to-confirm) fit for `PHASE_SWISH`-shaped problems.
- Choosing final numeric defaults for `attack_boost_db`, `sustain_cut_db`,
  or `collapse_swish`'s `cutoff_freq` — Gate 1 / architect decision.
- Fixing the OLA normalisation bug in `repair_whistles`, if the
  measurement in AC10 confirms it exists — that is an implementation
  defect for the python-developer/architect, not a requirements change.
- Extending `repair_whistles` to accept a time window — noted as an open
  contract gap, not designed here.
- GUI exposure of these flags (STORY-G1 is separate).

## Non-functional requirements
- Processing cost: all three functions run in C++ at presumably real-time-
  or-better speed for a 5-minute stereo track, but no measured baseline
  exists yet (see SPRINT-007-03, which covers overall pipeline throughput
  but not these specific stages). Recommend a baseline measurement be
  taken during Gate 1/implementation rather than asserted here.
- Reproducibility: bit-identical output for identical input+config (AC4).
- Failure posture: fail loudly on missing/broken `suno_dsp` when any flag
  is on; never a silent fallback to unmodified audio when a flag is
  explicitly enabled and the call was attempted.
- Every stage's action log must be sufficient for a human to reconstruct
  what was changed and why without re-running the pipeline (matches the
  existing `eq_actions`/`stereo_actions` logging convention already in
  `pipeline.py`).

## Open questions
1. **`repair_whistles` time-window gap**: the C++ function notches the
   whole file; STORY-007 flags a time window. Whole-file notch, a
   coverage-fraction gate (e.g. only apply if the flagged window covers
   most of the track), or a signature extension to accept a
   start/end — architect decision.
2. **OLA gain-normalisation risk in `repair_whistles`**: confirm by
   measurement whether the empty-frequency-list case is truly a no-op.
   If not, is this an implementation defect to fix before wiring, or does
   the story accept a small measured broadband gain change as part of
   "invoking the stage"? I do not have a position on this without the
   measurement.
3. **Short-input silence in `repair_whistles`**: required behaviour for
   audio under one STFT frame (~93 ms at 44.1 kHz) — refuse, bypass, or
   pad?
4. **`shape_transients` gain-law and constants**: is the near-binary
   attack/sustain switch (vs. a proportional response) acceptable dynamics
   behaviour, and are the 2 ms/50 ms/5 ms constants acceptable as asserted
   C++ literals, or do they need CLAUDE.md §5-style derivation/synthetic
   verification before Gate 1 can clear the stage?
5. **`collapse_swish` semantics vs. BACKLOG.md wording**: is BACKLOG.md's
   "mono-sum the side channel below a cutoff" a drafting error (my
   reading, based on the measured RBJ-lowpass-on-side behaviour and the
   PHASE_SWISH-detector fit), or does the architect want the C++ changed
   to match BACKLOG's literal wording instead? This determines the order
   of magnitude of the eventual default cutoff (low-kHz vs. ~100–150 Hz)
   and I am not choosing between them.
6. **`collapse_swish` vs. existing [5a]/[5b] stereo-correction stages**:
   does this story constitute the "explicit requirement" CLAUDE.md §4.2
   asks for before correcting stereo width, or does it need a separate
   sign-off?
7. **Confidence gate for `repair_whistles`**: is reusing STORY-007's
   existing `CONFIDENCE_THRESHOLD_TO_WARN = 0.8` as the frequency-feed gate
   acceptable, or should this story define an independent (and possibly
   higher) threshold given the consequence of a false positive is now an
   actual audio edit, not just a warning line in a report?
8. **STORY-007 documentation reconciliation**: who updates
   `stories/STORY-007/architecture.md` §7.3 and DOMAIN.md §4's "Cannot"
   table to reflect the CLAUDE.md §4.2a exception, and when? Not this
   story's deliverable, but it should not be left permanently
   inconsistent.
9. **L/R-independent processing in all three functions**: none of the
   three link stereo channels (repair_whistles and shape_transients
   process L/R independently; collapse_swish is M/S but still filters a
   single side signal without regard to per-channel content). Is
   independent per-channel processing acceptable for a mastering-stage
   tool, or does one/more of these need stereo-linked detection/gain
   before Gate 1 can clear it?

## Revision history
- 2026-08-16: Initial version. No prior `defects.md` existed for this
  story (folder created fresh in this run).
