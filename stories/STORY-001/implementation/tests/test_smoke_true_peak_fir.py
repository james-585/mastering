"""python-developer smoke check (not a QA-owned TC-numbered test) for
true_peak.py's v4 FIR oversampling filter, per architecture.md Section 7
(v4): "add a dedicated frequency-response test independent of any specific
track fixture: sweep a set of calibrated sine tones from roughly 0.5x to
~0.999x of the original Nyquist at a fixed, known amplitude, and assert the
filter's oversampled peak reading stays within the documented ripple
tolerance ... of the input amplitude across the whole sweep."

**Revised 2026-08-01 (python-developer), second pass.** Two things were
wrong with the original version of this test, both root-caused and fixed
here -- see `analysis/true_peak.py`'s module-level tuning note for the full
DSP write-up:

1. The original test drove the check end-to-end through `measure_true_peak()`
   at a handful of fixed frequencies/one fixed phase. That conflates the
   FIR filter's own passband ripple (what Section 7 actually asks to
   verify) with an unrelated, well-known discretization artifact of *any*
   max-over-discrete-oversampled-samples true-peak measurement: for a
   single sustained tone at a fixed phase, the true continuous-time peak
   can fall between oversampled-grid sample points, with a worst-case
   error of `1 - cos(pi/N)` in amplitude for N samples/cycle at the
   oversampled rate (e.g. ~0.11-0.17 dB for N=17-20, which is what
   factor=8 gives near 0.8-0.9x original Nyquist at 44.1kHz). This is
   inherent to the BS.1770-4 Annex 2 oversample-and-peak-scan method
   itself (present for any oversampler, soxr included), not a filter
   defect -- a fixed-phase sweep can hit this worst case at specific
   frequency/factor combinations by coincidence, causing false failures.
2. A follow-up tuning attempt (pushing the FIR's `cutoff` past original
   Nyquist to chase a flatter *frequency response*) passed a
   `scipy.signal.freqz`-only check but turned out to reintroduce a much
   worse defect: `upfirdn`'s zero-stuffing creates a spectral image at
   (original_sample_rate - f), which converges toward the same frequency
   as f itself near Nyquist. Pushing the filter's stopband past Nyquist to
   flatten the *passband* removes exactly the rejection needed to suppress
   that image, causing 5-6 dB *time-domain* errors that a frequency-
   response-only check cannot see (it doesn't model the image at all).
   This is why the test below checks the filter via freqz (to catch
   passband-flatness regressions) *and* the real time-domain pipeline (to
   catch image-leakage regressions) -- neither check alone is sufficient.

Given both effects, the filter design settled on `analysis/true_peak.py`
(cutoff at exactly original Nyquist, image-safe) is flat within 0.01 dB up
to ~80-85% of original Nyquist, degrading gracefully beyond that (still a
real improvement on soxr's ~0.54 dB droop at 94% Nyquist -- this design
measures ~0.02 dB at 85%, ~1.5 dB at 94%). It does NOT meet the full
<0.01 dB-to-0.999x-Nyquist aspirational target from architecture.md Section
7 -- verified computationally infeasible within the 5-minute NFR budget
(would need tens of thousands of FIR taps). Retagged Architectural in
defects.md (DEF-002 residual) rather than silently loosened here.
"""
from __future__ import annotations

import math

import numpy as np
import pytest
from scipy import signal

from suno_mastering.analysis.true_peak import _design_fir, measure_true_peak

from .conftest import cosine

# Achievable, numerically-verified passband-flatness bound for the current
# (image-safe, cutoff=original-Nyquist) filter design -- see
# analysis/true_peak.py's tuning note. NOT the full architecture.md Section 7
# aspirational target (<0.01 dB to 0.999x Nyquist), which was verified to
# require a computationally-infeasible filter length; tracked as an
# Architectural residual in defects.md (DEF-002).
_ACHIEVABLE_FLAT_FRACTION_OF_NYQUIST = 0.80
_ACHIEVABLE_RIPPLE_DB = 0.01


