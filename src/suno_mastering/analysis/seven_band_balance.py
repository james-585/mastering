"""Seven-band spectral balance, descriptive/comparison scheme (STORY-002
architecture.md Section 4.2). Runs alongside, never replaces,
frequency_balance.py's three-band correction scheme -- no threshold/flag
logic here; this is comparison-only across a reference set.

Reuses the shared Welch PSD helper (_psd.py) and the same silence-gating
convention as frequency_balance.py, so both schemes measure over the same
"active" (non-near-silent) audio.
"""
from __future__ import annotations

import numpy as np

from . import _psd
from .reference_types import SevenBandMeasurement, SevenBandResult
from .silence import extract_active_audio


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=1)


def measure_seven_band_balance(audio: np.ndarray, sr: int, config) -> SevenBandResult:
    mono = _to_mono(audio)
    active = extract_active_audio(
        mono, sr, block_ms=config.silence_block_ms, threshold_db=config.silence_gate_threshold_db
    )
    if active.size < 8:
        active = mono

    freqs, psd = _psd.compute_psd(active, sr)
    nyquist = sr / 2.0

    ref_power = _psd.band_power(freqs, psd, config.freq_reference_band_hz)

    bands = []
    for key, (lo, hi) in config.seven_bands_hz.items():
        resolved_hi = hi if hi is not None else nyquist
        power = _psd.band_power(freqs, psd, (lo, resolved_hi))
        relative_db = 10.0 * np.log10(power / ref_power)
        bands.append(
            SevenBandMeasurement(
                band=key, range_hz=(lo, resolved_hi), relative_db=float(relative_db)
            )
        )

    return SevenBandResult(bands=bands)
