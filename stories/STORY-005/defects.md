# STORY-005 Defects

QA automation run: 2026-08-15
Scope: gate-false-positive story (per-segment reliability handling, stable/confidence behavior, and downstream reporting).

---

## DEF-505
Status: Open
Reported by: qa-automation-engineer
Linked test case: AC1 through AC6 / gate false-positive audit
Description:
This story defines a specific false-positive gate defect in the HF extension path and includes a detailed audit of per-segment reliability, but no executable QA automation pass was found for the story. The contract and acceptance criteria are present, yet there is no live validation showing that the segment-level false positive is eliminated or explicitly caveated without regressions.

This is an automation-coverage gap and a verification gap: the requirement is documented, but there is no evidence that the code path was actually exercised.

Triage: Code-level
Fix notes:
Create the missing QA automation for the gate scan / false-positive audit and execute it before closing the story. This must include the per-segment false-positive checks and the stable/confidence behavior expected by the story.

---

## DEF-506
Status: Open
Reported by: qa-automation-engineer
Linked test case: AC1 / per-segment false-positive audit
Description:
A story-level QA pass is required to verify zero false positives and document the downstream effect on stable/confidence. The repository does not currently contain a pytest pass that performs this check across the relevant validation set.

Triage: Code-level
Fix notes:
Implement the story-specific test coverage and run it to confirm the segment-level values and confidence logic are consistent with the documented architecture.
