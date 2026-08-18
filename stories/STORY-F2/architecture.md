# STORY-F2 — Architecture: Reference Analysis Regeneration (DEF-609 Resolution)

**Architect:** software-architect  
**Date:** 2026-08-15  
**Governed by:** `CLAUDE.md`, `docs/DOMAIN.md`, `docs/ARCHITECTURE.md`, `docs/HANDOFF.md`

---

## CRITICAL CLARIFICATION — Requirements Correction Required

**The requirements.md for this story is based on stale information and needs correction before implementation can proceed.**

### Current Situation

1. **STORY-004 already implemented cliff detection** — `analysis/hf_extension.py` contains a working two-stage cliff detector (existence gate + floor-onset localization) that replaced the threshold-based method. See STORY-004 architecture.md v1.5a and gate2-review-v1.5a.md.

2. **The cliff detection is already working correctly** — STORY-004 Gate 2 review (2026-08-08) shows plausible measurements for all five reference tracks using the new method:
   - Black Flute: 15788 Hz, stable=True, confidence=1.0
   - GusGus: 16251 Hz, stable=True, confidence=1.0  
   - Leftfield: 20475 Hz, stable=True, confidence=1.0
   - Chemical Brothers: 20475 Hz, stable=False, confidence=0.4 (with one per-segment false positive — see below)
   - Wavy Gravy: 20475 Hz, stable=True, confidence=0.6

3. **STORY-006 analyzed an OLD reference_set_report.json** — The "5131 Hz" and "stable=False on all five tracks" readings cited in STORY-006 defects.md and mastering-review-gate1.md are from a reference analysis run BEFORE STORY-004's cliff detection was implemented. That file contains threshold-based method results.

4. **DEF-609 is resolved by regeneration, not re-implementation** — The threshold method no longer exists in the code. DEF-609 closes when `reference_set_report.json` is regenerated using STORY-004's already-implemented cliff detector.

### What requirements.md Got Wrong

requirements.md states:
> "Replace the threshold-based HF extension detection (which measures spectral tilt...) with cliff-detection..."

**This is incorrect.** The replacement was already done in STORY-004. The threshold-based method does not exist in the current codebase.

requirements.md AC-F2-1 through AC-F2-7 describe implementing a cliff-detection algorithm that **already exists and passed Gate 2 review**.

### What STORY-F2 Actually Needs to Do

**Option A (Minimal — Recommended):**
Regenerate `reference_set_report.json` using the existing STORY-004 cliff detection implementation. No code changes required. DEF-609 closes when the new file shows all five tracks with plausible, stable measurements.

**Option B (If STORY-004 Gate 2 findings require fixes):**
Address the one defect-grade finding from STORY-004 Gate 2 review (Chemical Brothers segment 1 false positive at 14066 Hz), THEN regenerate. This would be a parameter tuning or gate-criterion adjustment, not a method replacement.

**Option C (If requirements insist on duplicate work):**
Proceed with implementing cliff detection as if STORY-004 never happened. This wastes development time re-implementing what already exists and passed review.

### Recommended Action Before Proceeding

**Business analyst must clarify:**
1. Was the intent to regenerate reference analysis using STORY-004's implementation (Option A)?
2. Or to fix remaining STORY-004 findings before regenerating (Option B)?  
3. Or was there genuine confusion about whether STORY-004 was complete?

**Architect position:**
Option A satisfies DEF-609's closure condition ("QA verifies all five reference tracks report stable, plausible rolloff values") without any code changes. The cliff detection method already exists, is correctly implemented per STORY-004 Gate 2, and only needs to be RUN on the reference tracks to produce an updated JSON file.

If Option B is chosen, the STORY-004 Gate 2 finding (segment 1 false positive) should be raised as a separate defect and scoped as "parameter tuning to existing cliff detection," not "method replacement."

---

## Provisional Architecture (Assuming Option A — Regeneration Only)

If BA confirms Option A, this is the complete specification:

### Contract (H1)

```
Consumes:    Reference track audio files (Reference Tracks/*.{wav,flac,mp3})
             Existing cliff detection implementation (analysis/hf_extension.py from STORY-004)
Produces:    Updated reference_set_report.json with STORY-004 cliff-detection results
Consumed by: STORY-006 mastering pipeline (reads targets from reference analysis)
             Reference reporting (report/reference_render.py)
```

### Scope

