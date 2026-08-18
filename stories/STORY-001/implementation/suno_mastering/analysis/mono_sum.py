"""Mono-sum level change + band-specific cancellation (STORY-004
architecture.md Section 2 -- DEF-203 METHOD change, not a constant edit).

Superseded design (defects.md DEF-101/DEF-104/DEF-203, STORY-002
architecture.md Section 4.5): the broadband comparator divided
LUFS(mono_sum) by BS.1770's channel-SUMMED stereo LUFS, giving a rho=0
floor of -6.0206 dB. That is the arithmetically-correct answer to a
DIFFERENT question (mono sum vs. channel-summed stereo), not the
DOMAIN.md Section 3 / CLAUDE.md-authoritative comparison this project
reports: mono sum vs. a single channel / the channel-mean reference.

Corrected design (STORY-004 architecture.md Section 2.1): mono sum is
compared against the CHANNEL-MEAN power reference,
P_mean = (sigma_L^2 + sigma_R^2) / 2, computed in the linear-power domain
from each channel's own independent BS.1770-gated measurement (mirroring
exactly how the existing per-band comparator already averages psd_l/psd_r).
This gives the DOMAIN.md Section 3 floor exactly: rho=1.0 -> 0 dB, rho=0.0
(equal power) -> -3.0103 dB, rho=-1.0 -> -inf dB. See architecture.md
Section 2.1 for the full (unequal-channel-power) derivation and Section 2.2
for the implementation, including the both-channels-silent guard (Gate 1
advisory) and the NaN hardening.

Both the broadband and per-band comparators now share ONE constant,
_DECORRELATED_FLOOR_DB = 10*log10(0.5) = -3.0103 dB -- the per-band
comparator's formula was already correct (it always divided by the
channel-MEAN band power); only the broadband comparator's denominator
changes here.
"""
from __future__ import annotations

import math

import numpy as np

from . import _psd
from ..errors import InvalidWavError
from .loudness import measure_integrated_lufs
from .reference_types import BandCancellation, MonoSumResult

# Shared rho=0 (fully decorrelated, equal-power) floor for BOTH the
# broadband and per-band comparators -- STORY-004 architecture.md Section
# 2.1's derivation. Not two independently-tuned numbers: the same formula
# applied at two different bandwidths, using the same constant.
_DECORRELATED_FLOOR_DB = 10.0 * math.log10(0.5)  # -3.0103 dB


def _lufs_to_linear(lufs: float) -> float:
    """BS.1770: LUFS = -0.691 + 10*log10(z)  =>  z = 10**((LUFS+0.691)/10)."""
    if math.isnan(lufs):
        raise InvalidWavError("Cannot average a NaN LUFS value into channel_mean_lufs")
    if lufs == float("-inf"):
        return 0.0
    return 10.0 ** ((lufs + 0.691) / 10.0)


def _linear_to_lufs(z: float) -> float:
    if z <= 0.0:
        return float("-inf")
    return -0.691 + 10.0 * math.log10(z)


def _channel_mean_lufs(left_lufs: float, right_lufs: float) -> float:
    return _linear_to_lufs(
        (_lufs_to_linear(left_lufs) + _lufs_to_linear(right_lufs)) / 2.0
    )


def measure_mono_sum(audio: np.ndarray, sr: int, config) -> MonoSumResult:
    """`audio` must be genuine stereo (samples, 2) -- callers (pipeline.py)
    are responsible for skipping this measurement for mono tracks (per
    requirements.md's mono-reference-track handling)."""
    left = audio[:, 0]
    right = audio[:, 1]
    mono_sum = (left + right) / 2.0

    left_lufs = measure_integrated_lufs(left, sr)     # genuine single-channel calls,
    right_lufs = measure_integrated_lufs(right, sr)    # each its own independent BS.1770 gate

    if left_lufs == float("-inf") and right_lufs == float("-inf"):
        # Both channels exact digital silence -- guard placed BEFORE the
        # differencing, not as a post-hoc isnan() check on the result.
        # Without this branch: channel_mean_lufs and mono_lufs both
        # independently evaluate to -inf, and mono_lufs - channel_mean_lufs
        # is (-inf) - (-inf) = NaN in IEEE arithmetic, NOT -inf. `NaN <
        # threshold` is False in Python, so an unguarded silent stereo file
        # would silently report mono_sum_excess_cancellation = False
        # instead of a defined, plausibility-visible result (Gate 1
        # advisory, architecture.md Section 2.2). Two exactly-silent
        # channels are trivially identical, i.e. the rho=1 limit -- Section
        # 2.1's table gives 0 dB for rho=1, so that is the correct defined
        # value here, not a sentinel invented for this branch.
        return MonoSumResult(
            mono_sum_level_change_db=0.0,
            mono_sum_excess_cancellation=False,
            mono_sum_both_channels_silent=True,
            band_cancellations=[],  # no signal to compare per band either
        )

    channel_mean_lufs = _channel_mean_lufs(left_lufs, right_lufs)
    mono_lufs = measure_integrated_lufs(mono_sum, sr)

    mono_sum_level_change_db = float(mono_lufs - channel_mean_lufs)
    mono_sum_excess_cancellation = bool(
        mono_sum_level_change_db < config.mono_sum_excess_cancellation_threshold_db
    )

    band_cancellations = []
    freqs_sum, psd_sum = _psd.compute_psd(mono_sum, sr)
    freqs_l, psd_l = _psd.compute_psd(left, sr)
    freqs_r, psd_r = _psd.compute_psd(right, sr)
    # welch() with identical nperseg/sr on equal-length signals returns
    # identical freqs arrays; per-channel-mean PSD is the simple average.
    psd_channel_mean = (psd_l + psd_r) / 2.0

    for band_key, band_hz in config.seven_bands_hz.items():
        resolved_band = (band_hz[0], band_hz[1] if band_hz[1] is not None else sr / 2.0)
        power_sum = _psd.band_power(freqs_sum, psd_sum, resolved_band)
        power_channel_mean = _psd.band_power(freqs_l, psd_channel_mean, resolved_band)
        delta_db = 10.0 * np.log10(max(power_sum, 1e-20) / max(power_channel_mean, 1e-20))
        excess_delta_db = float(delta_db) - _DECORRELATED_FLOOR_DB
        cancellation = excess_delta_db < config.mono_band_cancellation_excess_db
        band_cancellations.append(
            BandCancellation(
                band=band_key, range_hz=resolved_band,
                delta_db=float(delta_db), excess_delta_db=float(excess_delta_db),
                cancellation=bool(cancellation),
            )
        )

    return MonoSumResult(
        mono_sum_level_change_db=mono_sum_level_change_db,
        mono_sum_excess_cancellation=mono_sum_excess_cancellation,
        mono_sum_both_channels_silent=False,
        band_cancellations=band_cancellations,
    )
