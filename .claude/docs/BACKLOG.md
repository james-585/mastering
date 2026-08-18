# Backlog

Sequenced. Each story states its contract per HANDOFF.md H1. Do not reorder
without reason — the sequence reflects dependency, not preference.

---

## STORY-004 — Measurement correctness (DEF-201, DEF-203, DEF-204)

**Priority: first. Nothing downstream is trustworthy until this passes.**

```
Contract
Consumes:  existing analysis implementation
Produces:  corrected analysis + ground-truth suite
Consumed by: STORY-005 (targets derived from these measurements)
```

### Scope

**DEF-201 — band-limit detection. METHOD change required (H6).**

Previous fix raised the threshold 6→20 dB. Evidence it is still wrong:
- All five references now report UNSTABLE. A band limit is a fixed property
  of a file (DOMAIN.md §2) — universal instability means the method tracks
  programme content.
- Leftfield reports 8170 Hz on a 1995 CD master extending to ~20 kHz.
- Threshold detection cannot work on declining spectra, at any threshold.

Replace with cliff detection: sustained ≥24 dB/octave across adjacent bins
followed by a floor. No cliff → `None`.

**DEF-203 — mono-sum baseline. Derivation required (H4).**

−6.02 dB is wrong; correct floor is −3.01 dB (DOMAIN.md §3). Show the
derivation. Verify at ρ = 1.0, 0.0, −1.0. Expect "excess cancellation" to
disappear on all five references — they are summing normally.

**DEF-204 — coverage.**

Establish why STORY-003's tests did not catch either. If the pink-noise
negative control exists and passes, it is not wired to the function that
produced the reference measurements — that is a separate finding.

### Acceptance
1. Pink-noise negative control written first, confirmed failing, then fixed
2. All five references report a plausible band limit or `None`; no value
   below 10 kHz on a commercial master
3. Band limit stable across segments, or absent
4. Mono-sum derivation in architecture.md; verified at three ρ values
5. Excess cancellation reported only below −4.5 dB
6. H5 plausibility gate on the full reference report
7. Gate 2 review passes

---

## STORY-005 — Wire targets into mastering (DEF-202)

```
Contract
Consumes:  Measurements from STORY-004
Produces:  targets.json (Targets schema, ARCHITECTURE.md §3.3)
Consumed by: mastering chain (§3.4)
```

### Scope
- Target derivation stage producing `targets.json`
- Subset selection: three modern masters only (CLAUDE.md §4.1)
- Every target carries its range
- Mastering chain reads `targets.json`; **all hardcoded spectral constants
  removed** — no `-1.50`, `-3.00`, `-4.00` anywhere
- Missing `targets.json` → fail loudly, never fall back to defaults

### Acceptance
1. `targets.json` conforms to schema, lists contributing and excluded tracks
2. No numeric spectral or dynamics target in mastering source or config
3. Report shows target ranges, not bare medians
4. Excluded tracks demonstrably do not shift derived values
5. Absent `targets.json` fails with a clear error

---

## STORY-006 — Corrective EQ

**Prerequisite: STORY-004 and STORY-005 complete.** Correcting toward
unverified targets is worse than not correcting.

```
Contract
Consumes:  targets.json, AudioBuffer
Produces:  corrected AudioBuffer + CorrectiveAction list
Consumed by: dynamics stage
```

### Scope
- Shelves and wide bells only. No surgical notching — mastering operates on
  a sum (DOMAIN.md §4).
- Correct only when source is **outside** the target range, only to the
  nearest edge
- Max ±2 dB (CLAUDE.md §4.2 — reference spectral agreement is poor)
- Applied before dynamics (DOMAIN.md §5)

### Acceptance
1. Source within range → **no correction applied** (negative control)
2. Source outside range → corrected to nearest edge, not to median
3. Correction never exceeds cap
4. Every action logged with before/after
5. Listening check: level-matched A/B on two systems, does not sound worse

---

## STORY-007 — Consistency across a body of work

```
Contract
Consumes:  targets.json, multiple AudioBuffers
Produces:  batch report + per-track masters
Consumed by: terminal
```

Batch processing with cross-track consistency reporting. Per DOMAIN.md §4,
consistency across a release is one of mastering's genuine wins and is
currently unexploited.

### Acceptance
1. Batch of N tracks processed, consistency deviation reported
2. Outlier tracks flagged
3. Per-track and summary reports

---

## STORY-008 — Stem-based pre-mastering workflow (upstream stems only)

```
Contract
Consumes:  pre-separated stem bundle or upstream-supplied stem files
Produces:  processed stem set + re-summed stereo AudioBuffer ready for mastering
Consumed by: mastering pipeline
```