# TC-025 (test-cases.md): full tiered ripple-vs-frequency envelope
# formalized in architecture.md v5 (DEF-002 second residual, "Architectural
# resolution of the second residual", 2026-08-01) to match the
# already-implemented, already-verified filter's real, measured behavior --
# replaces the v4 single flat <0.01dB-to-0.999x-Nyquist aspirational target.
# Nested/cumulative bands: (upper_fraction_of_nyquist, bound_db) pairs,
# lower edge of band i is band (i-1)'s upper edge (0 for the first).
_TIERED_RIPPLE_ENVELOPE = [
    (0.80, 0.01),
    (0.85, 0.05),
    (0.90, 0.5),
    (0.95, 2.5),
    (0.999, 6.5),
]


def _envelope_bound_db(fraction_of_nyquist: float) -> float:
    """TC-025: envelope is a step function of frequency -- every swept `f`
    must satisfy the bound of the *tightest* (smallest-upper-edge) tier it
    falls into, not just the bound at its own tier's edge."""
    for upper, bound in _TIERED_RIPPLE_ENVELOPE:
        if fraction_of_nyquist <= upper:
            return bound
    return _TIERED_RIPPLE_ENVELOPE[-1][1]


@pytest.mark.parametrize("factor", [4, 8])
def test_fir_filter_matches_tiered_ripple_envelope_v5_freqz_leg(factor):
    """TC-025 leg 1: filter magnitude response via freqz, densely swept
    (a genuine step-function check across ~0.5x-0.999x Nyquist, not five
    independent boundary-point checks) against architecture.md v5's tiered
    envelope. Also asserts the error direction is always attenuation
    (under-read), never gain, across the whole sweep -- the composite-peak
    safety argument for accepting this residual depends on that direction."""
    fir = _design_fir(factor)
    unity_db = 20 * np.log10(factor)

    fractions = np.linspace(0.50, 0.999, 400)
    freqs = 0.5 * fractions
    _, h = signal.freqz(fir, worN=freqs, fs=float(factor))
    mag_db = 20 * np.log10(np.abs(h) + 1e-20)

    # (a) attenuation-sign check: magnitude must never exceed unity gain by
    # more than a tiny numerical-ripple tolerance. A windowed-sinc (Kaiser)
    # FIR passband is not perfectly monotonic -- it has its own equiripple-
    # like sidelobe structure, so magnitude legitimately oscillates a few
    # ten-thousandths of a dB either side of unity even well inside the
    # verified-flat region (measured empirically: max overshoot ~0.00036 dB
    # at frac~0.81 for both factor=4 and factor=8, three orders of magnitude
    # below even the tightest 0.01 dB tier bound). `_ATTENUATION_SIGN_
    # TOLERANCE_DB` below is set an order of magnitude above that measured
    # noise floor so this remains a meaningful regression guard against a
    # real, dB-scale sign violation (e.g. the rejected cutoff-past-Nyquist
    # tuning attempt, which showed multi-dB image-leakage errors) without
    # false-failing on ordinary FIR passband micro-ripple.
    _ATTENUATION_SIGN_TOLERANCE_DB = 0.005
    assert np.all(mag_db <= unity_db + _ATTENUATION_SIGN_TOLERANCE_DB), (
        f"factor={factor}: filter magnitude exceeds unity gain (over-read) by "
        f"more than {_ATTENUATION_SIGN_TOLERANCE_DB} dB at fraction(s) "
        f"{fractions[mag_db > unity_db + _ATTENUATION_SIGN_TOLERANCE_DB]} -- "
        "violates the documented 'always attenuation, never gain' safety "
        "direction beyond ordinary FIR passband micro-ripple"
    )

    ripple = np.abs(mag_db - unity_db)
    bounds = np.array([_envelope_bound_db(f) for f in fractions])
    violations = ripple > bounds
    assert not np.any(violations), (
        f"factor={factor}: passband ripple exceeds the architecture.md v5 "
        f"tiered envelope at fraction(s) {fractions[violations][:5]} "
        f"(ripple {ripple[violations][:5]} dB vs bound {bounds[violations][:5]} dB)"
    )


