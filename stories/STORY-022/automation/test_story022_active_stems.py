from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
import json
from types import SimpleNamespace

import numpy as np
import pytest

from suno_mastering import stem_integration
from suno_mastering.cli import build_arg_parser
from suno_mastering.config import MasteringConfig, StemConfig
from suno_mastering.io.stem_separation import (
    MODEL_REGISTRY,
    StemBundle,
    clear_model_cache,
    split_stems,
)
from suno_mastering.report.builder import build_report
from suno_mastering.report.render import render_json


FOUR_SOURCES = ("drums", "bass", "other", "vocals")
SIX_SOURCES = FOUR_SOURCES + ("piano", "guitar")


class FakeTensor:
    def __init__(self, value: np.ndarray) -> None:
        self.value = value

    def float(self) -> FakeTensor:
        return self

    def unsqueeze(self, _axis: int) -> FakeTensor:
        return self


class FakeTorch:
    __version__ = "fake-torch-2.2"

    def __init__(self, *, cuda: bool = False) -> None:
        self.cuda = SimpleNamespace(is_available=lambda: cuda)
        self.backends = SimpleNamespace(
            mps=SimpleNamespace(is_available=lambda: False),
            cudnn=SimpleNamespace(deterministic=True, benchmark=False),
        )

    @staticmethod
    def from_numpy(value: np.ndarray) -> FakeTensor:
        return FakeTensor(value)

    @staticmethod
    def no_grad():
        return nullcontext()


class FakeModel:
    def __init__(self, sources: tuple[str, ...]) -> None:
        self.sources = sources
        self.segment = 10.0
        self.device = None

    def to(self, device: str) -> FakeModel:
        self.device = device
        return self


@dataclass
class MinimalMeasurements:
    marker: str


@pytest.fixture(autouse=True)
def isolated_model_cache():
    clear_model_cache()
    yield
    clear_model_cache()


@pytest.fixture
def audio() -> np.ndarray:
    left = np.linspace(-0.4, 0.4, 20, dtype=np.float64)
    return np.column_stack((left, left[::-1]))


def _output(sources: tuple[str, ...], samples: int) -> np.ndarray:
    separated = np.zeros((1, len(sources), 2, samples), dtype=np.float32)
    for index in range(len(sources)):
        separated[0, index] = (index + 1) * 0.01
    return separated


def _split(
    audio: np.ndarray,
    *,
    model_name: str,
    sources: tuple[str, ...],
    separated: np.ndarray,
    torch_module: FakeTorch | None = None,
) -> StemBundle:
    model = FakeModel(sources)
    return split_stems(
        audio,
        48_000,
        stem_config=StemConfig(model_name=model_name),
        torch_module=torch_module or FakeTorch(),
        model_loader=lambda _name: model,
        apply_model_fn=lambda *_args, **_kwargs: separated,
    )


def test_tc022_01_active_registry_and_cli_support_six_stems() -> None:
    assert MODEL_REGISTRY["htdemucs_6s"] == SIX_SOURCES
    assert MODEL_REGISTRY["htdemucs"] == FOUR_SOURCES
    assert StemConfig(model_name="htdemucs_6s").model_name == "htdemucs_6s"
    args = build_arg_parser().parse_args(["input.wav", "--stem-model", "htdemucs_6s"])
    assert args.stem_model == "htdemucs_6s"


def test_tc022_02_piano_and_guitar_are_explicit_channels(audio: np.ndarray) -> None:
    bundle = _split(
        audio,
        model_name="htdemucs_6s",
        sources=SIX_SOURCES,
        separated=_output(SIX_SOURCES, audio.shape[0]),
    )

    assert tuple(bundle) == SIX_SOURCES
    assert "piano" in bundle and "guitar" in bundle
    assert not np.array_equal(bundle["piano"], bundle["other"])
    assert not np.array_equal(bundle["guitar"], bundle["other"])


def test_tc022_03_partial_six_stem_bundle_is_rejected(audio: np.ndarray) -> None:
    partial_sources = SIX_SOURCES[:-1]
    with pytest.raises(ValueError, match="expected exactly"):
        _split(
            audio,
            model_name="htdemucs_6s",
            sources=partial_sources,
            separated=_output(partial_sources, audio.shape[0]),
        )


@pytest.mark.parametrize(
    ("model_name", "canonical", "reported"),
    [
        ("htdemucs", FOUR_SOURCES, ("vocals", "other", "drums", "bass")),
        (
            "htdemucs_6s",
            SIX_SOURCES,
            ("guitar", "vocals", "piano", "drums", "other", "bass"),
        ),
    ],
)
def test_tc022_04_mapping_follows_alternate_model_source_order(
    audio: np.ndarray,
    model_name: str,
    canonical: tuple[str, ...],
    reported: tuple[str, ...],
) -> None:
    separated = _output(reported, audio.shape[0])
    bundle = _split(
        audio,
        model_name=model_name,
        sources=reported,
        separated=separated,
    )

    assert tuple(bundle) == canonical
    for canonical_name in canonical:
        reported_index = reported.index(canonical_name)
        assert np.all(bundle[canonical_name] == pytest.approx((reported_index + 1) * 0.01))
    assert bundle.runtime_metadata["model_source_order"] == list(reported)
    assert bundle.runtime_metadata["canonical_source_order"] == list(canonical)


