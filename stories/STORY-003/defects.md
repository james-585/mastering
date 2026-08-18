# STORY-003 Defects

QA automation run: 2026-08-15
Scope: requirement/test-case audit and executable-test validation for the ground-truth harness story.

---

## DEF-303
Status: Open
Reported by: qa-automation-engineer
Linked test case: TC-001 through TC-080 (story-level coverage audit)
Description:
The story is documented as a ground-truth harness, but no executable pytest automation under `stories/STORY-001/implementation/tests/` was found for the story's required coverage set. The requirements and test-cases documents define a large set of analytically-derived checks, yet there is no corresponding automation implementation to execute and verify them. This is a QA coverage gap, not a code-path bug in the production audio logic.

The missing automation blocks a real QA pass on the story's acceptance criteria, including the required ground-truth checks for loudness, true peak, HF extension, dynamic range, spectral balance, stereo width, and sanity assertions.

Triage: Code-level
Fix notes:
The test-case-writer and python-developer must implement the missing pytest suite in the existing STORY-001 tests tree and execute it before this story can be considered complete. The story is not yet supported by executable evidence.

---

## DEF-304
Status: Open
Reported by: qa-automation-engineer
Linked test case: AC1 / AC13 coverage audit
Description:
The story declares that every measurement function must have a ground-truth test, but the repository does not contain a matching automation pass for this requirement. The implementation remains documentation-only and therefore cannot be validated against the production code path.

Triage: Code-level
Fix notes:
Create the missing ground-truth tests and run them against the current implementation before closure. This must be treated as a QA implementation gap rather than an accepted omission.
