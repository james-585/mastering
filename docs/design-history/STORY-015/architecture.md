# STORY-015 — Architecture: final quality and review loop for stem-based mastering

## Pipeline placement
This is the last stage in the mastering chain and sits after the final loudness and true-peak safety pass, before final export or user approval.

The control flow is:
1. ingest original source
2. stem separation or explicit stereo fallback
3. per-stem analysis and correction
4. transient Restoration / de-haze / stem imaging
5. bus glue and final dynamic balance
6. final loudness, DR, and true-peak validation
7. final quality review gate
8. export only after review decision or human override

## Architectural intent
The final review layer is not a vanity report. It is the product’s decision engine for whether the processed master is actually better in musical terms. It is designed to answer a single product question: “Is this output meaningfully improved in emotional, spatial, and tonal realism, or is it just numerically safe?”

## Core components
### 1. Before / after comparator
- Accepts the original track and the processed track as the minimum input.
- For stem-based workflows, also accepts per-stem data for clarity of interpretation.
- Computes before/after deltas for loudness, true peak, stereo width, spectral balance, transient energy, and human-meaningful quality signals such as clarity, control, fatigue, depth, and realism.
- Produces a normalized delta set that is reviewable and not dependent on the absolute loudness of the source.

### 2. Stem-quality analysis
- Evaluates each stem as a separate source of quality risk or quality gain.
- Flags issue types including dullness, fatigue, harshness, artificial width, lost transient attack, and instability in the stereo image.
- Aggregates the per-stem results into a final score and a per-stem audit note for human review.

### 3. Full-mix quality checks
- Recombines the stem-level observations into a whole-mix quality check.
- Looks for the common failure modes of the project: excessive brightness, over-compression, flattening, fatigue, unstable depth, and unrealistic width.
- Distinguishes real improvement from a “safe but lifeless” result.

### 4. Decision logic
The final layer outputs one of three states:
- Pass: the mix is meaningfully better than the original, with no unresolved major quality risks.
- Reject: the result is degraded, dull, harsh, artificial, or otherwise musically weak despite acceptable metrics.
- Refine: the result is not quite ready but the type of issue is clear enough to guide a specific corrective action.

The decision engine must weight evidence from:
- before/after clarity improvement
- control and dynamic structure retained or improved
- fatigue reduction or increase
- width and depth realism
- over-processing and artificiality indicators
- manual review feedback

### 5. Audit output for human review
The output must be human readable and explainable, not a black-box score.
It should generate:
- a summary verdict
- per-stem before/after deltas
- full-mix before/after summary
- risk flags for dullness, fatigue, artificial width, and over-processing
- final rationale for pass / reject / refine
- optional human override note with reason and scope

### 6. Human review integration
- Manual approval or rejection can override the default recommendation only when the reviewer provides a reasoned note.
- The result must still show the underlying metric evidence and the human rationale side by side.
- This preserves accountability and auditability.

## Quality signals tracked
The system must track and report at least the following outcome indicators:
- clarity improvement or loss
- transient control and realism
- fatigue or listening discomfort
- high-frequency harshness or excessive brightness
- artificial width and unstable stereo image
- depth and realism of the spatial field
- overall mix cohesion without flattening the arrangement

## Key design decisions
- Metrics are supporting evidence only; musical quality is the deciding factor.
- Stem-aware quality review is the default path.
- The final review is an active gate, not passive reporting.
- A “good numbers” summary is insufficient evidence of a good master.
- Rejection or refinement must be explicit when a result is not meaningfully better.

## Guardrails
- Never silently ship a result that is technically compliant but musically weak.
- Never treat LUFS, DR, or peak safety as proof of a good master.
- Never hide risk behind a clean numerical report.
- Use float64 internally and true-peak oversampling for any peak safety reporting.
- Keep the output auditable so that any reviewer can understand the pass / reject / refine decision.

## Expected result
This review stage transforms a good mastering pipeline into a trustworthy final product gate. It cannot allow a processed master to pass simply because it meets a metric checklist. The project’s final truth check is whether the output sounds better in the emotional and spatial sense, not just whether the report looks compliant.
