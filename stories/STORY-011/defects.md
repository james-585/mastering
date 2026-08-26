# STORY-011 Defects

This is the single running ledger of defects found against
`stories/STORY-011/implementation/`. Entries are never deleted, only
status-updated, so there is a full audit trail.

## Open issues
- DEF-011-05: Transient restoration fires on sustain-dominant stems (pads, slow-attack content) whose onset region has no meaningful attack energy, producing pumping artifacts and spectral damage in the mids/highs

## DEF-011-05
Status: Open
Reported by: user (listening review 2026-08-25, confirmed by analysis of Euphoric D Minor report)
Linked test case: none yet

Description:
`apply_stem_transient_restoration` applies onset-local gain to stems whose
onset window contains near-silence — not because the attack was compressed,
but because the stem is sustain-dominant (a pad or chord that fades in or
starts below the level it reaches in the body of the stem). The attack-ratio
metric (`_local_attack_ratio`) measures `peak(env[1ms:250ms]) / median(env[:25ms])`.
For a pad that starts from near-silence, `median(env[:25ms])` ≈ 0, making the
ratio arbitrarily large (observed: 511.28 on the "other" stem of
`Euphoric D Minor.wav`). This triggers the maximum gain cap (+3.5 dB) and
`action_type="attack_boost"` even though the onset region has no transient
energy to restore.

Reproduction evidence:
- Track: `C:\Users\james\Downloads\Euphoric D Minor.wav`
- Report: `Euphoric D Minor_mastered_report.json` (2026-08-25)
- Stem: "other" (pads/chords)
  - `onset_peak_before: 0.0171` (−35.3 dBFS onset window)
  - `global_peak_before: 0.524`
  - `onset/global ratio: 3.2%` — onset region has 3% of the stem's body energy
  - `severity: 511.28` — ratio inflated by near-zero baseline
  - `gain_db: 3.5` — full cap applied
- Blast radius: the onset window is the **first 80 ms of the file only**
  (`W = int(0.08 * 48000) = 3840 samples`). The gain boost affects 0.03%
  of a 244.8 s track. This is NOT the cause of any full-track mid/high
  damage — see separately-investigated EQ filter shape and DR expansion.
  The metric defect is real but its severity is low: a spurious 3.5 dB
  blip in the first 80 ms of the re-summed "other" stem, audible only at
  the very start of the track.

Root cause — two distinct gaps, both in `transient_restoration.py`:

1. **No onset significance gate.** The ratio metric cannot distinguish
   "attack was compressed to below the sustained level" from "stem is a pad
   with a slow natural attack." Both produce high ratios. For a pad that
   starts from silence, the ratio is pathologically large (511×) because
   the baseline window catches the silence. An onset window peak that is
   a small fraction of the global peak is direct evidence there is no
   meaningful attack to restore; the metric should gate out before the
   ratio is even computed.

2. **No reconstruction-quality guard.** When the forensics stage (STORY-023)
   finds a high reconstruction residual (WARN or higher), stem-based
   processing is operating on spectrally polluted input. The current stage
   has no awareness of separation quality and applies full gain regardless.
   (This gap may need an architectural decision on how forensics context
   is passed; noted here as a contributing factor.)

Triage: Code-level (gap 1 — onset significance gate in `transient_restoration.py`).
         Architectural (gap 2 — forensics context is not currently passed to this
         stage; the software-architect must decide the interface contract before
         gap 2 can be implemented).

Required fix for gap 1 (method change, not threshold tuning):
Add an `_onset_significant()` guard that computes `p_onset / global_peak_before`.
If this ratio is below a documented threshold, the onset region has no
meaningful signal relative to the stem body and no attack can be restored —
skip the stem with a new report-visible action type `"skipped_onset_quiet"`.
The threshold and its derivation must be documented in `architecture.md`
(H4/H6 pattern). This is a new evidence gate, not a tuning of the existing
ratio threshold or gain cap.

## DEF-011-01
Status: Closed (2026-08-17)
Reported by: qa-automation-engineer
Linked test case: none yet — test cases pending (test-case-writer to add
coverage for the input-peak safety response once the architecture
disposition lands)

Description:
`_peak_guard()` in `stories/STORY-011/implementation/transient_restoration.py`
(lines 34–37) raises a `ValueError` whenever a stem's *sample peak* exceeds
an undocumented hardcoded constant of 0.98. It is invoked pre-gain on the
INPUT stem (line ~113) and post-gain on the clipped output (line ~135).
On real material this aborts the entire 8-stage mastering run at Stage 8
of 8 (transient restoration) with:

