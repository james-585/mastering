from __future__ import annotations

from typing import Any

import numpy as np
from scipy.linalg import inv


_M_S_MATRIX = np.array([[0.5, 0.5], [0.5, -0.5]], dtype=np.float64)
_M_S_MATRIX_INV = inv(_M_S_MATRIX)


def _as_float64_stereo(audio: np.ndarray, *, name: str = "audio") -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"{name} must be a valid stereo array with shape (samples, 2)")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains NaN or Inf values")
    return arr


def _clip_guard(signal: np.ndarray, *, limit: float = 0.999999) -> None:
    peak = float(np.max(np.abs(signal))) if signal.size else 0.0
    if peak > limit:
        raise ValueError(f"Clipping safety guard failed: peak {peak:.6f} exceeds limit {limit:.6f}")


def encode_ms(stereo: np.ndarray) -> np.ndarray:
    """Encode stereo left/right signal into deterministic mid/side coordinates."""
    arr = _as_float64_stereo(stereo, name="stereo")
    encoded = arr @ _M_S_MATRIX.T
    _clip_guard(encoded)
    return encoded.astype(np.float64, copy=False)


def decode_ms(ms: np.ndarray) -> np.ndarray:
    """Decode deterministic mid/side representation back to left/right."""
    arr = _as_float64_stereo(ms, name="ms")
    decoded = arr @ _M_S_MATRIX_INV.T
    _clip_guard(decoded)
    return decoded.astype(np.float64, copy=False)


def _identity_bypass(stem: np.ndarray) -> np.ndarray:
    return stem


def _phase_null_check(stem: np.ndarray, *, tolerance: float = 1e-12) -> float:
    if stem.ndim != 2 or stem.shape[1] != 2:
        raise ValueError("phase null-check requires a stereo array with shape (samples, 2)")
    if stem.size == 0:
        return 0.0
    residual = float(np.max(np.abs(stem[:, 0] + stem[:, 1])))
    if not np.isfinite(residual):
        raise ValueError("Phase null-check produced non-finite residual")
    if residual > tolerance:
        raise ValueError(f"Phase null-check exceeded tolerance: residual={residual} > {tolerance}")
    return residual


def process_other_stem(
    stems: dict[str, np.ndarray],
    *,
    bypass: bool = False,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, np.ndarray]:
    """Process only the Demucs `other` stem with an explicit M/S transform and bypass identity branch."""
    if not isinstance(stems, dict):
        raise ValueError("stems must be a dict of stem_name -> stereo arrays")
    if "other" not in stems:
        raise ValueError("stems must include an 'other' stem")

    other = np.asarray(stems["other"], dtype=np.float64)
    other = _as_float64_stereo(other, name="other")

    result = dict(stems)
    status = "bypassed" if bypass else "active"
    if diagnostics is not None:
        diagnostics["status"] = status
        diagnostics["dtype"] = "float64"
        diagnostics["output_peak"] = float(np.max(np.abs(other))) if other.size else 0.0

    if bypass:
        result["other"] = _identity_bypass(other)
        if diagnostics is not None:
            diagnostics["residual"] = 0.0
            diagnostics["safety"] = "pass"
        return result

    encoded = encode_ms(other)
    decoded = decode_ms(encoded)
    residual = float(np.max(np.abs(decoded - other)))
    if residual > 1e-12:
        raise ValueError(f"M/S round-trip drift too large: max abs error {residual} > 1e-12")

    result["other"] = decoded
    if diagnostics is not None:
        diagnostics["residual"] = residual
        diagnostics["safety"] = "pass"
    return result
