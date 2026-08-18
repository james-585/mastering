"""Surgical, per-stem STATIONARY_WHISTLE repair.

Mix-level artifact detection cannot know which separated stem a whistle
actually lives in -- `ArtifactFlag` carries no stem attribution. This module
closes that gap for STATIONARY_WHISTLE only (it is the one artifact type with
a well-defined frequency and time window, so attribution is a real
measurement, not a guess): for each flagged tone, the stem carrying the
dominant share of energy at that frequency/time is notched with a narrow,
zero-phase IIR notch, crossfaded in only across the flagged window so
untouched audio is bit-for-bit outside it.

Two safety gates keep this from over-firing on ordinary sustained musical
content (a held bass note, drone, or cymbal wash also looks like a "narrow
persistent peak" to the detector): a confidence/prominence floor per flag,
and a per-track cap on how many flags may qualify at all before the whole
stage backs off and repairs nothing.

SMEARED_TRANSIENT / PHASE_SWISH / DIGITAL_HAZE are not handled here: they
describe cross-channel/structural properties with no honest way to assign
them to one stem, so they remain detect-only.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import filtfilt, iirpeak, iirnotch

from .stem_processing import StemAction

# Narrow notch -- high Q trades a wider stopband for less collateral damage
# to neighbouring content, matching the detector's own Q >= 8 "narrow" criterion.
_NOTCH_Q = 30.0
# A stem must hold this share of the flagged tone's total cross-stem energy
# before it is touched; below this, attribution is not reliable enough to act on.
_DOMINANCE_THRESHOLD = 0.6
# Energy floor below which a flag is treated as inaudible/noise-level and skipped.
_ENERGY_FLOOR = 1e-10
_CROSSFADE_MS = 50.0
# Same conservative floors as RepairWhistlesConfig's validated defaults (used
# for the whole-mix C++ notch path) -- a flag below either is not distinguishable
# from ordinary sustained musical content (a held bass/drone/cymbal note also
# looks like a "narrow persistent peak" to the detector).
_CONFIDENCE_THRESHOLD = 0.8
_PROMINENCE_FLOOR_DB = 10.0
# If more than this many flags pass the gates above on one track, the detector
# is very likely picking up structural/sustained musical content rather than
# generation artifacts -- back off entirely rather than carve dozens of notches
# across the mix, which would itself be an audible defect.
_MAX_REPAIRS_PER_TRACK = 20


def _window_samples(sample_rate: int, n_samples: int, start_s: float, end_s: float) -> tuple[int, int]:
    start = max(0, min(n_samples, int(round(start_s * sample_rate))))
    end = max(start, min(n_samples, int(round(end_s * sample_rate))))
    return start, end


def _band_energy(mono: np.ndarray, sample_rate: int, freq_hz: float, start: int, end: int) -> float:
    """RMS energy at freq_hz within [start, end), via a narrow resonant bandpass."""
    if end <= start:
        return 0.0
    segment = mono[start:end]
    if segment.size < 16:
        return float(np.sqrt(np.mean(np.square(segment)))) if segment.size else 0.0
    b, a = iirpeak(freq_hz, _NOTCH_Q, fs=sample_rate)
    filtered = filtfilt(b, a, segment)
    return float(np.sqrt(np.mean(np.square(filtered))))


def _crossfade_envelope(n_samples: int, sample_rate: int, start: int, end: int, crossfade_ms: float) -> np.ndarray:
    """1.0 = fully notched, 0.0 = fully original, ramped in/out around [start, end)."""
    envelope = np.zeros(n_samples, dtype=np.float64)
    ramp = max(1, int(round(crossfade_ms / 1000.0 * sample_rate)))
    ramp_in_start = max(0, start - ramp)
    ramp_out_end = min(n_samples, end + ramp)
    if ramp_in_start < start:
        envelope[ramp_in_start:start] = np.linspace(0.0, 1.0, start - ramp_in_start, endpoint=False)
    envelope[start:end] = 1.0
    if end < ramp_out_end:
        envelope[end:ramp_out_end] = np.linspace(1.0, 0.0, ramp_out_end - end, endpoint=False)
    return envelope


def attribute_and_repair_whistles(
    stems: dict[str, np.ndarray],
    sample_rate: int,
    artifact_flags: list,
) -> tuple[dict[str, np.ndarray], list[StemAction]]:
    """Notch STATIONARY_WHISTLE flags on whichever stem dominantly carries them.

    Returns (processed_stems, actions). Stems with no attributable flag are
    returned as unmodified copies; non-STATIONARY_WHISTLE flags are ignored.
    If an implausible number of flags qualify for repair, none are applied
    (see _MAX_REPAIRS_PER_TRACK) -- that volume of "whistles" is itself
    evidence the detector is reading sustained musical content, not artifacts.
    """
    processed = {name: np.asarray(audio, dtype=np.float64).copy() for name, audio in stems.items()}
    actions: list[StemAction] = []
    if not artifact_flags:
        return processed, actions

    candidates = [
        flag
        for flag in artifact_flags
        if getattr(flag, "artifact_type", None) == "STATIONARY_WHISTLE"
        and flag.confidence_score >= _CONFIDENCE_THRESHOLD
        and flag.details.get("prominence_db", 0.0) >= _PROMINENCE_FLOOR_DB
    ]
    if len(candidates) > _MAX_REPAIRS_PER_TRACK:
        return processed, actions

    monos = {
        name: audio.mean(axis=1) if audio.ndim == 2 else audio
        for name, audio in processed.items()
    }
    if not monos:
        return processed, actions
    n_samples = next(iter(monos.values())).shape[0]

    for flag in candidates:
        freq_hz = flag.details.get("frequency_hz")
        if freq_hz is None or not (0.0 < freq_hz < 0.5 * sample_rate * 0.98):
            continue
        start, end = _window_samples(sample_rate, n_samples, flag.timestamp_start_s, flag.timestamp_end_s)
        if end <= start:
            continue

        energies = {
            name: _band_energy(mono, sample_rate, freq_hz, start, end)
            for name, mono in monos.items()
        }
        total = sum(energies.values())
        if total <= _ENERGY_FLOOR:
            continue
        best_stem, best_energy = max(energies.items(), key=lambda kv: kv[1])
        if best_energy / total < _DOMINANCE_THRESHOLD:
            continue  # no single stem clearly carries this tone -- skip rather than guess

        stem_audio = processed[best_stem]
        b, a = iirnotch(freq_hz, _NOTCH_Q, fs=sample_rate)
        if stem_audio.ndim == 2:
            notched = np.column_stack([filtfilt(b, a, stem_audio[:, ch]) for ch in range(stem_audio.shape[1])])
        else:
            notched = filtfilt(b, a, stem_audio)

        envelope = _crossfade_envelope(n_samples, sample_rate, start, end, _CROSSFADE_MS)
        envelope_bcast = envelope[:, None] if stem_audio.ndim == 2 else envelope
        blended = stem_audio * (1.0 - envelope_bcast) + notched * envelope_bcast
        processed[best_stem] = blended
        monos[best_stem] = blended.mean(axis=1) if blended.ndim == 2 else blended

        actions.append(
            StemAction(
                stem_name=best_stem,
                action_type="whistle_notch",
                parameters={
                    "frequency_hz": round(float(freq_hz), 1),
                    "dominance_share": round(best_energy / total, 3),
                    "start_s": flag.timestamp_start_s,
                    "end_s": flag.timestamp_end_s,
                },
            )
        )

    return processed, actions
