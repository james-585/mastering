# STORY-015 — Test Cases

## TC-0151 — Good master passes final review
- Input: a mix with clearer transient definition, stable depth, controlled width, and lower fatigue than the original.
- Expected: final review result is `pass`.
- Evidence: before/after quality deltas show clearer output without a corresponding dullness, fatigue, or artificial-width risk signature.

## TC-0152 — Dull or over-processed master is rejected
- Input: a mix that has lost energy, lost depth, and feels lower in musical intent after processing.
- Expected: final review result is `reject`.
- Evidence: the review flags `dullness` or `over_processing` with an auditable reason for the fail state.

## TC-0153 — Fatigued or artificial master is flagged
- Input: a mix that becomes brighter, wider, and harsher than the original without a real musical gain.
- Expected: final review result is `reject` or `refine`.
- Evidence: the report calls out `fatigue` or `artificial_width` and does not allow a good-metrics-only pass.

## TC-0154 — Clean mix remains stable
- Input: a mix that is already balanced and naturally cohesive.
- Expected: final review result is `pass` with a stable/no-change summary.
- Evidence: the review does not invent risk on a healthy master and remains auditable as a no-op approval.

## TC-0155 — Before/after metrics and human-review signals agree
- Input: a sonic change that is both measured and personally reviewable.
- Expected: human review can reinforce the decision and the final result remains consistent with the recorded audit notes.
- Evidence: the final report includes recorded human approval or rejection with the decision logic and metric deltas aligned.

## TC-0156 — Audit trail exists for the final decision
- Input: any reviewed final master.
- Expected: the report includes the reason for pass / reject / refine and the auditable signal list.
- Evidence: each decision is traceable to the before/after evidence and not hidden behind a single metric summary.
