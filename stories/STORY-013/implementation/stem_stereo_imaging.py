from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import numpy as np
from scipy.signal import resample_poly


@dataclass(frozen=True)
class StemStereoAction:
    stem_name: str
    action_type: str
    width_before: float
    width_after: float
    correlation: float
    gain_db: float
    reason: str


def _as_float64(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim not in (1, 2):
        raise ValueError(f"Unsupported stem shape {arr.shape}; expected 1D or 2D audio")
    return arr


def _stereo_metrics(audio: np.ndarray) -> tuple[float, float]:
    if audio.ndim != 2 or audio.shape[1] != 2:
        return 0.0, 1.0

    left = audio[:, 0]
    right = audio[:, 1]
    if left.size == 0:
        return 0.0, 1.0

    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    mid_rms = float(np.sqrt(np.mean(mid ** 2)))
    side_rms = float(np.sqrt(np.mean(side ** 2)))
    width = side_rms / (mid_rms + 1e-9)

    if not np.isfinite(width):
        width = 0.0

    corr = float(np.corrcoef(left, right)[0, 1]) if left.size > 1 else 1.0
    if not np.isfinite(corr):
        corr = 1.0

    return width, corr


def _true_peak(audio: np.ndarray, oversample: int = 8) -> float:
    if audio.ndim == 1:
        arr = audio[np.newaxis, :]
    else:
        arr = audio
    up = np.empty((arr.shape[0], 0), dtype=np.float64)
    for ch in range(arr.shape[1]):
        ch_up = resample_poly(arr[:, ch], up=oversample, down=1)
        up = np.column_stack((up, ch_up)) if up.size else ch_up[:, np.newaxis]
    peak = float(np.max(np.abs(up))) if up.size else 0.0
    return peak


def _phase_guard(audio: np.ndarray) -> None:
    if audio.ndim != 2 or audio.shape[1] != 2:
        return
    width, corr = _stereo_metrics(audio)
    if corr < -0.2:
        raise ValueError(
            "Stem is phase-unstable; no stereo widening is applied to anti-correlated content."
        )
    if width > 1.3 and corr < 0.5:
        raise ValueError(
            "Stem exceeds safe stereo width and fails the phase/mono compatibility guard."
        )


def _is_silent(audio: np.ndarray) -> bool:
    if audio.size == 0:
        return True
    return float(np.max(np.abs(audio))) < 1e-7


def _stem_class(stem_name: str) -> str:
    s = stem_name.lower()
    if "kick" in s or "bass" in s:
        return "center"
    if "vocal" in s or "lead" in s:
        return "center"
    if "amb" in s or "pad" in s or "synth" in s or "fx" in s:
        return "wide"
    return "neutral"


def _apply_width_boost(audio: np.ndarray, boost: float) -> np.ndarray:
    left = audio[:, 0]
    right = audio[:, 1]
    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    widened_side = boost * side
    out = np.empty_like(audio, dtype=np.float64)
    out[:, 0] = mid + widened_side
    out[:, 1] = mid - widened_side
    return out


def apply_stem_stereo_imaging(
    stems: Dict[str, np.ndarray], sample_rate: int
) -> tuple[dict[str, np.ndarray], List[StemStereoAction]]:
    """Apply conservative stem-local stereo width or depth shaping.

    Policy:
      - Keep center-stable stems (kick, vocal, bass) anchored and no-op.
      - Widen only ambience, synth, and pad stems when there is enough real stereo
        information and the content remains mono-compatible.
      - Reject anti-correlated or phase-unstable content without manufacturing fake width.
      - Never create stereo information from mono or silence.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    processed: dict[str, np.ndarray] = {}
    actions: List[StemStereoAction] = []

    for stem_name, audio in stems.items():
        arr = _as_float64(audio)
        if arr.ndim == 1:
            processed[stem_name] = arr.copy()
            continue
        if arr.ndim != 2 or arr.shape[1] != 2:
            processed[stem_name] = arr.copy()
            continue

        if _is_silent(arr):
            processed[stem_name] = arr.copy()
            continue

        _phase_guard(arr)
        width_before, corr = _stereo_metrics(arr)

        stem_type = _stem_class(stem_name)
        if stem_type == "center":
            processed[stem_name] = arr.copy()
            continue

        if width_before <= 0.18:
            processed[stem_name] = arr.copy()
            continue
        if corr < -0.2:
            raise ValueError(
                f"Stem {stem_name} is phase-unstable and cannot be widened safely."
            )

        if stem_type == "wide":
            peak = float(np.max(np.abs(arr)))
            if peak > 0.95:
                arr = arr * (0.90 / max(peak, 1e-9))
                peak = float(np.max(np.abs(arr)))

            width_gain = max(1.0, min(1.8, 1.0 + 1.3 * width_before))
            out = _apply_width_boost(arr, width_gain)
            if _true_peak(out) > 1.0 + 1e-6:
                atten = 0.96 / max(_true_peak(out), 1e-9)
                out = out * atten
            width_after, _ = _stereo_metrics(out)
            if width_after <= width_before:
                processed[stem_name] = arr.copy()
                continue
            gain_db = 20.0 * np.log10(float(width_gain))
            processed[stem_name] = out
            actions.append(
                StemStereoAction(
                    stem_name=stem_name,
                    action_type="width_boost",
                    width_before=width_before,
                    width_after=width_after,
                    correlation=corr,
                    gain_db=gain_db,
                    reason=(
                        "Ambience/synth/pad stem had measurable but conservative stereo width "
                        "headroom and passed mono/phase safety checks; local widening was applied."
                    ),
                )
            )
            continue

        processed[stem_name] = arr.copy()

    return processed, actions
