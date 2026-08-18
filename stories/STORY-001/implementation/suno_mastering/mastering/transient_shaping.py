"""STORY-009 pipeline stage [5d]: `shape_transients`, wired to `suno_dsp`.

Config-gated, default off (architecture.md Section 1/7). Dynamics/glue tool
only -- this function must never be positioned, parameterised, or gated on
STORY-007's SMEARED_TRANSIENT detections (requirements.md "Rejected as out
of scope"; architecture.md Section 7 AC11/AC12). The signature below has no
parameter through which any detector/artifact-flag object could reach it --
that is a structural guard, not a comment.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import ShapeTransientsConfig


@dataclass
class TransientShapingAction:
    attack_boost_db: float
    sustain_cut_db: float
    peak_delta_db: float
    rms_delta_db: float


def _to_dsp_input(audio: np.ndarray) -> np.ndarray:
    """Explicit float64->float32 cast at the suno_dsp call boundary
    (architecture.md Section 2)."""
    return np.ascontiguousarray(audio, dtype=np.float32)


def _from_dsp_output(result: np.ndarray) -> np.ndarray:
    """Explicit float32->float64 cast immediately on the way back out of
    suno_dsp (architecture.md Section 2)."""
    return np.ascontiguousarray(result, dtype=np.float64)


def _db(ratio: float) -> float:
    if ratio <= 0.0:
        return float("-inf")
    return 20.0 * np.log10(ratio)


def _peak_rms_delta_db(original: np.ndarray, modified: np.ndarray) -> tuple[float, float]:
    orig_peak = float(np.max(np.abs(original))) if original.size else 0.0
    mod_peak = float(np.max(np.abs(modified))) if modified.size else 0.0
    orig_rms = float(np.sqrt(np.mean(np.square(original)))) if original.size else 0.0
    mod_rms = float(np.sqrt(np.mean(np.square(modified)))) if modified.size else 0.0

    peak_delta_db = _db(mod_peak) - _db(orig_peak) if orig_peak > 0.0 else 0.0
    rms_delta_db = _db(mod_rms) - _db(orig_rms) if orig_rms > 0.0 else 0.0
    return peak_delta_db, rms_delta_db


def apply_transient_shaping(
    audio: np.ndarray,
    sample_rate: int,
    config: ShapeTransientsConfig,
) -> tuple[np.ndarray, list]:
    """audio: float64, shape (n,) or (n, channels). Deliberately excludes
    any detector/artifact-flags parameter -- see AC11/AC12 guard above.

    The stereo-linked control signal (max(|L|,|R|) per sample, applied
    identically to both channels) and the 150 Hz detector-sidechain
    highpass ahead of rectification both live inside `suno_dsp.
    shape_transients` itself (src_cpp/spectral_repair.cpp) -- there is
    nothing left for this wrapper to link or filter; it only casts across
    the float32 boundary and logs before/after deltas.
    """
    import suno_dsp  # deferred: only imported when this stage actually runs

    dsp_input = _to_dsp_input(audio)
    dsp_output = suno_dsp.shape_transients(
        dsp_input, sample_rate, config.attack_boost_db, config.sustain_cut_db
    )
    output = _from_dsp_output(dsp_output)

    peak_delta_db, rms_delta_db = _peak_rms_delta_db(audio, output)

    # Report/log text describes this as dynamics shaping/glue only, never
    # as artifact repair or smearing correction (AC12) -- the field names
    # below are the entire vocabulary this stage emits.
    action = TransientShapingAction(
        attack_boost_db=config.attack_boost_db,
        sustain_cut_db=config.sustain_cut_db,
        peak_delta_db=peak_delta_db,
        rms_delta_db=rms_delta_db,
    )
    return output, [action]
