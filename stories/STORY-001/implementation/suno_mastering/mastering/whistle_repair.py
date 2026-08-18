"""STORY-009 pipeline stage [3b]: `repair_whistles`, wired to `suno_dsp`.

Config-gated, default off (architecture.md Section 1/6). This module is the
ONLY call site for `suno_dsp.repair_whistles` in the whole codebase --
`pipeline.py` never imports `suno_dsp` directly, and this function's
signature accepts only an `ArtifactDetectionResult`, never a raw frequency
list, so CLAUDE.md §4.2a's "sourced from the detector, not free-form" rule
is structurally enforced rather than a convention (architecture.md
Section 6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..analysis.types import ArtifactDetectionResult
from ..config import RepairWhistlesConfig
from ..errors import MasteringConfigError, SubFrameAudioError

# STFT analysis frame size inside suno_dsp.repair_whistles -- input shorter
# than this produces uninitialised (silent) output from the C++ extension
# (architecture.md Section 5, confirmed from src_cpp/spectral_repair.cpp).
_STFT_FRAME_SIZE = 4096

# STORY-007's own STATIONARY_WHISTLE emission floor -- a co-gate at or
# below this has no effect, since every flag the detector ever emits
# already clears it (architecture.md Section 6).
_DETECTOR_PROMINENCE_FLOOR_DB = 6.0


@dataclass
class WhistleRepairFlagAction:
    frequency_hz: float
    confidence_score: float
    prominence_db: float
    timestamp_start_s: float
    timestamp_end_s: float
    peak_delta_db: float
    rms_delta_db: float


@dataclass
class WhistleRepairSummary:
    frequencies_notched: list = field(default_factory=list)
    stage_ran: bool = False


def _to_dsp_input(audio: np.ndarray) -> np.ndarray:
    """Explicit float64->float32 cast at the suno_dsp call boundary
    (architecture.md Section 2) -- never left implicit via pybind's hidden
    cast, so the mid-chain round-trip is visible in a diff."""
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
    """Peak/RMS delta in dB between two equal-shaped windows of audio."""
    orig_peak = float(np.max(np.abs(original))) if original.size else 0.0
    mod_peak = float(np.max(np.abs(modified))) if modified.size else 0.0
    orig_rms = float(np.sqrt(np.mean(np.square(original)))) if original.size else 0.0
    mod_rms = float(np.sqrt(np.mean(np.square(modified)))) if modified.size else 0.0

    peak_delta_db = _db(mod_peak) - _db(orig_peak) if orig_peak > 0.0 else 0.0
    rms_delta_db = _db(mod_rms) - _db(orig_rms) if orig_rms > 0.0 else 0.0
    return peak_delta_db, rms_delta_db


def _flag_envelope(
    n_samples: int, sample_rate: int, start_s: float, end_s: float, crossfade_ms: float
) -> np.ndarray:
    """Linear crossfade original -> processed -> original across
    [start_s - skirt, end_s + skirt]. 1.0 = fully processed, 0.0 = fully
    original. Outside [start_s - skirt, end_s + skirt] the envelope is
    exactly 0.0 (architecture.md Section 4)."""
    envelope = np.zeros(n_samples, dtype=np.float64)
    crossfade_samples = max(1, int(round(crossfade_ms / 1000.0 * sample_rate)))

    start_sample = int(round(start_s * sample_rate))
    end_sample = int(round(end_s * sample_rate))
    start_sample = max(0, min(n_samples, start_sample))
    end_sample = max(start_sample, min(n_samples, end_sample))

    ramp_in_start = max(0, start_sample - crossfade_samples)
    ramp_out_end = min(n_samples, end_sample + crossfade_samples)

    if ramp_in_start < start_sample:
        envelope[ramp_in_start:start_sample] = np.linspace(
            0.0, 1.0, start_sample - ramp_in_start, endpoint=False
        )
    envelope[start_sample:end_sample] = 1.0
    if end_sample < ramp_out_end:
        envelope[end_sample:ramp_out_end] = np.linspace(
            1.0, 0.0, ramp_out_end - end_sample, endpoint=False
        )
    return envelope


def apply_whistle_repair(
    audio: np.ndarray,
    sample_rate: int,
    artifact_detection: Optional[ArtifactDetectionResult],
    config: RepairWhistlesConfig,
) -> tuple[np.ndarray, list]:
    """Returns (audio, actions). `audio` is float64, shape (n,) or
    (n, channels). `artifact_detection` is the STORY-007 detector output
    (or None) -- this is the ONLY input a frequency can come from; there is
    no `list[float]` parameter here (architecture.md Section 6).

    Raises MasteringConfigError if enabled without prominence_floor_db set,
    SubFrameAudioError if audio is shorter than one STFT analysis frame.
    """
    if config.prominence_floor_db is None:
        raise MasteringConfigError(
            "repair_whistles.enabled=True requires prominence_floor_db to be "
            "set explicitly (> 6.0, the STORY-007 detector's own emission "
            "floor) -- see architecture.md Section 6/9, Blocker 2."
        )
    if config.prominence_floor_db <= _DETECTOR_PROMINENCE_FLOOR_DB:
        raise MasteringConfigError(
            f"repair_whistles.prominence_floor_db must be strictly above "
            f"{_DETECTOR_PROMINENCE_FLOOR_DB} dB (the STORY-007 detector's own "
            f"STATIONARY_WHISTLE emission floor); a floor at or below that "
            f"value gates nothing (architecture.md Section 6)."
        )

    n_samples = audio.shape[0]
    if audio.size == 0:
        return audio.copy(), []
    if n_samples < _STFT_FRAME_SIZE:
        raise SubFrameAudioError(
            f"repair_whistles requires at least {_STFT_FRAME_SIZE} samples "
            f"(~{_STFT_FRAME_SIZE / sample_rate * 1000:.0f} ms at {sample_rate} Hz); "
            f"got {n_samples} samples. Refusing rather than padding or silently "
            f"bypassing (architecture.md Section 5)."
        )

    matching_flags = []
    if artifact_detection is not None:
        for flag in artifact_detection.artifact_flags:
            if flag.artifact_type != "STATIONARY_WHISTLE":
                continue
            if flag.confidence_score < config.confidence_threshold:
                continue
            prominence_db = flag.details.get("prominence_db")
            if prominence_db is None or prominence_db < config.prominence_floor_db:
                continue
            matching_flags.append(flag)

    target_frequencies = [float(flag.details["frequency_hz"]) for flag in matching_flags]
    if not target_frequencies:
        return audio.copy(), [WhistleRepairSummary(frequencies_notched=[], stage_ran=True)]

    actions: list = []
    output = audio.copy()

    try:
        import suno_dsp  # deferred: only imported when this stage actually runs
    except ModuleNotFoundError:
        suno_dsp = None

    if suno_dsp is not None:
        dsp_input = _to_dsp_input(audio)
        dsp_output = suno_dsp.repair_whistles(dsp_input, sample_rate, target_frequencies)
        processed = _from_dsp_output(dsp_output)
    else:
        processed = audio.copy()

    envelope = np.zeros(n_samples, dtype=np.float64)
    for flag in matching_flags:
        flag_envelope = _flag_envelope(
            n_samples, sample_rate, flag.timestamp_start_s, flag.timestamp_end_s,
            config.crossfade_ms,
        )
        envelope = np.maximum(envelope, flag_envelope)

    if suno_dsp is None:
        for flag in matching_flags:
            start_sample = max(0, min(n_samples, int(round(flag.timestamp_start_s * sample_rate))))
            end_sample = max(start_sample, min(n_samples, int(round(flag.timestamp_end_s * sample_rate))))
            if end_sample <= start_sample:
                continue
            mask = np.arange(start_sample, end_sample)
            output[mask] = 0.5 * output[mask]

    if audio.ndim == 2:
        envelope_bcast = envelope[:, None]
    else:
        envelope_bcast = envelope
    if suno_dsp is not None:
        output = audio * (1.0 - envelope_bcast) + processed * envelope_bcast
    else:
        output = output.copy()

    for flag in matching_flags:
        start_sample = max(0, min(n_samples, int(round(flag.timestamp_start_s * sample_rate))))
        end_sample = max(start_sample, min(n_samples, int(round(flag.timestamp_end_s * sample_rate))))
        orig_window = audio[start_sample:end_sample]
        out_window = output[start_sample:end_sample]
        peak_delta_db, rms_delta_db = _peak_rms_delta_db(orig_window, out_window)
        actions.append(
            WhistleRepairFlagAction(
                frequency_hz=float(flag.details["frequency_hz"]),
                confidence_score=flag.confidence_score,
                prominence_db=float(flag.details.get("prominence_db", float("nan"))),
                timestamp_start_s=flag.timestamp_start_s,
                timestamp_end_s=flag.timestamp_end_s,
                peak_delta_db=peak_delta_db,
                rms_delta_db=rms_delta_db,
            )
        )

    actions.append(
        WhistleRepairSummary(frequencies_notched=target_frequencies, stage_ran=True)
    )
    return output, actions
