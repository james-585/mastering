# STORY-025 Defects

## DEF-2501 — `orchestration.py` still gates `export_allowed` on the old STORY-015 proxy-metric review, not the new grounded module

**Status**: Closed
**Severity**: Architectural
**Raised by**: qa-automation-engineer (implementation review, cross-referencing architecture.md §2/§3)
**Date**: 2026-08-17
**Linked test case**: N/A (structural code-review finding, not a single TC — affects the AC5–AC9 chain as consumed by `orchestration.py`)

**Description**: `stories/STORY-016/implementation/orchestration.py` line 22 imports
`from final_quality_review import evaluate_quality_review` (STORY-015's proxy-metric
module — `clarity_delta`, `_spectral_tilt`) and calls it at line 108:
`review = evaluate_quality_review(original, final_mix, human_review=human_review)`.
This is the exact call site architecture.md §2's "Existing files changed" table and §3
("Pipeline Integration Point") specify must be updated: *"`MasteringOrchestrator.run()`'s
call... is changed to import from `grounded_quality_review` and pass `sample_rate`:
`evaluate_quality_review(original, final_mix, sr=sample_rate, human_review=human_review)`."*
This change was not made.

Meanwhile, `stories/STORY-017/implementation/real_world_validation.py` (updated for this
story) *does* import and call the new `grounded_quality_review.evaluate_quality_review`
(with `sr`) — but only *after* `pipeline.run()` returns, purely to build the report's
`decision`/`before_after`/`audit` fields. `pipeline.run()`'s own return value
(`result["export_allowed"]`, `result["export_reason"]`) is computed entirely from the old
proxy-metric review inside `orchestration.py`, including its odd `np.allclose`
auto-pass-on-unchanged-signal branch and its own separate (older, STORY-015-vintage)
`human_review` override logic (lines ~116–122) — none of which is touched by this story.

**Impact**: Two structurally different quality-review implementations are active on two
different code paths for the same pipeline run: `orchestration.py`'s internal
`export_allowed` gate is still driven by `clarity_delta`/`_spectral_tilt` proxies and never
sees the seven-band/DR/artifact-density/LUFS-matched evidence this story introduces, while
`real_world_validation.py`'s reported `decision` is driven by the new grounded module and a
real human review. Any caller of `MasteringOrchestrator.run()` directly (not through
`build_validation_report()`) — which per architecture.md §3 is `run()`'s only call site for
`quality_review` — still gets an export decision based on the metrics this story's
Story.md/requirements.md explicitly identify as invalid (a loudness proxy mislabeled as
clarity, a 2-bin FFT ratio mislabeled as spectral tilt). The release gate's actual
export-approval boolean (`export_allowed`) is not grounded by this story at all; only the
separately-computed report text is.

**Triage: Code-level.** This is not an open design question for the architect to resolve —
architecture.md v1.1 (Gate 1 passed) already specifies, unambiguously and in two places
(§2's file-change table, §3's integration-point description), exactly what the
`orchestration.py` call site change must be (`sr=sample_rate` keyword, import from
`grounded_quality_review`). The implementation simply did not make this already-decided
change. Per this story's own §2, no other orchestration change was required — this is a
one-call-site fix, not a redesign. Assigning to a future python-developer pass to implement
per the architecture as already written. (If, on inspection, the python-developer or
architect judges that `orchestration.py`'s bespoke `np.allclose`/human-review-override logic
built around the old review object shape also needs to change to work with
`QualityReviewResult`'s `pending_human_review` decision value, that follow-on question would
be an architectural one — but the base fact that the call site was never switched is a plain
implementation gap against an already-resolved architecture decision.)

**Architectural disposition recorded (2026-08-17, software-architect):** see
architecture.md §3.1 and §12 v1.2 entry. `export_allowed` is redefined as a
strictly mechanical export-safety gate (finite samples + true-peak ceiling),
decoupled from `review.decision` — the call site does switch to
`grounded_quality_review.evaluate_quality_review(..., sr=sample_rate, ...)` as
originally specified, but export_allowed's boolean no longer equals
`review.decision == "pass"`. Status remains Open — this is an architectural
resolution, not a code fix; python-developer must implement §3.1's exact
logic. QA closes once implemented and retested.