Allowed only when stems are supplied upstream. Not for stereo-derived source separation.

---

## STORY-009 — Wire C++ DSP extension into the mastering chain

> Historical note: this is a legacy experimental path, not the product's active
> architecture. The current product direction is Python-first, stem-aware, and
> CLI-based. C++ support remains optional and only relevant if future profiling
> proves a real bottleneck. This story is retained only as historical context
> and must not be treated as a current feature requirement.

```
Contract
Consumes:  src_cpp/spectral_repair.cpp (suno_dsp pybind11 module), STORY-007
           artifact-detector output (for repair_whistles only)
Produces:  three new/extended pipeline stages calling into suno_dsp, with
           logged actions in the report
Consumed by: mastering pipeline (pipeline.py)
```

The `suno_dsp` C++ extension exists (built via CMakeLists.txt / scikit-build)
but is not called anywhere in the Python pipeline. It contains three
functions; each needs a Gate 1 domain review before wiring, since none of
this has been through the story process yet.

### Scope

- **`repair_whistles`** (STFT notch filter): permitted only under the narrow
  exception in `CLAUDE.md` §4.2a — target frequencies must come from
  STORY-007's confirmed whistle-artifact detections, never free-form input.
  Placement: artifact-repair stage, before corrective EQ.
- **`shape_transients`** (fast/slow envelope transient shaper): dynamics
  stage, before loudness/limiting. Hardcoded attack/sustain time constants
  (2 ms / 50 ms / 5 ms smoothing) need H4 derivation or justification at
  Gate 1 — currently asserted, not derived.
- **`collapse_swish`** (mono-sum the side channel below a cutoff frequency):
  stereo-correction stage. Cutoff frequency needs a stated default and
  justification.

### Acceptance
1. Each function gated behind an explicit config flag; default off until
   Gate 1 clears it
2. `repair_whistles` only ever receives frequencies sourced from the
   STORY-007 detector — enforced in code, not just by convention
   (per CLAUDE.md §4.2a)
3. Every invocation logged in the returned `actions` payload and the report
4. Negative control: track with no detected whistles → `repair_whistles`
   not invoked, or invoked with an empty frequency list and a no-op result
5. Gate 1 mastering-engineer review passes on all three before implementation
6. Gate 2 review passes on measured output

---

## Next sprint follow-on tickets (deferred from STORY-007)

These items were intentionally deferred rather than left as active defects in
STORY-007. They are separate sprint tickets and should be scheduled as their
own work, not folded back into the Story 7 closure.

### SPRINT-007-01 — Project-level AudioBuffer contract cleanup

```
Contract
Consumes:  project architecture docs + analysis implementation
Produces:  resolved stage contract for AudioBuffer vs plain-array analysis input
Consumed by: all analysis stages and future stories
```

**Scope**
- Resolve the project-level mismatch between `docs/ARCHITECTURE.md` §3.1 and
  the actual STORY-001 analysis contract `(audio: np.ndarray, sr: int)`
- Decide whether the analyzer accepts `AudioBuffer` everywhere or whether the
  architecture is corrected to the current plain-array convention
- Update the architecture docs and any consuming story assumptions accordingly

**Acceptance**
1. Single agreed contract across project architecture and implementation
2. No code or story reads rely on a silently conflicting API
3. DEF-701 no longer needs to be tracked as an open defect

### SPRINT-007-02 — Sample-rate handling below 32 kHz

```
Contract
Consumes:  analysis input with arbitrary sample rate
Produces:  defined behaviour for 32 kHz and below
Consumed by: artifact analysis stage
```

**Scope**
- Define the required behaviour for sample rates below 32 kHz
- Confirm whether the detector should reject, degrade gracefully, or change
  windowing automatically
- Update requirements and test coverage to match the chosen behavior

**Acceptance**
1. Requirement is explicit and testable
2. Unsupported sample rates fail loudly or degrade by specification
3. No ambiguous silent resampling occurs

### SPRINT-007-03 — Performance SLA and throughput target

```
Contract
Consumes:  5-minute stereo track reference workload
Produces:  clear runtime target and measurement baseline
Consumed by: QA / release gate
```

**Scope**
- Define an explicit throughput target for a 5-minute stereo track at 44.1 kHz
- Record a measured baseline for the current implementation
- Decide whether this is a soft ceiling or enforced release gate

**Acceptance**
1. SLA exists in requirements or release gate docs
2. Measure is recorded and tracked
3. No open performance ambiguity remains in story requirements

### SPRINT-007-04 — Producer contract for artifact-detection input

