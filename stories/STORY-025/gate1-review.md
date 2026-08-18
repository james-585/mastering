# STORY-025 — Mastering-Engineer Gate 1 Review

## Scope reviewed
- `requirements.md`
- `architecture.md`
- `Story.md`
- Repo guardrails: `.claude/docs/CLAUDE.md` §6.3 (loudness A/B caveat), §7 (known-wrong patterns)

## Question at this gate
Will this method produce correct, musically defensible results on real programme material — not just the idealised case — and does the architecture correctly resolve the requirements' open questions without silently reintroducing a known-wrong pattern?

---

## Findings

### Finding 1 — `artifact_density_regression = 0.05` PROVISIONAL constant

- **Severity**: Concern
- **What is proposed**: A hardcoded 0.05 delta on `overall_artifact_density_score` (0.0–1.0 scale) triggers an `"artifact_density_regression"` flag. Labelled PROVISIONAL, explicitly flagged in §10 as undervalidated.
- **Ruling**: Acceptable as a PROVISIONAL placeholder, but only because of how it is consumed. §7's known-wrong pattern is "asserting a baseline constant without derivation" causing *wrong gain/correction logic* — i.e., the danger is a bad constant silently driving an automated decision. Here the constant only appends a string to a `flags: List[str]` that a human reviewer reads alongside the raw numeric delta; it does not gate pass/reject. That materially lowers the blast radius of an un-derived number. This is not the same category of risk as a hardcoded loudness target or band-limit threshold feeding an automated verdict.
- **Action required before Gate 2**: The report presented to the human reviewer must show the raw `artifact_density_delta` value, not just the boolean flag — architecture already stores this in `GroundedMetrics`, confirm it also surfaces in `before_after`/`audit` text so the human isn't reading an unearned "regression" label without the number behind it. Also confirm the audit line states plainly that this threshold is unvalidated (e.g. "flag threshold is provisional, not calibrated against reference data") so a future reader doesn't mistake the flag firing as a calibrated significance test. Calibration against real before/after reference-track measurements should happen before this project treats artifact-density flags as reliable signal for tuning decisions, but it is not a Gate 1 blocker given the human-authority design.

### Finding 2 — `spectral_shift_flag_db = 2.0` PROVISIONAL constant