**Fix notes** (python-developer, 2026-08-17): Method change, not a parameter
tweak. `orchestration.py` now imports `evaluate_quality_review` from
`grounded_quality_review` (STORY-025 added to `_FOR_IMPORT`) and calls it as
`evaluate_quality_review(original, final_mix, sr=sample_rate, human_review=human_review)`.
`export_allowed` is redefined exactly per §3.1: `mechanically_safe = np.isfinite(final_mix).all() and final_peak <= 1.0`;
when a real human verdict is present (`human_review is not None` and
`review.decision in {pass, reject, refine}`), `export_allowed = mechanically_safe and review.decision == "pass"`;
otherwise (`pending_human_review`) `export_allowed = mechanically_safe` only.
The old bespoke human-review-decision-parsing block (lines ~116-123) that
duplicated this logic against the raw `human_review` dict was removed, since
`review.decision` already reflects it. The `np.allclose` unchanged-signal
short-circuit no longer overwrites `review.decision`, `review.flags`, or
`review.summary` — it only adds an audit note; the real decision from
`evaluate_quality_review` (ordinarily `pending_human_review`) is preserved.
`export_reason` now distinguishes the mechanical-safety failure text from the
human reject/refine text and from the new `pending_human_review` case.
Added `result["quality_verdict_pending"] = review.decision == "pending_human_review"`.
Verified via `stories/STORY-025/automation` (46 passed) and STORY-017's
regression suite (2 passed), which exercise `orchestration.py` through
`pipeline.run()`.

**QA retest (2026-08-17, qa-automation-engineer):** Independently re-ran fast
STORY-025 suite (45 passed, 1 deselected slow) and read `orchestration.py`
directly rather than trusting the fix note. Confirmed line-by-line against
architecture.md §3.1: the call site imports and calls
`grounded_quality_review.evaluate_quality_review(original, final_mix,
sr=sample_rate, human_review=human_review)`; the `np.allclose` unchanged-signal
branch only appends an audit note and no longer overwrites `review.decision`;
`mechanically_safe = np.isfinite(final_mix).all() and final_peak <= 1.0`;
`export_allowed = mechanically_safe and review.decision == "pass"` only when a
real human verdict is present, else `export_allowed = mechanically_safe`;
`quality_verdict_pending` and the four-way `export_reason` text are both
present and correctly ordered. Matches §3.1 exactly. **Closing.**

---

## DEF-2502 — `artifact_density_regression` flag misses its own documented exact boundary due to float64 subtraction (TC-2506)

**Status**: Closed
**Severity**: Code-level
**Raised by**: qa-automation-engineer
**Date**: 2026-08-17
**Linked test case**: TC-2506 (test-cases.md F-2505 `art_flag_boundary = (0.10, 0.150)`, expected `artifact_density_delta == 0.050` and flag present)

**Description**: `compute_grounded_metrics()`'s flag condition is
`artifact_density_delta >= config.artifact_density_regression` (grounded_quality_review.py).
test-cases.md's own boundary fixture F-2505 sets
`art_flag_boundary = (original=0.10, processed=0.150)` and asserts the flag **is** present
(`0.050 >= 0.05` true "by construction"). In IEEE-754 float64, `0.150 - 0.10 ==
0.049999999999999996`, which is measurably *less than* `0.05` — the flag condition evaluates
False and `"artifact_density_regression"` is absent from `metrics.flags`, contradicting the
test case's expected result.

**Measured vs expected**: `metrics.artifact_density_delta == 0.049999999999999996` (measured);
test-cases.md's expected value is `0.050` exactly with the flag present. Automated test
`test_tc2506_artifact_density_boundary[artifact_pair1-True]` fails on this input.

**Impact**: Any before/after artifact-density pair whose *true* delta is exactly at the
0.05 threshold — a realistic occurrence, since `overall_artifact_density_score` values are
themselves floats derived from real measurements — has a roughly 50/50 chance of silently
missing the flag purely from float representation, not from the underlying audio evidence.
This is exactly the class of "reporting a fixed property as varying" / silent-precision-loss
risk this repo's instructions call out.

**Triage: Code-level.** The fix is a comparison-robustness fix (e.g. round both sides to a
fixed number of decimals before comparing, or compare with a small explicit epsilon), not a
change to the `0.05` threshold value itself — the PROVISIONAL threshold magnitude is
unaffected. The same float-precision risk likely also applies to the `dr_regression_db` and
`spectral_shift_flag_db` boundary comparisons (`<=`/`>=` with no epsilon); python-developer
should apply the same treatment to all three flag comparisons in `compute_grounded_metrics()`
rather than patching only the artifact-density case.

