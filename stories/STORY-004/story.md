# STORY-004 — Measurement correctness (DEF-201, DEF-203, DEF-204)

**Priority: first. Nothing downstream is trustworthy until this passes.**
Source: `docs/BACKLOG.md` STORY-004. Governed by `docs/CLAUDE.md`,
`docs/DOMAIN.md`, `docs/ARCHITECTURE.md`, `docs/HANDOFF.md` (H-rules).

## Contract (H1)
```
Consumes:    existing analysis implementation
             (stories/STORY-001/implementation/suno_mastering/analysis/*)
Produces:    corrected analysis + ground-truth suite
             (Measurements per ARCHITECTURE.md §3.2; ground-truth tests
             under stories/STORY-001/implementation/tests/)
Consumed by: STORY-005 (targets derived from these measurements)
```

## Scope

### DEF-201 — band-limit detection. METHOD change required (H6).
Previous fix raised the threshold 6→20 dB (a *parameter* change to a *wrong
method* — prohibited by H6). Evidence it is still wrong:
- All five references now report UNSTABLE. A band limit is a fixed property
  of a file (DOMAIN.md §2) — universal instability means the method tracks
  programme content.
- Leftfield reports 8170 Hz on a 1995 CD master extending to ~20 kHz.
- Threshold detection cannot work on declining spectra, at any threshold
  (DOMAIN.md §2; CLAUDE.md §5 known-wrong patterns).

Replace with cliff detection: sustained ≥24 dB/octave across adjacent bins
followed by a floor. No cliff → `None` (never a fallback value).
Return contract per ARCHITECTURE.md §3.2: `hf_band_limit_hz` (nullable) +
`hf_band_limit_confidence`.

### DEF-203 — mono-sum baseline. Derivation required (H4).
Per DOMAIN.md §3 and ARCHITECTURE.md §5, the correct floor is **−3.01 dB**
(uncorrelated equal-power, mono vs single channel), and **−6.02 dB is
wrong**. Field name per ARCHITECTURE.md §3.2: `mono_sum_level_change_db`.
Show the derivation in architecture.md. Verify at ρ = 1.0 (→ 0 dB),
0.0 (→ −3.01 dB), −1.0 (→ −∞). Expect "excess cancellation" to disappear on
all five references — they are summing normally. Excess reported only below
−4.5 dB (DOMAIN.md §3).

### DEF-204 — coverage.
Establish why STORY-003's tests did not catch either. QA's wiring-gap
investigation (stories/STORY-002/defects.md, "DEF-201 wiring-gap
investigation") already found the likely cause: the synthetic fixtures do
not exercise the real segmented, silence-gated code path, there was no
pink-noise-with-a-real-cutoff fixture, and no 48 kHz fixture (the real
tracks' sample rate). Close the gap; if the pink-noise negative control
exists and passes while the real path fails, that mis-wiring is itself the
finding.

## Acceptance (from BACKLOG.md)
1. Pink-noise negative control written first, confirmed failing, then fixed
   (H3/H7).
2. All five references report a plausible band limit or `None`; no value
   below 10 kHz on a commercial master (DOMAIN.md §2).
3. Band limit stable across segments, or absent.
4. Mono-sum derivation in architecture.md; verified at three ρ values.
5. Excess cancellation reported only below −4.5 dB.
6. H5 plausibility gate on the full reference report.
7. Gate 2 review passes.

Definition of Done: HANDOFF.md Part 3 (all items), including the human
level-matched listening check — though this story is analysis-only, so the
listening item applies vacuously (no audio is altered).

## Coordinator notes — read before running the pipeline

1. **The recovered architect "v3" resolution entries in
   `stories/STORY-002/defects.md` are CONTESTED for DEF-203 and must NOT be
   followed blindly.** Those entries (written under STORY-003's process,
   before these docs/gates existed) argue the −6.02 dB constant is correct
   as a BS.1770 *channel-summed* metric and propose keeping it (renamed
   `headroom_db`). That conflicts with DOMAIN.md §3 and ARCHITECTURE.md §5,
   which are authoritative ("where this document and an agent's assumption
   disagree, this document wins") and mandate the −3.01 dB definition and
   the `mono_sum_level_change_db` field. STORY-004 follows the docs: the
   mono-sum metric compares the mono sum against a single channel (ρ=0 →
   −3.01, ρ=1 → 0), not against the channel-summed stereo LUFS. The
   mastering-engineer Gate 1 review must confirm this reconciliation.
2. **The recovered architect v3 HF cliff-detection design broadly aligns**
   with DOMAIN.md §2 / ARCHITECTURE.md §5 (≥24 dB/oct, floor, None when no
   cliff) and is a useful starting point — but its return-contract naming
   (`cutoff_detected`/`rolloff_hz`) must be conformed to ARCHITECTURE.md
   §3.2's `hf_band_limit_hz` (nullable) + `hf_band_limit_confidence`.
3. **Implementation lives in STORY-001's tree** (shared across stories);
   there is no separate STORY-004 implementation folder. Modify
   `suno_mastering/analysis/*` and `tests/*` directly, per the standing
   convention (STORY-001/automation/README.md).
4. **`stories/STORY-002/defects.md` was accidentally destroyed and restored
   on 2026-08-03** (see its Recovery note). DEF-201/DEF-203/DEF-204 are the
   live items this story closes; DEF-202 is STORY-005's.
