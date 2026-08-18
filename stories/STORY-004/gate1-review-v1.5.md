# STORY-004 — Gate 1 Review v1.5 (Method Review)

Reviewer: mastering-engineer. Reviewing `architecture.md` at v1.5 against
`requirements.md`, `story.md`, `CLAUDE.md`, `DOMAIN.md`, `ARCHITECTURE.md`,
and `HANDOFF.md`. The original Gate 1 review (`gate1-review.md`) applied to
v1.2/v1.3; this review applies to v1.5 only.

---

## Verdict: PASS-WITH-BLOCKERS

One Blocker — §3.5 Step 1 repurposes a rejection-only constant as a positive
detection trigger, without re-deriving it for that role. On real programme
material with steep but filterless air-band roll-off — a case §3.4 itself
concedes is plausible — the tracker freezes early, anchors `passband_level`
at a lower frequency than the genuine wall, and reports a wrong number with
no fallback to `None`. Same structural error as DEF-201, different frequency
range.

Everything else described below is confirmed sound. The original Gate 1
Blocker (fixed 8.0 dB bar) is not regressed. The tie-free/saturation
argument is correct. The terminal freeze is correctly load-bearing. The
masking-fix from v1.4 is preserved. Implementation must not begin until
the Blocker below is closed in architecture.md.

---

## Findings

### 1. [BLOCKER] 12 dB/oct is used as a detection trigger; its derivation supports only a rejection criterion — fails unsafe on air-band roll-off