def _malformed_case(case: str, samples: int) -> tuple[tuple[str, ...], np.ndarray]:
    sources = SIX_SOURCES
    separated = _output(sources, samples)
    if case == "missing":
        sources = SIX_SOURCES[:-1]
        separated = _output(sources, samples)
    elif case == "extra":
        sources = SIX_SOURCES + ("noise",)
        separated = _output(sources, samples)
    elif case == "duplicate":
        sources = SIX_SOURCES[:-1] + ("piano",)
    elif case == "mono":
        separated = np.zeros((1, 6, 1, samples), dtype=np.float32)
    elif case == "wrong_length":
        separated = _output(sources, samples - 1)
    elif case == "wrong_count":
        separated = np.zeros((1, 5, 2, samples), dtype=np.float32)
    elif case == "non_finite":
        separated[0, 0, 0, 0] = np.nan
    else:
        raise AssertionError(f"unknown malformed case: {case}")
    return sources, separated


@pytest.mark.parametrize(
    "case",
    ["missing", "extra", "duplicate", "mono", "wrong_length", "wrong_count", "non_finite"],
)
def test_tc022_05_exhaustive_malformed_outputs_fail_without_fallback(
    audio: np.ndarray,
    case: str,
) -> None:
    sources, separated = _malformed_case(case, audio.shape[0])
    model = FakeModel(sources)
    applied_devices: list[str] = []

    def apply(_model, _tensor, *, device: str, **_kwargs):
        applied_devices.append(device)
        return separated

    with pytest.raises(ValueError):
        split_stems(
            audio,
            48_000,
            stem_config=StemConfig(model_name="htdemucs_6s", allow_device_fallback=True),
            torch_module=FakeTorch(cuda=True),
            model_loader=lambda _name: model,
            apply_model_fn=apply,
        )

    assert applied_devices == ["cuda"]


@pytest.mark.parametrize(
    ("model_name", "sources"),
    [("htdemucs", FOUR_SOURCES), ("htdemucs_6s", SIX_SOURCES)],
)
def test_tc022_06_uncorrected_residual_is_reported_without_stem_mutation(
    audio: np.ndarray,
    model_name: str,
    sources: tuple[str, ...],
) -> None:
    separated = _output(sources, audio.shape[0])
    original_output = separated.copy()
    bundle = _split(
        audio,
        model_name=model_name,
        sources=sources,
        separated=separated,
    )

    assert np.array_equal(separated, original_output)
    for index, source_name in enumerate(sources):
        expected_stem = np.asarray(original_output[0, index].T, dtype=np.float64)
        assert np.array_equal(bundle[source_name], expected_stem)

    reconstructed = sum(bundle.values(), np.zeros_like(audio))
    residual = audio - reconstructed
    expected_ratio = float(np.sum(np.square(residual)) / np.sum(np.square(audio)))
    assert bundle.runtime_metadata["residual_peak"] == pytest.approx(np.max(np.abs(residual)))
    assert bundle.runtime_metadata["residual_energy_ratio"] == pytest.approx(expected_ratio)


def test_tc022_07_six_stem_metadata_propagates_to_json_report(
    audio: np.ndarray,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    separated = _output(SIX_SOURCES, audio.shape[0])
    bundle = _split(
        audio,
        model_name="htdemucs_6s",
        sources=("guitar", "vocals", "piano", "drums", "other", "bass"),
        separated=separated,
    )
    monkeypatch.setattr(stem_integration, "split_stems", lambda **_kwargs: bundle)
    monkeypatch.setattr(
        stem_integration,
        "process_stems",
        lambda stems, sample_rate, identified_issues=None: (dict(stems), []),
    )
    monkeypatch.setattr(
        stem_integration,
        "sum_stems",
        lambda stems: sum(stems.values(), np.zeros_like(audio)),
    )

    _processed, stem_result = stem_integration.run_stem_preprocessing(
        audio,
        48_000,
        StemConfig(enabled=True, model_name="htdemucs_6s"),
    )
    # The stem stage augments the separation metadata with the STORY-019 M/S
    # boundary and STORY-023 forensics diagnostics, so the result metadata must
    # contain the original bundle metadata rather than be the identical object.
    assert bundle.runtime_metadata.items() <= stem_result.runtime_metadata.items()
    assert stem_result.runtime_metadata["model_name"] == "htdemucs_6s"

    solver = SimpleNamespace(
        target_lufs=-12.0,
        achieved_lufs=-12.1,
        achieved_true_peak_dbtp=-1.0,
        achieved_dr=9.0,
        source_dr=10.0,
        dr_floor_used=8.0,
        gain_db_applied=1.0,
        outer_iterations=1,
        peak_convergence_iterations=1,
        below_soft_band=False,
        below_documented_lufs_floor=False,
        rationale="fixture",
    )
    report = build_report(
        config=MasteringConfig(),
        input_path="input.wav",
        output_path="mastered.wav",
        input_hash="input-hash",
        output_hash="output-hash",
        before=MinimalMeasurements("before"),
        after=MinimalMeasurements("after"),
        resample_action=None,
        eq_actions=[],
        stereo_actions=[],
        solver_outcome=solver,
        integrity_verified=True,
        stem_runtime=stem_result.runtime_metadata,
    )
    payload = json.loads(render_json(report))
    runtime = payload["stem_runtime"]

    assert runtime["model_name"] == "htdemucs_6s"
    assert runtime["model_source_order"] == ["guitar", "vocals", "piano", "drums", "other", "bass"]
    assert runtime["canonical_source_order"] == list(SIX_SOURCES)
    assert set(runtime["stem_peaks"]) == set(SIX_SOURCES)
    assert "piano" in runtime["stem_peaks"] and "guitar" in runtime["stem_peaks"]