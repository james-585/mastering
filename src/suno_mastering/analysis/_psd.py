"""Shared Welch PSD helper (STORY-002 architecture.md Section 4.2: promoted
out of frequency_balance.py so seven_band_balance.py, hf_extension.py, and
per_band_stereo_width.py reuse the exact same Welch-parameter logic rather
than duplicating it).

Pure extraction: frequency_balance.py's own public function and output are
unchanged by this refactor.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import welch

_MIN_POWER = 1e-20


def welch_nperseg(sr: int, n_samples: int) -> int:
    # Need enough frequency resolution to resolve the 20-120Hz band cleanly;
    # cap at signal length and a sane upper bound for performance.
    target = 65536
    return int(min(target, max(1024, 2 ** int(np.floor(np.log2(max(n_samples, 1024)))))))


def compute_psd(audio: np.ndarray, sr: int):
    """Welch PSD of a mono 1-D signal, using the shared nperseg convention.
    Returns (freqs, psd). `noverlap=nperseg//2`, `average="mean"` --
    identical parameters used everywhere this helper is called, so
    welch()/csd() outputs stay directly comparable (per_band_stereo_width.py
    depends on this)."""
    nperseg = welch_nperseg(sr, audio.size)
    freqs, psd = welch(audio, fs=sr, nperseg=nperseg, noverlap=nperseg // 2, average="mean")
    return freqs, psd


def band_power(freqs: np.ndarray, psd: np.ndarray, band_hz: tuple) -> float:
    """Integrate PSD over [lo, hi] (trapezoidal); represents band power
    (units: power, i.e. PSD-density * Hz -- NOT directly comparable to a
    single PSD bin's density without dividing back out by the band width)."""
    lo, hi = band_hz
    mask = (freqs >= lo) & (freqs <= hi)
    if not mask.any():
        return _MIN_POWER
    return max(float(np.trapezoid(psd[mask], freqs[mask])), _MIN_POWER)


def band_mean_density(freqs: np.ndarray, psd: np.ndarray, band_hz: tuple) -> float:
    """Mean PSD density (power/Hz) over [lo, hi] -- comparable directly to a
    single PSD bin's density, unlike band_power() which is power-integrated
    over the band. Used by hf_extension.py's rolloff scan, which compares a
    per-bin density against a reference *density* level."""
    lo, hi = band_hz
    mask = (freqs >= lo) & (freqs <= hi)
    if not mask.any():
        return _MIN_POWER
    return max(float(np.mean(psd[mask])), _MIN_POWER)


def log_band_levels_db(
    freqs: np.ndarray, psd: np.ndarray, f_min: float, f_max: float,
    band_octave_fraction: float = 1.0 / 24.0,
) -> tuple:
    """Re-bin a linear Welch PSD onto a log-frequency grid of constant
    octave width (STORY-004 architecture.md Section 3.2). Returns
    (band_center_freqs_hz, band_level_db), power-averaged (not dB-averaged)
    within each band -- same convention as band_mean_density(). Sample-rate-
    invariant: bandwidth is defined in octaves, not Hz, so 44.1kHz and 48kHz
    inputs produce directly comparable band structure. A band containing
    zero linear PSD bins (only possible if band_octave_fraction is set
    finer than the local bin spacing) falls back to the nearest single bin
    rather than raising.
    """
    n_bands = int(np.ceil(np.log2(f_max / f_min) / band_octave_fraction))
    edges = f_min * (2.0 ** (np.arange(n_bands + 1) * band_octave_fraction))
    centers = np.sqrt(edges[:-1] * edges[1:])          # geometric mean
    levels_db = np.empty(n_bands)
    for i in range(n_bands):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if not mask.any():
            idx = int(np.argmin(np.abs(freqs - centers[i])))
            levels_db[i] = 10.0 * np.log10(max(psd[idx], _MIN_POWER))
        else:
            levels_db[i] = 10.0 * np.log10(max(float(np.mean(psd[mask])), _MIN_POWER))
    return centers, levels_db
