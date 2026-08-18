import numpy as np
import pytest

from stem_stereo_imaging import apply_stem_stereo_imaging


SR = 44100


def _stereo_signal(width=0.12, phase=0.0, amplitude=0.60):
    t = np.linspace(0, 1.0, SR, endpoint=False)
    carrier = np.sin(2 * np.pi * 220.0 * t)
    stereo = np.empty((SR, 2), dtype=np.float64)
    stereo[:, 0] = carrier * amplitude * (1.0 + width)
    stereo[:, 1] = carrier * amplitude * (1.0 - width)
    if phase:
        stereo[:, 1] *= -1.0
    return stereo


def test_vocal_stem_center_stability_is_noop():
    stereo = _stereo_signal(width=0.08)
    stereo[:, 0] += 0.03 * np.sin(2 * np.pi * 110.0 * np.linspace(0, 1.0, SR, endpoint=False))
    stereo[:, 1] += 0.03 * np.sin(2 * np.pi * 110.0 * np.linspace(0, 1.0, SR, endpoint=False))

    out, actions = apply_stem_stereo_imaging({"vocal": stereo}, SR)

    assert np.allclose(out["vocal"], stereo, atol=1e-12)
    assert actions == []


def test_ambience_stem_gets_limited_width_boost():
    stereo = _stereo_signal(width=0.38)
    out, actions = apply_stem_stereo_imaging({"ambience": stereo}, SR)

    assert len(actions) == 1
    assert actions[0].stem_name == "ambience"
    assert actions[0].action_type == "width_boost"
    assert np.mean((out["ambience"][:, 0] - out["ambience"][:, 1]) ** 2) > np.mean((stereo[:, 0] - stereo[:, 1]) ** 2)


def test_mono_compatible_stem_remains_unchanged():
    mono = np.column_stack([np.sin(2 * np.pi * 100.0 * np.linspace(0, 1.0, SR, endpoint=False)),
                            np.sin(2 * np.pi * 100.0 * np.linspace(0, 1.0, SR, endpoint=False))])

    out, actions = apply_stem_stereo_imaging({"bass": mono}, SR)

    assert np.allclose(out["bass"], mono, atol=1e-12)
    assert actions == []


def test_silent_stem_is_untouched():
    stereo = np.zeros((SR, 2), dtype=np.float64)
    out, actions = apply_stem_stereo_imaging({"pad": stereo}, SR)

    assert np.allclose(out["pad"], stereo, atol=1e-12)
    assert actions == []


def test_phase_unstable_stem_raises_for_safety():
    t = np.linspace(0, 1.0, SR, endpoint=False)
    stereo = np.column_stack([
        np.sin(2 * np.pi * 200.0 * t),
        -np.sin(2 * np.pi * 200.0 * t) * 0.8,
    ])

    with pytest.raises(ValueError):
        apply_stem_stereo_imaging({"synth": stereo}, SR)
