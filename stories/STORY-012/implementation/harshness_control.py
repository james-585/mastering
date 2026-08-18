from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class HarshnessAction:
    stem_name: str
    action_type: str
    gain_db: float
    band_hz: tuple[float, float]
    reason: str
    severity: float


def _as_float64(audio: np.ndarray) -> np.ndarray:
    arr = np.asarray(audio, dtype=np.float64)
    if arr.ndim not in {1, 2}:
        raise ValueError(f"Unsupported stem shape {arr.shape}; expected 1D or 2D audio")
    return arr


def _silence_guard(audio: np.ndarray) -> bool:
    if audio.size == 0:
        return True
    peak = float(np.abs(audio).max())
    rms = float(np.sqrt(np.mean(np.square(audio.astype(np.float64)))))
    return peak < 1e-5 or rms < 1e-6


def _band_edges(stem_name: str) -> tuple[float, float]:
    key = stem_name.lower()
    if "vocal" in key:
        return (2000.0, 4500.0)
    if "synth" in key or "lead" in key or "pad" in key:
        return (2200.0, 5500.0)
    if "drum" in key or "cymbal" in key or "perc" in key or "snare" in key:
        return (4000.0, 8000.0)
    return (2500.0, 5000.0)


def _stem_energy_ratio(audio: np.ndarray, sample_rate: int, band: tuple[float, float]) -> float:
    if audio.size == 0:
        return 0.0

    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    mono = np.asarray(mono, dtype=np.float64)
    if mono.size < 8:
        return 0.0

    spectrum = np.fft.rfft(mono)
    freqs = np.fft.rfftfreq(mono.size, d=1.0 / sample_rate)
    mag = np.abs(spectrum)

    band_mask = (freqs >= band[0]) & (freqs <= band[1])
    if not np.any(band_mask):
        return 0.0

    band_energy = float(np.mean(np.square(mag[band_mask])))
    guard_low = (freqs >= 150.0) & (freqs <= 2000.0)
    low_energy = float(np.mean(np.square(mag[guard_low]))) if np.any(guard_low) else 0.0
    baseline = low_energy + 1e-9
    return band_energy / baseline


def _apply_local_band_attenuation(audio: np.ndarray, sample_rate: int, band: tuple[float, float], gain_db: float) -> np.ndarray:
    gain_linear = 10.0 ** (gain_db / 20.0)
    out = np.asarray(audio, dtype=np.float64).copy()
    if out.ndim == 2:
        mono = out.mean(axis=1)
        mono_out = _apply_local_band_attenuation(mono, sample_rate, band, gain_db)
        return np.stack([mono_out, mono_out], axis=1)

    spectrum = np.fft.rfft(out)
    freqs = np.fft.rfftfreq(out.size, d=1.0 / sample_rate)
    mask = (freqs >= band[0]) & (freqs <= band[1])
    if np.any(mask):
        spectrum[mask] *= gain_linear
        processed = np.fft.irfft(spectrum, n=out.size)
        out = processed.astype(np.float64)
    return np.clip(out, -1.0, 1.0)


def _true_peak_estimate(audio: np.ndarray, sample_rate: int) -> float:
    arr = np.asarray(audio, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    oversampled = np.asarray(arr, dtype=np.float64)
    # Conservative 4x oversampling for true-peak safety.
    factor = 4
    if arr.ndim == 2:
        mono = arr.mean(axis=1)
        oversampled = np.interp(
            np.arange(0, mono.size * factor, 1 / factor),
            np.arange(mono.size),
            mono,
        )
    else:
        oversampled = np.interp(
            np.arange(0, arr.size * factor, 1 / factor),
            np.arange(arr.size),
            arr,
        )
    return float(np.max(np.abs(oversampled)))


def apply_stem_harshness_control(stems: dict[str, np.ndarray], sample_rate: int) -> tuple[dict[str, np.ndarray], list[HarshnessAction]]:
    """Apply conservative local harshness reduction to the offending stems only.

    The stage remains a no-op for already-clean or low-energy stems. It uses local
    band evidence and true-peak guards to avoid dulling or clipping.
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")

    processed: dict[str, np.ndarray] = {}
    actions: list[HarshnessAction] = []

    for stem_name, audio in stems.items():
        arr = _as_float64(audio)
        if _silence_guard(arr):
            processed[stem_name] = arr.copy()
            continue

        band = _band_edges(stem_name)
        ratio = _stem_energy_ratio(arr, sample_rate, band)
        if ratio < 1.25:
            processed[stem_name] = arr.copy()
            continue

        gain_db = -min(5.0, max(0.5, 0.75 * (ratio - 1.0)))
        if gain_db >= 0.0:
            processed[stem_name] = arr.copy()
            continue

        corrected = _apply_local_band_attenuation(arr, sample_rate, band, gain_db)
        corrected = np.clip(corrected, -1.0, 1.0)
        if _true_peak_estimate(corrected, sample_rate) > 0.995:
            corrected = np.clip(corrected * 0.95, -1.0, 1.0)
            gain_db = -min(abs(gain_db), 3.0)

        processed[stem_name] = corrected
        actions.append(
            HarshnessAction(
                stem_name=stem_name,
                action_type="local_dehaze",
                gain_db=float(gain_db),
                band_hz=band,
                reason=f"Local harshness reduction in {band[0]:.0f}-{band[1]:.0f} Hz band for {stem_name}.",
                severity=float(ratio),
            )
        )

    return processed, actions
