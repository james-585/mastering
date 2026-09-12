"""Per-band stereo width narrowing — STORY-006 architecture §6.

Applies M/S side-gain reduction to the sub (20–60 Hz) and low (60–120 Hz)
bands only.  All correction parameters are read from the targets.json
stereo_width block (AC13 — no hardcoded spectral policy values).

Method (H6 — method change, not parameter change):
  1. 8th-order Butterworth bandpass isolates the target band in each channel.
  2. Per-band M/S decomposition and side gain g (derived from the CSD-based
     width estimator formula, §6.3).
  3. Delta (correction only) is added back to the full-band signal, avoiding
     phase/magnitude artefacts from full reconstruct (§6.5).

The gain formula (§6.3):
    w_target = max(aim_point, w_src - max_step)   # cap in width units
    g = sqrt(w_target * (2 - w_src) / (w_src * (2 - w_target)))

pre_widths comes from Stage [2] measure_per_band_stereo_width (§6.2).
No second width estimator is implemented in this module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from scipy.signal import butter, sosfiltfilt


# Fixed frequency bounds per the seven-band scheme (architecture §6.5)
_BAND_HZ: Dict[str, Tuple[float, float]] = {
    "sub": (20.0, 60.0),
    "low": (60.0, 120.0),
}


@dataclass
class WidthCorrectiveAction:
    """Log entry for one per-band stereo width correction.

    Field order matches architecture §7.2.  aim_point is the near_mono_threshold
    (0.15) — NOT the floor (0.10).  applied is negative (narrowing).
    resulting_value is arithmetic (w_src + applied = w_target).
    """
    band: str              # "sub" | "low"
    trigger: str           # "width_above_threshold"
    source_value: float    # pre-correction band width from pre_widths
    aim_point: float       # near_mono_threshold (0.15); never the floor (0.10)
    applied: float         # -(w_src - w_target) — negative = narrowing
    cap_reached: bool      # True when max_step was the binding constraint
    resulting_value: float # w_target = w_src + applied (arithmetic)


def _apply_band_narrowing(
    audio: np.ndarray,
    sr: int,
    band_hz: Tuple[float, float],
    g: float,
) -> np.ndarray:
    """Bandpass-isolate band, apply M/S side gain g, add delta back to full signal.

    Returns a new array; never mutates the input (architecture §13).
    """
    sos = butter(8, band_hz, btype="bandpass", fs=sr, output="sos")
    L_band = sosfiltfilt(sos, audio[:, 0])
    R_band = sosfiltfilt(sos, audio[:, 1])
    M_band = (L_band + R_band) / 2.0
    S_band = (L_band - R_band) / 2.0
    L_band_new = M_band + g * S_band
    R_band_new = M_band - g * S_band
    delta_L = L_band_new - L_band
    delta_R = R_band_new - R_band
    out = audio.copy()
    out[:, 0] += delta_L
    out[:, 1] += delta_R
    return out


def apply_stereo_width_correction(
    audio: np.ndarray,
    sr: int,
    targets: Dict,
    pre_widths: Dict[str, float],
) -> Tuple[np.ndarray, List[WidthCorrectiveAction]]:
    """Apply single-pass per-band stereo width narrowing for sub and low bands.

    audio: float64, shape (N, 2) stereo — mono raises ValueError.
    sr: sample rate in Hz.
    targets: parsed targets.json as dict (from TargetsDocument.to_dict()).
    pre_widths: band_name -> width float, from Stage [2] measure_per_band_stereo_width.

    Returns (audio_out, actions).  audio_out is unmodified if no band triggers.
    All correction parameters are read from targets["stereo_width"][band] (AC13).

    Gain formula (§6.3 — method change from DEF-603):
        w_target = max(aim_point, w_src - max_step)  # cap in width units
        g = sqrt(w_target * (2 - w_src) / (w_src * (2 - w_target)))
    Cap is applied in width units, then g is solved — never clamped directly.

    Post-condition assertion (§6.4): resulting_value >= correction_floor.
    This fires only on programmer error (floor is unreachable by construction
    when w_target = max(0.15, w_src - 0.15) >= 0.15 > 0.10).
    """
    if audio.ndim != 2 or audio.shape[1] != 2:
        raise ValueError(
            "per-band stereo width correction requires stereo audio; mono not supported"
        )

    # Normalise to dict in case a TargetsDocument is passed directly
    t = targets.to_dict() if hasattr(targets, "to_dict") else targets

    out = audio.copy()
    actions: List[WidthCorrectiveAction] = []

    width_spec = t["stereo_width"]

    for band in ("sub", "low"):
        band_params = width_spec[band]
        threshold = float(band_params["near_mono_threshold"])
        aim_point = float(band_params["correction_aim_point"])
        floor = float(band_params["correction_floor"])
        max_step = float(band_params["max_correction_step"])

        w_src = float(pre_widths.get(band, 0.0))
        if w_src <= threshold:
            continue

        # Apply cap in width units (not in g — architecture §6.3 critical note)
        w_target = max(aim_point, w_src - max_step)
        cap_reached = w_target > aim_point  # True when step cap was binding

        # Solve for M/S side gain (§6.3)
        g = math.sqrt(w_target * (2.0 - w_src) / (w_src * (2.0 - w_target)))

        out = _apply_band_narrowing(out, sr, _BAND_HZ[band], g)

        applied = -(w_src - w_target)        # negative = narrowing
        resulting_value = w_src + applied    # = w_target (arithmetic)

        # Post-condition: floor is unreachable by construction, assertion guards
        # against programmer error in the formula above (§6.4)
        assert resulting_value >= floor, (
            f"stereo_width_corrector: resulting_value {resulting_value:.4f} "
            f"is below correction_floor {floor:.4f} for band '{band}' "
            f"(w_src={w_src}, w_target={w_target}) — formula error"
        )

        actions.append(WidthCorrectiveAction(
            band=band,
            trigger="width_above_threshold",
            source_value=w_src,
            aim_point=aim_point,
            applied=applied,
            cap_reached=cap_reached,
            resulting_value=resulting_value,
        ))

    return out, actions
