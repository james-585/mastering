# STORY-009 — Mastering-Engineer Review Brief: Stationary Whistle Parameters and Outcome

## Scope
This review is specifically for the `STATIONARY_WHISTLE` repair path used in the Sunday Club pass. The question is not whether the repair stage exists; it is whether the chosen parameters and the resulting intervention are musically and physically valid.

The review should determine:
- whether the current stationary-whistle parameters are appropriate,
- whether the repair method is doing the right kind of corrective action,
- whether the whole-file application is valid,
- and what the correct fix should be before the stage is ever considered for default-on use.

---

## Evidence to review
Use the live Sunday Club output as the basis for this review:
- `Reference Tracks/Sunday Club_mastered.wav`
- `Reference Tracks/Sunday Club_mastered_report.md`
- `Reference Tracks/Sunday Club_mastered_report.json`

The project already records the core concerns in:
- [stories/STORY-009/mastering-review-results.md](./mastering-review-results.md)
- [stories/STORY-009/mastering-review-methods.md](./mastering-review-methods.md)
- [stories/STORY-009/architecture.md](./architecture.md)

---

## What to judge

### 1) Parameter validity
Review the stationary-whistle repair parameters against the actual signal behaviour:
- detector frequency list source: only `ArtifactFlag.details["frequency_hz"]` values from `STATIONARY_WHISTLE` artifacts,
- confidence gate: current threshold basis and whether it is an audio-edit threshold or only a warning threshold,
- prominence gate: whether `prominence_db` is required as a second condition,
- notch width: Q ≈ 120 and nominal ~54 Hz width at 6.4 kHz,
- whole-track application: whether the same notch is being applied across the entire file instead of only the flagged time window,
- crossfade local windowing: whether the repair is a narrow time-local edit or a blanket correction.

### 2) Outcome plausibility
Review the measurable result of the pass:
- true peak sits exactly at the hard ceiling: `-1.00 dBTP`, leaving no margin,
- artifact burden remains high after treatment: `454` flags before and `92` after, dominated by `STATIONARY_WHISTLE`,
- repair actions report large energy changes such as peak/RMS deltas in the range of several dB,
- the file still contains the same whistle profile in substantial density after the intervention.

This is the core question: did the repair remove the stationary whistle without damaging programme content, or did it merely apply destructive broadband attenuation?

### 3) Method quality
The review should specifically assess whether the implementation is using the right method:
- narrow notch at the confirmed whistle frequency,
- only within the flagged time window,
- only for files with a valid detector output,
- with OLA gain preservation corrected,
- and without whole-file notching or aggressive compensation.

---

## Expected decision
The mastering engineer should determine whether the current approach is a valid repair strategy or whether it is a bad method that needs to be replaced.

The likely determination is:
- the current implementation is not a valid final mastering method,
- the repair action should not ship as-is,
- the correct fix is not “tune the parameters harder,” but rather to replace the method with a detector-gated, time-local, OLA-correct repair path.

Specifically, the review should confirm the following as the fix direction:
1. disable the default-on behavior,
2. fix the OLA overlap normalisation bug in the C++ implementation,
3. apply repairs only to confirmed `STATIONARY_WHISTLE` frequencies,
4. apply the repair only within the flagged time window,
5. keep the stage off by default until the method is verified on real programme material,
6. treat empty-frequency no-op cases as a required guardrail, not a tolerated level drift.

---

## Review outcome expected in the defect/decision record
The engineer should conclude one of the following:
- `valid and safe`, with a clear measurement and listening rationale, or
- `wrong method` with a replacement method specified.

For this case, the correct finding is expected to be: `wrong method`.

The reason is straightforward: the current repair is not preserving the programme while removing the whistle; it is reducing wider signal content and leaving the artifact burden largely unchanged. That is a method failure, not a parameter-tuning issue.
