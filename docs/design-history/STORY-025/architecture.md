# STORY-025 Architecture — Grounded Quality Validation

**Version:** 1.2
**Date:** 2026-08-17
**Status:** Gate 1 passed with notes (see §12 revision history) — implementation
may proceed. v1.2 disposes DEF-2501 and DEF-2503 (QA post-implementation
defects); see §12.

---

## Contract

```
Consumes:  stories/STORY-015/implementation/final_quality_review.py (evaluate_quality_review,
             _summary_metrics, _spectral_tilt, _stereo_width, _true_peak, QualityReviewResult)
           stories/STORY-017/implementation/real_world_validation.py (build_validation_report,
             ACCEPTED_PARAMETERS, DEFAULT_VALIDATION_SET)
           stories/STORY-016/implementation/orchestration.py (MasteringOrchestrator.run — the
             quality_review call site)
           suno_mastering.analysis.seven_band_balance.measure_seven_band_balance
           suno_mastering.analysis.dynamic_range.measure_dynamic_range
           suno_mastering.analysis.loudness.measure_integrated_lufs
           suno_mastering.analysis.artifact_detection.detect_artifacts
           suno_mastering.analysis.types.ArtifactDetectionResult
           suno_mastering.reference_analysis.config.ReferenceAnalysisConfig
           Reference Tracks/Sunday Club.wav (environment smoke-test fixture)

Produces:  grounded_quality_review.py — replacement verdict module (grounded metrics + mandatory
             LUFS-matching precondition + human-review-gated decision)
           lufs_matching.py — LUFS measurement + level-matching precondition
           environment_check.py — Demucs/Torch stem-separation smoke test
           human_review_capture.py — real (non-simulated) human listening capture
           Updated real_world_validation.py (env check + human review wiring, no more
             auto-generated pass/reject prose standing in for a listen)
           Updated orchestration.py call site (passes sample_rate, uses grounded module)

Consumed by: STORY-017 real-world validation re-run (interface only — see §9, OQ7 resolution);
             the release gate that currently reads evaluate_quality_review / build_validation_report
```

---

## 1. Design Intent

STORY-015's `evaluate_quality_review()` computed its verdict from two proxies
(`clarity_delta` — a loudness proxy mislabeled as clarity, and `_spectral_tilt` — a
2-bin FFT ratio) and never consulted STORY-007's artifact-density measurement or
STORY-001's BS.1770 loudness measurement. STORY-017's `build_validation_report()`
then wrapped that proxy verdict in auto-generated prose and left `human_decision`/
`human_note` unpopulated by default.

This story does **not** invent a new scoring formula to replace the old proxies.
It does two structurally different things:

1. **Replaces the proxy measurements with the project's existing grounded
   measurements** (seven-band spectral balance, TT DR, artifact density), computed
   only after a mandatory LUFS-matching precondition, per CLAUDE.md §6.3.
2. **Removes the verdict-computing authority from metrics entirely.** Per
   requirements.md's "Rejected as out of scope" section and DOMAIN.md's constraint
   that metrics cannot substitute for perceptual judgment on subjective qualities,
   the grounded metrics in this story produce **evidence and risk flags**, not a
   `pass`/`reject`/`refine` decision. The decision itself is always the human's.
   A run with no human review cannot produce a trusted verdict — it produces an
   explicit `pending_human_review` state that must not be treated as a pass.

This resolves OQ1 more simply than a threshold-combination formula would: there is
no if/elif chain deciding musical quality from numbers. The if/elif chain that
existed in `final_quality_review.py` is deleted, not re-parameterised.

**v1.2 note:** point 2 above (verdict authority removed from metrics) has a
direct consequence for `orchestration.py`'s *internal, automated*
`export_allowed` gate, which cannot obtain a human review inline during a
pipeline run. §3.1 makes that consequence explicit, since DEF-2501 found it
was not addressed by the original call-site description in §2/§3.

---

## 2. Module Layout — New and Changed Files

### New files (`stories/STORY-025/implementation/`)

```
grounded_quality_review.py   # evaluate_quality_review(), GroundedMetrics, QualityReviewResult
lufs_matching.py              # measure + match_levels(), LevelMatchResult, LevelMatchError
environment_check.py          # verify_stem_separation_environment(), EnvironmentCheckResult
human_review_capture.py       # capture_human_review(), HumanReviewRecord, HumanReviewRequiredError
review_config.py              # GroundedReviewConfig dataclass (PROVISIONAL constants live here)
```

### Existing files changed

| File | Change |
|---|---|
| `stories/STORY-016/implementation/orchestration.py` | `MasteringOrchestrator.run()`'s call to `evaluate_quality_review(original, final_mix, human_review=human_review)` (quality_review stage) is changed to import from `grounded_quality_review` and pass `sample_rate`: `evaluate_quality_review(original, final_mix, sr=sample_rate, human_review=human_review)`. **v1.2 (DEF-2501 disposition):** this call-site change is confirmed, but `export_allowed`'s computation is no longer `review.decision == "pass"` — see §3.1 for the full redefinition, which is a required part of this file's change, not optional. |
| `stories/STORY-017/implementation/real_world_validation.py` | `build_validation_report()` gains a mandatory environment-verification step before any stem-first `pipeline.run(..., use_stems=True, ...)` call, and a mandatory human-review input per file (no default bypass). Auto-generated `summary`/`auditable_summary` prose describing what a review "should" find is removed; report text is built from the grounded `before_after` evidence plus the actual `human_note`. See §7–§8. |

### Existing files unchanged (retained, deprecated)

`stories/STORY-015/implementation/final_quality_review.py` remains in place for
backward compatibility (same precedent as STORY-006 §3 keeping `eq.py`'s
`apply_corrective_eq()` after `corrective_eq.py` superseded it). It is no longer
imported by `orchestration.py` or `real_world_validation.py`. python-developer
should add a one-line deprecation note to its module docstring; its internals
are not touched by this story (`_spectral_tilt`, `clarity_delta`, etc. stay as
literal historical code, not deleted, since nothing in scope requires deleting
dead code from a prior story).

---

## 3. Pipeline Integration Point

