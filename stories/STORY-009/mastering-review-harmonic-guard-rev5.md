# STORY-009 — Mastering-Engineer Review: §6b Harmonic Guard Rev 5

Reviewed: `stories/STORY-009/architecture.md §6b` (rev 4/5),
`stories/STORY-009/mastering-review-harmonic-guard.md` (prior review),
`artifacts/Sunday Club_mastered_report.json` (live flag data, verified).
Material context: Sunday Club (club-oriented electronic, 48 kHz, 254.7 s,
439 STATIONARY_WHISTLE flags forwarded to repair in the Gate 2 test run).

---

## 1. Sibling Confirmation — K-inflation Resolution — PASS with required specification addition

**Physical soundness of the discriminator.**

The prior review (B.1 FAIL) found that the harmonic ratio test alone, applied to K candidate
peaks, yields a per-flag suppression probability approaching 1 at K ≥ 20 for any input
frequency — genuine whistle or not. The sibling confirmation added in rev 4 resolves this by
requiring, before suppressing, that at least one spectral peak exists within `delta·f0` Hz of
`f_flagged ± f0`. This requirement is assessed below in both the true-positive and
false-positive scenarios.

**Case A — genuine musical harmonic (flag IS the Nth harmonic of a real instrument).**

For a sustained pad or synth playing a note with fundamental f0: the harmonic series produces
energy at 1·f0, 2·f0, ..., N·f0, (N+1)·f0, .... If `f_flagged = N·f0`, then
`f_flagged + f0 = (N+1)·f0` and `f_flagged - f0 = (N-1)·f0` are adjacent harmonics in the
series. For instruments with a full harmonic series (sawtooth oscillators, most acoustic
instruments, many subtractive patches), these adjacent harmonics are prominently present and
will clear the 6 dB local-prominence gate used for `all_peak_freqs`. The sibling check will
succeed reliably for this case, provided the exception below is excluded.

**Case B — coincidental noise peak (f0 happens to be near a rational multiple of f_flagged
by chance).**

A noise or spectral artefact at frequency f0 has no physical relationship to f_flagged. There
is no mechanism by which a random spectral peak at f0 produces correlated energy at
`f_flagged + f0` or `f_flagged - f0` — those frequencies are not harmonically related to f0
unless f_flagged is an integer multiple of f0 in the spectral neighbourhood sense that the
sibling check requires. The sibling check will fail for coincidental matches as intended,
even at K ≥ 20.

**Verdict on K-inflation: PASS**, provided the self-confirming sibling guard below is added.

The B.1 K-inflation defect is resolved by the sibling confirmation mechanism. The
acceptance check in §6b.6 item 1 (null control suppression-rate comparison) remains required
as the empirical confirmation on real programme material.

**Required specification addition — self-confirming sibling guard.**

The current Step 5 sibling loop contains a hole: at `n_nearest = 2`, the downward sibling
target is `f_flagged - f0 = 2·f0 - f0 = f0` — exactly the candidate fundamental itself.
Since f0 was found by `find_peaks` and is present in `all_peak_freqs`, the sibling check
`np.any(np.abs(all_peak_freqs - sibling_f) <= delta·f0)` trivially succeeds without
providing any independent spectral evidence. The candidate confirms itself.

This is the same m=1 degeneracy that makes Option 2 ("any m·f0, m ≠ n_nearest") unsafe (see
§2b below), now appearing inside the ±f0 check at n_nearest=2. It recurs under the proposed
±2·f0 widening at n_nearest=3 (`f_flagged - 2·f0 = 3·f0 - 2·f0 = f0`). The general
condition: sibling_f = (n_nearest - k)·f0 self-confirms when n_nearest - k = 1, i.e., k =
n_nearest - 1.

**Fix: add one guard inside the sibling loop before the `np.any` call:**

```python
# Skip any sibling_f that would match f0 itself — provides no independent evidence.
if abs(sibling_f - f0) <= _HARMONIC_GUARD_DELTA * f0:
    continue
```

With this guard:
- n_nearest=2, ±f0: downward sibling (f0) is skipped; upward sibling (3·f0) is checked for
  independent confirmation. For a full-harmonic-series instrument, 3·f0 is present and
  confirms. For a coincidental noise peak at f0, 3·f0 is absent. Discrimination restored.