**Where**: §3.5 Step 1 (passband tracker freeze), interacting with §3.4
(where the constant's derivation lives) and §6 risk 13.

**What is proposed**: `hf_cliff_passband_max_slope_db_per_octave` (12.0
dB/oct) was derived in §3.4 as a **rejection bound** for gate candidates.
Derivation: DOMAIN.md's ceiling for ordinary programme material is ~6
dB/oct; doubling gives a conservative margin; this rejects candidates
where the pre-slope is already indistinguishable from a cliff. When the gate
rejects a candidate, the outcome is `None` — honest, compliant under AC2,
safe.

§3.5 Step 1 reuses this same constant as a **positive detection trigger**:
the tracker freezes — permanently — at the first band where the
trailing-octave slope exceeds 12 dB/oct, and the frozen `passband_level`
sets `L`, which sets `j*`, which is the reported frequency. When this fires
incorrectly, the outcome is a wrong number, not `None`. The constant's
derivation does not address this second use. "No new config field is
introduced" is presented in §3.3 as a virtue — it is the tell: reusing a
constant outside the scope of its derivation is the H4 asserted-not-derived
pattern.

**Why it fails on real programme material, concretely**: §3.4 itself, horn
(a), states explicitly that "real CD-sourced material's local slope across
the 10–20 kHz octave immediately below a genuine 20 kHz wall exceeds
`hf_cliff_passband_max_slope_db_per_octave` (12 dB/octave) — plausible per
DOMAIN.md §3's own observation that the air band can sit 10–25 dB below mid
by the top octave." Under v1.3/v1.4 that concession was safe: the gate
rejected the candidate → `None`. Under v1.5, the same spectrum causes the
tracker to freeze at the onset of the air-band roll-off, not at the genuine
wall. `passband_level` anchors where the tilt first steepens beyond 12
dB/oct; `L` drops with it; `j*` finds the first suffix-max crossing below
that depressed `L`, somewhere in the middle of the declining tilt. On a
track declining at 12–15 dB/oct across the top octave before a genuine 20
kHz wall, this produces a reported cutoff in the range of 10–15 kHz —
plausible-looking, wrong, and reached by ordinary programme content with no
actual wall. This is the same structural failure as DEF-201 (spectral tilt
crossing a threshold) shifted to the top end of the spectrum.

**§6 risk 13 does not protect against this**. Risk 13 scopes the trigger as
"an unusual but not impossible resonant/absorption dip." Air-band roll-off
is neither unusual nor a dip — it is the expected spectral shape of almost
every commercial master above 10 kHz, documented in DOMAIN.md §3 itself.
The protection risk 13 claims — "a notch that recovers cannot be reported"
— is real but orthogonal: air-band roll-off does not recover, it declines
monotonically to the floor, so `suffix_max` never rises back above the
depressed `L`. The never-recovers guard filters non-sustained dips; it does
not filter sustained ordinary decline.

**Step 0 does not rescue this either**. The gate qualifies a window at the
genuine wall (e.g., 20 kHz) on the 8 dB / 8-band drop criterion. The
tracker freezes on the 12 dB/oct trailing-octave criterion, which can fire
earlier, at a different index. The two tests are independent; nothing
structurally ties the freeze point to the gate's qualified window. §6 risk
14 exists precisely because they can disagree. A gate-yes / early-freeze
combination routes through the `candidates.min() >= freeze_index` check
in §3.5 Step 2 — but if the tracker froze early at, say, 8 kHz, then
`freeze_index` is in the 8 kHz region, `j*` is somewhere above it based on
the depressed `L`, and `candidates.min() >= freeze_index` is satisfied.
The `None` + warning branch is never reached; a wrong number is returned
with normal confidence.

**Side note on `candidates.min() < freeze_index`**: for any `j < freeze_index`,
the tracker was still updating `passband_level = levels_db[j]` at that band.
`suffix_max[j] >= levels_db[j] = passband_level > L` (since `L = passband_level
- 8`). So `suffix_max[j] > L` for every `j < freeze_index`, meaning no such
`j` satisfies `suffix_max[j] <= L`. The `candidates.min() < freeze_index`
condition is provably unreachable. The guard and the `candidates >= freeze_index`
filter are dead code — harmless, but they do not protect against the early-freeze
failure above, contrary to how §3.5 reads.

**The Leftfield worked derivation is not derived**. §3.5 traces j=89
continuing (levels[65]→levels[89], the 10–20 kHz octave "still an ordinary
tilt") and j=90 freezing (the genuine wall). This is an empirical claim that
Leftfield's 10–20 kHz trailing-octave slope stays ≤12 dB/oct — the exact
case §3.4 horn-(a) says may be false on CD material. §5.3 itself concedes
"the per-band `levels_db` array was never dumped in the v1.4 pass, only
candidate-window endpoint tuples" — so the trace was constructed without the
data it purports to derive from. It is a prediction, not evidence that Step 1
handles the air-band case correctly.

**What architecture.md must specify before implementation (pick one):**

1. **Freeze on the cliff criterion, not the passband ceiling.** Trigger the
   freeze using the same 8 dB / (≤ 1/3-octave window) test the gate already
   derives — or equivalently, on the ≥24 dB/oct slope the architecture
   already justifies for the cliff — so the trigger's burden of proof matches
   the claim being asserted. Keep 12 dB/oct where its derivation applies:
   as a gate rejection bound.

2. **Or: tie the freeze to the gate.** Require `freeze_index` to fall at
   or within a small band-count of a gate-qualified window's own start index
   `i`. If the tracker's first steep-slope band is not near any gate-qualified
   `i`, treat this as a gate/localization disagreement → `None` + warning.
   This makes the early-freeze case produce a `None` (risk 14's outcome)
   instead of a wrong number.

**Regardless of which is chosen, the following negative-control fixture is
required and is missing from §5.1**: tilted noise at 48 kHz, with a steep
but filterless top-octave slope (12–15 dB/oct from roughly 8 kHz upward,
matching §3.4's conceded real-material case), with a genuine brickwall at
20 kHz — assert `hf_band_limit_hz ≈ 20000 ± 879.1 Hz`, not a mid-band
value. None of the eleven fixtures in §5.1 constructs this. The existing
tilt-then-brickwall @20 kHz fixture uses −6 dB/oct pre-tilt, which trivially
stays under 12 dB/oct and cannot expose the early-freeze failure. This
fixture must be specified in architecture.md (what is "steep but filterless"
defined as, at the grid resolution used, so the test-case-writer can
construct it from first principles per H2) before implementation.

---

### 2. [ADVISORY] §5.3 spread check: Black Flute and GusGus identical at 0.1 Hz under v1.4

The v1.4 table records Black Flute and GusGus both at 16727.3 Hz — two
structurally different records agreeing to 0.1 Hz on a supposedly varying
property. The architecture declares the table stale and moves on. This is
the correct action (the table must be re-measured), but §5.3 should add
an explicit H5 check: if any two tracks land on the same grid band again
under v1.5, that coincidence must be explained before the results are
accepted for Gate 2. Identical values on distinct tracks are H5's spread
check and should be named as a required Gate 2 scrutiny item in §5.3, not
assumed resolved by having a new measurement mechanism.

This is not a blocker — it is a process requirement for Gate 2, and the
architecture's instruction to re-measure is correct. The concern is that
§5.3 does not currently invoke the spread check by name, and Gate 2 should
not need to rediscover it independently.

---

### 3. [ADVISORY] §6 risk 13: reclassify from "unusual" to "expected on real commercial material"

Risk 13 names notch-anchoring and scopes it to "unusual but not impossible
resonant/absorption dips." This understates the likely incidence: the
triggering condition (trailing-octave slope > 12 dB/oct) is conceded by
§3.4 to be plausible on ordinary air-band roll-off of real CD-sourced
material. The architecture should say so, rather than implying the risk is
limited to acoustic anomalies. Once the Blocker above is resolved (by
raising the freeze threshold or tying the freeze to the gate), the
residual version of this risk should be re-scoped accordingly — it may
become narrower or disappear entirely depending on the resolution chosen.

---

### 4. [ADVISORY] Above-Nyquist bands in suffix_max at 44.1 kHz

At 44.1 kHz, the grid produces n_bands=94 with `edges[94] ≈ 22651 Hz > Nyquist`.
The Nyquist clamp (`valid = centers <= nyquist_hz`) correctly excludes
band 93 (center ≈ 22326 Hz) from the candidate set. However, `suffix_max`
is computed over the full `levels_db` array (all 94 bands), so
`suffix_max[j]` for any valid j includes `levels_db[93]` in its trailing
max. If `levels_db[93]` is above `L` — because the last Welch bin at 22050
Hz carries some energy — no valid j can satisfy `suffix_max[j] <= L`,
routing to the gate/localization disagreement path (`None` + warning) even
when a genuine wall exists below 22050 Hz.

In practice this is benign: for 48 kHz tracks (the actual reference set)
there are no above-Nyquist bands; for Suno exports at 44.1 kHz, band limits
at 13–16 kHz mean energy at 22007–22050 Hz is at floor level, well below L.
The failure mode degrades to `None` + warning rather than a wrong number.
Recommend confirming at implementation time that `levels_db[93]` evaluates
near `_MIN_POWER` for expected 44.1 kHz inputs, and document that the
suffix_max is intentionally full-array. This is not a required architecture
change; it is an implementation-time verification item.

---

## Confirmed sound — stated plainly

**Original Gate 1 Blocker (v1.3 fix) is not regressed.** §3.3 specifies
`required_drop_db = hf_cliff_required_drop_db = 8.0 dB` independent of
window size `w`. §3.5 Step 2 uses `L = passband_level −
config.hf_cliff_required_drop_db` — the same 8.0 dB constant, not
`hf_cliff_floor_noise_margin_db` added to it, and not scaled. This is
confirmed preserved.

**The tie-free argument is correct.** `suffix_max[j]` is monotone
non-increasing (right-to-left running max). Therefore `{j : suffix_max[j]
<= L}` is an up-set: if j qualifies, so does every j' > j. An up-set has
exactly one minimum or is empty. No candidate list, no scoring function,
no argmax — nothing for two entries to tie on. Saturation at `_MIN_POWER`
produces a constant tail; a constant sequence still has a unique first
crossing below L. The v1.4 argmax mechanism (near-tied total_drop over a
flat floor, winner decided by Welch-estimator noise) is structurally absent
from this formulation and cannot recur.

**The terminal freeze is correctly load-bearing.** Inside a genuine floor,
the trailing-octave slope returns to ~0 dB/oct, which would re-satisfy the
≤12 test if the loop were allowed to resume. A resumable tracker would allow
`passband_level` to slide into the floor, pulling L and j* down with it —
reproducing in a different form exactly the "reference kept sliding deeper"
failure v1.4's 22328.2 Hz Leftfield result demonstrated. Freezing once,
permanently, is the correct design; the explanation in §3.5 is sound.

**v1.4's masking-fix is preserved under v1.5.** The short non-sustained
decline in the Leftfield masking case (Leftfield's ~9.29 dB feature
concentrated in roughly 1/3 octave) is diluted by the 2/3 octave of
ordinary content in the same trailing octave, keeping the octave-averaged
slope under 12 dB/oct — the tracker rides through it and `passband_level`
keeps updating past it. This is a structural property of the 1-octave
lookback, not fixture-specific. The property is correctly explained in §3.5.

**The §3.3 existence gate is unchanged.** Step 0 of §3.5 runs the gate and
returns `None` immediately on an empty qualifying set. All three
negative-control fixtures (tilt-only, pink noise, tilt+non-stationarity)
produce empty qualifying sets by the gate's own unchanged arithmetic —
confirmed in the v1.4 pass and unaffected a second time since the gate is
untouched. No regression in negative controls.

**The new inverse-of-v1.4 fixture requirement (§5.1) is correct.**
Requiring a fixture with an earlier genuine wall followed by a deeper
secondary feature inside the floor — asserting the earlier wall wins —
converts the prose retirement of risk 12 into an empirical test. Under
v1.5's terminal freeze, the tracker freezes at the first sustained
trailing-octave break and never resumes; a deeper feature inside the
established floor cannot un-freeze it. The fixture makes this testable.
v1.4 correctly could not specify this fixture; requiring it now is the
right call.

**DEF-203 (mono-sum, §2) is sound and unaffected by v1.4/v1.5.** The
derivation is correct, the both-channels-silent guard is correctly placed
before the subtraction, and the advisory from the original Gate 1 review
(NaN gap on two-channel silence) is closed properly. No new concerns.

---

## Summary for architect

The Blocker in §3.5 Step 1 must be resolved — specifically: derive (or
cite an existing derivation for) what slope threshold is appropriate as a
**detection trigger**, separately from the 12 dB/oct **rejection bound**
that §3.4 already derives. Then add the missing fixture: steep-but-filterless
air-band roll-off at 48 kHz, genuine brickwall at 20 kHz, asserting the 20
kHz value not a mid-band value. The v1.3 fix is intact, the tie-free
reformulation is correct, the masking-fix survives, and everything else may
proceed once the Blocker is closed.
