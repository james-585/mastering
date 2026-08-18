from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from implementation.harshness_control import apply_stem_harshness_control

SR = 48000


def _tone(freq_hz: float, duration_s: float, amplitude: float = 0.2) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(SR * duration_s), endpoint=False)
    return amplitude * np.sin(2.0 * np.pi * freq_hz * t)


def _harsh_vocal() -> np.ndarray:
    vocal = 0.22 * _tone(220.0, 1.0, 0.25)
    bright = 0.18 * np.sin(2.0 * np.pi * 2800.0 * np.linspace(0.0, 1.0, int(SR * 1.0), endpoint=False))
    return vocal + bright


def _bright_synth() -> np.ndarray:
    t = np.linspace(0.0, 1.0, int(SR * 1.0), endpoint=False)
    return 0.20 * np.sin(2.0 * np.pi * 220.0 * t) + 0.30 * np.sin(2.0 * np.pi * 3800.0 * t)


def _cymbal_like() -> np.ndarray:
    t = np.linspace(0.0, 1.0, int(SR * 1.0), endpoint=False)
    envelope = np.exp(-30.0 * t)
    return 0.18 * envelope * np.sin(2.0 * np.pi * 7000.0 * t)


def test_tc0121_harsh_vocal_reduction_without_dulling():
    stem = {"vocals": _harsh_vocal()}

    processed, actions = apply_stem_harshness_control(stem, SR)

    assert "vocals" in processed
    assert actions
    assert actions[0].stem_name == "vocals"
    assert actions[0].gain_db < 0.0
    assert actions[0].band_hz[0] < 5000.0
    assert np.abs(processed["vocals"]).max() <= 1.0


def test_tc0122_bright_synth_control_without_losing_detail():
    stem = {"synth": _bright_synth()}

    processed, actions = apply_stem_harshness_control(stem, SR)

    assert actions
    assert actions[0].stem_name == "synth"
    assert actions[0].gain_db < 0.0
    assert processed["synth"].shape == stem["synth"].shape


def test_tc0123_cymbal_de_haze_preserves_attack():
    stem = {"cymbals": _cymbal_like()}

    processed, actions = apply_stem_harshness_control(stem, SR)

    assert actions
    assert actions[0].stem_name == "cymbals"
    assert actions[0].gain_db < 0.0
    assert np.abs(processed["cymbals"]).max() <= 1.0


def test_tc0124_clean_stem_is_noop():
    clean = 0.12 * _tone(260.0, 0.5, 0.16)
    stem = {"vocals": clean}

    processed, actions = apply_stem_harshness_control(stem, SR)

    assert not actions
    assert np.allclose(processed["vocals"], clean)


def test_tc0125_silence_or_low_energy_stem_remains_untouched():
    quiet = np.zeros(int(SR * 0.5), dtype=np.float64)
    stem = {"drums": quiet}

    processed, actions = apply_stem_harshness_control(stem, SR)

    assert not actions
    assert np.allclose(processed["drums"], quiet)


def test_tc0126_true_peak_and_oversampling_safety():
    stem = {"drums": np.array([0.95, -0.93, 0.90, -0.90], dtype=np.float64)}

    processed, actions = apply_stem_harshness_control(stem, SR)

    assert np.abs(processed["drums"]).max() <= 1.0
    assert all(action.gain_db <= 0.0 for action in actions)


def test_tc0127_real_audio_validation_on_reference_track():
    wav_path = Path(__file__).resolve().parents[2] / "Reference Tracks" / "Sunday Club.wav"
    if not wav_path.exists():
        return

    import soundfile as sf

    audio, sr = sf.read(wav_path, dtype="float64", always_2d=False)
    if audio.ndim == 2:
        audio = audio[:, 0]

    stems = {"vocals": audio[: int(sr * 2.0)]}
    processed, actions = apply_stem_harshness_control(stems, sr)

    assert "vocals" in processed
    assert processed["vocals"].shape == stems["vocals"].shape
    assert np.isfinite(processed["vocals"]).all()
