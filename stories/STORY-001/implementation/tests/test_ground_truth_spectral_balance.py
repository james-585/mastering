"""STORY-003 ground-truth tests -- spectral balance (AC8), test-cases.md
TC-040 through TC-044. Covers both seven_band_balance.py (STORY-002) and
frequency_balance.py (STORY-001's three-band scheme) -- both share the
identical _psd.py boundary convention.
"""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering.analysis.seven_band_balance import measure_seven_band_balance
from suno_mastering.analysis.frequency_balance import measure_frequency_balance
from suno_mastering.analysis.sanity import check_seven_band_adjacent_deltas
from suno_mastering.analysis import _psd
from suno_mastering.config import MasteringConfig

from .ref_helpers import band_limited_noise_mono, white_noise_mono, ref_config

pytestmark = pytest.mark.ground_truth

SR = 44100
SR2 = 48000


def test_tc040_band_limited_noise_dominates_its_band():
    """AC8a, directional/relational (architecture.md Section 7.4): the
    bandpass confines the dominant signal component to the high_mid
    (2000-5000 Hz) band by construction; the exact numeric gap depends on
    filter order/floor-amplitude choices, so a relational assertion is the
    honest ground truth here, not a fabricated precise number.

    Empirically tightened (this QA pass) from architecture.md's illustrative
    ">=20dB" figure: at the originally-illustrated order=4/floor_amplitude=
    0.005, the measured gap to the nearest non-target band ("high",
    5000-10000Hz -- adjacent to the target band) was only ~16.5-16.9dB
    regardless of floor_amplitude (bandpass transition-band leakage into
    the immediately-adjacent band, not floor-noise-limited) -- see
    ref_helpers.band_limited_noise_mono's own docstring. Raising the filter
    order to 8 (this helper's new default) restores a measured ~19.9-20.4dB
    gap across 5 seeds; the assertion below uses 18.0dB (not 20.0dB) as a
    safety margin against seed-to-seed variance rather than the exact,
    close-to-boundary measured figure for this specific seed."""
    mono = band_limited_noise_mono(SR, duration_s=4.0, band_hz=(2000, 5000), seed=1, amplitude=0.2)
    audio = np.stack([mono, mono], axis=1)
    result = measure_seven_band_balance(audio, SR, ref_config())
    by_band = {b.band: b.relative_db for b in result.bands}
    dominant = max(by_band, key=by_band.get)
    assert dominant == "high_mid"
    for band, val in by_band.items():
        if band == "high_mid":
            continue
        assert by_band["high_mid"] - val >= 18.0, f"{band}: gap={by_band['high_mid'] - val}"


@pytest.mark.parametrize("sr", [44100, 48000])
def test_tc041_equal_energy_white_noise_matches_closed_form_seven_band(sr):
    """AC8b, exact closed-form. For genuinely flat white noise,
    _psd.band_power's trapezoidal integral of a constant density over
    [lo,hi] is density*(hi-lo) to a very good approximation, so
    relative_db(band) = 10*log10(width_band/width_ref) INDEPENDENT of the
    actual noise realization -- a purely geometric prediction, not obtained
    by running the tool."""
    mono = white_noise_mono(sr, duration_s=5.0, seed=1, amplitude=0.1)
    audio = np.stack([mono, mono], axis=1)
    result = measure_seven_band_balance(audio, sr, ref_config())
    by_band = {b.band: b for b in result.bands}

    ref_width = 2000.0 - 500.0
    for band in result.bands:
        lo, hi = band.range_hz
        width = hi - lo
        predicted_db = 10.0 * np.log10(width / ref_width)
        assert band.relative_db == pytest.approx(predicted_db, abs=1.0), (
            f"{band.band}: measured={band.relative_db}, predicted={predicted_db}"
        )


@pytest.mark.parametrize("sr", [44100, 48000])
def test_tc042_equal_energy_white_noise_matches_closed_form_three_band(sr):
    """AC1 coverage for measure_frequency_balance (STORY-001's three-band
    scheme) -- identical formula/reasoning to TC-041, applied to
    frequency_balance.py's own configured band edges."""
    mono = white_noise_mono(sr, duration_s=5.0, seed=1, amplitude=0.1)
    audio = np.stack([mono, mono], axis=1)
    config = MasteringConfig()
    result = measure_frequency_balance(audio, sr, config)

    ref_lo, ref_hi = config.freq_reference_band_hz
    ref_width = ref_hi - ref_lo

    for band_measurement, band_hz in [
        (result.low_end, config.freq_low_band_hz),
        (result.low_mid_mud, config.freq_mud_band_hz),
        (result.presence_harsh, config.freq_presence_band_hz),
    ]:
        lo, hi = band_hz
        width = hi - lo
        predicted_db = 10.0 * np.log10(width / ref_width)
        assert band_measurement.relative_db == pytest.approx(predicted_db, abs=1.0)


def test_tc043_boundary_frequency_attributed_to_both_adjacent_bands():
    """AC8c, direct unit test of _psd.band_power -- no audio synthesis. All
    real energy concentrated at exactly the shared low/low_mid boundary bin
    (120 Hz). _psd.py's mask is (freqs>=lo)&(freqs<=hi), inclusive on both
    ends, so the boundary bin's energy must appear in BOTH adjacent bands.
    A synthesized-tone test cannot isolate this convention (Welch spectral
    leakage spreads energy across neighboring bins regardless of which
    convention band_power uses) -- must hand-build the array."""
    freqs = np.array([100.0, 120.0, 140.0])
    psd = np.array([1e-20, 1.0, 1e-20])
    power_low = _psd.band_power(freqs, psd, (60.0, 120.0))
    power_low_mid = _psd.band_power(freqs, psd, (120.0, 500.0))
    assert power_low > 1e-10
    assert power_low_mid > 1e-10


@pytest.mark.parametrize("sr", [44100, 48000])
def test_tc044_flat_white_noise_zero_seven_band_adjacent_delta_warnings(sr):
    """Negative control: TC-041's own closed-form white-noise table should
    produce zero seven-band adjacent-delta sanity warnings -- ordinary flat/
    broadband material must not trip the AC10 plausibility check."""
    mono = white_noise_mono(sr, duration_s=5.0, seed=1, amplitude=0.1)
    audio = np.stack([mono, mono], axis=1)
    result = measure_seven_band_balance(audio, sr, ref_config())
    warnings = check_seven_band_adjacent_deltas(result.bands)
    assert warnings == [], f"unexpected warnings: {warnings}"
