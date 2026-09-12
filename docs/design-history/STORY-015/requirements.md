# STORY-015 — Requirements: Final quality and review loop for stem-based mastering

## Contract
Consumes: the processed stem set, recombined final mix, and the completed loudness/true-peak safety pass.
Produces: a final quality gate that decides whether the mastered output is genuinely better musically, not merely compliant on paper, and records the rationale for that decision in an auditable report.

## Restated intent
The final quality layer is the project’s ultimate truth check. The phase must prove that the result actually sounds better in the emotional, spatial, and tonal sense, not simply that it meets threshold values. The review loop is therefore a product-facing decision system, not a logging utility.

## Requirements
1. Before/after review of the processed file against the original
   - For the full mix and each contributing stem, calculate a before/after summary covering clarity, control, tonal balance, fatigue, width, depth, and realism.
   - Compare the original source against the final mastered output with level-normalized listening cues and technical metric deltas so that improvements are materially visible and not hidden by gain matching.
   - The system must report whether the output is better, unchanged, or worse in musically meaningful terms.
   - A good numerical report is never enough to override a poor musical result.

2. Stem-by-stem and bus-level reporting
   - The review layer must present a stem-level report for drums, bass, vocals, synths/pads, ambience, and any remaining non-primary stems used in the process.
   - The report must also include a final bus or full-mix summary that explains what changed after the entire chain.
   - Each stem must show the salient quality signals: transient clarity, low-end control, high-frequency harshness, stereo spread, depth, and any layer-specific fatigue signals.
   - The audit trail must allow a reviewer to see which stem drove the result and why.

3. Detection of over-processing, dullness, fatigue, and artificial width
   - The review must explicitly detect and report the following risk patterns:
     - over-processing or over-compression
     - dullness or low-end/upper-mid flattening
     - listener fatigue from excessive brightness or repeated high-energy content
     - artificial width or phase-unstable stereo spread
     - loss of realism or depth from aggressive imaging or transient damage
   - These checks must be based on before/after evidence, not on a blanket assumption that “if the numbers are good, the sound is good.”

4. Decision logic for manual approval or rejection
   - The review layer must produce a decision of pass, reject, or refine.
   - A pass requires evidence that the output is measurably and musically better than the original, with no significant residual risk flags.
   - A reject requires evidence of meaningful degradation or a poor musical outcome, even if the metrics look technically acceptable.
   - A refine state requires a targeted, explainable correction path rather than a silent override.
   - Manual approval and rejection decisions must be preserved in the final report with a reasoned human note.

5. Traceability and auditable rationale
   - Every pass, reject, or refine decision must be traceable to the underlying before/after evidence.
   - The final report must include: raw metric deltas, stem signals, risk flags, and a short narrative explaining why the result passes or fails.
   - The review layer must record the specific reason a master was accepted or rejected, so that a reviewer can reconstruct the decision later without guesswork.

6. No hidden “good numbers” excuse for poor musical result
   - Compliance metrics may be used as supporting evidence, but they are never a substitute for musical evaluation.
   - The final output may not be approved purely because LUFS, DR, or peak values are within tolerance.
   - If the mix is not meaningfully better in realism, control, spatiality, or comfort, the review must reject or trigger refinement.

7. Stem-first default, stereo fallback only when explicit
   - The review layer must operate on stem-aware data as the default workflow.
   - Stereo-only output remains a fallback path only when the content is not already stem-separated or the workflow decides stem separation is not valid.
   - The final review must clearly state when a stereo fallback limits the quality assessment and whether the result should be treated as a constrained compromise, not a full-quality master.

8. Implementation and safety requirements
   - Internal signal processing must remain float64; integer conversion only occurs at the final I/O boundary.
   - True-peak measurement must use oversampling rather than sample peak.
   - The review system must be conservative and auditable; it must not silently hide risk behind a clean report.

## Acceptance criteria
- The final review compares before/after quality signals for the full mix and each stem.
- The system calls out dullness, fatigue, over-processing, artificial width, and realism loss explicitly.
- The pass / reject / refine decision is clear and supported by evidence.
- Human review can approve or reject the output with a reasoned note.
- The final report is auditable and traceable to the underlying mix change.
- A technically compliant but musically weak result is not accepted.
- If the output is not meaningfully better, the review either rejects it or triggers refinement.