```
ERROR: ValueError: Transient restoration unsafe: stem peak 0.9831 exceeds safe limit
FAILED - see error message above.
```

This is a method defect, not a calibration defect:

1. **The guard's premise is wrong for stem-domain input.** The restoration
   gain is onset-local only (first 80 ms window per stem) and the output is
   `np.clip`'d to ±1.0 before the post-gain guard, so the output path cannot
   exceed ±1.0 regardless of input peak. An individual stem's sample peak
   (0.9831) can legitimately exceed the re-summed mix peak (0.751464)
   because stems are partially uncorrelated — a near-full-scale stem is
   ordinary programme material, not an unsafe condition. Aborting on input
   peak treats a normal signal property as a fault.
2. **The constant is undocumented.** STORY-011 architecture.md specifies
   only a ±1.0 hard `_clip_guard` contract ("For any operation that can
   push signal beyond ±1.0, the code must raise a ValueError"). The 0.98
   sample-peak abort is an implementation addition with no architectural
   basis, and it fires on a signal that cannot push the (clipped) output
   beyond ±1.0.
3. **The failure mode is wrong.** Crashing the whole run at the final
   stage — after ~245 s of Demucs CPU stem separation plus re-summation,
   tonal balance, and width stages — discards all completed work for a
   condition that could be handled deterministically (clamp gain to
   available headroom, or skip the stem unchanged with a report-visible
   note). The run's CLI progress is reporter-driven, so the abort also
   surfaces as a bare exception string rather than a structured,
   report-visible rejection.

Per the repo's known-wrong-patterns rule ("Fixing a wrong method by
tuning its parameter instead of replacing the method"), this must NOT be
resolved by raising or otherwise tuning the 0.98 threshold.

Reproduction evidence:
- Command: production CLI `master_track.bat` on
  `C:\Users\james\Downloads\Twilight Caverns.wav` with stem separation
  enabled (model=htdemucs, 4-stem profile).
- Separation itself was clean: `sources=['drums','bass','other','vocals']`,
  `residual_peak=1.195301e-01`, `residual_energy_ratio≈0.00082`,
  re-summed peak 0.751464.
- The pipeline completed re-summation, tonal balance, and width stages,
  then aborted at Stage 8 of 8 (transient restoration) after ~245 s of
  Demucs CPU separation time.
- Exact error: `ValueError: Transient restoration unsafe: stem peak 0.9831
  exceeds safe limit`, followed by `FAILED - see error message above.`
- Key contradiction: the aborted stem peak (0.9831) is a valid,
  sub-full-scale value, and it correctly exceeds the re-summed mix peak
  (0.751464) because the stems are partially uncorrelated — the guard is
  comparing a stem-domain quantity against an undocumented mix-domain
  intuition.

Impact:
Total loss of the mastering run at the final stage on legitimate,
not-extreme programme material — any Suno export whose separated stems
peak above 0.98 (common for loud normalised sources) will hit this
deterministically. The user pays the full ~4-minute stem-separation cost
and receives no master and no actionable report. Because the trigger is a
normal stem-level property, the defect will recur across a large fraction
of real inputs whenever stem separation is enabled, not just on edge
cases.

Triage: Architectural

Rationale: the defect is in the safety-response contract itself — the
architecture only specifies the ±1.0 hard `_clip_guard`, and says nothing
about how the pipeline should respond when a stem has limited headroom for
onset-local gain. The software-architect must decide the
headroom-management contract (clamp vs. trim vs. skip-with-report) before
implementation proceeds; this is not a straightforward logic bug the
developer can patch in place.

Fix notes:
(python-developer / software-architect, 2026-08-17: architecture revised
with the "Headroom-management contract" — clamp-then-report replacing the
abort; gate-1 review APPROVED-WITH-CONDITIONS with the F1 derivation
rewrite and F2 Hann fade-out envelope both landed. Implementation now
computes a deterministic onset-headroom clamp, returns hot stems unchanged
with a `skipped_headroom` action, and raises only on sample peak > 1.0.)

QA closure evidence (2026-08-17):
1. Regression tests demonstrating the fixed behaviour pass:
   - TC-0121 (hot stem 0.9831-peak reproduction: returns unchanged with
     `skipped_headroom`, does NOT raise) — written before the fix against
     the revised architecture and confirmed failing on the abort code.
   - TC-0118 (ground-truth clamp bound), TC-0122 (legality guard boundary),
     TC-0123 (hot healthy stem no-op), TC-0119 (envelope shape) all pass.
2. H5 plausibility gate on REAL output: the Twilight Caverns production
   run that previously aborted at Stage 8 with
   `ValueError: stem peak 0.9831` now completes end-to-end — overall PASS,
   -12.60 → -13.54 LUFS (target -13.54), true peak -2.48 → -2.55 dBTP
   (ceiling -1.00), 0 clipped samples, non-destructive integrity check
   PASSED. All values physically plausible and mutually consistent.
3. Method change, not parameter change (H6): the abort-on-input-peak
   method was REPLACED by the clamp-then-report contract; the 0.98 value
   was retained per architect H6 disposition with a corrected derivation,
   not tuned.
4. Caveat recorded separately: the action records this rework produces do
   not surface in the generated report — logged as DEF-011-04 against the
   report path. That gap does not reopen this defect (the abort itself is
   resolved) but means the clamp/skip decisions are currently invisible to
   the end user on real runs.

Recommended direction for the architect's disposition: (resolved — the
clamp-then-report contract adopted option A from the list below)
- Keep the ±1.0 hard guard as specified in architecture.md.
- Replace the pre-gain input-peak abort with a deterministic gain clamp:
  compute the restoration gain such that the predicted post-gain
  onset-window peak stays ≤ 0.98; a clamp-to-zero result means skip the
  stem unchanged and record a report-visible action (stem name, requested
  vs applied gain).