Confirmed from `orchestration.py`: `MasteringOrchestrator.run()` holds `original`
(the pre-processing float64 copy taken at ingest) and `final_mix` (post bus-glue,
post final-safety-limiter output) in scope at the point it currently calls
`evaluate_quality_review(original, final_mix, human_review=human_review)` — this
is the sole call site for the quality-review stage. `sample_rate` is already a
parameter of `run()`, so no new data needs to be threaded through the stem/mix
pipeline — only the one call site changes (new `sr=sample_rate` keyword and a
new import). No stage reordering. `human_review` continues to flow through
`run()`'s existing parameter unchanged; §8 defines who is responsible for
populating it before `run()` is invoked from the real-world validation path.

```
... bus_glue → final_safety → [quality_review: grounded_quality_review.evaluate_quality_review] → export_allowed
```

---

### 3.1 `export_allowed` redefinition — DEF-2501 disposition (v1.2)

**The problem.** `grounded_quality_review.evaluate_quality_review()`'s
`decision` is `"pending_human_review"` whenever `human_review is None` (§7.3)
— by design, metrics alone can no longer render pass/reject/refine. But
`orchestration.py`'s `run()` is an internal, synchronous pipeline call: it has
no mechanism to obtain a real human review inline, and the overwhelming
majority of its invocations (batch runs, any caller other than the
human-in-the-loop validation path in §8) pass `human_review=None`. If
`export_allowed` were left as `review.decision == "pass"` unchanged, it would
go from "always a deterministic boolean" (old proxy module) to "false on
almost every automated run" (new module) — silently turning every batch
pipeline invocation into a permanent export block. That is not a defensible
reading of this story's intent, and it is exactly the kind of decision this
repo's rules require the architect to make explicitly rather than leave to
the developer.

**Disposition: `export_allowed` is redefined as a strictly mechanical
export-safety gate, decoupled from the musical quality verdict.**

This is a real conceptual split that already existed implicitly in the old
code (peak/finite-sample safety vs. "does it sound better") but was never
made explicit because the old proxy review always returned a deterministic
verdict, masking the difference. STORY-025 must make the split explicit
because it is the story that removes automated verdict authority from
metrics.

- **Export safety (mechanical, orchestration-owned, unchanged in spirit from
  today's actual safety guarantees):** the exported signal must be finite (no
  NaN/Inf) and within the true-peak safety ceiling already enforced by
  `_apply_final_safety()` (≤ 1.0 linear / ~0 dBTP, attenuated to 0.98 when
  needed). This is a factual, always-computable check — it does not require a
  human and does not require the grounded metrics module at all. It answers
  "is it safe to write this file to disk," not "is this a good master."
- **Quality verdict (musical, human-owned, per §1/§7.3):** `review.decision`
  (`pass` | `reject` | `refine` | `pending_human_review`) and
  `review.flags`/`review.before_after` continue to be computed by
  `grounded_quality_review.evaluate_quality_review()` and are carried
  unmodified in `result["quality_report"]`. This is evidence for a human,
  never a release-gate boolean by itself.

**Revised `export_allowed` logic:**

```python
review = evaluate_quality_review(original, final_mix, sr=sample_rate, human_review=human_review)

mechanically_safe = bool(np.isfinite(final_mix).all()) and final_peak <= 1.0

if human_review is not None and review.decision in {"pass", "reject", "refine"}:
    # A real human verdict was supplied inline (e.g. orchestration invoked from
    # the human-in-the-loop path after capture_human_review() has already run).
    # Honor it: an unsafe-but-human-approved file must still not export, and a
    # safe-but-human-rejected file must not export either.
    export_allowed = mechanically_safe and (review.decision == "pass")
else:
    # review.decision == "pending_human_review": no trusted musical verdict is
    # available inline. export_allowed here answers ONLY "is this file safe to
    # write," not "is this a good master" — those are different questions and
    # must not be conflated.
    export_allowed = mechanically_safe

result["quality_verdict_pending"] = review.decision == "pending_human_review"
```

`result["export_reason"]` must be updated to distinguish the two failure
modes in its text (e.g. `"Export blocked: signal contains non-finite samples
or exceeds the true-peak safety ceiling."` vs. the existing
human-decision-based reject/refine strings) — a caller reading
`export_reason` must be able to tell a technical safety failure from a
musical rejection without inspecting `quality_report` separately.

**The existing `np.allclose(original, final_mix)` short-circuit is retained
but must no longer overwrite `review.decision`.** Today's code forcibly sets
`review.decision = "pass"` when the signal is unchanged — that made sense
when metrics had verdict authority, but forcibly minting a `"pass"` verdict
this way now contradicts §1's removal of automated pass authority from
metrics. The corrected behavior: when the signal is unchanged,
`export_allowed` may still be `True` via the mechanical-safety path above (an
unchanged signal is trivially safe), and `result["audit"]` should note why (no
processing occurred), but `review.decision` itself must be left as whatever
`evaluate_quality_review` actually returned (ordinarily
`"pending_human_review"` when no human review was supplied). This is an
implementation correction flowing directly from this disposition, not a
further open question.

**Why not require a human review before allowing any export at all** (the
alternative of making `export_allowed` always `False` without one)? Because
`export_allowed` here is this repo's *mechanical* release gate — the same
concept STORY-016 originally built it to be (peak safety, finite samples,
override bookkeeping) — not the "was this heard and approved" gate, which is
`build_validation_report()`'s job (§8) via `capture_human_review()`.
Conflating the two would make every batch/CI-style pipeline run permanently
unexportable the moment this story's module is wired in, which is a
regression in tool usability with no compensating safety benefit — the actual
audio-safety guarantee (peak ceiling, finiteness) is unaffected either way.
Any caller that wants a human-gated release must go through
`build_validation_report()`, which already enforces "no default bypass" (§8,
AC9) at that layer.

---

## 4. lufs_matching.py Design

### 4.1 Why gain-matching, and which side moves

CLAUDE.md §6.3: level-matching is mandatory before comparing a mastered result to
a reference, because the streaming-safe target can sound quieter than the
reference when heard unmatched. Here "the reference" the human is judging against
is the **original** (pre-master) file — the human needs to know whether the
*master itself*, not a loudness difference, made the mix sound better. The method
is therefore: measure integrated LUFS of both via the existing
`measure_integrated_lufs`, then apply a single linear gain to `processed` so its
integrated LUFS equals the original's.

### 4.2 Tolerance — derived, not asserted

