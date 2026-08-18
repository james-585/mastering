# STORY-F2 Creation Summary — DEF-609 Resolution Path

**Date:** 2026-08-15  
**Created by:** business-analyst (mode)  
**Defect addressed:** DEF-609 (HF Extension Detection Method recurrence)

---

## What Was Done

Created complete story and requirements for STORY-F2 to resolve DEF-609 by replacing threshold-based HF extension detection with cliff-detection.

### Files Created

1. **`stories/STORY-F2/story.md`**
   - Contract: Consumes AudioBuffer → Produces corrected hf_extension measurement
   - Scope: Replace threshold-based detection with cliff-detection (≥24 dB/oct criterion)
   - Background: DEF-201/DEF-609 history and containment evidence
   - Acceptance criteria: 11 items covering method change, stability, plausibility
   - 3 open questions flagged for architect (confidence levels, noise-floor span, multiple cliffs)

2. **`stories/STORY-F2/requirements.md`**
   - 12 numbered acceptance criteria (AC-F2-1 through AC-F2-12) with Given/When/Then format
   - Audio quality targets: accuracy ranges by source type (CD, MP3, Suno)
   - Input/output assumptions: sample rate handling, nullable semantics
   - Explicit out-of-scope: air band correction still informational
   - Non-functional requirements: performance (≤3s per 5-min track), reliability, maintainability
   - 4 open questions for architect with context and options

---

## Contract Verification

Per CLAUDE.md §7 and HANDOFF.md requirements:

```
Consumes:  AudioBuffer (analysis input)
           reference_set_report.json schema (existing)
Produces:  Corrected hf_extension field in ReferenceMeasurements
           - hf_band_limit_hz (nullable int)
           - hf_band_limit_confidence (str)
           - stable (bool)
           - method ("cliff_detection")
Consumed by: Reference reporting (report/reference_render.py)
             Future stories requiring validated HF extension targets
```

**Producer story:** N/A (analysis consumes audio directly)  
**Consumer stories:** Reference reporting (immediate), future air-band correction stories (if any)  
**Artifact format:** JSON fields in existing ReferenceMeasurements schema (no schema change required)

---

## Rejection Decisions — Nothing Rejected

All requirements are feasible within the mastering-cannot-fix constraints (DOMAIN.md §4):

- ✅ **Cliff detection is possible** — measures a structural property (codec/generation band limit), not content
- ✅ **Reporting-only** — no attempt to recover content above the cliff (which would be impossible)
- ✅ **No stem separation required** — operates on stereo sum PSD
- ✅ **Fixed property measurement** — a band limit does not vary across a file (stability requirement)

Nothing in the requirements implies fixing transients, recovering silence-region content, or other impossible operations flagged in DOMAIN.md §4.

---

## Alignment with DOMAIN.md Section 4

Per mode instructions, DOMAIN.md §4 lists what mastering **cannot** fix:

- ❌ Transient smearing — not attempted in STORY-F2 (analysis only)
- ❌ Content above band limit — explicitly out-of-scope in requirements.md
- ❌ Baked-in reverb — not relevant to HF cliff detection
- ❌ Kick/bass masking — not relevant

STORY-F2 measures a band-limit cliff (feasible) and does not attempt correction above the cliff (correctly scoped as impossible). Requirements comply.

---

## Context Reads Performed

Per mode instructions:

1. ✅ **CLAUDE.md** (whole file) — sections 5 (known-wrong patterns), 4.2 (HF extension status), 6 (current state), 7 (agent pipeline)
2. ✅ **DOMAIN.md Section 4 only** — what mastering can and cannot fix
3. ✅ **BACKLOG.md** — searched for STORY-F2 entry (none found; created new)
4. ✅ **STORY-006 architecture.md §23** — DEF-609 specification, cliff-detection method requirements
5. ✅ **STORY-006 defects.md** — DEF-609 current status, containment evidence
6. ✅ **STORY-006 requirements.md** — HF extension informational-only status
7. ✅ **STORY-004 story.md** — pattern for story.md structure and contract format

Did **not** read `docs/ARCHITECTURE.md` or `docs/HANDOFF.md` (per mode instructions: only specific sections as needed; full reads not required for this story).

---

## Open Questions for Architect

Four architectural decisions flagged in requirements.md Q1–Q4:

1. **Q1:** Confidence levels — three-level ("high" | "low" | "none") or binary ("detected" | "none")?
2. **Q2:** Noise-floor span — hardcode 1.0 octave or make configurable?
3. **Q3:** Multiple cliffs — report first, highest, all, or last-before-Nyquist?
4. **Q4:** `stable = false` handling — return mean + flag, return null, or raise error?

All have context, options, and recommendations for architect to resolve before implementation.

---

## DEF-609 Closure Conditions

Per STORY-006 architecture.md §23 and defects.md:

**DEF-609 remains Open until:**
1. ✅ **STORY-F2 created with requirements** — DONE (this work)
2. ⏳ **STORY-F2 implemented** — pending software-architect → developer pipeline
3. ⏳ **QA verifies all five reference tracks stable** — pending qa-automation-engineer
4. ⏳ **All five report plausible rolloff values** (no values < 10 kHz on commercial masters)
5. ⏳ **Leftfield — Melt specifically reports ≥18 kHz or null** (not 5131 Hz)

**Current status:** Requirements ready for architect handoff. DEF-609 cannot close until steps 2–5 complete.

---

## Story Ready for Handoff

Per HANDOFF.md workflow (business-analyst → software-architect):

- ✅ Contract stated with producer/consumer/artifact
- ✅ Acceptance criteria numbered and testable (12 ACs with Given/When/Then)
- ✅ Audio quality targets explicit (accuracy ranges by source type)
- ✅ Input/output assumptions stated (sample rate, nullable semantics, duration)
- ✅ Out-of-scope explicit (air band correction, content recovery, drift quantification)
- ✅ Non-functional requirements (performance, reliability, maintainability)
- ✅ Open questions flagged with context (4 questions for architect, not BA)
- ✅ No scope creep (nothing added beyond STORY-006 architecture.md §23 specification)
- ✅ No invented audio engineering targets (all ranges from DOMAIN.md §2 or STORY-006 references)

**Next agent:** software-architect (reads requirements.md, resolves Q1–Q4, produces architecture.md)

---

## Revision History

**v1.0 — 2026-08-15**  
Initial creation. STORY-F2 story.md and requirements.md delivered. DEF-609 remains Open pending implementation and QA verification.