- Option B: a pre-Stage-8 headroom trim applied to the stem set, if the
  architect prefers headroom management as a pipeline stage rather than a
  per-stem gain bound.
- Option C (keep the abort) is rejected: it crashes the full run on
  ordinary material for a condition the output clip already makes
  impossible.
- Explicitly: raising the 0.98 threshold is the known-wrong
  parameter-tuning pattern and is NOT an acceptable resolution — the
  abort-on-input-peak method is what is wrong.

## DEF-011-02
Status: Closed (2026-08-17)
Reported by: qa-automation-engineer (referred by mastering-engineer gate-1
finding F6; correction specified by software-architect in the 2026-08-17
architecture revision, bundled with the DEF-011-01 rework)
Linked test case: TC-0126

Description:
`_local_attack_ratio()` in
`stories/STORY-011/implementation/transient_restoration.py` called
`scipy.signal.hilbert(audio)` without an `axis` argument. `hilbert`
defaults to `axis=-1`; on a `(samples, 2)` stereo stem that transforms
across the 2-sample CHANNEL axis. The N=2 Hilbert multiplier is [1, 1],
i.e. the 2-point transform is the identity, so the resulting "analytic
envelope" degenerates to the rectified waveform `max(|L|, |R|)`,
oscillating to zero twice per period — a meaningless envelope on stereo
material, which is the normal case for this stage. Downstream 2-D
max/median flattening laundered the garbage into plausible-looking scalars
(baseline median (√2/2)·A instead of A), and the mono-only test fixtures
hid the defect entirely.

Analytic discrimination (TC-0126 stereo fixture, 480 Hz sines at 48 kHz,
left 0.60 during the onset window / 0.10 after, right 0.30 constant):
- correct axis (axis=0 + per-sample cross-channel max): baseline 0.60,
  onset peak 0.60 → attack ratio 1.0 ideal (1.216 measured, amplitude-step
  ringing at n=3840 absorbed by the test band).
- broken axis: baseline (√2/2)·0.60 = 0.42426, peak 0.60 (the sample grid
  hits the sine peak exactly) → ratio √2 = 1.41421 (1.4149 measured).
QA confirmed the broken-axis value by direct simulation before writing the
regression test, so TC-0126 is proven to fail on the unfixed code.

Triage: Code-level (implementation bug with an architect-specified
correction: `hilbert(..., axis=0)` plus explicit per-sample cross-channel
max reduction).

Fix notes:
(python-developer, 2026-08-17: implemented as `hilbert(..., axis=0)` with
`env.max(axis=1)` cross-channel reduction; pending QA retest — see QA
summary below)

QA closure evidence (2026-08-17):
1. TC-0126 (stereo fixture, 480 Hz sines at 48 kHz, known-by-construction
   attack ratio 1.0) passes — written before the fix and confirmed failing
   on the broken-axis code (1.4149 measured vs 1.0 expected; the √2
   identity-envelope signature).