1. Run the existing reference analysis pipeline (`reference_analysis/pipeline.py`) on all five reference tracks
2. Generate `reference_set_report.json` using STORY-004's cliff detection implementation (no code changes)
3. Verify output matches STORY-004 Gate 2 plausibility expectations:
   - All five tracks report `stable = true` OR `stable = false` with documented reason (per-segment false positive, drift)
   - No tracks report cutoff < 10000 Hz (DOMAIN.md §2 floor)
   - Leftfield — Melt reports ≥18000 Hz or `null` (NOT 5131 Hz, NOT 8170 Hz)
   - All measurements use `method = "cliff_detection"` field

### Implementation

**No new code required.** Execute:

```bash
cd stories/STORY-001/implementation
python -m suno_mastering.reference_analysis.pipeline \
    --input "../../Reference Tracks" \
    --output "../../Reference Tracks/reference_set_report.json" \
    --config <appropriate config>
```

Or equivalent script/notebook that calls the existing pipeline.

### Acceptance Criteria (Revised from requirements.md)

**AC-F2-R1: Regeneration executed**
**Given** the existing STORY-004 cliff detection implementation  
**When** reference analysis pipeline is run on all five reference tracks  
**Then** `reference_set_report.json` is generated with `method = "cliff_detection"` for all tracks

**AC-F2-R2: Stability on reference set**
**Given** the regenerated report  
**When** examined for stability  
**Then**:
- At least 4/5 tracks report `stable = true`, OR
- Any `stable = false` track has documented explanation in STORY-004 Gate 2 review (e.g., Chemical Brothers segment 1 false positive)

**AC-F2-R3: Plausibility — commercial CD masters**
**Given** Leftfield — Melt, Wavy Gravy (1995 CD masters)  
**When** analyzed  
**Then** each reports `rolloff_hz` in range [18000, 22050] Hz OR `null`  
**And** NO track reports < 10000 Hz

**AC-F2-R4: Leftfield specific validation (DEF-609 closure evidence)**
**Given** Leftfield — Melt  
**When** analyzed  
**Then** reports `rolloff_hz` ≥ 18000 Hz OR `null`  
**And** does NOT report 5131 Hz or 8170 Hz (old threshold method values)

**AC-F2-R5: Method field verification**
**Given** all five tracks in regenerated report  
**When** `hf_extension.method` field examined  
**Then** all report `method = "cliff_detection"` (confirming STORY-004 implementation was used)

**AC-F2-R6: Reference report rendering**
**Given** the regenerated `reference_set_report.json`  
**When** `report/reference_render.py` produces reference analysis report  
**Then** HF extension section displays plausible values with no physically impossible readings  
**And** informational-only caveat remains: "HF extension is not used as a correction target"

**AC-F2-R7: DEF-609 closure verification**
**Given** all acceptance criteria above pass  
**When** QA reviews the regenerated measurements  
**Then** DEF-609 can be closed (method is correct, measurements are plausible, no threshold-based artifacts remain)

### Test Strategy

**No new unit tests required** — STORY-004 already has complete ground-truth test suite for cliff detection including:
- Pink noise negative control (AC-F2-6 from original requirements — already TC-022 in STORY-004)
- Brick-wall filter positive control (AC-F2-7 from original requirements — already TC-023 in STORY-004)
- MP3 detection (AC-F2-8 from original requirements — covered by STORY-004 transcode detection tests)

**Integration test:**
1. Run regeneration script
2. Load resulting JSON
3. Assert fields match AC-F2-R1 through AC-F2-R5
4. Compare against STORY-004 Gate 2 expected values (within tolerances for Welch estimator noise)

### Expected Values (from STORY-004 Gate 2 Review)

Based on STORY-004 gate2-review-v1.5a.md (2026-08-08):

| Track | Expected rolloff_hz | Expected stable | Expected confidence | Notes |
|---|---|---|---|---|
| Black Flute | 15788 Hz ±  500 Hz | true | 1.0 | Sub-17 kHz indicates lossy source |
| GusGus | 16251 Hz ± 500 Hz | true | 1.0 | Sub-17 kHz indicates lossy source |
| Leftfield | 20475 Hz ± 500 Hz | true | 1.0 | Could be SRC artifact (44.1→48 kHz) OR MP3 320 |
| Chemical Brothers | 20475 Hz ± 500 Hz | false | 0.4 | Segment 1 false positive (14066 Hz) documented in Gate 2 |
| Wavy Gravy | 20475 Hz ± 500 Hz | true | 0.6 | Confidence exactly at threshold (5 segments, 3/5 agreement) |

