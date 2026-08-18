# STORY-004 Defects

QA automation run: 2026-08-15
Scope: measurement-correction story (DEF-201, DEF-203, DEF-204) verification and coverage audit.

---

## DEF-404
Status: Open
Reported by: qa-automation-engineer
Linked test case: TC-401 through TC-459 (story-level coverage audit)
Description:
This story defines a measurement-correction pass and a set of analytical tests for DEF-201 and DEF-203, but no executable QA automation pass was found for the story itself. The requirements and test-cases documents describe specific falsification and regression controls, yet the repository does not contain a corresponding pytest run that validates them.

This is a clear QA automation gap: the implementation and test surface are described, but the story lacks execution evidence that would demonstrate the measurement fixes are real and not just documented.

Triage: Code-level
Fix notes:
Implement and execute the missing automation against the analysis pipeline before closure. The current story is documentation-only and not yet supported by live verification.

---

## DEF-405
Status: Open
Reported by: qa-automation-engineer
Linked test case: AC1 / AC6 / AC9 audit
Description:
The story requires the prior band-limit and mono-sum defects to be re-verified with ground-truth tests and negative controls. The expected defects are present in the documentation, but the actual QA pass has not been executed. This leaves the story without an evidence trail for the fix-method checks and regression guard conditions.

Triage: Code-level
Fix notes:
The missing test execution must be created and run before this story can be closed. The audit must include the negative controls and the method-change checks required by H6.
