"""Band-energy vs. genre-reference-curve analysis (architecture.md Section
2: scipy.signal.welch + numpy).

Thresholds and the reference curve itself are resolved values (requirements
.md Section 2 / architecture.md Section 8 item 1):
  - low-end (20-120Hz):     reference -1.5dB; thin low-end when measured <
                            reference - 4.0dB (i.e. below -5.5dB relative).
  - low-mid/mud (200-500Hz): reference -3.0dB; muddiness when measured >
                            reference + 3.0dB (i.e. above 0.0dB relative).
  - presence/harsh (2-5kHz): reference -4.0dB; harshness when measured >
                            reference + 3.0dB (i.e. above -1.0dB relative).
All levels are expressed in dB relative to the 500Hz-2kHz reference band's
own average energy.
"""
from __future__ import annotations

import numpy as np

from ._psd import band_power as _band_power
from ._psd import compute_psd as _compute_psd
from .silence import extract_active_audio
from .types import BandMeasurement, FrequencyBalanceResult

_MIN_POWER = 1e-20


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=1)


def measure_frequency_balance(audio: np.ndarray, sr: int, config) -> FrequencyBalanceResult:
    mono = _to_mono(audio)
    active = extract_active_audio(
        mono, sr, block_ms=config.silence_block_ms, threshold_db=config.silence_gate_threshold_db
    )
    if active.size < 8:
        active = mono  # degenerate/very short input: fall back to whatever we have

    freqs, psd = _compute_psd(active, sr)

    ref_power = _band_power(freqs, psd, config.freq_reference_band_hz)
    ref_curve = config.reference_curve()

    def make_band(key: str, band_hz: tuple, ref_key: str, threshold_db: float, direction: str, flag_name: str) -> BandMeasurement:
        power = _band_power(freqs, psd, band_hz)
        relative_db = 10.0 * np.log10(power / ref_power)
        reference_db = float(ref_curve["bands"][ref_key]["relative_db"])
        deviation_db = relative_db - reference_db
        if direction == "below":
            flagged = deviation_db < -threshold_db
        else:
            flagged = deviation_db > threshold_db
        return BandMeasurement(
            range_hz=band_hz,
            relative_db=float(relative_db),
            reference_db=reference_db,
            deviation_db=float(deviation_db),
            flagged=bool(flagged),
            flag_name=flag_name if flagged else None,
        )

    low_end = make_band(
        "low_end", config.freq_low_band_hz, "low_end",
        config.thin_low_end_threshold_db, "below", "thin_low_end",
    )
    low_mid_mud = make_band(
        "low_mid_mud", config.freq_mud_band_hz, "low_mid_mud",
        config.muddiness_threshold_db, "above", "muddiness",
    )
    presence_harsh = make_band(
        "presence_harsh", config.freq_presence_band_hz, "presence_harsh",
        config.harshness_threshold_db, "above", "harshness",
    )

    return FrequencyBalanceResult(
        low_end=low_end, low_mid_mud=low_mid_mud, presence_harsh=presence_harsh
    )
