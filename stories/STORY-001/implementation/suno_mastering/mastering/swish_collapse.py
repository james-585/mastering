"""STORY-009 pipeline stage [5c]: `collapse_swish`, wired to `suno_dsp`.

Config-gated, default off, manually-enabled only -- never auto-triggered by
STORY-007's PHASE_SWISH detector flags (architecture.md Section 8; CLAUDE.md
§4.2a's exception is narrow and does not extend to PHASE_SWISH per
requirements.md "Explicit out-of-scope"). `artifact_detection` is consumed
only to append advisory PHASE_SWISH context to the action log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..analysis.types import ArtifactDetectionResult
from ..config import CollapseSwishConfig
from ..errors import MasteringConfigError
from ..reference_analysis.config import SEVEN_BANDS_HZ

_Q = 0.7071067811865476  # Butterworth Q, matches suno_dsp's deployed biquad


@dataclass
class BandSkirtOverlap:
    band_name: str
    band_range_hz: list
    skirt_severity: str  # "unaffected" | "partial(-1..-3dB)" | "significant(>=-3dB)"


@dataclass
class CollapseSwishAction:
    cutoff_freq_hz: float
    side_energy_delta_db: float
    phase_swish_flags_present: int
    overlapping_5a_bands: list


def _to_dsp_input(audio: np.ndarray) -> np.ndarray:
    """Explicit float64->float32 cast at the suno_dsp call boundary
    (architecture.md Section 2)."""
    return np.ascontiguousarray(audio, dtype=np.float32)


def _from_dsp_output(result: np.ndarray) -> np.ndarray:
    """Explicit float32->float64 cast immediately on the way back out of
    suno_dsp (architecture.md Section 2)."""
    return np.ascontiguousarray(result, dtype=np.float64)


def _lowpass_biquad_coeffs(cutoff_freq_hz: float, sample_rate: int) -> tuple:
    """RBJ lowpass biquad, Q=0.7071 -- exact coefficient set deployed inside
    suno_dsp.collapse_swish (src_cpp/spectral_repair.cpp), reproduced here
    in float64 so the -1dB/-3dB points below are computed from the actual
    deployed digital filter, not the analog Butterworth prototype
    (architecture.md Section 8)."""
    omega = 2.0 * np.pi * cutoff_freq_hz / sample_rate
    sin_w = np.sin(omega)
    cos_w = np.cos(omega)
    alpha = sin_w / (2.0 * _Q)

    b0 = (1.0 - cos_w) * 0.5
    b1 = 1.0 - cos_w
    b2 = (1.0 - cos_w) * 0.5
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w
    a2 = 1.0 - alpha

    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _magnitude_response_db(coeffs: tuple, freqs_hz: np.ndarray, sample_rate: int) -> np.ndarray:
    """|H(e^jw)| in dB, evaluated numerically from the deployed biquad's
    own b0,b1,b2,a1,a2 coefficients (architecture.md Section 8: the digital
    biquad is a bilinear-transform warp of the analog prototype, so the
    analog `0.713*fc` formula is a cross-check only, not the value used)."""
    b0, b1, b2, a1, a2 = coeffs
    omega = 2.0 * np.pi * freqs_hz / sample_rate
    z_inv = np.exp(-1j * omega)
    numerator = b0 + b1 * z_inv + b2 * z_inv**2
    denominator = 1.0 + a1 * z_inv + a2 * z_inv**2
    magnitude = np.abs(numerator / denominator)
    with np.errstate(divide="ignore"):
        return 20.0 * np.log10(np.maximum(magnitude, 1e-12))


def _find_skirt_points(cutoff_freq_hz: float, sample_rate: int) -> tuple[float, float]:
    """Numerically locate f_-1dB and f_-3dB on the deployed biquad's own
    response (architecture.md Section 8). The response is monotonically
    non-increasing from 0 dB at DC (Q=0.7071, no resonant peak), so a fine
    linear grid search from DC to Nyquist is sufficient and exact enough
    for report classification purposes."""
    coeffs = _lowpass_biquad_coeffs(cutoff_freq_hz, sample_rate)
    nyquist = sample_rate / 2.0
    grid = np.linspace(0.0, nyquist, 20001)
    response_db = _magnitude_response_db(coeffs, grid, sample_rate)

    idx_minus1 = np.searchsorted(-response_db, 1.0)  # first index where response_db <= -1
    idx_minus3 = np.searchsorted(-response_db, 3.0)  # first index where response_db <= -3

    f_minus1db = float(grid[min(idx_minus1, len(grid) - 1)])
    f_minus3db = float(grid[min(idx_minus3, len(grid) - 1)])
    # f_minus3db is exactly cutoff_freq_hz by construction (Q=0.7071); the
    # numeric search should land very close to it -- not asserted here,
    # left as a cross-check for test-case-writer.
    return f_minus1db, f_minus3db


def _classify_band(band_lo_hz: float, band_hi_hz: float, f_minus1db: float, f_minus3db: float) -> str:
    if band_hi_hz <= f_minus1db:
        return "unaffected"
    if band_lo_hz >= f_minus3db:
        return "significant(>=-3dB)"
    return "partial(-1..-3dB)"


def _overlapping_bands(cutoff_freq_hz: float, sample_rate: int) -> list:
    """Classifies each of the seven-band scheme's bands (the existing
    per-band definitions that feed Stage [5a]'s width measurement/
    correction -- reference_analysis.config.SEVEN_BANDS_HZ) against
    collapse_swish's numerically-derived -1dB/-3dB skirt points. Only
    bands that are at least partially inside the skirt are included
    (architecture.md Section 8/11, Blocker 8 revision)."""
    f_minus1db, f_minus3db = _find_skirt_points(cutoff_freq_hz, sample_rate)
    nyquist = sample_rate / 2.0

    overlaps = []
    for band_name, (lo, hi) in SEVEN_BANDS_HZ.items():
        resolved_hi = hi if hi is not None else nyquist
        severity = _classify_band(lo, resolved_hi, f_minus1db, f_minus3db)
        if severity != "unaffected":
            overlaps.append(
                BandSkirtOverlap(
                    band_name=band_name,
                    band_range_hz=[lo, resolved_hi],
                    skirt_severity=severity,
                )
            )
    return overlaps


def _side_energy_db(audio: np.ndarray) -> float:
    side = (audio[:, 0] - audio[:, 1]) / 2.0
    rms = float(np.sqrt(np.mean(np.square(side)))) if side.size else 0.0
    if rms <= 0.0:
        return float("-inf")
    return 20.0 * np.log10(rms)


def apply_collapse_swish(
    audio: np.ndarray,
    sample_rate: int,
    config: CollapseSwishConfig,
    artifact_detection: Optional[ArtifactDetectionResult] = None,
) -> tuple[np.ndarray, list]:
    """audio: float64, shape (n, 2) -- stereo only. `artifact_detection` is
    advisory-only: it never gates or parameterises the call into
    suno_dsp.collapse_swish (architecture.md Section 8)."""
    if config.cutoff_freq_hz <= 0.0:
        raise MasteringConfigError(
            "collapse_swish.enabled=True requires cutoff_freq_hz to be set "
            "explicitly (> 0.0, below Nyquist) -- see architecture.md "
            "Section 8/9, Blocker 6."
        )

    phase_swish_count = 0
    if artifact_detection is not None:
        phase_swish_count = sum(
            1 for f in artifact_detection.artifact_flags if f.artifact_type == "PHASE_SWISH"
        )

    if audio.ndim != 2 or audio.shape[1] != 2:
        action = CollapseSwishAction(
            cutoff_freq_hz=config.cutoff_freq_hz,
            side_energy_delta_db=0.0,
            phase_swish_flags_present=phase_swish_count,
            overlapping_5a_bands=[],
        )
        return audio, [{"skipped": "not stereo"}, action]

    import suno_dsp  # deferred: only imported when this stage actually runs

    side_energy_before_db = _side_energy_db(audio)

    dsp_input = _to_dsp_input(audio)
    dsp_output = suno_dsp.collapse_swish(dsp_input, sample_rate, config.cutoff_freq_hz)
    output = _from_dsp_output(dsp_output)

    side_energy_after_db = _side_energy_db(output)
    if side_energy_before_db == float("-inf") or side_energy_after_db == float("-inf"):
        side_energy_delta_db = 0.0
    else:
        side_energy_delta_db = side_energy_after_db - side_energy_before_db

    overlapping_bands = _overlapping_bands(config.cutoff_freq_hz, sample_rate)

    action = CollapseSwishAction(
        cutoff_freq_hz=config.cutoff_freq_hz,
        side_energy_delta_db=side_energy_delta_db,
        phase_swish_flags_present=phase_swish_count,
        overlapping_5a_bands=overlapping_bands,
    )
    return output, [action]
