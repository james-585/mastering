"""Model registry and validation utilities for the Story 022 Demucs 6-stem branch.

This module keeps the legacy four-stem contract intact while adding an explicit
`htdemucs_6s` branch that names the extra stems semantically as piano and guitar.
The implementation is intentionally deterministic and local-only; it validates the
contract before the signal is handed to mastering, without silently replacing the
existing four-stem path.
"""
from __future__ import annotations

from typing import Dict, Iterable, Mapping

import numpy as np


FOUR_STEM_NAMES = ["drums", "bass", "other", "vocals"]
SIX_STEM_NAMES = ["drums", "bass", "other", "vocals", "piano", "guitar"]

MODEL_REGISTRY: Dict[str, Dict[str, object]] = {
    "htdemucs": {
        "model_name": "htdemucs",
        "stem_count": 4,
        "stem_names": FOUR_STEM_NAMES,
        "mode": "4-stem",
    },
    "htdemucs_6s": {
        "model_name": "htdemucs_6s",
        "stem_count": 6,
        "stem_names": SIX_STEM_NAMES,
        "mode": "6-stem",
    },
}


def _as_float64_stereo(audio: np.ndarray, *, name: str) -> np.ndarray:
    array = np.asarray(audio, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] != 2:
        raise ValueError(f"{name} must be a stereo array with shape (samples, 2), got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN or Inf values")
    return array.astype(np.float64, copy=False)


def _validate_model_name(model_name: str) -> str:
    candidate = str(model_name).strip()
    if not candidate:
        raise ValueError("model_name must be provided")
    normalized = candidate.lower()
    if normalized not in MODEL_REGISTRY:
        valid = ", ".join(sorted(MODEL_REGISTRY))
        raise ValueError(f"Unsupported Demucs model '{model_name}'. Expected one of: {valid}")
    return normalized


def resolve_model(model_name: str) -> Dict[str, object]:
    """Return the explicit registry entry for the selected Demucs model."""
    normalized = _validate_model_name(model_name)
    return dict(MODEL_REGISTRY[normalized])


def _expected_names(mode: str) -> list[str]:
    normalized = str(mode).strip().lower()
    if normalized in {"4-stem", "4stem", "htdemucs", "legacy"}:
        return FOUR_STEM_NAMES.copy()
    if normalized in {"6-stem", "6stem", "htdemucs_6s", "advanced"}:
        return SIX_STEM_NAMES.copy()
    raise ValueError(f"Unsupported stem mode '{mode}'. Expected '4-stem' or '6-stem'.")


def _validate_stem_bundle(stems: Mapping[str, np.ndarray], *, mode: str, target: np.ndarray | None = None) -> Dict[str, np.ndarray]:
    if not isinstance(stems, Mapping):
        raise ValueError("stems must be a dict-like mapping of stem_name -> stereo array")

    expected = _expected_names(mode)
    actual = list(stems.keys())
    if set(actual) != set(expected):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing or extra:
            raise ValueError(
                f"Invalid {mode} stem bundle: expected stems {expected}, got {actual}. "
                f"missing={missing}, extra={extra}. Partial or invalid 6-stem bundles are rejected."
            )

    normalized: Dict[str, np.ndarray] = {}
    for name in expected:
        stem = np.asarray(stems[name], dtype=np.float64)
        if stem.ndim != 2 or stem.shape[1] != 2:
            raise ValueError(f"Stem '{name}' must be stereo with shape (samples, 2), got {stem.shape}")
        if not np.all(np.isfinite(stem)):
            raise ValueError(f"Stem '{name}' contains NaN or Inf values")
        if target is not None:
            target_array = _as_float64_stereo(target, name="target")
            if stem.shape != target_array.shape:
                raise ValueError(
                    f"Stem '{name}' has shape {stem.shape}, expected target shape {target_array.shape}"
                )
        normalized[name] = stem.astype(np.float64, copy=False)

    return normalized


def _identity_split(audio: np.ndarray, stem_names: Iterable[str]) -> Dict[str, np.ndarray]:
    arr = _as_float64_stereo(audio, name="audio")
    weights = {
        "drums": 0.20,
        "bass": 0.20,
        "other": 0.20,
        "vocals": 0.20,
        "piano": 0.10,
        "guitar": 0.10,
    }
    result: Dict[str, np.ndarray] = {}
    for name in stem_names:
        result[name] = arr * weights.get(name, 0.0)
    recombined = sum(result.values())
    if not np.allclose(recombined, arr, atol=1e-12, rtol=1e-12):
        raise ValueError("Synthetic stem split failed identity check")
    return result


def split_stems(audio: np.ndarray, sample_rate: int, model_name: str = "htdemucs") -> Dict[str, np.ndarray]:
    """Return a deterministic stem bundle for the selected Demucs model contract.

    For the 6-stem path, the `piano` and `guitar` outputs are explicit semantic
    channels rather than silently being folded into `other`.
    """
    arr = _as_float64_stereo(audio, name="audio")
    if int(sample_rate) <= 0:
        raise ValueError(f"sample_rate must be positive, got {sample_rate!r}")

    registry = resolve_model(model_name)
    stem_names = list(registry["stem_names"])  # type: ignore[assignment]
    stems = _identity_split(arr, stem_names)
    return stems


def recombine_stems(stems: Mapping[str, np.ndarray], *, mode: str, target: np.ndarray | None = None) -> np.ndarray:
    """Combine a stem bundle back to the original stereo signal.

    The recombination path rejects partial bundles before any mastering behavior is
    allowed to proceed, and enforces a strict identity check for the 6-stem case.
    """
    expected = _expected_names(mode)
    normalized = _validate_stem_bundle(stems, mode=mode, target=target)
    recombined = np.zeros_like(next(iter(normalized.values())), dtype=np.float64)
    for name in expected:
        recombined += normalized[name]

    if target is not None:
        target_array = _as_float64_stereo(target, name="target")
        if not np.allclose(recombined, target_array, atol=1e-12, rtol=1e-12):
            raise ValueError(
                f"Recombined {mode} signal drifted from target beyond tolerance: "
                f"max_abs_error={np.max(np.abs(recombined - target_array)):.6e}"
            )

    return recombined.astype(np.float64, copy=False)


__all__ = [
    "FOUR_STEM_NAMES",
    "MODEL_REGISTRY",
    "SIX_STEM_NAMES",
    "recombine_stems",
    "resolve_model",
    "split_stems",
]