**Fix notes** (python-developer, 2026-08-17): Parameter/comparison-robustness
fix, not a threshold-value change — none of `dr_regression_db`,
`artifact_density_regression`, or `spectral_shift_flag_db`'s magnitudes were
altered. Added a module-level `_FLAG_EPSILON = 1e-9` in
`grounded_quality_review.py` and rewrote all three flag conditions in
`compute_grounded_metrics()` to compare with that tolerance
(e.g. `artifact_density_delta >= config.artifact_density_regression - _FLAG_EPSILON`)
instead of a bare `>=`/`<=` on the raw float64 delta. TC-2506's boundary
fixture (`art_flag_boundary = (0.10, 0.150)`) now flags correctly. Verified
with the full `stories/STORY-025/automation` suite (46 passed, was 44 passed/2 failed).

**QA retest (2026-08-17, qa-automation-engineer):** Re-ran the fast STORY-025
suite independently (45 passed, 1 deselected slow) — `test_tc2506_artifact_density_boundary`
is in this set and passes. Read `grounded_quality_review.py` directly:
`_FLAG_EPSILON = 1e-9` is applied to all three flag comparisons
(`dr_regression_db`, `artifact_density_regression`, `spectral_shift_flag_db`),
not just the one reported in the defect — matches the fix note's claim and the
defect's own recommendation to treat all three uniformly. Threshold magnitudes
unchanged (comparison-robustness fix, not a parameter retune). **Closing.**

---

## DEF-2503 — Real Demucs environment smoke test fails on real fixture: per-stem noise-floor check is too strict for a real 8 s music window (TC-2527)

**Status**: Closed
**Severity**: Architectural
**Raised by**: qa-automation-engineer
**Date**: 2026-08-17
**Linked test case**: TC-2527 (real, non-mocked integration test, `@pytest.mark.slow`)

**Description**: Running `verify_stem_separation_environment()` with all defaults against
the real `Reference Tracks/Sunday Club.wav` fixture (real Demucs 4.1.0 / torch 2.13.0+cpu,
`htdemucs_6s`, 8 s clip at the fixed 30 s offset per Gate 1 Finding 4) raises
`EnvironmentVerificationError`:

```
Stem 'other' RMS (3.623e-05) is at or below the noise floor (1.000e-03, from
MasteringConfig.silence_gate_threshold_db); the model may be silently returning a
degenerate (near-zero) stem.
```

Real inference genuinely ran (confirmed via captured Hugging Face Hub download log lines —
no import/dependency failure), and 5 of 6 stems presumably cleared the floor; the `other`
stem's RMS in this specific 8-second window is below the noise-floor threshold the check
requires **every** stem to clear.

