# STORY-011 — Gate 1 Review: DEF-011-01 Headroom-Clamp Revision

Reviewer: mastering-engineer
Date: 2026-08-17
Reviewed: `architecture.md` (revised 2026-08-17, "Headroom-management
contract"), `defects.md` (DEF-011-01), current
`implementation/transient_restoration.py`, `requirements.md`, CLAUDE.md,
DOMAIN.md.

## Verdict: APPROVED-WITH-CONDITIONS

The clamp-then-report method is sound and resolves DEF-011-01 by the correct
route: it replaces a wrong method (aborting on a normal stem-level property)
rather than tuning its parameter, keeps the ±1.0 legality guard where it
belongs, and degrades gracefully with report visibility, satisfying
requirements.md AC7. The clamp arithmetic is exact because the gain is
uniform over exactly the window the peak is measured on — the derivation in
the architecture is correct as stated.

Two findings require architect disposition before implementation proceeds
(one condition, one concern). One separately-flagged observation is confirmed
as defect-worthy and must go to QA.

---

## Ruling on the flagged question: is the 0.175 dB margin adequate?

**The value 0.98 may stand, but the stated rationale for it is physically
wrong and must be re-derived. The margin question as posed — "does 0.175 dB
absorb re-sum growth at bus glue?" — has a definite answer: no, and it was
never going to.**

Worst-case re-sum growth is not a small signal-dependent wobble around
0.175 dB. If two stems are each clamped to 0.98 and their onset peaks land
coincident and same-sign at bus glue, the sum peaks at 1.96 — +6.02 dB over
a single stem, not +0.175 dB. Coincident onsets are not exotic: all stems
share the same window (the first 80 ms of the file), and on material that
starts on a downbeat the drums and bass onsets are correlated by
construction — they were separated from the same kick transient. Four
coherent stems would be +12 dB. No sub-0.2 dB ceiling margin can "absorb"
that, and claiming it does is exactly the asserted-baseline pattern H4
exists to prevent.

The reason 0.98 is nonetheless acceptable is a different fact, which the
architecture leaves unstated: **the intermediate chain is float64 end to
end, integer conversion happens only at final I/O boundaries (CLAUDE.md hard
constraint), and stage 8 owns the −1.0 dBTP ceiling with oversampled
metering.** In a float64 intermediate, a re-summed bus momentarily at 1.3
is not clipping — it is level that the loudness/true-peak stage will
measure and turn down. Under that invariant, the per-stem ceiling's real
jobs are only (a) keeping each stem individually legal for any per-stem
integer export or per-stem clip check, and (b) bounding how much extra
crest the stage injects. For those jobs 0.98 is harmless conservatism, and
retaining the existing value rather than re-deriving it is the correct H6
posture — *for the value*. The derivation text must change.

One further point the report layer must respect: 0.98 is a **sample-peak**
ceiling. A stem at 0.98 sample peak can exceed 1.0 dBTP after oversampled
measurement — inter-sample overshoot of 1–2 dB on transient-heavy material
is ordinary. That is fine, because stage 8 owns true peak, but no report
or reason string may describe a 0.98-clamped stem as "true-peak safe."

**Condition for approval:** re-derive the ceiling rationale in the
architecture — state the float64/no-intermediate-clip invariant explicitly
as the load-bearing safety fact, and delete the claim that the 0.175 dB
margin absorbs re-sum growth. The number stays; the justification changes.

---

## Findings

### F1 — CONCERN (approval condition): clamp ceiling derivation asserts a physically false margin

- **What is proposed**: "Headroom-management contract" §Derivation, bullet 3
  — the 0.175 dB margin's purpose includes absorbing "small peak growth when
  boosted stems are re-summed at bus glue."
- **Why it fails**: per the ruling above, worst-case coherent re-sum growth
  is +6 dB per coincident stem pair, unbounded by any per-stem ceiling. The
  margin absorbs float rounding and nothing else. An engineer reading the
  derivation would conclude the intermediate bus is protected against
  overshoot; it is not, and does not need to be — for a different reason
  the document does not state.
- **What to do instead**: re-derive as: ceiling value retained (H6), safety
  provided by the float64-intermediate invariant plus stage 8's ownership of
  the −1.0 dBTP ceiling; ceiling's function limited to per-stem legality and
  bounding injected crest. Add the explicit requirement that no stage
  between transient restoration and the final safety stage may perform
  integer conversion or a ±1.0 clip; if any ever does, this ceiling must be
  re-derived against the true re-sum bound.

### F2 — CONCERN: codifying the uniform rectangular gain window locks in an audible edge discontinuity

- **What is proposed**: the contract derives clamp exactness from "the
  restoration gain is applied uniformly to a single window," and the current
  implementation does exactly that — a rectangular gain step ending at
  sample W.
- **Why it fails on real programme material**: a hard gain step from
  `10^(g/20)` back to unity at sample W is a waveform discontinuity of
  magnitude `(g−1)·x[W]`. On any stem with signal present at the window
  edge, that is an audible click 80 ms in — a new artifact introduced by a
  stage whose purpose is removing artifacts. The architecture's "exact
  predictability" argument now gives this shape a contractual reason to
  exist, which makes the artifact load-bearing.
- **What to do instead**: specify a short raised-cosine taper (a few ms) on
  the gain shape at the window edge. The clamp survives intact: with any
  taper bounded by `g_applied`, every window sample is scaled by at most
  `g_applied`, so the post-gain onset peak is bounded by
  `p_onset · 10^(g_applied/20)` — the prediction becomes a conservative
  bound instead of an exact equality, which costs nothing and removes the
  click. Record `onset_peak_after` as measured (not predicted) once a taper
  exists.

### F3 — NOTE: clamping against onset-window peak (not global peak) is the physically correct choice

Confirmed sound. The gain touches only the window, so only the window's peak
can grow; a global peak elsewhere in the file is untouched by the stage and
needs no headroom from it. Clamping against the global peak would skip
legitimate work on stems whose hot sample sits nowhere near the processing
region. The legality guard correctly owns the > 1.0 case regardless of
location. The defect-reproduction scenario also behaves sensibly: a stem at
0.9831 inside the window has headroom of `20·log10(0.98/0.9831) ≈ −0.027 dB`
— negative, so the stem is skipped unchanged with a visible action. A stem
already at 0.9831 in its attack region has no room for a boost; skipping is
the right musical answer, and the stem demonstrably does not need help being
loud. No action required.

### F4 — NOTE: skip-unchanged is the sonically safest of the available responses

Endorsed over the alternatives. Boost-then-clip puts distortion exactly on
the transient — the worst possible place. Boost-then-limit turns this stage
into a dynamics processor it was never designed to be. The rejected Option B
(pre-stage broadband trim) was correctly rejected: it alters the input to
every downstream stem detector and violates "if the signal is already good,
do not change it." The disposition's rejection rationale is sound. No action
required.

### F5 — NOTE: action-record fields are sufficient; one optional addition

`requested_gain_db`, `onset_peak_before/after`, and `action_type` give a
mastering engineer what is needed to judge the decision: what was wanted,
what headroom existed, what happened. One optional addition — the stem's
**global** sample peak — would let a reader distinguish "stem hot
everywhere, skip obviously correct" from "only the onset is hot" without
re-measuring. Not required; the record is adequate as specified. The
reason-string conventions (stating both requested and applied gain, and the
measured onset peak on skips) are exactly right.

### F6 — SEPARATE DEFECT (for QA to log): `hilbert` transform axis on 2-D stems

The architect flagged this; my domain view: **yes, this is absolutely worth
a QA defect — it is a wrong-method bug on the normal case, not an edge
case.** `scipy.signal.hilbert` defaults to `axis=-1`. Stems arrive as
`(samples, 2)`, so the transform runs across the 2-sample **channel** axis,
not the time axis. A Hilbert transform of a 2-point signal is meaningless;
the "envelope" it produces on stereo stems is garbage, and every attack
ratio derived from it — the evidence on which the entire stage fires — is
measuring numerical noise, not attack strength. Mono stems are unaffected,
which is how this can hide: synthetic mono fixtures pass while real stereo
stems get a nonsense metric. The downstream flattening (`np.max`,
`np.median` over the whole 2-D onset block) then launders the garbage into a
plausible-looking scalar. This is precisely the class of bug that ships
because a number comes out. It must be logged by QA and fixed in the same
rework that implements the clamp; the fix is `axis=0` (transform along
samples), and the fixtures must include a stereo case with a known attack
ratio so this cannot regress silently. It does not block approval of the
clamp contract itself — the clamp is independent of how `g_req` is derived —
but the stage cannot be trusted on real (stereo) material until it is fixed.

---

## Summary for the architect

Per the follow-up rule, F1 and F2 require explicit disposition in
architecture.md before implementation. F1 is the approval condition. F3–F5
are confirmations, recorded so the review is not silent on the flagged
questions. F6 is referred to QA for defect logging; no architectural
disposition needed beyond scheduling the fix alongside the clamp rework.
