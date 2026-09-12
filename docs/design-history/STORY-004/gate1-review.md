# STORY-004 — Gate 1 Review (Method Review)

Reviewer: mastering-engineer. Reviewed against `requirements.md`,
`architecture.md`, `CLAUDE.md`, `DOMAIN.md`, and the DEF-201/DEF-203/DEF-204
history in `stories/STORY-002/defects.md` (original entries, REOPENED
entries, the wiring-gap investigation, and both v3 architect-resolution
entries).

## Verdict: PASS-WITH-BLOCKERS

One Blocker. The mono-sum redesign (DEF-203) is sound and may proceed as
specified. The HF cliff detector's core mechanism (DEF-201) correctly
closes the mid-band false-positive failure mode that shipped twice
(GusGus 1979 Hz, Leftfield 8170 Hz) — say so plainly, this is real,
careful work, not a restatement of the old bug. But the near-Nyquist
truncation the architect added specifically to reach DOMAIN.md's 20–22 kHz
CD/lossless row introduces a **new** false-positive mode at the opposite
end of the spectrum, one that is structurally harder to catch than the one
being fixed, because a spurious ~20.7 kHz reading is *plausible* — it will
pass AC2 and Gate 2 by inspection. This must be closed in architecture.md
before implementation, not discovered after a third round of "green suite,
wrong real-world number."

---

## Findings

### 1. [BLOCKER] Near-Nyquist truncated-window criterion will fire on ordinary top-end roll-off, not just genuine cliffs

**Where**: §3.3 (near-Nyquist window/floor truncation), §3.4 (passband
precondition), §3.5 (floor criterion), interacting with the real reference
set's sample rate (48 kHz, CLAUDE.md §4.1).