**Is this plausible, or an implementation bug?** This is physically plausible, not
implausible: `htdemucs_6s` separates into `drums, bass, other, vocals, piano, guitar`, and it
is entirely ordinary for a real mixed track to have no meaningful "other"/"piano"/"guitar"
content in any given 8-second window (e.g. a passage that is just drums/bass/vocals). A
near-silent "other" stem here is consistent with the actual music, not evidence the model
silently returned zeros for every stem. The check as specified (architecture.md §5.2:
"assert every returned stem is finite... and non-degenerate... so a model that silently
returns zeros does not pass") does not distinguish "the model is broken" from "this
particular stem legitimately has nothing in it this window" — it requires all 6 stems to
individually clear a noise floor, which is a stronger claim than "real separation occurred."

**Impact**: As currently specified and implemented, the mandatory AC7 environment-verification
step **cannot pass** against its own designated real fixture at its own fixed, architecturally
-mandated offset/duration (30 s / 8 s on `Sunday Club.wav`) — the exact scenario Gate 1
Finding 4 was written to make reliable. This defeats AC7's purpose: `build_validation_report()`
would report `stem_first_verified: False` on a healthy, correctly-functioning environment,
mislabeling every file in the run as `"stem_first_path_unverified"` even though stem
separation is demonstrably working.

**Triage: Architectural.** This is not a simple parameter retune (e.g. lowering the noise
floor would just move the false-negative risk to a genuinely quieter stem, and does not
address the structural claim mismatch). The design question — should the check require *all
six* stems non-degenerate, or only a subset (e.g. drums/bass/vocals, which are near-universal
in mixed music), or use a different verification signal entirely (e.g. sum-of-stems
reconstructs the input to within tolerance, proving the model ran and produced coherent
output, without asserting every individual stem is audible) — is a design decision for the
architect/mastering-engineer, consistent with how Gate 1 Finding 4 (a related false-negative
concern) was resolved architecturally rather than left to python-developer's discretion. An
alternative fixture/offset that is confirmed (by ear or by measurement) to contain audible
content in all six `htdemucs_6s` categories simultaneously would also resolve this, but
choosing or deriving that fixture window is itself an architectural/mastering-engineer
judgment call (per this repo's "derive every constant, never assert one inline" convention),
not something QA or python-developer should pick unilaterally.

**Architectural disposition recorded (2026-08-17, software-architect):** see
architecture.md §5.2.1 and §12 v1.2 entry. The "all six stems non-degenerate"
requirement is replaced with (a) a sum-of-stems reconstruction-error check
(`reconstruction_error_ratio <= 0.5`, PROVISIONAL) and (b) a noise-floor check
restricted to the near-universal stem subset `{drums, bass, vocals}` only.
Status remains Open — python-developer must implement §5.2.1's exact checks
against the real fixture; QA closes once implemented and TC-2527 passes.

**Fix notes** (python-developer, 2026-08-17): Method change, not a parameter
tweak. `environment_check.py`'s per-stem loop no longer requires all six
stems to individually clear the noise floor. Implemented both §5.2.1 checks:
(a) sum-of-stems reconstruction check — `reconstruction_error_ratio` computed
as residual RMS / input RMS, must be `<= _RECONSTRUCTION_ERROR_RATIO_MAX (0.5)`;
(b) noise-floor check restricted to `_NEAR_UNIVERSAL_STEMS[model_name]`
(a `model_name -> near_universal_stems` mapping, `{"htdemucs_6s": ["drums", "bass", "vocals"]}`,
not hardcoded inline per-call). All stems are still checked for finiteness.
Added the three new `EnvironmentCheckResult` fields
(`reconstruction_error_ratio`, `verified_nonsilent_stems`,
`noise_floor_checked_stems`) populated from the real check results. Updated
`test_tc2523_clip_read_starting_at_offset_not_file_start`'s mock (it returned
four identical copies of the clip rather than a partition summing back to it,
which now legitimately fails the new reconstruction check for a reason
unrelated to what that test covers) to split the clip evenly across stems.
Verified against the real `Reference Tracks/Sunday Club.wav` fixture: TC-2527
now passes (real htdemucs_6s inference, ~10s including model load).

**QA retest (2026-08-17, qa-automation-engineer):** Ran TC-2527 directly with
`pytest -m slow -k tc2527` against the real `Sunday Club.wav` fixture (not
skipped) — 1 passed in 10.23s, consistent with real htdemucs_6s inference
(not a mock). Read `environment_check.py` directly: `_RECONSTRUCTION_ERROR_RATIO_MAX
= 0.5` gates a real `reconstruction_error_ratio` computed from summed stems vs.
the input clip; `_NEAR_UNIVERSAL_STEMS["htdemucs_6s"] = ["drums", "bass",
"vocals"]` is a lookup table (not hardcoded per-call) and only this subset is
required to clear the noise floor; `other`/`piano`/`guitar` are checked for
finiteness only. Matches §5.2.1 exactly, both checks present and combined
correctly. **Closing.**

---

## DEF-2504 — STORY-017's pre-existing regression tests broken by this story's mandatory `human_reviews` contract change

**Status**: Closed
**Severity**: Code-level
**Raised by**: qa-automation-engineer
**Date**: 2026-08-17
**Linked test case**: N/A (pre-existing STORY-017 regression suite, not a STORY-025 test case — discovered while confirming STORY-025's `build_validation_report()` changes did not silently break other consumers)

**Description**: `stories/STORY-017/implementation/tests/test_story017_real_world_validation.py`
(both `test_story017_real_world_validation_report_is_auditable` and
`test_story017_validation_rejects_weak_but_safe_outcomes`) call
`build_validation_report(paths)` / `build_validation_report([], synthetic_case=flat)` with no
`human_reviews` argument and `interactive_review` defaulting to `False`. This is exactly the
"no default bypass" case this story's AC9 requires (architecture.md §8 step 2), and it now
correctly raises `HumanReviewRequiredError` — but neither test was updated to supply a
`human_reviews` dict, so both now fail with an uncaught exception instead of exercising their
original intent.

**Measured vs expected**: Both tests raise
`human_review_capture.HumanReviewRequiredError: No human review supplied for
'synthetic_validation_case'/'...Sunday Club.wav' and interactive_review is False; ...` instead
of returning a report dict.

**Impact**: STORY-017's own regression suite no longer passes; it does not currently
distinguish "the new mandatory-human-review contract is working as intended" (which is
correct, per AC9) from "the test itself is stale." Left as-is, a real regression in
`build_validation_report()` unrelated to human-review gating could pass unnoticed because
the suite fails at the same early point regardless.

**Triage: Code-level.** This is not an architectural question — architecture.md already
specifies the new required signature and behavior (§8), and DEF-2504 is simply that the
STORY-017 test file was not updated to match it. Fix is to update
`test_story017_real_world_validation.py` to pass a `human_reviews` dict (or monkeypatch
`capture_human_review`) so the tests exercise the report-building logic they were written to
cover, rather than failing at the human-review gate every time.

**Fix notes** (python-developer, 2026-08-17): Test-fixture update, not a
production code change. Both tests in `test_story017_real_world_validation.py`
now build a `human_reviews: Dict[str, HumanReviewRecord]` (keyed by
`str(Path(path))`, matching `_resolve_human_review`'s `str(resolved)` key on
Windows, and by `"synthetic_validation_case"` for the synthetic path) and pass
it to `build_validation_report(...)`, so both tests exercise the report-building
logic instead of failing at the human-review gate. While fixing this, the DEF-2501
fix (routing `pipeline.run()`'s internal quality review through the grounded
module) exposed a second, previously-masked incompatibility: the second test's
literal all-zero "musically weak" fixture always measures non-finite (`-inf`)
BS.1770 LUFS, which `lufs_matching.match_levels()` correctly rejects
(`LevelMatchError`) rather than silently proceeding — true digital silence can
never be evaluated by the grounded module by design. Replaced the literal
`np.zeros(...)` fixture with a quiet, finite-LUFS tone (0.01 amplitude, 1s) that
preserves the test's "weak/reject" intent without relying on true silence.
Both tests now pass (2 passed).

**QA retest (2026-08-17, qa-automation-engineer):** Independently re-ran
`stories/STORY-017/implementation/tests/test_story017_real_world_validation.py`
in full (not through STORY-025's suite) — 2 passed in 270.85s. The long
runtime confirms these are exercising the real pipeline/report-building path,
not short-circuiting at the human-review gate. Also confirms this is a
non-trivial pass: both tests build a real `human_reviews` dict and reach
assertions on the actual report content, not merely "no exception raised."
**Closing.**

---

## DEF-2505 — `HumanReviewRequiredError` messages `!r`-format the file path, doubling backslashes in audit/log text on Windows

**Status**: Closed
**Severity**: Code-level (low severity — cosmetic/audit-readability, not a functional defect)
**Raised by**: qa-automation-engineer
**Date**: 2026-08-17
**Linked test case**: TC-2541 (observed while asserting the error "names the specific path")

**Description**: `real_world_validation.py`'s `_resolve_human_review()` raises
`HumanReviewRequiredError(f"No human review supplied for {review_key!r} and ...")`. Using
`!r` (repr) on a Windows path string doubles every backslash character in the resulting
message text (e.g. `C:\Users\...` becomes the literal characters `C:\\Users\\...` in the
exception's `str()`), rather than reproducing the actual path as written. The path is still
technically identifiable, but does not literally match the input path string, which matters
for this story's stated "auditable" requirement on report/error text.

**Impact**: Low — the file is still identifiable to a human reader, but log/audit text
containing a doubled-backslash path is a minor readability defect and could complicate
automated log-scraping/matching against real file paths.

**Triage: Code-level.** Trivial fix: use the plain path string (or quote it without
`repr()`, e.g. an f-string with explicit quotes) instead of `!r`.

**Fix notes** (python-developer, 2026-08-17): Parameter/formatting fix, not a
method change. The actual `!r`-formatted path is in
`stories/STORY-017/implementation/real_world_validation.py`'s
`_resolve_human_review()` (not `human_review_capture.py` — `human_review_capture.py`'s
`!r` usages are on `decision`/`note` validation-error text, not file paths; the
path-doubling bug described here is specifically the `HumanReviewRequiredError`
raised by `_resolve_human_review()`). Changed
`f"No human review supplied for {review_key!r} and ..."` to
`f"No human review supplied for '{review_key}' and ..."` — an explicit quoted
f-string instead of `repr()`, so Windows paths no longer double their
backslashes in the message. Updated `test_tc2541_no_human_reviews_raises_naming_the_file`
(which had asserted the buggy doubled-backslash text as expected behavior) to
assert the plain path string instead. Verified: full `stories/STORY-025/automation`
suite passes (46 passed).

**QA retest (2026-08-17, qa-automation-engineer):** Read `real_world_validation.py`
directly — `_resolve_human_review()`'s `HumanReviewRequiredError` message now
uses `f"No human review supplied for '{review_key}' and ..."` (explicit quotes,
no `!r`); confirmed no other `!r`-on-a-path usage remains in that function.
`test_tc2541_no_human_reviews_raises_naming_the_file` (in the fast suite, 45
passed) asserts the plain path string. **Closing.**
