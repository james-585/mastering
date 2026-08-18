# STORY-003: Ground-truth test harness

## User Story
As a producer, I want every measurement function verified against
synthetic signals whose correct answer is known by construction, so
that the tool's numbers can be trusted — and so that wrong numbers
fail a test instead of appearing in a report.

## Why this comes before more features
Three defects (DEF-201, DEF-202, DEF-203) passed the existing test
suite, including one producing physically impossible output (a
commercial record reported as rolling off at 1979 Hz). The tests
verify that functions run and return plausible types; they do not
verify that the returned values are correct.

Every feature built on top of an unverified measurement inherits that
uncertainty. This story fixes the foundation.

## Builds on
STORY-001 / STORY-002 — modify the existing implementation and test
suite directly. Do not create a parallel test structure.

## Core principle

For each measurement, construct a signal where the correct answer is
known **by construction, not by measurement**. Then assert the tool
returns that answer within a stated tolerance.

If the correct answer for a test signal has to be obtained by running
the tool, that is not a ground-truth test — it is a regression test,
and it will happily lock in a wrong value.

## Required ground-truth tests

**Loudness (LUFS)**
- ITU-R BS.1770 compliance signals where the standard states the
  expected result
- 1 kHz sine at known amplitude → known LUFS, within ±0.1 LU
- Verify a 6 dB gain change moves integrated loudness by 6 LU

**True peak (dBTP)**
- Signal engineered so inter-sample peaks exceed sample peak by a
  known margin → assert measured true peak exceeds sample peak
  accordingly
- Full-scale sine at exact Nyquist-adjacent frequency (classic
  inter-sample overshoot case)
- Assert sample-peak and true-peak implementations return *different*
  values on this signal — if they match, true peak is not implemented

**HF extension / rolloff** — this is the one that failed
- White noise brickwalled at exactly 15 kHz → must detect ~15 kHz
- White noise brickwalled at exactly 8 kHz → must detect ~8 kHz
- Full-band white noise (no cutoff) → must report no cutoff, or
  Nyquist, NOT a mid-band value
- **Pink noise with no cutoff** → must report no cutoff. This is the
  test DEF-201 would have failed: pink noise has a naturally
  declining spectrum, and a threshold-based detector will falsely find
  a cutoff in it.
- Signal with cutoff changing partway through → drift detection fires

**Dynamic range / LRA**
- Constant-level sine → DR and LRA near zero
- Alternating loud/quiet sections with known level difference → LRA
  approximates that difference
- Verify LRA is not simply reporting peak-to-trough of the whole file

**Spectral balance**
- Band-limited noise in exactly one band → that band dominates,
  others near-silent
- Equal-energy pink noise → known relative band distribution
- Verify band edges: energy at exactly a boundary frequency is
  attributed to the correct band

**Stereo width / correlation**
- Identical L and R → correlation 1.0, width 0.0
- Inverted R → correlation -1.0, mono sum near-silent
- Uncorrelated noise L and R → correlation near 0.0
- **Mono-sum level change for each of the above** → this is the test
  that resolves DEF-203, because the expected value is derivable
  analytically for each case

## Sanity assertions — cheap, catch the impossible

Beyond exact-value tests, add assertions that catch physically
impossible results regardless of implementation:

- HF rolloff below 5 kHz on material with air-band energy above
  -40 dB → fail
- Measured LUFS above 0 or below -70 → fail
- Correlation outside [-1.0, 1.0] → fail
- Any band relative level implausibly far from the others → warn

These would have caught DEF-201 immediately without knowing the
correct answer.

## Acceptance criteria
1. Every public measurement function has at least one ground-truth
   test with an analytically-derived expected value
2. Test signals are generated programmatically (numpy/scipy), not
   loaded from files
3. Each ground-truth test states in a comment *why* the expected value
   is what it is — the derivation, not just the number
4. Sanity assertions run on every measurement, in production code as
   well as tests, and surface warnings in the report
5. The full ground-truth suite runs in under 30 seconds
6. DEF-201 and DEF-203 are demonstrably caught by new tests before
   they are fixed — write the failing test first, confirm it fails,
   then fix

## Non-functional
- Signals kept short (2-5 s). No test in this suite loads real audio.
- Session-scoped fixtures for any signal used by multiple tests.
