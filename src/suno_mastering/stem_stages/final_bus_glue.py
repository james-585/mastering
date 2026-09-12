from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
from scipy.signal import resample_poly


@dataclass(frozen=True)
class FinalBusGlueAction:
    stem_name: str
    action_type: str
    gain_db: float
    before_peak: float
    after_peak: float
    before_lufs: float | None
    after_lufs: float | None
    reason: str


def _as_float64(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim not in (1, 2):
        raise ValueError(f"Unsupported bus shape {arr.shape}; expected 1D or 2D audio")
    return arr


def _mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio.astype(np.float64, copy=False)
    return np.mean(audio, axis=1).astype(np.float64)


def _true_peak(audio: np.ndarray, oversample: int = 8) -> float:
    arr = _as_float64(audio)
    mono = _mono(arr)
    if mono.size == 0:
        return 0.0
    if oversample <= 1:
        return float(np.max(np.abs(mono)))
    x = np.arange(mono.size, dtype=np.float64)
    up = np.arange(0, mono.size, 1.0 / oversample, dtype=np.float64)
    oversampled = np.interp(up, x, mono)
    return float(np.max(np.abs(oversampled)))


def _stereo_metrics(audio: np.ndarray) -> tuple[float, float]:
    arr = _as_float64(audio)
    if arr.ndim != 2 or arr.shape[1] != 2:
        return 0.0, 1.0
    left = arr[:, 0]
    right = arr[:, 1]
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    mid_rms = float(np.sqrt(np.mean(mid ** 2)))
    side_rms = float(np.sqrt(np.mean(side ** 2)))
    width = side_rms / (mid_rms + 1e-9)
    corr = float(np.corrcoef(left, right)[0, 1]) if left.size > 1 else 1.0
    if not np.isfinite(corr):
        corr = 1.0
    if not np.isfinite(width):
        width = 0.0
    return float(width), float(corr)


def _recombine_mix(stems: Dict[str, np.ndarray]) -> np.ndarray:
    if "mix" in stems:
        return _as_float64(stems["mix"]).copy()
    if not stems:
        raise ValueError("No stems provided for final bus glue")

    first = _as_float64(next(iter(stems.values())))
    shape = first.shape
    mix = np.zeros(shape, dtype=np.float64)
    for audio in stems.values():
        arr = _as_float64(audio)
        if arr.shape != shape:
            raise ValueError(f"Stem shape mismatch in final mix recombination: {arr.shape} vs {shape}")
        mix = mix + arr
    return mix


def _already_cohesive(audio: np.ndarray) -> bool:
    peak = _true_peak(audio)
    if peak < 0.15:
        return True
    width, corr = _stereo_metrics(audio)
    if audio.ndim == 2 and width < 0.12 and corr > 0.85 and peak < 0.55:
        return True
    if audio.ndim == 2 and width < 0.18 and corr > 0.9 and peak < 0.45:
        return True
    return False


def _bus_glue(audio: np.ndarray, amount: float) -> np.ndarray:
    arr = _as_float64(audio)
    if arr.ndim != 2 or arr.shape[1] != 2:
        return arr.copy()
    left = arr[:, 0].copy()
    right = arr[:, 1].copy()
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    tightened_side = side * (1.0 - amount)
    out = np.empty_like(arr, dtype=np.float64)
    out[:, 0] = mid + tightened_side
    out[:, 1] = mid - tightened_side
    return out


def _dynamic_balance(audio: np.ndarray, gain_db: float) -> np.ndarray:
    arr = _as_float64(audio)
    gain = 10.0 ** (gain_db / 20.0)
    out = arr * gain
    return out


def apply_final_bus_glue(stems: Dict[str, np.ndarray], sample_rate: int) -> tuple[dict[str, np.ndarray], List[FinalBusGlueAction]]:
    """Apply conservative final bus glue and dynamic balancing.

    The stage is intentionally conservative: it remains a no-op when the recombined mix is
    already cohesive, and it uses oversampled true-peak safeguarding before final output.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    processed: dict[str, np.ndarray] = {}
    actions: List[FinalBusGlueAction] = []

    mix = _recombine_mix(stems)
    before_peak = _true_peak(mix)
    if _already_cohesive(mix):
        processed["mix"] = mix.copy()
        return processed, actions

    width_before, corr = _stereo_metrics(mix)
    gain_db = 0.0
    out = mix.copy()
    reason = ""

    if mix.ndim == 2 and width_before > 0.30 and corr < 0.82:
        glue_amount = min(0.20, 0.06 + 0.12 * (width_before - 0.30))
        out = _bus_glue(out, glue_amount)
        gain_db -= 1.2 + 1.5 * glue_amount
        reason = "Bus glue tightened diffuse stereo and stabilized the overall image without flattening transients."
    elif mix.ndim == 2 and width_before > 0.12 and corr > 0.65:
        balance_gain = -min(1.2, max(0.2, 0.75 * (width_before - 0.12)))
        out = _dynamic_balance(out, balance_gain)
        gain_db += balance_gain
        reason = "Dynamic balance trimmed a slightly over-energetic bus to preserve contour and keep the mix from feeling loose or unstable."
    elif before_peak > 0.92:
        safety_gain = -min(4.0, max(1.0, 20.0 * np.log10(0.92 / max(before_peak, 1e-9))))
        out = _dynamic_balance(out, safety_gain)
        gain_db += safety_gain
        reason = "Safety attenuation reduced the risk of transients exceeding the true-peak ceiling."

    after_peak = _true_peak(out)
    if after_peak > 1.0 + 1e-6:
        attenuation = 0.96 / max(after_peak, 1e-9)
        out = out * attenuation
        gain_db += 20.0 * np.log10(float(attenuation))
        reason = "True-peak check required a final safety collapse to keep the bus under the project ceiling."

    if np.allclose(out, mix, atol=1e-12, rtol=0.0):
        processed["mix"] = mix.copy()
        return processed, actions

    processed["mix"] = out
    action_type = "bus_glue" if "glue" in reason.lower() else "dynamic_balance"
    if "peak" in reason.lower() or "safety" in reason.lower():
        action_type = "safety_attenuation"

    actions.append(
        FinalBusGlueAction(
            stem_name="mix",
            action_type=action_type,
            gain_db=float(gain_db),
            before_peak=float(before_peak),
            after_peak=float(after_peak),
            before_lufs=None,
            after_lufs=None,
            reason=reason,
        )
    )

    return processed, actions
