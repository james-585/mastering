"""Per-band stereo width via Welch/CSD (STORY-002 architecture.md Section
4.4). Deliberately NOT a filter-bank design -- a frequency-domain
coherence-style estimate directly from PSD/CSD outputs, per the advisor
review referenced in architecture.md.

    S_LL, S_RR = welch(L), welch(R)
    S_LR       = csd(L, R)
    width[band] = 1 - |Re{integral_band S_LR}| / sqrt(integral_band S_LL * integral_band S_RR)

0 = fully correlated/mono in that band, 1 = fully decorrelated. `welch` and
`csd` must share identical parameters (nperseg/noverlap/window) for the
normalization to be valid -- both route through the shared _psd.py Welch
convention.

Stated caveat (must also appear in the report, per architecture.md):
this is a magnitude/frequency-domain estimate, not literal band-filtered
time-domain correlation -- cheaper, no filter design needed, but answers a
slightly different question. Not to be presented as identical to
stereo_phase.py's broadband time-domain correlation figure.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import csd

from . import _psd
from .reference_types import PerBandWidthMeasurement, PerBandWidthResult

_MIN_POWER = 1e-20


def measure_per_band_stereo_width(audio: np.ndarray, sr: int, config) -> PerBandWidthResult:
    """`audio` must be genuine stereo (samples, 2) -- callers are
    responsible for skipping this measurement for mono tracks."""
    left = audio[:, 0]
    right = audio[:, 1]

    nperseg = _psd.welch_nperseg(sr, left.size)
    freqs_ll, s_ll = _psd_welch_matching(left, sr, nperseg)
    freqs_rr, s_rr = _psd_welch_matching(right, sr, nperseg)
    freqs_lr, s_lr = csd(left, right, fs=sr, nperseg=nperseg, noverlap=nperseg // 2, average="mean")

    nyquist = sr / 2.0
    bands = []
    for key, (lo, hi) in config.seven_bands_hz.items():
        resolved_hi = hi if hi is not None else nyquist
        band_hz = (lo, resolved_hi)
        p_ll = _psd.band_power(freqs_ll, s_ll, band_hz)
        p_rr = _psd.band_power(freqs_rr, s_rr, band_hz)
        # Integrate the complex cross-spectral density's real part over the
        # band the same way _band_power integrates a real PSD.
        mask = (freqs_lr >= lo) & (freqs_lr <= resolved_hi)
        if mask.any():
            p_lr_real = float(np.trapezoid(np.real(s_lr[mask]), freqs_lr[mask]))
        else:
            p_lr_real = 0.0

        denom = np.sqrt(max(p_ll, _MIN_POWER) * max(p_rr, _MIN_POWER))
        width = 1.0 - abs(p_lr_real) / denom if denom > 0 else 0.0
        # Cauchy-Schwarz bounds |integral S_LR| <= sqrt(integral S_LL * integral S_RR)
        # for the true (unwindowed) cross-spectrum; Welch's finite-window
        # estimate can overshoot this slightly. Clamp rather than let a
        # small numerical excursion outside [0, 1] leak into the report --
        # a large excursion would indicate a real bug, not noise.
        width = float(np.clip(width, 0.0, 1.0))

        bands.append(PerBandWidthMeasurement(band=key, range_hz=band_hz, width=width))

    return PerBandWidthResult(bands=bands)


def _psd_welch_matching(x: np.ndarray, sr: int, nperseg: int):
    from scipy.signal import welch

    return welch(x, fs=sr, nperseg=nperseg, noverlap=nperseg // 2, average="mean")
