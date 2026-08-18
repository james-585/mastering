import numpy as np
import pytest

from stem_ms_dsp import _phase_null_check, decode_ms, encode_ms, process_other_stem


def _fixture_stereo() -> np.ndarray:
    left = np.array([0.15, -0.20, 0.35, -0.40, 0.55, -0.60, 0.75, -0.80], dtype=np.float64)
    right = np.array([0.10, -0.30, 0.45, -0.50, 0.65, -0.70, 0.85, -0.90], dtype=np.float64)
    return np.column_stack([left, right])


def test_ms_round_trip_exactness():
    stereo = _fixture_stereo()
    encoded = encode_ms(stereo)
    decoded = decode_ms(encoded)

    assert encoded.shape == stereo.shape
    assert encoded.dtype == np.float64
    assert np.max(np.abs(decoded - stereo)) <= 1e-12


def test_bypass_identity_preserves_other_stem_and_mix():
    other = _fixture_stereo()
    vocals = other * 0.5
    drums = other * 0.25
    bass = other * 0.1
    stems = {"vocals": vocals, "drums": drums, "bass": bass, "other": other}

    result = process_other_stem(stems, bypass=True)

    assert result["other"] is other
    assert np.max(np.abs(result["other"] - other)) == 0.0
    recombined = result["vocals"] + result["drums"] + result["bass"] + result["other"]
    expected = vocals + drums + bass + other
    assert np.max(np.abs(recombined - expected)) == 0.0


def test_phase_null_sum_in_bypass_path_is_effectively_zero():
    other = np.array(
        [
            [0.5, -0.5],
            [0.25, -0.25],
            [-0.75, 0.75],
            [0.1, -0.1],
        ],
        dtype=np.float64,
    )
    stems = {"vocals": other, "drums": other * 0.2, "bass": other * 0.1, "other": other}

    result = process_other_stem(stems, bypass=True)
    residual = result["other"] - other

    assert np.max(np.abs(residual)) <= 1e-12
    assert _phase_null_check(result["other"], tolerance=1e-12) <= 1e-12


def test_invalid_input_rejected_before_output_written():
    with pytest.raises(ValueError, match="finite|stereo|shape|invalid"):
        encode_ms(np.array([[1.0, np.nan], [2.0, 3.0]], dtype=np.float64))

    with pytest.raises(ValueError, match="stereo|shape"):
        process_other_stem({"other": np.array([1.0, 2.0, 3.0], dtype=np.float64)})


def test_clipping_guard_raises_before_silent_overflow():
    stereo = np.array([[1.1, -1.1], [0.3, -0.3]], dtype=np.float64)
    with pytest.raises(ValueError, match="clipping|safety|peak"):
        encode_ms(stereo)


def test_process_other_stem_reports_status_and_diagnostics():
    other = _fixture_stereo()
    diagnostics: dict[str, object] = {}
    result = process_other_stem({"other": other}, diagnostics=diagnostics, bypass=False)

    assert result["other"].shape == other.shape
    assert diagnostics["status"] in {"active", "bypassed"}
    assert diagnostics["output_peak"] >= 0.0
    assert diagnostics["dtype"] == "float64"