- **Severity**: Concern
- **What is proposed**: RMS shift across six seven-band deltas ≥ 2.0 dB triggers `"spectral_shift_significant"`.
- **Ruling**: Same disposition as Finding 1, and for the same reason — flag-only, human-consumed, not a pass/fail cutoff. 2.0 dB RMS across bands is not an obviously implausible order of magnitude for "worth a listener's attention" (CLAUDE.md §6's targeting-policy table treats spectral balance as soft-corrected within a reference range, not a hard number), so it isn't a placeholder in the "hardcoded -1.50/-3.00/-4.00" sense the repo has previously banned — those were final targets baked into gain decisions. This is a screening heuristic for a human, not a target.
- **Action required before Gate 2**: Same as Finding 1 — surface the raw `spectral_rms_shift_db` value alongside the flag, and label the constant provisional in the audit trail so it isn't later mistaken for a derived musical threshold.

### Finding 3 — `_stereo_width` / `_true_peak` retained as supplementary-only, not superseded

- **Severity**: Note
- **What is proposed**: Ported verbatim, reported in `before_after`, but feed no flag and no decision (§7.4).
- **Ruling**: Correct. Both are legitimate, already-grounded measurements (unlike `_spectral_tilt`/`clarity_delta`, which this story correctly removes). Width and true peak are not among the story's four named problems, and inventing new flag thresholds around them here would be exactly the kind of un-derived-constant risk this review should be pushing back on elsewhere, not adding. Keeping them as reported evidence without a threshold is the right level of restraint. Confirmed as-is — no change needed.
- One sharpening for the record: §7.5's handling of `peak_delta_db_unmatched` (computed on the raw, not level-matched, pair) is the correct call. True-peak safety is a property of the actual exported file at its real output level; level-matching it for an A/B would misreport what the export will actually do on playback. This is consistent with — not in tension with — CLAUDE.md §6.3, which mandates matching for *comparative listening judgment*, not for a safety measurement.

### Finding 4 — `clip_seconds = 8.0` smoke-test length: fit for its stated purpose, but the fixed-offset slice risks a false failure

- **Severity**: Concern
- **What is proposed**: Read the first 8 seconds of `Sunday Club.wav`, run real `htdemucs_6s`, assert all stems finite and above a noise floor.
- **Ruling on length**: 8 seconds is long enough for the check's actual job. The failure modes this check exists to catch — missing/incompatible torch or demucs, a broken model load, a silently-zero-output stem — all manifest on inference of any non-trivial clip length; they do not require a longer excerpt to surface. This is a "does the environment work at all" check, not a separation-quality check, and the repo's own ~123s full-track data point is there to establish base plausibility, not something this smoke test needs to reproduce at scale. 8s is proportionate and not wastefully slow.
- **The real risk is not duration, it's offset**: the design takes "the first `clip_seconds`" of the fixture unconditionally. If `Sunday Club.wav` opens with an intro fade-in, silence, or a sparse/ambient passage (common in electronic music), a stem's RMS could legitimately sit near the noise floor for reasons that have nothing to do with the model being broken — producing a false `EnvironmentVerificationError` on a healthy environment, or worse, requiring the noise-floor threshold to be loosened until it stops being a meaningful check at all.
- **Action required before Gate 2**: Either (a) confirm — by ear or by a quick level check — that the first 8 seconds of the actual `Sunday Club.wav` fixture are not silence/fade-in, or (b) take the clip from a fixed offset into the track (e.g. seconds 30–38) rather than the literal file start, so the smoke test isn't coupled to whatever happens to be at time zero of one specific reference file. This is a one-line implementation change, not an architecture rewrite, but it should be specified now rather than discovered as a flaky test later.

### Finding 5 — Decision authority moving entirely to the human reviewer

- **Severity**: Note — confirmed as the musically correct posture
- **What is proposed**: Grounded metrics never produce an automated `pass`/`reject`/`refine`; a run without a human review yields `pending_human_review`, which cannot be mistaken for a trusted verdict.
- **Ruling**: This is the correct direction, and a clear improvement over STORY-015. STORY-015's failure was not merely that its metrics were crude proxies — it was that crude proxies were allowed to stand in for a musical judgment at all. CLAUDE.md is explicit that "a technically compliant but musically flat output is not a success" and that metrics are "necessary, but not sufficient." An if/elif chain over spectral/DR/artifact deltas, however well-calibrated, still cannot judge fatigue, believability of depth, or whether a correction sounds natural versus mechanical — the things this project actually cares about. Removing automated verdict authority and making every trusted decision human-authored is the only architecture consistent with that standing decision. The `pending_human_review` sentinel value doing real work (distinct from all three legitimate verdicts, not defaultable, not silently swallowed by a caller) is the correct mechanism for preventing regression back to an unreviewed pass.
- No action required. This should not be revisited or "simplified" back toward automated scoring in a later story without an explicit architectural decision to do so.

---

## Other observations (not separately dispositioned, no action needed)

- `dr_regression_db = 3.0` reuses STORY-006's already-derived `dr_max_reduction_db` rather than inventing a new constant — correct application of "derive every constant" (it is literally derived, by reuse, not asserted).
- LUFS-matching direction (gain applied to `processed` to match `original`) is a reasonable reading of CLAUDE.md §6.3 for this specific comparison (judging whether the master itself sounds better, not whether it's louder), and requirements.md correctly leaves this as an assumption for BA confirmation rather than the architect asserting it silently.
- `lufs_match_tolerance_lu = 0.5` is derived from the BS.1770 gating-edge-case reasoning in §4.2, not asserted as a round number — this is the right standard to hold every other constant to.

---

## Architect follow-up (per repo rule)

Per the repo's Architect follow-up rule, every finding above needs an explicit disposition recorded in `architecture.md`'s revision history before implementation proceeds — "no blockers" is not sufficient on its own. Findings 1, 2, and 4 are Concerns requiring an action item (surface raw deltas + provisional labelling in audit text; fix the fixture-offset risk in the environment check). Findings 3 and 5 are Notes requiring only an explicit "accepted as-is, no change" record.

---

## Gate status

**No Blockers.** All five items the architect flagged for judgment are resolved:

1. Both PROVISIONAL constants (`artifact_density_regression`, `spectral_shift_flag_db`) are acceptable to carry forward as labelled placeholders, because they gate a flag surfaced to a human, not an automated verdict — provided the raw values are surfaced alongside the flag and the provisional status is stated in the audit trail (action item, not a blocker).
2. `_stereo_width`/`_true_peak` should remain supplementary-only, exactly as designed — confirmed.
3. The 8-second smoke-test clip length is adequate for its stated purpose; the actionable risk is the fixed start-of-file offset, not the duration (action item, not a blocker).
4. Moving decision authority entirely to the human reviewer is the musically correct posture for this project and a clear improvement over STORY-015's automated-verdict design — confirmed, no change.

**PASS WITH NOTES.** Implementation may proceed once the architect records an explicit disposition for each finding above in `architecture.md`'s revision history (per the repo's Architect follow-up rule), and the two action items (Findings 1/2's audit-surfacing requirement, Finding 4's fixture-offset fix) are captured in architecture.md so python-developer implements them rather than discovering them at QA.

## Revision history
- 2026-08-17: Initial Gate 1 review for STORY-025.