- n_nearest=3, ±2·f0 (proposed widening): downward ±2 sibling (f0) is skipped; upward ±2
  sibling (5·f0) is checked. For a square-wave (odd-harmonic) instrument, 5·f0 is present
  and confirms. Discrimination restored.

This guard requires no new parameters and does not change the algorithm's structure. The
architecture must add it to §6b.2 Step 5 before implementation proceeds.

---

## 2. Odd-Harmonic Risk — Mitigation Selected: ±2·f0 Widening

### 2a. Timbre class: cannot be confirmed absent

The Sunday Club material is club-oriented electronic music with dense pad and synth content.
The flag data in `Sunday Club_mastered_report.json` (see Section 3) shows flags at frequencies
consistent with musical pitches: 130, 166, 196, 246, 262, 290, 330, 408, 440, 494, 522, 590,
824, 988 Hz and others. This is consistent with synthesiser pad content, and the variety of
pitch classes suggests polyphonic synthesis from one or more synth layers.

The architecture correctly identifies square-wave oscillators and pulse pads as common in
this genre. No analysis available to this review can distinguish a sawtooth from a square
oscillator source from the flag frequency data alone: both produce a tonal peak at the
fundamental. A confident "timbre class absent" finding would require stem-level listening or
spectral analysis of isolated synth layers, which is outside the scope of this document.

**Conclusion: the odd-harmonic risk cannot be dismissed as absent. A mitigation is required.**

### 2b. Assessment of the two candidate mitigations

**Option 2 — Generalise to any m·f0, m ≠ n_nearest (not recommended as specified).**

This option has a degenerate case that makes it unsafe: for any candidate f0 found by
`find_peaks`, the candidate peak at frequency f0 is by definition present in `all_peak_freqs`
(it passed the local-prominence gate that produced the candidate set). Checking for a peak at
m·f0 with m = 1 will always succeed for any candidate, because f0 is its own spectral peak.
The `m ≠ n_nearest` exclusion does not exclude m = 1 when n_nearest > 1 (which it always is,
since the flag frequency exceeds f0). This degenerates to: "suppress if any candidate f0 is
found," which is equivalent to the pre-sibling-confirmation state and reintroduces the
K-inflation defect the sibling check was designed to fix.

This flaw is fixable by adding a further exclusion `m ≠ 1` alongside `m ≠ n_nearest`. With
that correction, "any m·f0, m ≠ 1, m ≠ n_nearest" is a sound formulation. However, it
requires iterating m from 2 to N_MAX, skipping n_nearest — up to N_MAX-2 comparisons per
candidate — whereas the ±2·f0 option resolves the specific odd-harmonic failure mode with
four comparison targets per candidate and no loop. Given that the documented failure mode
is odd-harmonic timbres specifically, the more targeted fix is preferred.

**Option 1 — Widen to ±2·f0 (selected).**

For a flag at `f_flagged = n·f0` on a square-wave or pulse-pad timbre: n is odd. The sibling
targets under ±2·f0 are `(n+2)·f0` and `(n-2)·f0`. Since `n ± 2` preserves parity (adding
or subtracting 2 from an odd number yields another odd number), both siblings are odd
multiples of f0 — structurally present in any square or pulse-wave harmonic series. The
widened check succeeds where the ±f0 check fails.

Boundary cases under the self-confirming guard added in §1:

- n_nearest = 3: downward ±2·f0 sibling `= 3·f0 - 2·f0 = f0`. Self-confirming guard fires
  (|f0 - f0| = 0 ≤ delta·f0); sibling is skipped. Upward ±2·f0 sibling `= 5·f0`: present for
  any odd-harmonic instrument. Confirmed. Guard does not block the valid evidence path.

- n_nearest = 1: this case can occur (f_flagged/f0 ≈ 1.0x with |r-1| ≤ delta). Downward
  ±f0 sibling `≈ 0 Hz` or negative: filtered by existing `sibling_f ≤ 0` guard. Upward ±f0
  sibling `≈ 2·f0`. The self-confirming guard: |2·f0 - f0| = f0 >> delta·f0, so it does not
  fire; the upward sibling is a valid independent check. This case is uncommon in practice
  (requires a candidate peak very close to the flagged frequency from below).

