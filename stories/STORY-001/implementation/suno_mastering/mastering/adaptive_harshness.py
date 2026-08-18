from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import sosfiltfilt

from ..analysis.types import FrequencyBalanceResult


@dataclass
class AdaptiveHarshnessConfig:
    enabled: bool = False
    broad_threshold_db: float = 5.0
    narrow_threshold_db: float = 2.5
    broad_gain_db: float = -2.0
    narrow_gain_db: float = -3.0
    max_gain_db: float = 4.0


@dataclass
class AdaptiveHarshnessAction:
    method: str
    reason: str
    center_hz: float
    gain_db: float
    bandwidth_octaves: float | None = None


def _peaking_sos(sr: float, f0: float, gain_db: float, bandwidth_octaves: float):
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / sr
    sin_w0 = np.sin(w0)
    cos_w0 = np.cos(w0)
    alpha = sin_w0 * np.sinh((np.log(2) / 2) * bandwidth_octaves * (w0 / sin_w0))
    b0 = 1 + alpha * a
    b1 = -2 * cos_w0
    b2 = 1 - alpha * a
    a0 = 1 + alpha / a
    a1 = -2 * cos_w0
    a2 = 1 - alpha / a
    sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
    return sos


def _low_shelf_sos(sr: float, f0: float, gain_db: float):
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / sr
    sin_w0, cos_w0 = np.sin(w0), np.cos(w0)
    slope = 1.0
    alpha = (sin_w0 / 2) * np.sqrt((a + 1 / a) * (1 / slope - 1) + 2)
    two_sqrt_a_alpha = 2 * np.sqrt(a) * alpha
    b0 = a * ((a + 1) - (a - 1) * cos_w0 + two_sqrt_a_alpha)
    b1 = 2 * a * ((a - 1) - (a + 1) * cos_w0)
    b2 = a * ((a + 1) - (a - 1) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1) + (a - 1) * cos_w0 + two_sqrt_a_alpha
    a1 = -2 * ((a - 1) + (a + 1) * cos_w0)
    a2 = (a + 1) + (a - 1) * cos_w0 - two_sqrt_a_alpha
    sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
    return sos


def _band_center_hz(band_hz: tuple) -> float:
    lo, hi = band_hz
    return float(np.sqrt(lo * hi))


def _band_width_octaves(band_hz: tuple) -> float:
    lo, hi = band_hz
    return float(np.log2(hi / lo))


def apply_adaptive_harshness(
    audio: np.ndarray,
    sr: int,
    freq_balance: FrequencyBalanceResult,
    config: AdaptiveHarshnessConfig | None = None,
):
    config = config or AdaptiveHarshnessConfig()
    if not config.enabled:
        return audio.copy(), []

    if sr <= 0:
        raise ValueError("Invalid sample rate")

    out = audio.copy()
    actions: list[AdaptiveHarshnessAction] = []
    presence = freq_balance.presence_harsh
    deviation = float(presence.deviation_db)
    low_mid_deviation = float(freq_balance.low_mid_mud.deviation_db)

    if deviation >= config.broad_threshold_db and low_mid_deviation < config.narrow_threshold_db:
        gain_db = -min(abs(config.broad_gain_db), config.max_gain_db)
        f0 = 3500.0
        sos = _low_shelf_sos(sr, f0, gain_db)
        out = sosfiltfilt(sos, out, axis=0)
        actions.append(AdaptiveHarshnessAction(
            method="broad_shelf",
            reason="broad_brighness",
            center_hz=f0,
            gain_db=gain_db,
            bandwidth_octaves=None,
        ))
        return out, actions

    if deviation >= config.narrow_threshold_db:
        gain_db = -min(abs(config.narrow_gain_db), config.max_gain_db)
        f0 = _band_center_hz(presence.range_hz)
        bw = _band_width_octaves(presence.range_hz)
        sos = _peaking_sos(sr, f0, gain_db, bw)
        out = sosfiltfilt(sos, out, axis=0)
        actions.append(AdaptiveHarshnessAction(
            method="narrow_cut",
            reason="narrow_resonance",
            center_hz=f0,
            gain_db=gain_db,
            bandwidth_octaves=bw,
        ))

    return out, actions
