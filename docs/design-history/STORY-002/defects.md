# STORY-002: Defects / architecture-routed findings

No defects.md existed for this story prior to this implementation pass.
Entries below were found and reasoned through during first implementation
(python-developer), each tagged per the standing convention: `Architectural`
entries are things this implementer could not silently resolve one way or
another without making an undocumented product/design call, so they route
back to the architect rather than being worked around quietly. None of
these blocked completing the implementation -- each has a concrete,
smallest-reasonable-call resolution taken here, stated explicitly, pending
architect review.

All three entries below have now been reviewed by the software-architect
(this pass) and resolved. Each resolution was independently verified
against the actual shipped code (`analysis/mono_sum.py`, `analysis/
reference_types.py`, `analysis/clipping.py`, `analysis/true_peak.py`,
`analysis/__init__.py::measure_all`, `reference_analysis/config.py`) before
a decision was made, not accepted on the report's word alone. Full reasoning
lives in architecture.md v2 (§4.5, §7.1, §7.2, §15 revision history); this
file records the status change and the concrete instructions for
python-developer.

---

DEF-202

Status: Open Reported by: james (report review) Triage: Architectural

Description: The mastering tool does not consume the reference measurements STORY-002 produces. The mastering report's "Reference (rel. dB)" column shows -1.50, -3.00, -4.00 — round placeholder numbers that appear nowhere in the reference set report.

Actual measured reference medians: sub -1.743, low 3.266, low_mid 0.932, high_mid -7.207, high -9.772, air -16.015.

Loudness shows the same disconnect: reference median is -8.70 LUFS; mastering config targets -14.5 to -13.5 LUFS, derived independently rather than from the reference set.

Expected behaviour: the mastering stage reads the machine-readable reference aggregate produced by STORY-002 (AC9) and uses those values as its correction targets. Hardcoded spectral targets should not exist in the mastering config at all.

Note on loudness specifically: this is NOT simply "use -8.70." Streaming normalisation means mastering to the reference loudness would be counterproductive. The loudness target should remain streaming-appropriate; it is the spectral and dynamics targets that must be reference-derived. Architect to define which measured metrics become targets directly and which are informational.

Why architectural: this is a missing pipeline connection between two stages, not a coding error.


---

## DEF-205 — Gate false positive on real programme material (Chemical Brothers segment 1)

**Status**: Open  
**Triage**: Architectural  
**Raised by**: mastering-engineer Gate 2 review (2026-08-08), `stories/STORY-004/gate2-review-v1.5a.md`

On The_Chemical_Brothers_-_Live_Again_ft_Halo_Maud.wav, segment 1 (0–50s) reports
`hf_band_limit_hz = 14066 Hz` — a false positive. The track's confirmed whole-track
wall is at 20475.1 Hz (25.79 dB margin). In segment 1, `_gate_scan` returned i_max=71
(centers≈12502 Hz) on programme content in that 50-second window; `_floor_onset_index`
correctly localized the floor onset at band 77 (14066 Hz) relative to that anchor.
The number is wrong — it is not an abstention (None), it is a positive claim that the
HF band limit is 14066 Hz in that segment.

The mechanism is gate admission of ordinary spectral decline in complex programme
material as a qualifying cliff candidate. This is architecture.md §3.4 horn-(a) on
real material: the gate at 8.0 dB / 12 dB/oct misses genuine walls in 16% of segment
calls (4/25 segments across Chemical Brothers and Wavy Gravy returned None) and
simultaneously admits false positives in others. The segment 1 false positive was masked
at the whole-track level only because it was 6409 Hz from the true value (outside the
2000 Hz agreement tolerance); a false positive within 2000 Hz of the true wall would
have inflated confidence without being caught.

**Root cause**: gate criterion (§3.3/§3.4) is not tight enough to reject ordinary
spectral decline in dynamic commercial programme material when operating on 50-second
segments. The 8.0 dB drop / 12 dB/oct slope derivation is designed for whole-track
PSD; its statistical properties degrade on shorter windows.