@pytest.mark.parametrize("factor", [8])
def test_measure_true_peak_matches_tiered_ripple_envelope_v5_end_to_end_leg(default_config, factor):
    """TC-025 leg 2: end-to-end measure_true_peak() deviation, densely swept,
    against the same tiered envelope -- distinct from the freqz leg above
    (this exercises the real pipeline: filter + guard-region trim + peak
    scan). A quarter-sample phase offset per swept frequency keeps the
    discrete-grid phase-alignment artifact (module docstring point 1,
    bounded separately by test_measure_true_peak_worst_case_grid_alignment_
    matches_closed_form_bound) from coincidentally landing at its
    frequency-specific worst case for every single swept point, per
    test-cases.md TC-025's explicit note not to attribute that artifact's
    deviation to filter ripple."""
    sr = 44100
    amplitude = 10 ** (-1.0 / 20)
    nyquist = sr / 2.0

    fractions = np.linspace(0.50, 0.995, 60)
    for frac in fractions:
        freq = frac * nyquist
        x = cosine(freq, sr, duration_s=1.0, amplitude=amplitude, phase=math.pi / 4 + 0.3 * frac)
        tp = measure_true_peak(x, sr, default_config)
        expected_dbtp = 20 * np.log10(amplitude)
        deviation = expected_dbtp - tp.dbtp  # positive = under-read, as expected

        bound = _envelope_bound_db(float(frac))
        # Generous grid-alignment margin (module docstring point 1) added on
        # top of the filter-ripple envelope bound for this end-to-end leg
        # only -- the freqz leg above is the pure filter-ripple check.
        grid_alignment_margin_db = 0.2
        assert -0.05 <= deviation <= bound + grid_alignment_margin_db, (
            f"factor={factor} frac={frac:.4f}: measured deviation {deviation:.4f} dB "
            f"outside [-0.05, {bound + grid_alignment_margin_db:.4f}] dB "
            f"(envelope bound {bound} dB + grid-alignment margin)"
        )


@pytest.mark.parametrize("factor", [2, 4, 8, 16])
def test_fir_filter_passband_flat_up_to_achievable_fraction(factor):
    """Direct frequency-response check of the FIR filter itself (freqz):
    flat within the achievable bound up to _ACHIEVABLE_FLAT_FRACTION_OF_NYQUIST,
    guarding against a filter-design regression in that region."""
    fir = _design_fir(factor)
    unity_db = 20 * np.log10(factor)  # upfirdn zero-stuffing gain compensation

    freqs = np.linspace(1e-3, 0.5 * _ACHIEVABLE_FLAT_FRACTION_OF_NYQUIST, 200)
    _, h = signal.freqz(fir, worN=freqs, fs=float(factor))
    mag_db = 20 * np.log10(np.abs(h))
    ripple = float(np.max(np.abs(mag_db - unity_db)))

    assert ripple < _ACHIEVABLE_RIPPLE_DB, (
        f"factor={factor}: worst-case passband ripple {ripple:.5f} dB up to "
        f"{_ACHIEVABLE_FLAT_FRACTION_OF_NYQUIST}x Nyquist"
    )