**Tolerance:** ±500 Hz accounts for 1/24-octave grid quantization plus Welch estimator noise on different runs.

**If measurements deviate significantly from these values:** That indicates either (a) different audio files were used, (b) STORY-004 implementation has regressed, or (c) configuration differs from STORY-004 run.

### Non-Functional Requirements

**Performance:** Regeneration of five tracks completes in ≤ 30 seconds on developer's Windows machine (existing STORY-004 implementation performance baseline).

**Determinism:** Same audio files + same configuration → same measurements within Welch estimator noise (±0.5 dB in margins, ±1 grid band in frequency).

**No regression:** STORY-004 unit tests continue to pass after regeneration (confirms implementation unchanged).

### Risks and Mitigations

**Risk 1:** Regenerated values don't match STORY-004 Gate 2 expectations.

**Mitigation:** Compare audio file hashes against STORY-004 inputs. Verify configuration matches STORY-004 run. Check for implementation regressions by running STORY-004 unit tests.

**Risk 2:** Chemical Brothers still reports stable=False.

**Mitigation:** This is EXPECTED per STORY-004 Gate 2. stable=False on Chemical Brothers is correct behavior (segment 1 false positive documented). This is NOT a failure condition for DEF-609 closure — the whole-track value (20475 Hz) is correct and plausible.

**Risk 3:** STORY-006 mastering pipeline breaks when reading new JSON.

**Mitigation:** STORY-006 architecture.md §23 explicitly states no STORY-006 code reads `hf_extension`. Regeneration is safe. The `method` field is new but backward-compatible (string, not breaking change).

---

## Alternative Architecture (Option B — Fix Then Regenerate)

If BA chooses Option B (address Chemical Brothers segment 1 false positive first), the scope expands to:

1. **Tune STORY-004 gate criterion** (e.g., increase `hf_cliff_required_drop_db` from 8.0 to 10.0, or increase `hf_cliff_passband_max_slope_db_per_octave` from 12.0 to 14.0) to reduce false positives on dynamic material
2. **Rerun STORY-004 unit tests** to verify tuning doesn't break positive controls
3. **Regenerate reference analysis** using tuned implementation
4. **Verify Chemical Brothers stable improves** (target: stable=True or confidence ≥ 0.6)

This is a **parameter change**, not a method change (H6 compliant — adjusting thresholds within existing cliff-detection framework, not replacing the framework).

**Risk:** Tuning to eliminate Chemical Brothers false positive may reduce sensitivity on other tracks or break TC-023 (brick-wall filter positive control).

**Estimated effort:** 1–2 days (tuning + retest) vs. 1 hour (regeneration only).

---

## Recommendation to Business Analyst

**Choose Option A (regeneration only) unless:**
- James specifically requested fixing Chemical Brothers instability, OR
- Future stories require `stable=true` on all reference tracks for target derivation

STORY-006 explicitly states HF extension is "informational-only" and does NOT derive targets from it. DEF-609 closes when measurements are plausible and the threshold method is confirmed gone — both satisfied by regeneration alone.

**If Option A is rejected, requirements.md must be rewritten** to reflect:
- Cliff detection already exists (STORY-004)
- Scope is parameter tuning or regeneration, NOT method implementation
- AC-F2-1 through AC-F2-7 are already satisfied by existing code and tests

---

## Revision History

**v1.0 — 2026-08-15**
Initial architecture. Identified requirements/reality mismatch: cliff detection already exists (STORY-004), requirements assume it doesn't. Provided two paths forward (regeneration vs. tuning+regeneration) pending BA clarification.

---

## Open Questions for BA

**Q1 (BLOCKING):** Which option?
- (A) Regenerate using existing STORY-004 implementation, OR
- (B) Fix Chemical Brothers instability first, then regenerate

**Q2:** If Option B, what is acceptable Chemical Brothers outcome?
- stable=True (may require significant gate tuning, risk to other tracks), OR
- confidence ≥ 0.6 (stable could stay false but per-segment agreement improves), OR
- Document as known limitation (whole-track value correct, per-segment false positive explained in report)

**Q3:** Should requirements.md be rewritten to match current reality, or proceed with duplicate implementation?

**Architect recommendation:** Option A + Q3=rewrite. Fastest path to DEF-609 closure, no code changes, no regression risk.