**Impact**: confidence/stable is correct at the whole-track level for this track
(false positive is caught by agreement test). Impact is bounded: the whole-track output
20475.1 Hz is plausible and the false-positive segment does not propagate to the
reported value. However, any use-case that reads per-segment values (not just the
whole-track summary) will see a spurious 14066 Hz on segment 1.

**Required**: Architecture revision to specify either (a) tighter gate admission
criterion for segment-level passes, (b) a per-segment gate parametrization that
differs from the whole-track one, or (c) explicit documentation that per-segment
values are not individually reliable and must not be consumed without the stability
flag and whole-track value.

---

## DEF-206
Status: Closed
Reported by: qa-automation-engineer
Linked test case: STORY-005 TC-507
Description: STORY-005 architecture.md §9.1's literal AC6 fixture design for TC-507
(digital-zero stopband between F_false and F_real, with the "fill the stopband" noise
injected only above F_real) is empirically incompatible with `_gate_scan`'s floor-coverage
test (hf_extension.py) for any candidate window near F_false. Root cause: the deep
digital-zero buffer between F_false and F_real, followed by a "recovery" back up to the
injected floor level above F_real, causes the fraction of the floor region sitting above
`floor_ref + hf_cliff_floor_noise_margin_db` to exceed the (1 - hf_cliff_floor_min_fraction)
= 20% budget for every candidate window ending inside the digital-zero buffer — confirmed
by direct construction-time measurement (`_detect_cliff` returned `None` on the segment-1
slice built per the architecture's literal recipe: P=-59.9 dB passband, digital-zero
stopband 8125-15339 Hz, A=-69.9 dB injection above 16000 Hz — coverage fails because bands
81-93 sit far above `floor_ref(-200 dB) + 3 dB`). Separately, architecture §9.1's suggested
F_real ≈ 20000 Hz leaves only ~3 1/24-octave grid bands between F_real and Nyquist at
44100 Hz — insufficient for the 8-band gate window plus floor-coverage bands required by
`hf_cliff_target_window_octaves`/`hf_cliff_min_floor_bands`, independent of the coverage
issue above.
Triage: Architectural (test-fixture/specification design issue in architecture.md §9.1 /
test-cases.md TC-507, not a product-code bug — `_gate_scan`, `_floor_onset_index`, and
`_detect_cliff` are unchanged by STORY-005 by design and behaved correctly and consistently
throughout; the fixture recipe itself does not achieve the geometry it claims to).
Fix notes: Worked around within the QA pass without requiring a code change or an
architect re-invocation: TC-507 was re-fixtured using
`brickwall_lowpass_noise_with_floor_mono` with a uniform, full-band floor for segment 0
(cutoff_hz=F_false=8000, floor_below_db=10.0) instead of the two-region
digital-zero-then-injection construction, and F_real lowered to 16000 Hz (documented
deviation, ~11 grid bands of margin to Nyquist instead of ~3). This fixture passes cleanly
and preserves the test's intent (a genuine per-segment false positive disagreeing with the
whole-track result by more than `hf_stability_tolerance_hz`, both propagating correctly to
JSON and markdown). Recommend architecture.md §9.1 and test-cases.md TC-507 be updated to
reference this corrected fixture recipe (uniform full-band floor per segment, not a
digital-zero buffer + highpass-only injection) so a future re-read of the spec does not
reproduce this same construction-time failure. No `_gate_scan`/`_detect_cliff` code change
is warranted — the detector correctly rejected the originally-specified fixture because
that fixture's own geometry does not, in fact, produce a clean isolated false-positive-only
signal at the segment level.

**Status: Architectural.** (Worked around within this QA pass via a corrected fixture
construction in test_story005_def205.py so TC-507 passes and provides real coverage —
but this is a method change to the fixture (two-region digital-zero-then-injection →
uniform full-band floor) plus a parameter change (F_real 20000 → 16000 Hz), not a fix to
the architecture.md §9.1 / test-cases.md TC-507 specification itself, which still
documents the broken recipe. Per H7 criterion 4, a method-caused defect cannot be closed
by a workaround that leaves the specified method undocumented/uncorrected. Requires
software-architect to update architecture.md §9.1 (and test-case-writer to update
test-cases.md TC-507) with the corrected fixture recipe before this can move to Closed.)

---