```
Contract
Consumes:  upstream audio artifact produced by the rendering or mastering stage
Produces:  explicit producer story and file-format contract
Consumed by: artifact detector consumers
```

**Scope**
- Define which story/producer supplies the incoming audio buffer or file
- Clarify the object and file-format contract used by the downstream detector
- Resolve backlog ID mismatch between artifact detection references and the
  active story mapping

**Acceptance**
1. All upstream producer details are documented
2. No story assumes an unspecified consumer/producer relationship
3. Contract is unambiguous enough for implementation without code inspection

### SPRINT-007-05 — Resolve [OPEN] expected-value test cases

```
Contract
Consumes:  unresolved test-case values from STORY-007
Produces:  fully specified expected values or formally deferred assumptions
Consumed by: QA automation
```

**Scope**
- Resolve the test cases still marked `[OPEN]` in `stories/STORY-007/test-cases.md`
- Replace placeholders with measured values or explicit deferred assumptions
- Confirm whether open-question dependencies are resolved or intentionally
  deferred before automation is expected to pass

**Acceptance**
1. No unresolved `[OPEN]` assertions remain in the story's active test list
2. Every expected result is either measured or explicitly deferred with owner
3. QA automation can interpret the test contract without guesswork

### SPRINT-007-06 — Optional drift-rate detector for stationary whistle suppression

```
Contract
Consumes:  persistent whistle candidate detections
Produces:  optional vibrato/drift-rate suppression logic
Consumed by: artifact detector heuristics
```

**Scope**
- Add optional drift-rate suppression for sustained musical tones or vibrato
- Measure expected false-positive rate on real musical content before enabling
- Keep this enhancement out of the MVP path unless product requirements justify it

**Acceptance**
1. Benefit is quantified on real material
2. False-positive reduction is demonstrated
3. The enhancement remains clearly optional unless BA explicitly upgrades it

### SPRINT-007-07 — Human listening check and release validation

```
Contract
Consumes:  final artifact report and flagged outputs
Produces:  release sign-off evidence for human listening
Consumed by: release gate / project owner
```

**Scope**
- Run the human A/B check on level-matched material and confirm no acoustic
  degradation beyond the tool's stated reporting-only intent
- Record whether the artifact detector is a reporting aid or a release gate
- Close the final sign-off loop absent automated proof of sonic correctness

**Acceptance**
1. Human listening confirmation is recorded
2. Release gate decision is explicit: reporting-only vs. blocking artifact gate
3. No story-level sign-off relies solely on automated tests

---

## STORY-G1 — GUI

**Prerequisite: STORY-007 complete** (batch pipeline must exist before it can be wrapped).

```
Contract
Consumes:  complete mastering pipeline (single-track and batch modes)
Produces:  GUI application wrapping CLI entry points
Consumed by: end user (James, local Windows machine)
```

### Scope (to be confirmed by business-analyst)

Technology choice — desktop (tkinter/PyQt), local web (Gradio/Streamlit), or
TUI (Textual) — is deliberately deferred to BA stage. Constraints that apply
regardless of technology:

- Local-only; no server, no cloud dependency
- No new mastering logic in the GUI layer — all processing calls existing
  pipeline entry points
- Must expose: file selection, single-track master, batch folder processing,
  live progress, final report display
- Windows 11 Home, single-user deployment

### Acceptance

1. User can select an audio file and trigger a single-track master
2. User can select a folder and trigger batch processing
3. Progress is visible during processing
4. Mastering report is displayed in-app on completion
5. No mastering logic lives in GUI code — all delegates to pipeline modules

---

## STORY-F1 — VST3 hosting (PARKED)

**Do not schedule until the licence spike passes.**

Spike first, 15 minutes, outside the pipeline: does bx_mastering load and
authorise via `pedalboard.load_plugin()` outside a DAW? If not, void.

If viable, this is plausibly the largest quality jump available — but it
requires subprocess isolation (plugins can crash the interpreter
uncatchably) and must never become a hard dependency.

---

## Deliberately not on this backlog

| Item | Reason |
|---|---|
| Stem processing | Out of scope (CLAUDE.md §2). Architecture leaves the door open (§4). |
| RoEx integration | Out of scope. Cost. |
| Reverb removal, transient repair | Impossible at master stage (DOMAIN.md §4). |
| CI, remote git | Out of scope. |

---

## The lever this backlog does not pull

Per the mastering engineer: variance between Suno generations exceeds
anything mastering contributes. Generating ten takes and keeping the
cleanest will improve output more than several of these stories.

This tool is worth building. It is not the biggest lever. Both are true.
