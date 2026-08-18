import numpy as np

from final_bus_glue import apply_final_bus_glue

SR = 44100


def _stereo_bus(correlation=0.9, amplitude=0.35):
    t = np.linspace(0, 1.0, SR, endpoint=False)
    base = np.sin(2 * np.pi * 110.0 * t)
    left = base * amplitude
    right = base * amplitude
    drift = 0.06 * np.sin(2 * np.pi * 220.0 * t)
    left += drift
    right = correlation * right + (1.0 - correlation) * drift
    return np.column_stack([left, right]).astype(np.float64)


def test_mix_already_cohesive_is_noop():
    bus = _stereo_bus(correlation=0.94, amplitude=0.30)
    out, actions = apply_final_bus_glue({"mix": bus}, SR)

    assert np.allclose(out["mix"], bus, atol=1e-12)
    assert actions == []


def test_bus_glue_applies_only_when_needed():
    bus = _stereo_bus(correlation=0.45, amplitude=0.55)
    bus[:, 0] += 0.35 * np.sin(2 * np.pi * 8.0 * np.linspace(0, 1.0, SR, endpoint=False))
    out, actions = apply_final_bus_glue({"mix": bus}, SR)

    assert len(actions) >= 1
    assert actions[0].action_type in {"bus_glue", "dynamic_balance"}
    assert np.max(np.abs(out["mix"])) <= 1.0 + 1e-6


def test_dynamic_balance_preserves_transient_shape():
    t = np.linspace(0, 1.0, SR, endpoint=False)
    bus = np.column_stack([
        np.sin(2 * np.pi * 220.0 * t) + 0.8 * (np.exp(-((t - 0.25) ** 2) / 0.0008) - np.exp(-((t - 0.75) ** 2) / 0.0008)),
        np.sin(2 * np.pi * 220.0 * t) + 0.7 * (np.exp(-((t - 0.25) ** 2) / 0.0008) - np.exp(-((t - 0.75) ** 2) / 0.0012)),
    ]).astype(np.float64)
    out, actions = apply_final_bus_glue({"mix": bus}, SR)

    assert len(actions) >= 1
    assert np.max(np.abs(out["mix"])) <= 1.0 + 1e-6
    assert np.argmax(np.abs(out["mix"][:, 0])) == np.argmax(np.abs(bus[:, 0]))


def test_true_peak_guard_blocks_clipping_risk():
    t = np.linspace(0, 1.0, SR, endpoint=False)
    bus = np.column_stack([
        0.98 * np.sin(2 * np.pi * 200.0 * t),
        0.98 * np.sin(2 * np.pi * 200.0 * t + np.pi / 2),
    ]).astype(np.float64)
    out, actions = apply_final_bus_glue({"mix": bus}, SR)

    assert np.max(np.abs(out["mix"])) <= 1.0 + 1e-6