A linear gain of `g` dB shifts every ungated per-block power in BS.1770 by
exactly `g` dB, so a single computed gain step (`gain_db = original_lufs -
processed_lufs`) reproduces the target LUFS to within numerical precision in the
overwhelming majority of cases. The only source of residual error is a block
that crosses the relative (−10 LU) gate threshold as a side effect of the gain
change, which is a real but narrow edge case (near-silent or highly bimodal
material). `lufs_match_tolerance_lu = 0.5` is the tolerance used to re-verify the
match after applying the gain — chosen as a safety margin around the gating edge
case above, not an arbitrary round number. It is not itself a decision threshold;
it only decides whether the match step succeeded.

### 4.3 Interface

```python
@dataclass
class LevelMatchResult:
    original_lufs: float
    processed_lufs: float           # before matching
    matched_processed_lufs: float   # after matching, re-measured
    gain_applied_db: float
    matched_processed: np.ndarray
    within_tolerance: bool


class LevelMatchError(RuntimeError):
    """Raised when level-matching cannot bring processed audio within tolerance
    of the original's integrated LUFS (e.g. -inf LUFS on a near-silent input)."""


def match_levels(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
    tolerance_lu: float = 0.5,
) -> LevelMatchResult:
    """Measure integrated LUFS for both via measure_integrated_lufs, apply a
    single linear gain to `processed` so its LUFS matches `original`, and
    re-measure to confirm. Raises LevelMatchError if either LUFS measurement
    is non-finite (e.g. silence-gated to -inf) or the re-measured match falls
    outside tolerance_lu. Never silently returns an unmatched result."""
```

This is the sole legal entry point for producing a level-matched pair.
`grounded_quality_review.py` has no code path that computes a spectral/DR/
artifact delta without calling this first — resolving AC5/AC6 structurally
rather than by convention.

---

## 5. environment_check.py Design

### 5.1 Scope, per the repo-memory fact

`memories/repo/suno-mastering-status.md` already confirms Demucs 4.1.0 / torch
2.13.0+cpu are installed and `htdemucs_6s` real weights separated a full track
into 6 coherent stems in ~123s CPU time. That satisfies "does this environment
work at all" as a one-time fact. What is still missing is a **repeatable,
lightweight, per-run check** that the specific environment `build_validation_report()`
is executing in right now can actually do real separation — not a heavyweight
provisioning stage, and not a re-run of the full 123s job on every validation
pass.

### 5.2 Design — short-clip smoke test

**v1.2 (DEF-2503 disposition) — the per-stem noise-floor requirement is
revised. See §5.2.1 immediately below for the corrected criterion; the fields
and signature shown here are updated accordingly.** The narrative rationale in
the original paragraph (clip duration, fixed offset) is unchanged and
retained.

```python
@dataclass
class EnvironmentCheckResult:
    available: bool
    torch_version: Optional[str]
    demucs_version: Optional[str]
    model_name: str
    stem_count: int
    elapsed_s: float
    checked_at: datetime
    error: Optional[str]
    # v1.2 additions (DEF-2503) — surfaced for audit, not just a pass/fail bool:
    reconstruction_error_ratio: float          # see §5.2.1
    verified_nonsilent_stems: List[str]        # which stems cleared the noise floor
    noise_floor_checked_stems: List[str]       # which stems the noise floor was even applied to


class EnvironmentVerificationError(RuntimeError):
    """Raised when real Demucs/Torch stem separation cannot be confirmed."""


_DEFAULT_FIXTURE = _REPO_ROOT / "Reference Tracks" / "Sunday Club.wav"
_FIXTURE_CLIP_SECONDS = 8.0          # short slice — smoke test, not a full-track re-run
_FIXTURE_CLIP_OFFSET_SECONDS = 30.0  # Gate 1 Finding 4 action item — see rationale below


def verify_stem_separation_environment(
    fixture_path: Path = _DEFAULT_FIXTURE,
    clip_seconds: float = _FIXTURE_CLIP_SECONDS,
    clip_offset_seconds: float = _FIXTURE_CLIP_OFFSET_SECONDS,
    model_name: str = "htdemucs_6s",
) -> EnvironmentCheckResult:
    """Import torch and demucs, read clip_seconds of fixture_path starting at
    clip_offset_seconds (not the literal file start) in-memory (no
    intermediate file written), run real htdemucs_6s inference, and assert
    (a) every returned stem is finite (no NaN/Inf), (b) the stems sum back to
    approximately reconstruct the input clip (§5.2.1 — proves real,
    coherent model execution regardless of any individual stem's content),
    and (c) the near-universal stem subset {drums, bass, vocals} individually
    clears a noise floor (§5.2.1 — proves the model is not silently
    zeroing its output for the stems expected to be active in virtually any
    mixed-music window). 'other', 'piano', and 'guitar' are NOT required to
    individually clear the noise floor — see §5.2.1 for why. Raises
    EnvironmentVerificationError with a clear message on any import failure,
    inference failure, reconstruction-tolerance failure, or degenerate
    near-universal-stem result — no silent fallback. Also raises if
    fixture_path's duration is shorter than clip_offset_seconds +
    clip_seconds, rather than silently clipping to a shorter window. Does not
    cache across process runs; each invocation of build_validation_report()
    re-verifies the environment it is actually running in, at a cost of
    single-digit seconds (an 8 s clip scaled from the ~123 s / full-track
    reference point is well under the compute budget of the validation run
    itself)."""
```

`clip_seconds=8.0` is a design choice for keeping the check "lightweight,"
proportionate to the confirmed ~123s/full-track data point. The
mastering-engineer's Gate 1 review confirmed 8 s is adequate for this check's
actual job — confirming real inference runs at all (broken import, broken
model load, silently-zero-output stem), not judging separation quality — so
duration is unchanged; see gate1-review.md Finding 4 and §12 below.

**`clip_offset_seconds = 30.0` (Gate 1 Finding 4 action item):** the clip is
now taken from a fixed 30-second offset into `Sunday Club.wav`, not from the
literal file start. Rationale: an intro fade-in, lead-in silence, or a
sparse/ambient opening passage — plausible on this file, and common in
electronic music generally — could sit near the noise floor at `t=0` for
reasons unrelated to whether the model/environment actually works, producing
a false `EnvironmentVerificationError` on a healthy environment. 30 s is
chosen as a value comfortably past a typical intro/fade-in without requiring
a by-ear/level check of this exact fixture to be re-verified on every run; it
is a safety margin, not a value derived from measuring this specific file. If
`Sunday Club.wav` is ever replaced with a different fixture, this offset
should be re-confirmed against the new file's actual intro length.