**What is proposed**: near Nyquist, the candidate window shrinks to as few
as `hf_cliff_min_window_bands = 3` bands (1/8 octave), with
`required_drop_db` scaled down to `3 × 1.0 dB = 3.0 dB` over that window,
monotonicity checked with ±1 dB wiggle tolerance per band-step, and a
floor region of only `hf_cliff_min_floor_bands = 2` bands (1/12 octave)
required not to "recover" above `levels_db[i] − required_drop_db +
noise_margin`, which at the truncated 3 dB drop reduces to "the floor must
not climb back above roughly where the candidate started" — a near-vacuous
constraint at this window size. This truncation is explicitly added (and,
per the revision history, twice arithmetically corrected) specifically so
a genuine CD/lossless 20–22 kHz band limit (DOMAIN.md §2's own table) is
reachable at all, rather than structurally excluded.

**Why it fails, concretely**: 3 dB of monotonic decline over a 1/8-octave
window, followed by two non-recovering bands, is not a discriminating test
for "a filter cliff exists here." It is closely consistent with the
**ordinary, un-filtered top end of a normal 48 kHz master** — mastering-
chain analog/converter reconstruction roll-off, dither/noise-shaping
behaviour near Nyquist, and simply the fact that there is very little
musical energy at 21 kHz on any commercial source. DOMAIN.md §3 itself
says "air band 10–25 dB below mid is normal, not a defect" — a spectrum
that is already 10–25 dB down by the air band, continuing to decline
gently into the last octave before Nyquist, can satisfy a 3 dB/1-8-octave
drop with no real wall present at all.

This interacts badly with the passband gate (§3.4): for a genuine 20 kHz
candidate at 48 kHz, the pre-candidate slope is evaluated over the
10–20 kHz octave against the 12 dB/octave ceiling. On real material this
region frequently declines faster than that (again, DOMAIN.md's own
10–25 dB air-band figure), so one of two things happens and the
architecture does not derive which: (a) the gate correctly rejects, and
the "adaptive truncation" this section exists to add buys nothing (a
genuine CD-master cliff at 20 kHz is *still* not reported, just with
`None` instead of a truncation bug); or (b) the gate passes on a candidate
that is really the tail of ordinary roll-off, and the weak truncated
criterion above then fires — producing exactly the kind of number this
story exists to stop shipping, except this time it is *inside the
plausible range* (DOMAIN.md's 20–22 kHz CD/lossless row), so AC2 ("every
value is either a plausible band limit... or None") and a casual Gate 2
read will both pass it. 8170 Hz on Leftfield was caught because it was
obviously wrong. A spurious 20774 Hz will not be caught the same way — it
requires the reviewer to know the number sits exactly at the detector's
own admissibility ceiling, which is not visible from the report alone.

**Concrete discriminator, for whoever fixes this**: any reported
`hf_band_limit_hz` landing within about one grid band (~586 Hz at 20 kHz)
of the derived truncation ceiling (≈20774 Hz at 48 kHz, ≈19087 Hz at
44.1 kHz, §3.5) is a truncation artifact until proven otherwise — a real
filter has no reason to land exactly at the detector's own structural
limit.

**What to do instead** (architecture.md must pin down one of these before
implementation, not leave it to the developer):
1. Truncated-window candidates must still satisfy the **full interior
   drop** (8 dB over the 1/3-octave window), not a scaled-down
   `w × 1.0 dB`; truncation should shrink the *window*, not the *bar*. Or
2. Truncated-window detections report `None` with the existing
   "not measurable near Nyquist" report text (§4 item 10) — this
   collapses risk #4's stated ambiguity into the honest, already-planned
   answer, and removes the near-vacuous partial criterion entirely. Or
3. Truncated-window detections that do pass are carried on the return
   contract as distinctly flagged (e.g. `near_nyquist_truncated: bool`)
   so they can never be read or reported as a confirmed, full-strength
   detection.
4. **Regardless of which of the above is chosen, add the missing negative
   control**: every fixture in §5.1 targets *mid-band* false positives
   (the GusGus/Leftfield failure mode). None targets a near-Nyquist false
   positive. Add at minimum: (a) a 48 kHz fixture that is full-band,
   pink/tilted (not white — see below), with ordinary top-end roll-off and
   no real filter, asserting `hf_band_limit_hz is None` (or the
   truncation-flag, per whichever fix is chosen); (b) ideally a
   noise-shaped-dither variant (energy rising toward Nyquist, which should
   also fail the monotonicity test) as a second, independent check.

**Second, smaller defect in the same area**: §5.1's new 20 kHz/48 kHz
ground-truth fixture is specified as a **brickwall** (white-noise-style,
by the naming convention shared with TC-020/021). A white-noise brickwall
has ~0 dB/octave pre-slope and trivially clears the 12 dB/octave passband
gate — it validates that the detector can find a cliff when nothing before
it declines, which is exactly the case the mid-band fixtures already
cover. It does not exercise the passband-gate/truncation interaction
described above, which is the actually load-bearing case at this
frequency. §5.1 already specifies tilt for the 15 kHz "pink noise
brickwalled" fixture; the same treatment (tilted source, then brickwalled)
is needed for the 20 kHz/48 kHz fixture, not a bare brickwall, or this
fixture will pass regardless of how item 1–3 above is resolved and give
false confidence.

---

### 2. [ADVISORY, confirmed sound] DEF-201 core mechanism — mid-band false-positive closure

The two-stage cliff detector's core design (log-frequency grid, §3.2;
24 dB/octave sustained-slope test with monotonicity tolerance, §3.3;
tilt-compensated local-slope passband gate at 12 dB/octave, §3.4) directly
and correctly closes the failure mode that shipped twice. The 12 dB/octave
gate is 2× DOMAIN.md §2's stated ~6 dB/octave ceiling for "heavily
filtered" ordinary material — a defensible margin, not an arbitrary
number. The `f_min = hf_cliff_search_min_hz / 2` derivation (§3.4) is
worked through explicitly and correctly guarantees `i − 24 ≥ 0` for every
candidate at or above the search floor, so the passband check has no skip
branch across the exact 3–8 kHz region where GusGus's 1979 Hz and
Leftfield's 8170 Hz false positives occurred — this is the right fix,
applied exactly where it needed to be applied, and it is shown, not
asserted. On Leftfield specifically: since a genuine mid-band wall does
not exist on that track, the corrected detector should now report either
a plausible near-20 kHz value or `None` (both are compliant outcomes under
AC2), not a mid-band number — the design supports this, subject to
finding #1 above being resolved so a near-20 kHz report, if it occurs, is
trustworthy rather than a truncation artifact.

### 3. [ADVISORY] Near-Nyquist `None` ambiguity (risk #4) — honestly disclosed, not hidden, but tied to finding #1

The architecture is explicit, in both §3.5 and the planned report text
(§4 item 10), that `None` near the truncation ceiling conflates "confirmed
no cliff" with "not measurable in the remaining bandwidth" — this is
disclosed to the report reader, not silently collapsed into a single
misleading state. That is the right way to handle an unavoidable
ambiguity given ARCHITECTURE.md §3.2's single-nullable-state contract,
which this story correctly does not attempt to change (changing the
binding return contract is out of this story's scope). This finding is
subsumed by finding #1: if truncated detections are made to report `None`
(option 2 above), this ambiguity becomes the *only* thing near-Nyquist
`None` means, which is a strict improvement and worth adopting together
with the fix to finding #1.

### 4. [ADVISORY] `hf_band_limit_confidence` None-branch semantics (risk #7) — fully specified, not open

§3.7 defines both branches of `_compute_confidence` explicitly, including
the found-`None`-and-corroborated-by-segments case (agreement on absence
counts as confidence). This is the right call — DOMAIN.md's own point that
generative material "may drift within one file" means disagreement near a
`None` boundary is a real, reportable signal, not an implementation gap.
No further Gate 1 action needed; this was correctly not left to be
invented ad hoc at implementation time, per requirements.md's Open
Question 1.

### 5. [ADVISORY] Judgment-call constants (risk #2)

`hf_cliff_floor_min_fraction` (0.8), `hf_cliff_floor_noise_margin_db`
(3.0), `hf_cliff_log_band_octave_fraction` (1/24), `hf_cliff_search_min_hz`
(3000.0), `hf_cliff_confidence_stable_floor` (0.6) are reasonable starting
points for real programme material and are correctly flagged as judgment
calls rather than asserted as derived, consistent with this codebase's own
precedent (`analysis/sanity.py`'s seven-band thresholds). No Gate 1 action
required beyond what §5.3 already plans: confirm against the real
five-track set at Gate 2, and treat any surprising result as grounds to
revisit the constant, not to declare the method wrong.

### 6. [ADVISORY] Mono-sum derivation and comparator (DEF-203) — sound, matches DOMAIN.md §3, and correctly rejects the v3 entry

The derivation in §2.1 (`Var(M) = (σ_L² + σ_R² + 2ρσ_Lσ_R)/4`, compared to
channel-mean power `P_mean = (σ_L² + σ_R²)/2`) is algebraically correct
and reduces exactly to DOMAIN.md's three stated points at equal channel
power (ρ=1 → 0 dB, ρ=0 → −3.0103 dB, ρ=−1 → −∞), while additionally
generalising correctly to the unequal-power case real material actually
presents — this is stronger than what DOMAIN.md's own worked example
requires, not merely equivalent to it. Computing `channel_mean_lufs` from
each channel's own independent BS.1770-gated measurement, in the linear
power domain, rather than compositing a synthetic "mean signal," is the
correct method — it keeps the comparison in K-weighted, gated terms
(consistent with CLAUDE.md's "LUFS not RMS" discipline) rather than
silently substituting a raw-power proxy. The one-sided `< −4.5 dB` trigger
correctly leaves the −3.0 to −4.5 dB band unflagged, as required. The v3
entry's −6.0206 dB / channel-summed comparator is correctly and explicitly
rejected, with the reason shown (different comparator, not the same
question with a different answer) rather than merely asserted — this
satisfies AC7's explicit reconciliation requirement.

**One number worth flagging explicitly so it is not misread at Gate 2**:
the task framing that reached this review cites "the five references
measured −3.47 to −4.03 dB" as the band that must remain unflagged. Those
are the **old, superseded-comparator** figures (requirements.md states
this explicitly and instructs that they must not be carried forward as
the expected post-fix range). Under the corrected comparator, values are
expected to shift by approximately **+3.01 dB**, landing near **−0.46 to
−1.02 dB** — well clear of −4.5 dB, but not in the old −3.0…−4.5 dB
window, and that is expected, not a regression. A useful, cheap
internal-consistency check for Gate 2 that the architecture does not
currently specify (§5.2 only checks per-band/broadband agreement on a
synthetic ρ=0 fixture): back-solve `ρ` from each reference's corrected
`mono_sum_level_change_db` via `10·log10((1+kρ)/2)` and confirm it falls
in DOMAIN.md §3's stated 0.5–0.9 correlation range for commercial
electronic material (the −0.46 to −1.02 dB figures above imply ρ ≈
0.78–0.90, comfortably inside). Recommend this be added as a Gate 2 check,
not a Gate 1 blocker — it needs the real corrected numbers to run.

### 7. [ADVISORY] Unhandled `NaN` case: both channels exact digital silence

§2.2's hardening explicitly guards `_lufs_to_linear` against `NaN` input
and explicitly verifies `-inf` propagates correctly for the ρ=−1
(full-cancellation) case. It does not address the case where **both**
channels are exact digital silence: `left_lufs = right_lufs = −inf` →
`channel_mean_lufs = −inf` (via `_linear_to_lufs(0.0)`), `mono_lufs =
−inf`, and `mono_lufs − channel_mean_lufs` is `−inf − (−inf)`, which is
`NaN` in IEEE arithmetic, not `−inf`. `NaN < −4.5` evaluates `False` in
Python, so `mono_sum_excess_cancellation` would silently be `False` on a
completely silent file rather than flagging or explicitly excluding it.
This is an edge case (a genuinely silent stereo file), not a defect that
would surface on real programme material, but it is a gap in otherwise
careful `NaN`/`-inf` handling and should be closed with one explicit
branch (e.g. both-channels-silent → report `mono_sum_level_change_db =
0.0` or a distinct sentinel, not a `NaN`-derived `False`) before
implementation, since it is cheap to specify now and easy to miss later.

### 8. [ADVISORY] Remaining open risks (§6 items 3, 8, 9, 10)

`hf_cliff_search_min_hz` as a search floor rather than a plausibility
floor (risk #3), the field-ownership deferrals into `ReferenceMeasurements`
rather than `Measurements` (risks #8, #2.4/#3.9), and the
`plausibility_warnings`/`sanity_warnings` naming gap (risk #9) are all
correctly scoped as out of this story's contract (analysis-only, not a
`Measurements` restructure) and correctly flagged for STORY-005 rather
than silently decided or silently left inconsistent. No Gate 1 objection.
The missing `defects.md` append (risk #10) is a process/tooling
limitation, not a methods issue, and is outside this review's remit.

---

## Summary for the developer

Do not start implementation on §3.3/§3.5's near-Nyquist truncation as
currently specified — finding #1 is a Blocker and must be resolved in
architecture.md first (pick one of the three mechanisms listed, and add
the missing negative-control fixture regardless of which is chosen).
Everything else — the mid-band cliff-detection redesign, the mono-sum
re-derivation, the confidence semantics, and the flagged judgment-call
constants — is sound and may proceed once finding #1 is closed. Findings
#6 and #7 are cheap, concrete additions the architect should fold in at
the same time rather than treat as separate follow-up passes.