- Upward sibling at n_nearest = N_MAX: `(N_MAX + 2)·f0` may exceed Nyquist or the analysis
  range. The existing `sibling_f >= sample_rate / 2.0` guard handles this correctly.

The ±2·f0 widening covers:
- Full-harmonic-series instruments: adjacent harmonics at n±1 already confirmed by ±f0 check.
- Odd-harmonic-only instruments (square wave, 50% pulse): harmonics at n±2 confirmed by the
  widening.
- Mixed-harmonic instruments (asymmetric pulse, many FM patches): at least one of the four
  sibling targets will land on a present harmonic, provided three or more harmonics of f0 are
  above the prominence floor in the analysis window.

The widening does not cover an instrument with energy ONLY at every third harmonic (n, n±3, ...).
No standard synthesis waveform produces this pattern; it is not a relevant failure mode for
electronic dance music.

**Architecture revision required — §6b.2 Step 5.**

The sibling loop must be updated from two targets to four, and the self-confirming guard
added. The combined specification for the sibling inner loop is:

```python
for sibling_f in [f_flagged + f0, f_flagged - f0,
                  f_flagged + 2 * f0, f_flagged - 2 * f0]:
    if sibling_f <= 0.0 or sibling_f >= sample_rate / 2.0:
        continue   # out of Nyquist range
    if abs(sibling_f - f0) <= _HARMONIC_GUARD_DELTA * f0:
        continue   # would match the candidate f0 itself — no independent evidence
    if np.any(np.abs(all_peak_freqs - sibling_f) <= _HARMONIC_GUARD_DELTA * f0):
        sibling_confirmed = True
        break
```

This is the complete Step 5 sibling loop specification. No other change to the algorithm is
required. Implementation must not proceed against the current ±f0-only, guard-free specification.

---

## 3. Flag Frequency Distribution

**Source data and JSON structure verification.**

`artifacts/Sunday Club_mastered_report.json` contains three substantive sections:

1. Pre-master artifact detection flags (deeply nested structure with
   `"artifact_type": "STATIONARY_WHISTLE"`, `"details": {"frequency_hz": ...}`). Confirmed
   STATIONARY_WHISTLE type at line 5951 (590.0 Hz flag, timestamp 5.5–7.25 s, confidence 1.0).

2. Post-master artifact detection flags (same nested structure, different timestamps,
   overlapping frequency content). Confirmed by reading lines 17040–17100, which show
   identical flag format with `"artifact_type": "STATIONARY_WHISTLE"`.

3. Repair action log (flat structure, lines ≈18180 onward): `"frequency_hz"` at top level,
   alongside `"confidence_score"`, `"prominence_db"`, `"timestamp_start_s"`,
   `"timestamp_end_s"`, `"peak_delta_db"`, `"rms_delta_db"`. The presence of `peak_delta_db`
   and `rms_delta_db` fields confirms these are the frequencies that were actually forwarded
   to `suno_dsp.repair_whistles` and notched in the Gate 2 test run. This section is the
   source of the "439 flags" figure cited in the architecture.

**Sub-2kHz count from the repair action log.**

Searching the repair action log section for `frequency_hz` values below 2000 Hz:

Sub-1000 Hz entries (19 total): 130 Hz (×2), 166 Hz (×2), 190 Hz, 196 Hz (×3), 246 Hz (×2),
262 Hz, 290 Hz, 330 Hz, 408 Hz, 494 Hz, 522 Hz, 590 Hz, 824 Hz, 988 Hz.

1000–1999 Hz entries (2 total): 1182 Hz, 1600 Hz.

**Total sub-2kHz flags in repair action log: 21 of 439, approximately 4.8%.**

This is well below the 10% materiality threshold stated in the prior review (B.3), at which
the `f_min_flag = 2000 Hz` assumption and the derived `l_analysis` would need revision.

**Character of sub-2kHz flags.**