### 5.2.1 Corrected verification criterion — DEF-2503 disposition (v1.2)

**The problem.** The original design asserted every one of `htdemucs_6s`'s six
stems (`drums, bass, other, vocals, piano, guitar`) must individually clear a
fixed noise floor. Against the mandated fixture/offset, the `other` stem is
genuinely near-silent in this 8 s window — real, ordinary musical sparsity,
not model failure (5 of 6 stems clear the floor; only `other` does not).
Lowering the floor only shifts the false-negative risk to whichever stem is
quietest in a given window; it does not fix the structural mismatch between
"all six stems individually audible" and "real separation occurred." Picking
a different fixture/offset does not generalize — any real mixed track can
have a section where `other`/`piano`/`guitar` are legitimately silent, so a
fixture chosen to avoid this today is fragile to any future change of
fixture, offset, or model.

**Disposition: replace the single "all six stems non-degenerate" requirement
with two combined checks, neither of which is fragile to normal musical
sparsity:**

1. **Sum-reconstruction check (primary — proves the model actually ran and
   produced coherent output, independent of any stem's content).**
   `htdemucs_6s` stems are trained so that summing all returned stems
   approximately reconstructs the input mix (this is the decomposition
   objective the model is trained against — the six stems are a *partition*
   of the mix's energy, not six independent signals). Compute:

   ```python
   reconstructed = sum(stems.values())
   residual = clip - reconstructed
   reconstruction_error_ratio = (
       float(np.sqrt(np.mean(residual ** 2))) / float(np.sqrt(np.mean(clip ** 2)) + 1e-12)
   )
   ```

   and require `reconstruction_error_ratio <= 0.5` (residual RMS no more than
   half the input clip's RMS). This is a deliberately generous bound: it is a
   smoke test for "did real, coherent separation happen" (catching an
   all-zero, all-noise, or garbage-output model — cases where the residual
   would be comparable to or larger than the original signal), not a
   separation-quality benchmark. **PROVISIONAL, same category as
   `artifact_density_regression`/`spectral_shift_flag_db` (§7.1):** the exact
   `0.5` bound is not derived from a corpus of known-good vs. known-broken
   inference runs; it is a reasoned, generous smoke-test margin, flagged here
   for the mastering-engineer to validate/tighten against real captured runs
   (e.g. compare `reconstruction_error_ratio` on this fixture across several
   confirmed-healthy runs to see where it actually sits) before being treated
   as fully calibrated. It is not blocking implementation because — like the
   other two PROVISIONAL constants — it gates a smoke-test failure that a
   human/CI log can inspect and revise, not a silent musical decision.
2. **Near-universal-subset noise-floor check (secondary — catches partial
   degeneracy the sum check could theoretically mask, e.g. one
   silently-zeroed stem whose energy is small enough not to move the residual
   ratio much).** Require only `{"drums", "bass", "vocals"}` to individually
   clear the existing noise floor (`MasteringConfig.silence_gate_threshold_db`,
   unchanged). These three are the near-universal subset for mixed
   popular/electronic music — a mixed track without any drums, bass, *and*
   vocals simultaneously for an entire 8 s window is atypical, whereas
   `other`/`piano`/`guitar` are commonly and legitimately silent for extended
   passages depending on arrangement. This is confirmed empirically for the
   mandated fixture/offset by DEF-2503 itself. `other`, `piano`, and `guitar`
   are still checked for finiteness (existing check, unchanged) but are
   **not** required to individually clear the noise floor.

Both checks must pass; either failing raises `EnvironmentVerificationError`
with a message identifying which check failed and the measured value (no
silent pass on a partial result). `EnvironmentCheckResult` carries
`reconstruction_error_ratio`, `verified_nonsilent_stems` (the near-universal
subset that actually cleared the floor), and `noise_floor_checked_stems`
(always `["drums", "bass", "vocals"]` for `htdemucs_6s`, but not hardcoded in
the check itself — read from a small `model_name -> near_universal_stems`
mapping in `environment_check.py` so a different `model_name` does not
silently reuse `htdemucs_6s`'s subset) for audit visibility — an
`EnvironmentCheckResult` with `available=True` should let a human see *why*
it passed, not just that it did.

**Why not "assert all six stems sum back close to the original, full stop,
with no per-stem check at all"** (the simplest alternative)? Because the sum
check alone cannot distinguish "the model correctly attributed all energy to
`drums` and legitimately zeroed the other five stems on this window" from a
genuinely different, more concerning failure — a model that has collapsed to
outputting the input mix as a single stem — from "the model correctly
attributed energy across a realistic subset of stems." A pathological model
that copies the input to one stem and zeros the rest would pass a sum-only
check while providing no real evidence of *separation* capability, only of
signal pass-through. The near-universal-subset check keeps a floor on "did
separation-shaped output occur," while accepting that not all six stems need
audible content in every window.

### 5.3 How `build_validation_report()` uses it (AC7)

`build_validation_report()` calls `verify_stem_separation_environment()` once,
before any file enters `pipeline.run(..., use_stems=True, ...)`. On success, the
report carries `"stem_first_verified": True` plus the `EnvironmentCheckResult`
fields for audit (v1.2: including `reconstruction_error_ratio` and
`verified_nonsilent_stems`, so a reviewer can see the actual evidence, not just
a boolean). On `EnvironmentVerificationError`, the report does **not**
silently continue under stereo fallback as if that were equivalent — it sets
`"stem_first_verified": False`, records the failure reason, and every file
processed in that run is labelled in its report item as
`"stem_first_path_unverified"`. This satisfies AC7's "report that the stem-first
path is unverified" without crashing the whole validation run outright (a
build_validation_report caller may still want the stereo-fallback numbers for
other purposes, but they must not be presented as validating the stem-first
product direction per CLAUDE.md §3).

---

## 6. human_review_capture.py Design (OQ6)

### 6.1 Mechanism

Two supported input sources, either of which must yield a fully-populated,
non-templated record — there is no third "skip" path:

1. **Structured review file** (preferred for batch/reproducible validation runs):
   a JSON file at `<audio_path>.review.json` alongside each validation track,
   containing `{"reviewer": str, "decision": "pass"|"reject"|"refine", "note": str,
   "reviewed_at": iso8601 str}`.
2. **Interactive CLI prompt** (for single-file/manual review): `input()` prompts
   for decision and note at the terminal. If stdin is not a TTY (non-interactive
   process, e.g. invoked from a script with no attached terminal), this path
   raises rather than silently defaulting — a non-interactive environment cannot
   produce a "real" human review.

### 6.2 Anti-templating check

`note` must be non-empty after stripping, at least 10 characters, and must not
match any of the literal auto-generated phrases this story removes from
`real_world_validation.py` (e.g. starting with `"REJECT — real-world validation
on"` or `"the source remained musically weak"`) — a denylist of the exact
strings `_summarise_decision()`/`_build_tuning_decisions()` used to generate, so
a stale copy-paste of the old auto-text cannot pass as if a human wrote it.

### 6.3 Interface

```python
@dataclass
class HumanReviewRecord:
    reviewer: str
    decision: str            # "pass" | "reject" | "refine"
    note: str
    reviewed_at: str          # ISO 8601
    method: str                # "review_file" | "cli_prompt"


class HumanReviewRequiredError(RuntimeError):
    """Raised when no valid, non-templated human review can be obtained."""


def capture_human_review(
    track_path: Path,
    interactive: bool = True,
) -> HumanReviewRecord:
    """Look for '<track_path>.review.json' first; if absent and interactive is
    True, prompt at the terminal. Validates decision/note per §6.2. Raises
    HumanReviewRequiredError if neither source yields a valid record."""
```

`evaluate_quality_review()` itself continues to accept a plain
`human_review: Optional[Dict[str, str]] = None` (see §7.3) so the
grounded-metrics computation stays unit-testable without a person in the loop
(NFR reproducibility) — `capture_human_review()` is the thing that
`real_world_validation.py` calls to actually obtain that dict before invoking
the orchestrator/quality-review path in the trusted validation flow.

---

## 7. grounded_quality_review.py Design

### 7.1 GroundedReviewConfig (`review_config.py`)

All comparison thresholds live in one dataclass — never as literals in
`grounded_quality_review.py` — per this repo's "derive every constant, never
assert one inline" convention.

```python
@dataclass
class GroundedReviewConfig:
    reference_analysis: ReferenceAnalysisConfig = field(default_factory=ReferenceAnalysisConfig)
    lufs_match_tolerance_lu: float = 0.5          # derived, §4.2 — not a verdict threshold

    # Reused, not invented: STORY-006's already-derived DR policy constant.
    # dr_max_reduction_db (3.0) is the project's existing "never reduce DR by
    # more than this vs. source" cap (config.py); reused here as the same
    # magnitude that would flag a DR *regression* on before/after comparison.
    dr_regression_db: float = 3.0                 # = MasteringConfig.dr_max_reduction_db

    # PROVISIONAL — no existing project data derives this. STORY-007 only
    # normalizes overall_artifact_density_score to [0.0, 1.0]; it never
    # defines a before/after comparison delta. Flagged for mastering-engineer
    # (§10) to validate/replace against real reference-track before/after
    # measurements before this is treated as a real gate.
    # Gate 1 action item (Finding 1): the raw artifact_density_delta value
    # and this PROVISIONAL label must both be surfaced in
    # evaluate_quality_review's audit trail (§7.3), not just the boolean
    # flag — see gate1-review.md Finding 1, §12 revision history.
    artifact_density_regression: float = 0.05     # PROVISIONAL

    # PROVISIONAL — RMS shift across the six non-reference seven-band deltas
    # (see §7.2) large enough to flag "the tonal balance moved substantially"
    # for human attention. Not a pass/fail threshold — it only decides
    # whether a flag is raised for the human reviewer to weigh.
    # Gate 1 action item (Finding 2): same audit-surfacing requirement as
    # artifact_density_regression above — see gate1-review.md Finding 2,
    # §12 revision history.
    spectral_shift_flag_db: float = 2.0           # PROVISIONAL
```

### 7.2 GroundedMetrics — the grounded, evidence-only computation

```python
@dataclass
class GroundedMetrics:
    original_lufs: float
    processed_lufs: float
    lufs_gain_applied_db: float
    spectral_band_delta_db: Dict[str, float]   # 7 keys, "mid" delta always 0.0 by definition
    spectral_rms_shift_db: float               # RMS of the six non-"mid" band deltas
    dr_original: float
    dr_processed: float
    dr_delta: float
    artifact_density_original: float
    artifact_density_processed: float
    artifact_density_delta: float
    width_delta: float                          # retained from STORY-015 _stereo_width (§7.4)
    peak_delta_db_unmatched: float               # retained from STORY-015 _true_peak; NOT level-matched (§7.5)
    flags: List[str]                             # risk evidence only, never a verdict


def compute_grounded_metrics(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
    config: GroundedReviewConfig = GroundedReviewConfig(),
) -> GroundedMetrics:
    """
    1. match = match_levels(original, processed, sr, config.lufs_match_tolerance_lu)
       (raises LevelMatchError, not swallowed — AC6).
    2. seven_band_original = measure_seven_band_balance(original_mono_or_stereo, sr, config.reference_analysis)
       seven_band_processed = measure_seven_band_balance(match.matched_processed, sr, config.reference_analysis)
       per-band delta = processed.relative_db - original.relative_db (dict keyed by band name).
       spectral_rms_shift_db = sqrt(mean(delta_i**2 for band != "mid")) — "mid" excluded because
       relative_db is defined relative to that band, so its own delta is always exactly 0.0 and
       would only dilute, never inform, the RMS.
    3. dr_original = measure_dynamic_range(original, sr, config.reference_analysis)
       dr_processed = measure_dynamic_range(match.matched_processed, sr, config.reference_analysis)
       dr_delta = dr_processed - dr_original.
    4. _, artifact_original = detect_artifacts(original, sr)
       _, artifact_processed = detect_artifacts(match.matched_processed, sr)
       artifact_density_delta = artifact_processed.overall_artifact_density_score
                                 - artifact_original.overall_artifact_density_score.
    5. width_delta, peak_delta_db_unmatched computed on the RAW (unmatched) original/processed
       pair — see §7.5 for why true peak stays unmatched.
    6. flags: append "dynamic_range_regression" if dr_delta <= -config.dr_regression_db;
       append "artifact_density_regression" if artifact_density_delta >= config.artifact_density_regression;
       append "spectral_shift_significant" if spectral_rms_shift_db >= config.spectral_shift_flag_db.
       No flag is a pass/fail decision by itself.
    """
```

### 7.3 evaluate_quality_review — decision authority moves to the human

```python
@dataclass
class QualityReviewResult:
    decision: str                 # "pass" | "reject" | "refine" | "pending_human_review"
    summary: str
    flags: List[str]
    before_after: Dict[str, float]   # flattened GroundedMetrics scalar fields (spectral_band_delta_db
                                       # flattened as "spectral_band_delta_db.<band>")
    human_decision: Optional[str] = None
    human_note: str = ""
    audit: List[str] | None = None

    def to_dict(self) -> Dict[str, Any]: ...


def evaluate_quality_review(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
    human_review: Optional[Dict[str, str]] = None,
    config: GroundedReviewConfig = GroundedReviewConfig(),
) -> QualityReviewResult:
    """
    metrics = compute_grounded_metrics(original, processed, sr, config)   # AC1-AC6

    If human_review is None:
        decision = "pending_human_review"
        human_decision = None; human_note = ""
        audit = ["No human listening review was supplied; this result is evidence only "
                 "and must not be treated as a trusted pass/reject/refine verdict."] + flag audit lines
    Else:
        decision = human_review["decision"] (must be one of pass/reject/refine, else raise ValueError)
        human_decision = decision; human_note = human_review["note"]
        audit = [f"Human review ({human_review.get('reviewer', 'unspecified')}): {human_note}"]
              + flag audit lines describing which grounded flags were present as supporting evidence

    summary is built from decision + flags, never from a hardcoded per-decision template string
    that could be mistaken for review prose (distinguish from STORY-017's old auto-text bug).
    """
```

**Flag audit lines — Gate 1 action item (Findings 1 and 2):** for every flag
present in `metrics.flags`, the corresponding audit line must state the raw
delta value behind it, not just the flag name, and — for the two PROVISIONAL
thresholds — must state plainly that the threshold is unvalidated. This
applies in **both** branches above (`human_review is None` and populated), so
the number and its provisional status reach the human reviewer whether or
not a review has yet been recorded. Required format per flag:

- `"artifact_density_regression"` →
  `f"artifact_density_regression flag (PROVISIONAL threshold "
  f"{config.artifact_density_regression}, not calibrated against reference "
  f"data): raw artifact_density_delta = {metrics.artifact_density_delta:+.4f}"`
- `"spectral_shift_significant"` →
  `f"spectral_shift_significant flag (PROVISIONAL threshold "
  f"{config.spectral_shift_flag_db} dB, not calibrated against reference "
  f"data): raw spectral_rms_shift_db = {metrics.spectral_rms_shift_db:.2f} dB"`
- `"dynamic_range_regression"` → states the raw `dr_delta` the same way, but
  **without** a PROVISIONAL caveat — `dr_regression_db` is a derived reuse of
  STORY-006's `dr_max_reduction_db` (§7.1), not an undervalidated placeholder.

This is a Gate 1 action item, not optional formatting — a human reading only
the flag name (e.g. "artifact_density_regression") without the number behind
it cannot judge whether a provisional, uncalibrated threshold firing is worth
weighing at all. python-developer must implement these exact audit-line
contents, not a paraphrase.

**AC1–AC3 resolution**: `_spectral_tilt` and `clarity_delta` are not present anywhere in
`compute_grounded_metrics`/`evaluate_quality_review` — the seven-band and TT DR
measurements are the only spectral/dynamics inputs, and no further ad hoc metric
is invented (`spectral_rms_shift_db` is a plain RMS aggregation of the *existing*
`measure_seven_band_balance` output, not a new measurement method).

**AC8–AC9 resolution**: `evaluate_quality_review` accepts `human_review=None` for
unit-testability (NFR reproducibility — test-case-writer can assert
`compute_grounded_metrics` determinism without a person). But `decision` in that
case is `"pending_human_review"`, a value distinct from all three legitimate
verdicts, so no caller can mistake it for a trusted pass. §8 makes
`real_world_validation.py`'s default path require a real `human_review`.

§3.1 (v1.2) makes `orchestration.py`'s internal `export_allowed` gate not
depend on this value being anything other than `pending_human_review` in the
common automated-run case.

### 7.4 `_stereo_width` and `_true_peak` — OQ4 resolution (assumption pending confirmation)

Requirements OQ4 asks whether these should remain supplementary or be superseded.
**Assumption made here, pending mastering-engineer confirmation (§10):** they
remain in `before_after` as supplementary reported evidence (ported verbatim from
`final_quality_review.py`, unchanged math) but do **not** feed any flag or the
decision. Rationale: the story's four named problems (spectral tilt, clarity,
artifact density, LUFS) do not call these two wrong, but nothing in this story's
scope asks for new flag logic to be built around them either — inventing new
width/peak flag thresholds would violate the "no new ad hoc metric" instruction
in AC3's spirit even though AC3 only names spectral/DR/artifact explicitly.

**Gate 1 disposition: confirmed as-is, no change** (gate1-review.md Finding 3 —
see §12). The mastering-engineer confirmed both measurements are legitimate,
already-grounded, and correctly excluded from flag/decision logic; inventing a
new threshold here would itself be exactly the un-derived-constant risk this
project is trying to avoid.

### 7.5 Why `peak_delta_db_unmatched` stays unmatched

True-peak safety is a property of the actual exported file at its real output
level, not a relative "did it get better" comparison — level-matching for an A/B
listen (CLAUDE.md §6.3) and true-peak safety measurement are different concerns.
Matching `processed` up or down to `original`'s LUFS before measuring peak would
report a peak value the exported file never actually has. `peak_delta_db_unmatched`
is computed on the raw pre-match pair and named explicitly so no downstream
report mistakes it for a level-matched quantity.

The mastering-engineer's Gate 1 review confirmed this is the correct call and
consistent with, not in tension with, CLAUDE.md §6.3 (which mandates matching
for comparative *listening* judgment, not for a safety measurement) — see
gate1-review.md Finding 3.

**v1.2 note (DEF-2501 cross-reference):** §3.1's mechanical `export_allowed`
gate uses `final_peak` as computed directly by `_apply_final_safety()` inside
`orchestration.py`, not `peak_delta_db_unmatched` from this module — the two
are different quantities (an absolute safety ceiling check vs. a reported
before/after delta) and must not be confused or merged.

---

## 8. real_world_validation.py Changes (AC7, AC8, AC9)

`build_validation_report()`'s signature gains a required review source — there is
no default that produces a trusted report without it:

```python
def build_validation_report(
    paths: Sequence[str] | None = None,
    synthetic_case: np.ndarray | None = None,
    human_reviews: Optional[Dict[str, HumanReviewRecord]] = None,   # keyed by resolved path
    interactive_review: bool = False,   # if True, missing entries fall through to capture_human_review()'s CLI prompt
) -> dict[str, Any]:
```

Sequence per file, inside the existing `for path in source_paths:` loop:

1. `verify_stem_separation_environment()` is called **once**, before the loop
   (not per file) — its result gates `stem_first_verified` for the whole report
   (§5.3), since it verifies the environment, not a specific file.
2. For each file: resolve `human_reviews.get(str(resolved))`; if absent and
   `interactive_review` is True, call `capture_human_review(resolved,
   interactive=True)`; if absent and `interactive_review` is False, raise
   `HumanReviewRequiredError` naming the file — this is the "no default bypass"
   requirement (AC9). The prior behavior of silently producing a report with
   `human_decision=None` is removed.
3. `pipeline.run(audio, sample_rate, stems=None, use_stems=True,
   allow_stereo_fallback=True, human_review=review_record_as_dict)` — same call
   shape as today, with the resolved human review now actually passed through
   (previously `build_validation_report()` never passed `human_review` to
   `pipeline.run()` at all).
4. The auto-generated `summary`/`auditable_summary` strings
   (`_summarise_decision()`, the `tuning_decisions` reason strings built from the
   decision label) are replaced with report text built from
   `result["quality_report"]["before_after"]` (the grounded metrics) and the
   actual `human_note` — not from a decision-keyed template string.

`ACCEPTED_PARAMETERS` gains one entry: `"stem_first_verified": <bool from the
environment check>` so the accepted-parameters block itself records whether this
run's product-direction claim is backed by a real stem-separation confirmation.

---

## 9. OQ7 resolution — re-running STORY-017 is not this story's implementation work

This architecture defines the interface `build_validation_report()` must expose
(§8) and the modules it depends on (§4–§6), so a subsequent STORY-017 re-run can
use them. Actually invoking `build_validation_report()` against
`DEFAULT_VALIDATION_SET` with a genuine person listening to real output — the
thing that produces the actual trusted validation result — is an operational
step that happens after implementation, not a thing an automated test can
perform on this story's behalf. python-developer implements the code path and
the test-case-writer/QA verify it fails loudly without a real review and behaves
deterministically with one; the human-listening re-run itself is out of scope
for STORY-025's own acceptance, consistent with the Contract's "Consumed by:
STORY-017 real-world validation re-run" phrasing.

---

## 10. Flagged for mastering-engineer (Gate 1)

> **Disposition recorded 2026-08-17 — see §12 (v1.1) for the explicit resolution
> of every item below, per gate1-review.md and this repo's Architect follow-up
> rule.** Items 1, 2, and 4 below have action items applied (§7.1/§7.3, §5.2);
> items 3 and 5 are confirmed accepted as-is.

1. **`artifact_density_regression = 0.05` is PROVISIONAL** (§7.1). No existing
   project data derives a defensible before/after artifact-density delta
   threshold. This needs validation against real reference-track before/after
   measurements (or explicit rejection in favour of a different mechanism, e.g.
   reporting the raw delta without a flag threshold at all) before Gate 2.
2. **`spectral_shift_flag_db = 2.0` is PROVISIONAL** (§7.1) — same caveat: this
   flags "worth a human's attention," not a fitness judgment, but the magnitude
   itself is not derived from data.
3. **§7.4 — whether `_stereo_width`/`_true_peak` should remain supplementary-only**
   (an assumption made here, not a requirements-level decision) needs explicit
   confirmation; if the mastering engineer believes width or peak swings should
   also raise a flag, that logic needs to be added before Gate 2, not
   retrofitted post-implementation.
4. **§5.2 — `clip_seconds = 8.0` for the environment smoke test** is a judgment
   call about what constitutes a meaningful (not just fast) confidence check on
   real Demucs inference, not a derived constant.
5. **Decision-authority shift (§1, §7.3)**: this architecture removes all
   automated pass/reject/refine authority from metrics and makes every trusted
   verdict human-authored, with metrics reduced to evidence/flags. This is a
   significant behavior change from STORY-015's original design intent (an
   automated "musical" verdict) and should be explicitly confirmed as the
   correct reading of requirements.md's "Rejected as out of scope" section
   before implementation proceeds.

**v1.2 addition** — the new `reconstruction_error_ratio <= 0.5` bound (§5.2.1)
is flagged for the mastering-engineer in the same spirit as items 1/2 above:
a reasoned, generous PROVISIONAL smoke-test margin, not a corpus-derived
constant. It gates a loud, inspectable smoke-test failure, not a silent
verdict, so it is not treated as a Gate 2 blocker, but should be validated
against a small set of confirmed-healthy real inference runs before being
considered fully calibrated.

---

## 11. Assumptions pending BA confirmation

- **LUFS-matching direction** (§4.1): gain is applied to `processed` to match
  `original`'s LUFS, not the reverse. Requirements.md does not state which side
  moves; this is the only direction consistent with "does the master itself
  sound better, independent of a level difference," but it is an assumption.
- **`pending_human_review` as a fourth decision value** (§7.3): requirements.md's
  Input/output assumptions section says the `QualityReviewResult` dataclass
  *shape* is retained, but does not explicitly authorise a fourth string value
  in the `decision` field beyond pass/reject/refine. This architecture reads
  that as compatible with "shape retained" (no field added or removed) and
  necessary to satisfy AC9 without a hard exception on every call to
  `evaluate_quality_review` from a test context.

---

## 12. Revision history

- 2026-08-17 (v1.0): Initial architecture for STORY-025, resolving requirements.md
  OQ1–OQ7. Introduces `grounded_quality_review.py`, `lufs_matching.py`,
  `environment_check.py`, `human_review_capture.py`, `review_config.py`. Two
  provisional thresholds and one design judgment call flagged for
  mastering-engineer Gate 1 (§10).
- 2026-08-17 (v1.1): Gate 1 review disposition (gate1-review.md, verdict PASS
  WITH NOTES, no blockers). Per the repo's Architect follow-up rule, all five
  findings are dispositioned explicitly, not left as "no blockers":

  1. **`artifact_density_regression = 0.05` (PROVISIONAL)** — action item
     applied. §7.1 now cross-references, and §7.3 now specifies exactly, a
     mandatory flag-audit-line format that surfaces the raw
     `artifact_density_delta` value and an explicit "PROVISIONAL, not
     calibrated against reference data" label whenever the flag fires, in
     both the human-reviewed and `pending_human_review` paths. The
     reviewer's rationale for accepting the constant itself as a
     placeholder — it only gates a flag surfaced to a human, never an
     automated pass/reject/refine decision — is adopted as-is; calibration
     against real reference-track before/after measurements remains a
     pre-Gate-2 recommendation, not a blocker.
  2. **`spectral_shift_flag_db = 2.0` (PROVISIONAL)** — same action item and
     disposition as (1): §7.3's flag-audit-line spec now requires the raw
     `spectral_rms_shift_db` value plus the PROVISIONAL label whenever
     `spectral_shift_significant` fires.
  3. **`_stereo_width`/`_true_peak` supplementary-only (§7.4), no flag/decision**
     — accepted as-is, no change. The mastering-engineer confirmed this is
     correct: neither measurement is among the story's four named problems,
     and adding new flag thresholds around them would itself be the kind of
     un-derived-constant risk this project works to avoid. §7.4/§7.5 updated
     with a one-line pointer to this confirmation.
  4. **Fixed smoke-test clip offset (§5.2)** — action item applied. The
     8-second Demucs environment-check clip is now read starting at a fixed
     `clip_offset_seconds = 30.0` into `Sunday Club.wav`, instead of literal
     file start, so a possible intro fade-in/silence at `t=0` cannot produce
     a false `EnvironmentVerificationError` on a healthy environment. Clip
     *duration* (8 s) is unchanged — the reviewer separately confirmed 8 s is
     adequate for the check's actual job (confirming real inference runs at
     all, not judging separation quality).
  5. **Decision authority moved entirely to a human reviewer (§1, §7.3)** —
     accepted as-is, no change. The mastering-engineer confirmed this is the
     musically correct posture and a clear improvement over STORY-015's
     automated-verdict design. This should not be revisited toward automated
     scoring in a later story without an explicit architectural decision to
     do so.

  **Downstream impact for python-developer**: `verify_stem_separation_environment()`
  (§5.2) gains a `clip_offset_seconds` parameter (default `30.0`) and must
  validate the fixture is long enough for `clip_offset_seconds + clip_seconds`
  rather than silently truncating. `evaluate_quality_review`'s audit-line
  construction (§7.3) is now specified as exact required content (raw value +
  provisional label per flag), not general prose — implement it as specified,
  not paraphrased. No other implementation-facing interface in this
  architecture changed as a result of Gate 1.

