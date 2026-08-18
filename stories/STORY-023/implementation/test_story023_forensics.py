import numpy as np

from audio_forensics import (
    DiagnosticsReport,
    flag_clipping,
    flag_phase_mismatch,
    measure_reconstruction_residual,
    run_forensics,
)


SAMPLE_RATE = 44100


def _stereo_signal(length=256):
    t = np.linspace(0.0, 1.0, length, endpoint=False, dtype=np.float64)
    left = 0.35 * np.sin(2.0 * np.pi * 220.0 * t)
    right = 0.33 * np.sin(2.0 * np.pi * 330.0 * t)
    return np.stack([left, right], axis=1)


def test_tc023_01_clipping_detected():
    signal = _stereo_signal(256)
    signal[64:, 0] = 1.05
    signal[64:, 1] = -1.10
    report = run_forensics(signal, signal.copy(), {"mix": signal.copy()}, SAMPLE_RATE)

    assert flag_clipping(signal) is True
    assert report.clipping_detected is True
    assert report.clipping_channel in {"left", "right"}
    assert report.safe is False


def test_tc023_02_phase_mismatch_detected():
    t = np.linspace(0.0, 1.0, 512, endpoint=False, dtype=np.float64)
    tone = 0.35 * np.sin(2.0 * np.pi * 220.0 * t)
    signal = np.stack([tone, tone], axis=1)
    mismatched = signal.copy()
    mismatched[:, 1] *= -1.0

    report = run_forensics(signal, mismatched, {"mix": mismatched}, SAMPLE_RATE)

    assert flag_phase_mismatch({"mix": mismatched}) is True
    assert report.phase_mismatch_detected is True
    assert report.safe is False


def test_tc023_03_reconstruction_artifacts_detected():
    original = _stereo_signal(512)
    artifact = original.copy()
    artifact[:, 0] += 0.05 * np.sin(2.0 * np.pi * 10.0 * np.linspace(0.0, 1.0, artifact.shape[0], endpoint=False))
    residual = measure_reconstruction_residual(original, artifact)

    assert residual > 1e-6
    report = run_forensics(original, artifact, {"mix": artifact.copy()}, SAMPLE_RATE)
    assert report.residual_error_dbfs < 0.0
    assert report.reconstruction_artifact_detected is True
    assert report.safe is True
    assert report.status == "warn"
    assert report.to_dict()["status"] == "warn"


def test_tc023_04_clean_identity_path_passes():
    original = _stereo_signal(512)
    stems = {"drums": original * 0.2, "bass": original * 0.3, "other": original * 0.2, "vocals": original * 0.3}
    report = run_forensics(original, original.copy(), stems, SAMPLE_RATE)

    assert report.safe is True
    assert report.clipping_detected is False
    assert report.phase_mismatch_detected is False
    assert report.reconstruction_artifact_detected is False
    assert isinstance(report, DiagnosticsReport)
    assert report.to_dict()["status"] == "pass"
