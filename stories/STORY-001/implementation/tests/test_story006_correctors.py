import numpy as np

from suno_mastering.mastering.corrective_eq import apply_corrective_eq
from suno_mastering.mastering.stereo_width_corrector import apply_stereo_width_correction


def test_corrective_eq_returns_actions_and_modifies_audio():
    # simple mono signal
    sr = 44100
    t = np.linspace(0, 1.0, sr, endpoint=False)
    audio = 0.01 * np.sin(2 * np.pi * 200.0 * t)  # low-mid tone
    audio = audio.astype(np.float64)

    # targets: minimal structure required by the implementation
    targets = {
        "spectral_bands": {
            "sub": {"range_db_re_mid": {"min": -6.0, "max": 6.0}, "freq_hz": [20, 60], "correction_cap_db": 3.0},
            "low_mid": {"range_db_re_mid": {"min": -3.0, "max": 3.0}, "freq_hz": [120, 500], "correction_cap_db": 3.0},
        },
        "de_mud": {"flag_threshold_db_above_mid": 4.0, "correction_aim_point_db": 2.0},
    }

    pre_band_levels = {"sub": -8.0, "low_mid": 5.0, "mid": 0.0}

    out, actions = apply_corrective_eq(audio, sr, targets, pre_band_levels)
    assert isinstance(actions, list)
    assert len(actions) >= 1
    # audio should be modified (not bitwise equal)
    assert not np.allclose(out, audio)


def test_stereo_width_corrector_scales_side_channel_and_reports():
    sr = 44100
    n = sr // 10
    rng = np.random.default_rng(0)
    left = rng.normal(0, 0.1, n)
    right = rng.normal(0, 0.1, n)
    stereo = np.stack([left, right], axis=1)

    targets = {
        "stereo_width": {
            "sub": {
                "near_mono_threshold": 0.15,
                "correction_aim_point": 0.15,
                "correction_floor": 0.10,
                "max_correction_step": 0.15,
            },
            "low": {
                "near_mono_threshold": 0.15,
                "correction_aim_point": 0.15,
                "correction_floor": 0.10,
                "max_correction_step": 0.15,
            },
        }
    }
    pre_widths = {"sub": 0.8, "low": 0.6}

    out, actions = apply_stereo_width_correction(stereo.copy(), sr, targets, pre_widths)
    assert isinstance(actions, list)
    assert len(actions) >= 1
    # side energy should be reduced for at least one band -> signal changed
    assert not np.allclose(out, stereo)