- 2026-08-17 (v1.2): Disposition of two QA-raised, Architectural-severity
  post-implementation defects (defects.md DEF-2501, DEF-2503). Both
  dispositions are recorded here in full; defects.md is updated to point to
  this version rather than restating the reasoning.

  1. **DEF-2501 — `orchestration.py`'s internal `export_allowed` gate.**
     Disposition: **yes, the call site is switched to
     `grounded_quality_review.evaluate_quality_review(original, final_mix,
     sr=sample_rate, human_review=human_review)`** as v1.0/v1.1 already
     specified — but `export_allowed` itself is redefined (new §3.1) as a
     **strictly mechanical export-safety gate** (finite samples + true-peak
     ceiling), decoupled from the musical `review.decision`, because the
     grounded module's decision is `"pending_human_review"` on every
     automated run with no inline human review, and `orchestration.run()` has
     no mechanism to obtain one. When a real human review *is* supplied
     inline, it still gates export_allowed (mechanical safety AND human
     "pass"). The pre-existing `np.allclose` unchanged-signal short-circuit
     is retained for `export_allowed` purposes but must **no longer overwrite
     `review.decision`** to a fabricated `"pass"`, since that would
     reintroduce automated verdict authority this story removes. See §3.1 for
     the full reasoning and the exact revised logic. `result["quality_report"]`
     continues to carry the ungated grounded verdict/evidence unchanged, and a
     new `result["quality_verdict_pending"]` boolean is added so callers can
     tell "exported, verdict still pending" apart from "exported, human
     approved."
  2. **DEF-2503 — Demucs environment smoke test fails on real fixture.**
     Disposition: **replace the "all six stems non-degenerate" requirement
     with two combined checks** (new §5.2.1): (a) a sum-of-stems
     reconstruction-error check (`reconstruction_error_ratio <= 0.5`,
     PROVISIONAL, flagged for mastering-engineer per §10) that proves real,
     coherent model execution regardless of any individual stem's content,
     and (b) a noise-floor check restricted to the near-universal stem subset
     `{drums, bass, vocals}` rather than all six — `other`/`piano`/`guitar`
     remain checked for finiteness only, since their silence in any given
     window is ordinary musical sparsity, not model failure. This is grounded
     in the actual failure evidence from TC-2527 (5 of 6 stems cleared the
     floor; only the legitimately-sparse `other` stem did not) and avoids the
     rejected alternatives: lowering the floor (moves the false-negative risk
     rather than resolving it) and picking a different fixture/offset (does
     not generalize — any real mixed track can have a sparse `other`/`piano`/
     `guitar` window). `EnvironmentCheckResult` gains
     `reconstruction_error_ratio`, `verified_nonsilent_stems`, and
     `noise_floor_checked_stems` fields for audit visibility.

  **Downstream impact for python-developer**: `orchestration.py`'s
  `export_allowed`/`export_reason`/`np.allclose` logic must be rewritten per
  §3.1, not just the import/call-site line. `environment_check.py`'s
  `EnvironmentCheckResult` and `verify_stem_separation_environment()` gain the
  new fields/checks in §5.2/§5.2.1; the per-stem noise-floor loop must be
  restricted to the near-universal subset and the sum-reconstruction check
  added. Existing unit tests referencing the old six-stems-always-checked
  behavior (if any, outside TC-2527) will need updating to match §5.2.1.