2. H5 plausibility: fixed code measures 1.216 on the stereo fixture
   (amplitude-step ringing absorbed by the test band) and 1.0000 on an
   integer-cycle mono control — both physically sensible for the material.
3. Method change, not parameter change (H6): the transform axis and the
   cross-channel reduction were corrected per the architect-specified fix;
   no threshold or window parameter was tuned.
4. STORY-016 consumer regression: 5/5 passed post-fix.

## DEF-011-03
Status: Closed (2026-08-18)
Reported by: qa-automation-engineer
Linked test case: none yet — coverage gap against test-cases.md (the
healthy no-op fixtures TC-0114/TC-0123 use constant-amplitude tones; QA
flags this to test-case-writer for a non-integer-cycle steady-tone no-op
case once the metric handles boundaries)

Description:
Found during TC-fixture calibration (2026-08-17) while cross-checking
measured values against what the material obviously is (H5 plausibility
gate). `_local_attack_ratio()` on a constant-amplitude 441 Hz cosine
(0.5 s at 44.1 kHz = 220.5 cycles, i.e. a non-integer cycle count) returns
2.419 — an apparent strong "attack deficit" on a signal whose envelope is
physically constant (true ratio 1.0; an integer-cycle 440 Hz control
measures 1.0000000000000986 through the identical code path).

Mechanism (measured): the FFT-based `scipy.signal.hilbert` assumes periodic
extension; the ~2·A wrap discontinuity between the last and first samples
produces an envelope edge spike at n=0 (env[0] = 2.395 on a 0.99-amplitude
tone, settling to 0.990 by mid-file). The baseline statistic is robust
(median of the first 1102 samples = 0.98998), but the peak statistic takes
`max` over the analysis window, which includes n=0, so the ratio reads
2.395/0.990 = 2.419.

Impact: healthy steady-content stems (e.g. synth pads) can measure ratios
up to ~2.4, exceeding the per-stem thresholds (1.7–2.4) and receiving a
spurious onset boost of up to (ratio − threshold)·1.6 dB (≈1.15 dB for an
"other"-classified stem at the observed worst case) — a false-positive
boost on material with no transient defect. Real Suno stems are
non-periodic, so a wrap discontinuity at the file boundary is the norm,
not the edge case. The TC-0114/TC-0123 healthy fixtures happen to dodge
this via integer cycle counts; QA has kept them on integer-cycle
construction (documented in the test file) so they do not mask this
defect.

Triage: Code-level (metric boundary handling — e.g. exclude a short lead-in
region from the peak statistic or taper before the Hilbert transform; NOT a
threshold tuning, per the known-wrong-patterns rule).

Fix notes:
(python-developer, 2026-08-18: in `_local_attack_ratio()`, replaced `peak = np.max(onset)` with
a lead-in skip: `leadin = max(4, int(0.001 * sample_rate)); peak = np.max(onset[leadin:]) if
onset.size > leadin else np.max(onset)`. The wrap spike at n=0 is confined to the first ~1 ms;
skipping it for the peak statistic leaves the full onset region visible. Baseline (median) is
unchanged. No threshold tuning.)

QA closure evidence (2026-08-18):
1. Repro script `_repro_def011_03.py`: 441 Hz non-integer-cycle ratio now **1.026** (was 2.419);
   440 Hz integer-cycle control **1.000** (unchanged). Both within oracle bands.
2. TC-0127 added and passes: non-integer-cycle [0.9, 1.3] ✓, integer control [0.95, 1.05] ✓,
   apply path emits no spurious action ✓.
3. Full STORY-011 suite: **20 passed** (previously 19; TC-0127 is the addition).
4. Method change, not threshold tune: only the peak-statistic boundary was fixed; no threshold,
   no window size, no gain parameter was altered.

## DEF-011-04
Status: Closed (2026-08-18)
Reported by: qa-automation-engineer
Linked test case: TC-0116 (report visibility) — covers the module-level
action record contents; the gap below is in the STORY-001 report path and
needs test-case-writer coverage at the pipeline/report-builder level.