@pytest.mark.parametrize("factor", [4, 8])
def test_fir_filter_image_rejection_beyond_nyquist(factor):
    """Guards against re-introducing the image-leakage regression (tuning
    attempt 2 in the module docstring): the filter's stopband, evaluated
    just above original Nyquist (where the zero-stuffing image of
    near-Nyquist content lands), must show real, substantial attenuation
    relative to unity gain -- not the near-zero attenuation a
    cutoff-pushed-past-Nyquist design would show there."""
    fir = _design_fir(factor)
    unity_db = 20 * np.log10(factor)

    # Just above original Nyquist (0.5 in fs=factor units) -- this is
    # exactly where the zero-stuffing image of near-Nyquist input content
    # lands (image freq = 1 - f -> 0.5 as f -> 0.5). 0.51 sits right at the
    # transition-band center (attenuation still ramping up there by
    # design), so it gets a weaker bound; 0.55/0.6 are further into the
    # stopband and must show strong rejection -- this is what a
    # cutoff-pushed-past-Nyquist design (the rejected tuning attempt 2)
    # would fail.
    freqs_above_nyquist = np.array([0.51, 0.55, 0.6])
    _, h = signal.freqz(fir, worN=freqs_above_nyquist, fs=float(factor))
    mag_db = 20 * np.log10(np.abs(h) + 1e-20)
    attenuation_db = unity_db - mag_db  # positive = attenuated, as expected

    assert attenuation_db[0] > 3, (
        f"factor={factor}: insufficient rejection ramp-up at 0.51x Nyquist "
        f"({attenuation_db[0]:.2f} dB)"
    )
    assert np.all(attenuation_db[1:] > 20), (
        f"factor={factor}: insufficient stopband rejection just above Nyquist "
        f"({attenuation_db} dB) -- risk of zero-stuffing image leakage"
    )


@pytest.mark.parametrize(
    # 0.8 is deliberately excluded here: at factor=8/44.1kHz/phase=pi/4 it is
    # the known worst-case grid-alignment coincidence (N=20 samples/cycle,
    # see test_measure_true_peak_worst_case_grid_alignment_matches_closed_form_bound
    # below), not a filter-design regression -- covered separately there.
    "freq_frac_of_nyquist", [0.5, 0.6, 0.7, 0.75]
)
def test_measure_true_peak_matches_known_amplitude_within_achievable_band(
    default_config, freq_frac_of_nyquist
):
    """End-to-end sanity check via measure_true_peak(), restricted to the
    achievable-flat frequency band, at a phase chosen to avoid the known
    worst-case discrete-grid-alignment coincidence (see module docstring
    point 1) -- exercises the real pipeline (filter + guard-region trim +
    peak scan)."""
    sr = 44100
    amplitude = 10 ** (-1.0 / 20)
    freq = freq_frac_of_nyquist * (sr / 2.0)
    x = cosine(freq, sr, duration_s=1.0, amplitude=amplitude, phase=math.pi / 4)

    tp = measure_true_peak(x, sr, default_config)

    expected_dbtp = 20 * np.log10(amplitude)
    ripple = abs(tp.dbtp - expected_dbtp)
    assert ripple < default_config.true_peak_monotonicity_tolerance_db


def test_measure_true_peak_worst_case_grid_alignment_matches_closed_form_bound():
    """Documents and bounds the known, accepted discretization artifact
    (module docstring point 1): at factor=8/44.1kHz, freq=0.8x Nyquist
    (17640 Hz) gives exactly N=20 oversampled-rate samples/cycle, an
    unlucky exact-integer alignment that reproduces the theoretical
    worst-case peak-detection error `1 - cos(pi/N)` on every cycle. This is
    a property of the max-over-oversampled-samples method itself (present
    for any oversampler, including the pre-v4 soxr path), not a FIR
    filter-design defect -- bounded here against its own closed-form
    prediction rather than the tighter filter-ripple tolerance."""
    sr = 44100
    factor = 8
    n_samples_per_cycle = 20
    freq = (sr * factor) / n_samples_per_cycle
    assert freq / (sr / 2.0) == pytest.approx(0.8, abs=1e-6)  # sanity: matches the known case

    amplitude = 10 ** (-1.0 / 20)
    x = cosine(freq, sr, duration_s=1.0, amplitude=amplitude, phase=math.pi / 4)

    from suno_mastering.config import MasteringConfig

    tp = measure_true_peak(x, sr, MasteringConfig())

    expected_dbtp = 20 * np.log10(amplitude)
    worst_case_bound_db = -20 * np.log10(math.cos(math.pi / n_samples_per_cycle))
    ripple = expected_dbtp - tp.dbtp  # this artifact only ever under-reads, never over-reads

    assert -0.01 <= ripple <= worst_case_bound_db + 0.01
