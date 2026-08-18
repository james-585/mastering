"""Sanity assertions -- cheap, always-on checks that catch physically
impossible measurement results regardless of which measurement bug produced
them (STORY-003 architecture.md Section 4; story.md's "Sanity assertions --
cheap, catch the impossible" section; DEF-201 is the concrete case that
motivated this module: a report showing both a 1979 Hz rolloff and
substantial 10-24 kHz air-band energy, physically inconsistent claims that
should have been caught immediately without knowing the "correct" rolloff
value).

Hard rule, load-bearing: a sanity check NEVER raises and NEVER aborts a
run. story.md's own language ("-> fail") could be misread as "raise an
exception" -- it does not mean that here. "fail" severity means the report
shows an unambiguous FAIL marker next to a value a producer should not
trust; "warn" means a milder flag. Both are advisory metadata attached to
the result (see analysis/types.py::Measurements.sanity_warnings and
analysis/reference_types.py::ReferenceMeasurements.sanity_warnings), never a
crashed pipeline run -- the same posture as this project's existing
`suspected_transcode` flag. A false positive on genuine, unusual-but-real
audio must degrade to "an odd report annotation," not a failed run.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .reference_types import SevenBandMeasurement

# Correlation is a normalized cross-correlation; [-1, 1] by definition. An
# epsilon is required (not a bare [-1, 1] comparison) because
# correlation_coefficient() computes num/denom from two independently
# rounded floating-point sums (stereo_phase.py), so genuinely identical
# channels can read fractionally over 1.0 (e.g. 1.0000000000000002) as a
# pure floating-point artifact -- without the epsilon, the check
# false-positives on the single MOST correct possible input.
_CORRELATION_EPSILON = 1e-6

# BS.1770 integrated loudness is a power-mean of per-block mean-squares that
# individually passed the -70 LUFS absolute gate; a finite value below this
# floor is mathematically impossible for a correct implementation (see
# check_lufs_plausible's docstring for the proof), not merely "suspicious."
_LUFS_ABSOLUTE_FLOOR = -70.0

# DEF-206: the literal story.md "> 0.0" ceiling has no derivation behind it,
# unlike the -70 floor, and demonstrably false-positives on legitimate,
# non-clipping audio -- a dual-mono sine at amplitude 0.999 (genuinely
# non-clipping) reads up to +3.297 dB at 8 kHz through the shipped,
# unmodified measure_all(), purely as the correct, expected consequence of
# two already-established, already-correct properties of this codebase's own
# BS.1770 implementation stacking: K-weighting's high-shelf boost, and
# BS.1770's channel-SUMMED convention (the same convention DEF-101/DEF-203
# already establish as correct, not a bug). See architecture.md Section 4.2
# for the full derivation; summary: for any non-clipping (|x|<=1), <=2-channel
# (this codebase's own _SUPPORTED_CHANNELS={1,2} ingest limit, enforced at
# io/ingest.py and io/reference_ingest.py), standard-weighted (G_i=1.0)
# signal, BS.1770's own channel-summed integrated-loudness formula cannot
# mathematically exceed roughly +6.37 dB at this codebase's supported sample
# rates (a full-scale dual-mono square wave at the K-weighting shelf's own
# peak-gain frequency is the theoretical worst case) -- 6.5 is that bound
# with margin, not tightened below it.
_LUFS_CEILING_DB = 6.5

# DEF-201's own report-review finding, restated as a standing invariant
# (story.md's literal figures): a band limit below this frequency is only
# physically plausible if the air band shows genuinely low energy.
# STORY-004 architecture.md Section 4 item 7b: raised from 5000.0 to
# 10000.0 -- a doc-derived correction, not parameter tuning of the detector
# under test. DOMAIN.md Section 2 states explicitly "any reported cutoff
# below ~10 kHz on a commercial release is a measurement error," and AC2
# requires exactly this ("no value below 10 kHz is reported for a
# commercial master"). At the previous 5000.0 value, a reported 7 kHz band
# limit satisfied neither DOMAIN.md's plausibility statement nor AC2.
_HF_ROLLOFF_SUSPECT_HZ = 10000.0
_HF_AIR_BAND_ENERGY_FLOOR_DB = -40.0

# Seven-band adjacent-delta plausibility thresholds (architecture.md Section
# 4.2 -- a provisional, explicitly-flagged architectural judgment call, not
# a derived invariant like the LUFS bound; see architecture.md Section 9
# item 1). Two thresholds, not one: the air band legitimately sits far below
# the mid-band reference on ordinary commercial masters (DEF-201's own
# report data shows ~-20 dB there with no HF problem at all), so a single
# threshold tight enough to catch a genuine sign/computation bug would
# false-positive on that ordinary case.
_SEVEN_BAND_ADJACENT_DELTA_THRESHOLD_DB = 25.0
_SEVEN_BAND_AIR_ADJACENT_DELTA_THRESHOLD_DB = 40.0


@dataclass
class SanityWarning:
    metric: str       # e.g. "correlation_range", "integrated_lufs_range",
                       # "hf_rolloff_vs_air_band", "seven_band_adjacent_delta.high_air"
    severity: str      # "fail" | "warn" -- see module docstring's hard rule
    message: str       # human-readable, must include the actual offending value(s)


def check_correlation_range(correlation: float) -> Optional[SanityWarning]:
    """Correlation range: [-1.0, 1.0], exact by definition of a normalized
    cross-correlation -- any value outside this range is a computation bug,
    not a measurement of real audio. math.isnan is checked first: NaN
    compares False against every bound below, so a NaN would otherwise sail
    through silently."""
    if math.isnan(correlation):
        return SanityWarning("correlation_range", "fail", "correlation is NaN")
    if correlation < -1.0 - _CORRELATION_EPSILON or correlation > 1.0 + _CORRELATION_EPSILON:
        return SanityWarning(
            "correlation_range", "fail",
            f"correlation {correlation:.6f} outside [-1.0, 1.0]",
        )
    return None


def check_lufs_plausible(lufs: float) -> Optional[SanityWarning]:
    """-inf is the documented, legitimate BS.1770-gated result for
    silence/near-silence (loudness.py's own docstring; STORY-001's existing
    test_silence_dynamics.py already exercises this) -- exempt exactly
    -inf, not any "looks quiet" heuristic.

    A FINITE value below -70 is not merely suspicious, it is mathematically
    impossible for a correct implementation: BS.1770's integrated loudness
    is a power-mean (not a plain average) of per-block mean-squares that
    individually passed the -70 LUFS absolute gate. Each surviving block's
    mean-square x_i satisfies -0.691 + 10*log10(x_i) > -70, i.e.
    x_i > 10**((-70+0.691)/10). The arithmetic mean of positive values is
    >= any individual value's own floor, so mean(x_i) has that same floor,
    and therefore -0.691 + 10*log10(mean(x_i)) > -70 whenever the gate let
    anything through at all. A finite value < -70 can only mean a bug (e.g.
    an ungated computation), not real audio -- this resolves the
    silent-vs-non-silent ambiguity without needing a heuristic: the
    invariant is exact.

    The upper bound, _LUFS_CEILING_DB (DEF-206, see the module-level comment
    and architecture.md Section 4.2 for the full derivation), is a genuine
    hard bound, not the story.md-literal "> 0.0" figure this check originally
    shipped with -- 0.0 false-positived on legitimate, non-clipping,
    K-weighting-shelf-boosted / channel-summed audio (DEF-206)."""
    if math.isnan(lufs):
        return SanityWarning("integrated_lufs_range", "fail", "LUFS is NaN")
    if lufs == float("-inf"):
        return None  # legitimate gated-silence result, not a failure
    if lufs < _LUFS_ABSOLUTE_FLOOR or lufs > _LUFS_CEILING_DB:
        return SanityWarning(
            "integrated_lufs_range", "fail",
            f"integrated LUFS {lufs:.2f} outside (-70, {_LUFS_CEILING_DB}] and not -inf",
        )
    return None


def check_hf_rolloff_vs_air_band(
    hf_band_limit_hz: Optional[float],
    insufficient_duration: bool,
    air_relative_db: Optional[float],
) -> Optional[SanityWarning]:
    """Uses the SAME power-integrated air-band figure already surfaced in
    every seven-band report (SevenBandMeasurement.relative_db for
    band="air") -- deliberately avoids converting to the density-domain
    figure the HF-extension scan uses internally (architecture.md Section
    2.4): introducing a second, subtly-different definition of "air-band
    energy" for this one check would be a needless source of confusion when
    the figure already on the page serves the job.

    air_relative_db is Optional: a caller with a non-default seven_bands_hz
    config that omits "air" entirely passes None, in which case this check
    is skipped rather than raising.

    `hf_band_limit_hz is None` (STORY-004): this guard's *meaning* now
    covers three cases -- insufficient duration, a confirmed absence of a
    cliff, or "not measurable near Nyquist" (architecture.md Section 3.5) --
    but its *behavior* (skip the check) is correct for all three: there is
    nothing to cross-check against air-band energy when there is no
    reported band limit."""
    if hf_band_limit_hz is None or insufficient_duration or air_relative_db is None:
        return None
    if hf_band_limit_hz < _HF_ROLLOFF_SUSPECT_HZ and air_relative_db > _HF_AIR_BAND_ENERGY_FLOOR_DB:
        return SanityWarning(
            "hf_rolloff_vs_air_band", "fail",
            f"band limit reported at {hf_band_limit_hz:.0f} Hz but air band "
            f"(10-24 kHz) reads {air_relative_db:.1f} dB relative "
            f"(> {_HF_AIR_BAND_ENERGY_FLOOR_DB:.0f} dB) -- physically inconsistent, a real "
            f"{hf_band_limit_hz:.0f} Hz cutoff would show air-band energy far below this",
        )
    return None


def check_seven_band_adjacent_deltas(
    bands: "List[SevenBandMeasurement]",
    threshold_db: float = _SEVEN_BAND_ADJACENT_DELTA_THRESHOLD_DB,
    air_threshold_db: float = _SEVEN_BAND_AIR_ADJACENT_DELTA_THRESHOLD_DB,
) -> List[SanityWarning]:
    """`bands` iterated in config.seven_bands_hz's own insertion order (sub,
    low, low_mid, mid, high_mid, high, air) -- already the correct
    frequency ordering, no re-sort needed. Every non-air-adjacent pair uses
    the tighter `threshold_db`, since natural -3 to -6 dB/octave tilt over
    the ~1-3 octave gaps between non-air adjacent seven-band edges rarely
    exceeds ~15-20 dB even on atypical mixes."""
    out: List[SanityWarning] = []
    for a, b in zip(bands, bands[1:]):
        limit = air_threshold_db if "air" in (a.band, b.band) else threshold_db
        delta = abs(a.relative_db - b.relative_db)
        if delta > limit:
            out.append(
                SanityWarning(
                    f"seven_band_adjacent_delta.{a.band}_{b.band}", "warn",
                    f"{a.band} ({a.relative_db:.1f} dB) vs {b.band} "
                    f"({b.relative_db:.1f} dB): {delta:.1f} dB gap exceeds "
                    f"{limit:.1f} dB plausibility threshold",
                )
            )
    return out
