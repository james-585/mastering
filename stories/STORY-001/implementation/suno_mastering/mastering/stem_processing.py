"""Targeted DSP for isolated stems (STORY-008).

Applies frequency-band-specific corrections to individual stems before
re-summation, enabling surgical fixes that would damage other elements if
applied to the stereo mix:

  - Bass stem: Mono summing below 90 Hz (phase-robust sub-bass)
  - Vocal stem: Low-pass at 15 kHz (remove AI sizzle), high-pass at 80 Hz (rumble)
  - Drums/Other: Pass-through (reserved for future transient processing)

All filter designs use scipy.signal Butterworth filters with orders/slopes
matching the spec (STORY-008 §3 Phase B).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

import numpy as np
from scipy.signal import butter, sosfiltfilt

logger = logging.getLogger(__name__)


# ── Dataclass for logging DSP actions ─────────────────────────────────────────

@dataclass
class StemAction:
    """Records one DSP operation applied to a stem.
    
    Attributes:
        stem_name: "vocals" | "drums" | "bass" | "other"
        action_type: "mono_sub" | "hf_rolloff" | "lf_cut" | "passthrough"
        parameters: dict with filter-specific keys (frequency_hz, filter_type, order)
    """
    stem_name: str
    action_type: str
    parameters: dict


# ── Bass stem: Mono sub-bass (<90 Hz) ─────────────────────────────────────────

def _mono_sum_sub_bass(
    audio: np.ndarray,
    sample_rate: int,
    cutoff_hz: float = 90.0,
) -> np.ndarray:
    """Mono-sum only the sub-bass band while preserving stereo content above cutoff_hz.

    This must operate on the actual low-frequency spectral band rather than on the
    whole stem. Collapsing the entire bass stem to mono destroys stereo detail at
    higher bass frequencies and creates the ringy, phase-unnatural artifact that
    users hear as bass-level ringing. The low-band is forced to mono in the FFT
    domain, while all bins above the cutoff remain stereo.
    """
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2:
        return arr.copy()

    cutoff = float(cutoff_hz)
    if not np.isfinite(cutoff) or cutoff <= 0.0 or cutoff >= sample_rate / 2.0:
        return arr.copy()

    n = arr.shape[0]
    if n == 0:
        return arr.copy()

    fft = np.fft.rfft(arr, axis=0)
    freqs = np.fft.rfftfreq(n, d=1.0 / sample_rate)
    mono_band = 0.5 * (fft[:, 0] + fft[:, 1])

    low_mask = freqs <= cutoff
    out_fft = fft.copy()
    out_fft[low_mask, 0] = mono_band[low_mask]
    out_fft[low_mask, 1] = mono_band[low_mask]

    out = np.fft.irfft(out_fft, n=n, axis=0)
    logger.debug(f"Applied mono summing below {cutoff_hz} Hz in the spectral low band only")
    return np.asarray(out, dtype=np.float64)


# ── Vocal stem: High-frequency rolloff + low-frequency cut ────────────────────

def _apply_vocal_filters(
    audio: np.ndarray,
    sample_rate: int,
    lpf_hz: float = 15000.0,
    hpf_hz: float = 80.0,
) -> np.ndarray:
    """Apply low-pass and high-pass filters to vocal stem.
    
    Low-pass: 2nd-order Butterworth at 15 kHz to eliminate AI generation sizzle.
    High-pass: 3rd-order (18 dB/octave) Butterworth at 80 Hz to remove rumble/DC.
    
    Args:
        audio: float64, shape (samples, 2) stereo
        sample_rate: int
        lpf_hz: low-pass cutoff (default 15 kHz)
        hpf_hz: high-pass cutoff (default 80 Hz)
    
    Returns:
        Filtered audio array.
    """
    out = audio.copy()
    
    # Low-pass: 2nd-order Butterworth at 15 kHz
    sos_lp = butter(2, lpf_hz, btype="lowpass", fs=sample_rate, output="sos")
    out[:, 0] = sosfiltfilt(sos_lp, out[:, 0])
    out[:, 1] = sosfiltfilt(sos_lp, out[:, 1])
    logger.debug(f"Applied 2nd-order low-pass at {lpf_hz} Hz to vocals")
    
    # High-pass: 3rd-order (18 dB/octave) Butterworth at 80 Hz
    sos_hp = butter(3, hpf_hz, btype="highpass", fs=sample_rate, output="sos")
    out[:, 0] = sosfiltfilt(sos_hp, out[:, 0])
    out[:, 1] = sosfiltfilt(sos_hp, out[:, 1])
    logger.debug(f"Applied 3rd-order high-pass at {hpf_hz} Hz to vocals")
    
    return out


# ── Public API: Process all stems ─────────────────────────────────────────────

def process_stems(
    stems: dict,
    sample_rate: int,
    identified_issues: list[dict] | None = None,
) -> tuple[dict, List[StemAction]]:
    """Apply targeted DSP to a stem only after that stem's issue has been identified.

    This matches the workflow requirement: repairs occur only after an issue is
    explicitly detected and attributed to a stem. If no issue list is supplied,
    or no identified issue matches a stem, the stem remains untouched.

    Args:
        stems: dict mapping stem_name -> float64 array (samples, 2)
        sample_rate: int, sample rate in Hz
        identified_issues: optional list of issue records with at least
            {'stem_name': ..., 'issue_type': ...}

    Returns:
        (processed_stems, actions)
    """
    processed = {}
    actions = []
    issue_map = {
        str(issue.get("stem_name", "")).strip(): issue
        for issue in (identified_issues or [])
        if str(issue.get("stem_name", "")).strip()
    }

    for stem_name, audio in stems.items():
        processed[stem_name] = audio.copy()

        if stem_name not in issue_map:
            continue

        if stem_name == "bass":
            processed[stem_name] = _mono_sum_sub_bass(audio, sample_rate)
            action = StemAction(
                stem_name="bass",
                action_type="mono_sub",
                parameters={"frequency_hz": 90.0, "filter_type": "lowpass", "order": 8}
            )
            actions.append(action)
            print(f"[Stem fix] stem={stem_name} action={action.action_type} parameters={action.parameters}")

        elif stem_name == "vocals":
            processed[stem_name] = _apply_vocal_filters(audio, sample_rate)
            hf_action = StemAction(
                stem_name="vocals",
                action_type="hf_rolloff",
                parameters={"frequency_hz": 15000.0, "filter_type": "lowpass", "order": 2}
            )
            lf_action = StemAction(
                stem_name="vocals",
                action_type="lf_cut",
                parameters={"frequency_hz": 80.0, "filter_type": "highpass", "order": 3}
            )
            actions.extend([hf_action, lf_action])
            print(f"[Stem fix] stem={stem_name} action={hf_action.action_type} parameters={hf_action.parameters}")
            print(f"[Stem fix] stem={stem_name} action={lf_action.action_type} parameters={lf_action.parameters}")

    logger.info(f"Processed {len(stems)} stems with {len(actions)} actions")
    return processed, actions


# ── Re-summation with sanity checks ───────────────────────────────────────────

def sum_stems(
    stems: dict,
) -> np.ndarray:
    """Sum processed stems back into a single stereo array.
    
    Args:
        stems: dict mapping stem_name -> float64 array (samples, 2)
    
    Returns:
        Summed stereo array, shape (samples, 2), float64.
    
    Raises:
        ValueError: if stems have mismatched shapes or contain NaN/Inf values.
    
    Performs sanity checks:
        - All stems must have identical shape
        - No NaN or Inf values in any stem
        - Warns if summed audio clips (peak >= 0.999)
    """
    stem_list = list(stems.values())
    stem_names = list(stems.keys())
    
    # Shape consistency check
    shapes = [s.shape for s in stem_list]
    if len(set(shapes)) > 1:
        raise ValueError(
            f"Cannot sum stems with mismatched shapes: "
            f"{dict(zip(stem_names, shapes))}"
        )
    
    # NaN/Inf check
    for name, audio in stems.items():
        if not np.isfinite(audio).all():
            raise ValueError(f"Stem '{name}' contains NaN or Inf values")
    
    # Sum all stems
    summed = np.sum(stem_list, axis=0)
    
    # Clipping warning
    peak = np.abs(summed).max()
    if peak >= 0.999:
        logger.warning(
            f"Stem re-summation resulted in clipping: peak = {peak:.6f}. "
            f"Consider normalizing stems before summing."
        )
    
    logger.info(f"Summed {len(stems)} stems: peak = {peak:.6f}")
    return summed
