"""Shared fixtures/helpers for the STORY-025 automated test suite.

Signal-construction helpers implement the fixtures specified in test-cases.md
(F-2501 - F-2505) so tests are deterministic and traceable back to a fixture ID.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

BANDS = ["sub", "low", "low_mid", "mid", "high_mid", "high", "air"]


# ---------------------------------------------------------------------------
# F-2501: gain-scaled stationary tone pair (match_levels correctness by
# construction -- uniform gain on a stationary signal shifts BS.1770
# integrated LUFS by exactly the gain in dB).
# ---------------------------------------------------------------------------

def make_f2501(delta_db: float, sr: int = 44100, duration_s: float = 5.0) -> Tuple[np.ndarray, np.ndarray, int]:
    n = int(sr * duration_s)
    t = np.arange(n) / sr
    original = 0.2 * np.sin(2 * np.pi * 440.0 * t)
    processed = original * (10 ** (delta_db / 20.0))
    return original, processed, sr


def make_f2501_stereo(delta_db: float, sr: int = 44100, duration_s: float = 5.0) -> Tuple[np.ndarray, np.ndarray, int]:
    original, processed, sr = make_f2501(delta_db, sr, duration_s)
    original_stereo = np.column_stack([original, original])
    processed_stereo = np.column_stack([processed, processed])
    return original_stereo, processed_stereo, sr


# ---------------------------------------------------------------------------
# F-2502: bimodal near-silent/loud signal (forces the gating-edge residual)
# ---------------------------------------------------------------------------

def make_f2502(sr: int = 44100) -> Tuple[np.ndarray, np.ndarray, int]:
    rng = np.random.default_rng(42)
    quiet = 0.0005 * rng.standard_normal(int(sr * 8.0))
    loud = 0.5 * np.sin(2 * np.pi * 440.0 * np.arange(int(sr * 1.0)) / sr)
    original = np.concatenate([quiet, loud])
    processed = np.concatenate([quiet * (10 ** (40 / 20.0)), loud])
    return original, processed, sr


# ---------------------------------------------------------------------------
# F-2503: silence (forces non-finite LUFS)
# ---------------------------------------------------------------------------

def make_f2503(sr: int = 44100) -> Tuple[np.ndarray, np.ndarray, int]:
    original = np.zeros(int(sr * 3.0))
    processed = 0.3 * np.sin(2 * np.pi * 440.0 * np.arange(int(sr * 3.0)) / sr)
    return original, processed, sr


# ---------------------------------------------------------------------------
# F-2504: mocked seven-band deltas
# ---------------------------------------------------------------------------

@dataclass
class FakeBandMeasurement:
    band: str
    relative_db: float


@dataclass
class FakeSevenBandResult:
    bands: List[FakeBandMeasurement]


def make_seven_band_result(relative_db_by_band: Dict[str, float]) -> FakeSevenBandResult:
    return FakeSevenBandResult(
        bands=[FakeBandMeasurement(band=b, relative_db=relative_db_by_band[b]) for b in BANDS]
    )


F2504_ORIGINAL_RELATIVE_DB = {b: 0.0 for b in BANDS}
F2504_PROCESSED_RELATIVE_DB = {
    "sub": 2.0, "low": -1.0, "low_mid": 0.0, "mid": 0.0,
    "high_mid": 3.0, "high": -2.0, "air": 1.0,
}


def uniform_band_deltas(x: float) -> Dict[str, float]:
    """All six non-"mid" bands set to `x`; "mid" (the reference band) stays 0.0."""
    return {b: (0.0 if b == "mid" else x) for b in BANDS}


# ---------------------------------------------------------------------------
# F-2505: mocked DR / artifact-density pairs
# ---------------------------------------------------------------------------

DR_NO_FLAG = (10.0, 7.01)
DR_FLAG_BOUNDARY = (10.0, 7.00)
DR_FLAG_CLEAR = (10.0, 5.00)

ARTIFACT_NO_FLAG = (0.10, 0.149)
ARTIFACT_FLAG_BOUNDARY = (0.10, 0.150)
ARTIFACT_FLAG_CLEAR = (0.10, 0.200)


@dataclass
class FakeArtifactResult:
    overall_artifact_density_score: float


def make_artifact_pair(original_score: float, processed_score: float):
    return (None, FakeArtifactResult(overall_artifact_density_score=original_score)), (
        None,
        FakeArtifactResult(overall_artifact_density_score=processed_score),
    )


def patch_seven_band(monkeypatch, original_relative_db: Dict[str, float], processed_relative_db: Dict[str, float]):
    """Patch grounded_quality_review.measure_seven_band_balance so the first
    call (original) returns `original_relative_db` and the second call
    (level-matched processed) returns `processed_relative_db`."""
    import grounded_quality_review as gqr

    results = iter([
        make_seven_band_result(original_relative_db),
        make_seven_band_result(processed_relative_db),
    ])

    def fake(audio, sr, config):
        return next(results)

    monkeypatch.setattr(gqr, "measure_seven_band_balance", fake)


def patch_dynamic_range(monkeypatch, dr_original: float, dr_processed: float):
    import grounded_quality_review as gqr

    values = iter([dr_original, dr_processed])

    def fake(audio, sr, config):
        return next(values)

    monkeypatch.setattr(gqr, "measure_dynamic_range", fake)


def patch_artifacts(monkeypatch, score_original: float, score_processed: float):
    import grounded_quality_review as gqr

    values = iter([score_original, score_processed])

    def fake(audio, sr):
        return None, FakeArtifactResult(overall_artifact_density_score=next(values))

    monkeypatch.setattr(gqr, "detect_artifacts", fake)


def patch_no_flags(monkeypatch):
    """Patch all three grounded-metric dependencies so no flag fires --
    isolates a test's assertions to whichever metric it sets up separately."""
    patch_seven_band(monkeypatch, F2504_ORIGINAL_RELATIVE_DB, dict(F2504_ORIGINAL_RELATIVE_DB))
    patch_dynamic_range(monkeypatch, *DR_NO_FLAG)
    patch_artifacts(monkeypatch, *ARTIFACT_NO_FLAG)