Description:
`apply_stem_transient_restoration` returns a list of
`TransientRestorationAction` records (architecture.md "Action record
(public contract)"), and the STORY-001 pipeline correctly collects them:
`_apply_story_11_17_stem_mastering()` (pipeline.py ~line 167) returns them
in the `story_11_17_actions` dict, which is merged into
`MasteringResult.actions` (pipeline.py ~line 501,
`actions.update(story_11_17_actions)`).

But the actions never reach the generated report:

1. `report_builder.build_report()`
   (`stories/STORY-001/implementation/suno_mastering/report/builder.py`,
   signature at line 63) accepts per-stage action lists for resample, eq,
   stereo, repair_whistles, collapse_swish, shape_transients, and
   adaptive_harshness — but has NO parameter for the story_11_17 lists
   (`transient_restoration`, `harshness_control`, `stereo_imaging`,
   `bus_glue`). `ReportData` (line 17) has no corresponding field either.
2. The pipeline call site (pipeline.py ~line 460) consequently cannot pass
   them; the stage-8 records are dropped at the report boundary.
3. Real-track confirmation: the completed Twilight Caverns report JSON
   (`C:\Users\james\Downloads\Twilight Caverns_mastered_report.json`,
   2026-08-17) contains action keys only for
   `adaptive_harshness_actions`, `collapse_swish_actions`, `eq_actions`,
   `repair_whistles_actions`, `resample_action`,
   `shape_transients_actions`, `stereo_actions` — no `transient`
   or `restoration` key anywhere in the document (verified by recursive
   key search, `automation/_inspect_report.py`). The markdown report's
   "Corrective actions taken" section likewise lists no transient-
   restoration entry.

Linked contract: requirements.md requirement 6 ("Keep all restoration
decisions report-visible and traceable in the final audit log") and AC6
("Given each stem action, when the final report is generated, then the
stem name, reason, gain, and action type must be visible in the audit
log"); architecture.md reason-string conventions are explicitly labelled
"(report visibility)" and the `global_peak_before` field exists
specifically "for report context". All of these are defeated if the
records stop at `MasteringResult.actions`.

Impact:
On the real track, the user cannot tell whether Stage 8 boosted, clamped,
or skipped each stem — including the `skipped_headroom` case that the
DEF-011-01 rework specifically designed to be report-visible. The audit
trail for a safety-relevant decision (a hot stem returned unchanged) is
absent from the only persisted artifact. This also made the real-track
retest evidence for DEF-011-01 partially indirect: QA could confirm the
run no longer aborts, but cannot confirm from the report WHICH action
type fired on the hot stem.

Triage: Code-level
Rationale: the stage-side contract is implemented correctly; the drop is a
wiring gap between pipeline.py and report/builder.py (add the four action
lists to `build_report`/`ReportData` and pass them at the call site, then
render them in the report writers). No pipeline redesign required — this
mirrors how the other per-stage action lists already flow.

Fix notes:
(python-developer, 2026-08-18: added four fields to ReportData and four
parameters to build_report() in report/builder.py; updated the call site in
pipeline.py to pass story_11_17_actions values; added rendering blocks for
all four action types in report/render.py. JSON output via dataclasses.asdict
picks up the new fields automatically.)

---

## QA summary — DEF-011 rework pass (2026-08-17)

- Story suite: `venv\Scripts\python.exe -m pytest stories/STORY-011/automation -q`
  → **19 passed** (TC-0111–TC-0114, TC-0116 amended, TC-0117, TC-0118–TC-0126;
  stale TC-0115 replaced).
- STORY-016 orchestration regression:
  `venv\Scripts\python.exe -m pytest stories/STORY-016 -q` → **5 passed**.
- STORY-001 pipeline subset (call-chain relevant):
  `test_pipeline_stage_bars.py test_cli_progress.py test_story008_stem_separation.py`
  → **25 passed, 2 deselected**.
- STORY-001 full regression ("not slow"):
  `venv\Scripts\python.exe -m pytest stories/STORY-001/implementation/tests -q -m "not slow"`
  → **437 passed, 16 skipped, 16 deselected, 0 failures** in 1875.38 s
  (log: `artifacts/scratch/story001_regression.log`). No regressions
  attributable to the STORY-011 rework.
- Real-track verification (H5): the original failing production input,
  `C:\Users\james\Downloads\Twilight Caverns.wav`, now completes end-to-end
  (PASS, exit 0): `Twilight Caverns_mastered.wav` produced 2026-08-17,
  −12.60 → −13.54 LUFS, −2.48 → −2.55 dBTP (ceiling −1.00), 0 clipped
  samples, non-destructive integrity check PASSED. Stage 8 no longer
  aborts.
- Defect dispositions: DEF-011-01 Closed (clamp-then-report), DEF-011-02
  Closed (hilbert axis), DEF-011-03 Open (hilbert wrap-boundary spike —
  reproduced 2.4192 vs 1.0 control), DEF-011-04 Open (action records
  dropped from report path).