The sub-2kHz frequencies align closely with Western equal-temperament pitch classes:
130 Hz (≈ C3), 166 Hz (≈ E3), 190 Hz (≈ F#3), 196 Hz (≈ G3), 246 Hz (≈ B3), 262 Hz (≈ C4),
290 Hz (≈ D4), 330 Hz (≈ E4), 408 Hz (≈ Ab4), 440 Hz (≈ A4), 494 Hz (≈ B4), 522 Hz (≈ C5),
590 Hz (≈ D5), 824 Hz (≈ Ab5), 988 Hz (≈ B5). These are musical notes. The fact that they
appeared in the repair action log — and therefore received a notch — is directly attributable
to the absence of the harmonic guard in the Gate 2 test run. The peak_delta_db values in the
repair log (e.g., −3.03 dB for the 590 Hz flag) confirm the notch operated on musical content.

**Full frequency range in repair log**: approximately 130 Hz (lowest) to 22400 Hz (highest).

**Distribution summary**:
- 14–22 kHz: the majority of the 439 flags fall in this band. Flags at 20000–22400 Hz
  (83–93% of Nyquist at 48 kHz) are almost certainly neural codec quantisation artefacts,
  not musical content. This is the dominant category.
- 4–10 kHz: a meaningful cluster (estimated 80–100 flags) in this range. Mix of probable
  pad harmonics in the lower part and potential encoder artefacts in the upper part.
- Below 2 kHz: 21 flags (≈5%), confirmed musical tonal content.

**Implication for `f_min_flag = 2000 Hz` assumption.**

The 4.8% sub-2kHz fraction is below the revision threshold. The `l_analysis` derivation
based on `f_min_flag = 2000 Hz` (yielding 8192 samples at 44.1 kHz / 48 kHz) is valid for
this material. The harmonic guard will lack adequate resolution for the ~21 sub-2kHz flags
(their relevant musical fundamentals, at 130–990 Hz, may fall below f0_min = 200 Hz or at
the edge of the guard's resolution). However, these flags are unambiguously musical tones;
they should be suppressed by the harmonic guard because they have strong fundamentals and
harmonic series. The risk from inadequate resolution at these very low frequencies is that
the guard might miss the fundamental rather than incorrectly pass the flag — i.e., the guard
might fail to protect them (miss suppression), not mis-suppress a genuine whistle. This is
a known gap, documented in the architecture as the "N > 10" and "f0_min" open risks, and is
acceptable given the 5% scale.

---

## Summary Verdict

**Proceed to implementation**, subject to one architecture revision (§6b.2 Step 5 update)
before the developer begins.

**Required before implementation — §6b.2 Step 5 revision.**

The architecture must update §6b.2 Step 5 to specify:

1. **±2·f0 widening**: extend the sibling target list from `[f_flagged + f0, f_flagged - f0]`
   to `[f_flagged + f0, f_flagged - f0, f_flagged + 2·f0, f_flagged - 2·f0]`.

2. **Self-confirming sibling guard**: inside the sibling loop, before the `np.any` proximity
   check, skip any `sibling_f` where `abs(sibling_f - f0) <= delta·f0`. This prevents the
   candidate fundamental from confirming itself as its own sibling at n_nearest = 2 (±f0
   path) and n_nearest = 3 (±2·f0 path).

The complete four-line inner loop specification is given in §2b above. These two changes are
confined to Step 5; no other section of §6b requires modification.

**Items fully resolved by rev 4/5 + this review:**

- §6b.2 K-inflation (B.1 from prior review): RESOLVED. Sibling confirmation is physically
  sound; self-confirming sibling guard specified above closes the remaining hole.
- §6b.6 item 0 (odd-harmonic risk): RESOLVED by selecting ±2·f0 mitigation. Architecture
  revision to §6b.2 Step 5 is the implementation prerequisite.
- §6b.6 item 3 (f_min_flag = 2000 Hz assumption): CONFIRMED by repair action log data. Sub-
  2kHz flags are 21 of 439 (4.8%), below the 10% revision threshold.

**Items open and acceptable to proceed once architecture revision is in place:**

- §6b.6 item 1 (offline acceptance check with null control): Required post-implementation
  validation before the stage may move to default-on. Acceptance criteria in §6b.6 are
  correctly specified.
- §6b.6 item 2 (6 dB prominence threshold calibration): Valid concern; calibrate using
  offline check results. Not a pre-implementation blocker.
- §6b.6 item 4 (stage remains enabled=False): Unchanged.
- §6b.2 N_MAX > 10 gap (flags rooted in sub-bass fundamentals): Acknowledged known
  limitation; not a blocker.
- §6b.2 detuned/inharmonic synthesis pass-through risk: Known limitation; not a blocker.
