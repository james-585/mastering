from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import numpy as np
import pytest

from suno_mastering.config import StemConfig
from suno_mastering.io.stem_separation import (
    CACHE_SCHEMA_VERSION,
    clear_model_cache,
    resolve_device,
    split_stems,
)


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
    __version__ = "fake-torch-2.1"

    def __init__(self, *, cuda: bool = False, mps: bool = False) -> None:
        self.cuda = SimpleNamespace(is_available=lambda: cuda)
        self.backends = SimpleNamespace(
            mps=SimpleNamespace(is_available=lambda: mps),
            cudnn=SimpleNamespace(deterministic=True, benchmark=False),
        )

    @staticmethod
    def from_numpy(value: np.ndarray) -> FakeTensor:
        return FakeTensor(value)

    @staticmethod
    def no_grad():
        return nullcontext()

    @staticmethod
    def initial_seed() -> int:
        return 20260817

    @staticmethod
    def are_deterministic_algorithms_enabled() -> bool:
        return True


class FakeModel:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.sources = SIX_SOURCES if model_name == "htdemucs_6s" else FOUR_SOURCES
        self.segment = None
        self.device = None

    def to(self, device: str) -> FakeModel:
        self.device = device
        return self


@pytest.fixture(autouse=True)
def isolated_model_cache():
    clear_model_cache()
    yield
    clear_model_cache()


@pytest.fixture
def audio() -> np.ndarray:
    return np.full((24, 2), 0.2, dtype=np.float64)


def _output_for(model: FakeModel, samples: int, *, finite: bool = True) -> np.ndarray:
    output = np.zeros((1, len(model.sources), 2, samples), dtype=np.float32)
    for index in range(len(model.sources)):
        output[0, index] = (index + 1) * 0.01
    if not finite:
        output[0, 0, 0, 0] = np.nan
    return output


def test_tc021_01_cuda_device_selection() -> None:
    assert resolve_device(FakeTorch(cuda=True, mps=True)) == "cuda"


def test_tc021_02_mps_device_selection() -> None:
    assert resolve_device(FakeTorch(cuda=False, mps=True)) == "mps"


def test_tc021_03_cpu_device_selection() -> None:
    assert resolve_device(FakeTorch(cuda=False, mps=False)) == "cpu"


def test_tc021_04_identical_model_and_device_hit_cache(audio: np.ndarray) -> None:
    loaded: list[FakeModel] = []
    applied_models: list[FakeModel] = []

    def loader(name: str) -> FakeModel:
        model = FakeModel(name)
        loaded.append(model)
        return model

    def apply(model: FakeModel, _tensor, **_kwargs):
        applied_models.append(model)
        return _output_for(model, audio.shape[0])

    first = split_stems(
        audio,
        44_100,
        stem_config=StemConfig(),
        torch_module=FakeTorch(),
        model_loader=loader,
        apply_model_fn=apply,
    )
    second = split_stems(
        audio,
        44_100,
        stem_config=StemConfig(),
        torch_module=FakeTorch(),
        model_loader=loader,
        apply_model_fn=apply,
    )

    assert len(loaded) == 1
    assert applied_models[0] is applied_models[1]
    assert first.runtime_metadata["cache_hit"] is False
    assert second.runtime_metadata["cache_hit"] is True


def test_tc021_05_cache_isolated_by_device_and_model(audio: np.ndarray) -> None:
    loads: list[tuple[str, str | None]] = []

    def loader(name: str) -> FakeModel:
        model = FakeModel(name)
        loads.append((name, model.device))
        return model

    def apply(model: FakeModel, _tensor, **_kwargs):
        return _output_for(model, audio.shape[0])

    bundles = [
        split_stems(
            audio,
            44_100,
            stem_config=StemConfig(model_name="htdemucs"),
            torch_module=FakeTorch(),
            model_loader=loader,
            apply_model_fn=apply,
        ),
        split_stems(
            audio,
            44_100,
            stem_config=StemConfig(model_name="htdemucs"),
            torch_module=FakeTorch(cuda=True),
            model_loader=loader,
            apply_model_fn=apply,
        ),
        split_stems(
            audio,
            44_100,
            stem_config=StemConfig(model_name="htdemucs_6s"),
            torch_module=FakeTorch(cuda=True),
            model_loader=loader,
            apply_model_fn=apply,
        ),
    ]

    assert len(loads) == 3
    assert [bundle.runtime_metadata["cache_hit"] for bundle in bundles] == [False, False, False]
    assert [bundle.runtime_metadata["final_device"] for bundle in bundles] == ["cpu", "cuda", "cuda"]


def test_tc021_06_run_only_controls_reuse_model(audio: np.ndarray) -> None:
    load_count = 0
    calls: list[dict] = []

    def loader(name: str) -> FakeModel:
        nonlocal load_count
        load_count += 1
        return FakeModel(name)

    def apply(model: FakeModel, _tensor, **kwargs):
        calls.append(kwargs)
        return _output_for(model, audio.shape[0])

    first = split_stems(
        audio,
        44_100,
        stem_config=StemConfig(
            shifts=1,
            overlap=0.25,
            segment_seconds=None,
            profile_version="run-a",
        ),
        torch_module=FakeTorch(),
        model_loader=loader,
        apply_model_fn=apply,
    )
    second = split_stems(
        audio,
        44_100,
        stem_config=StemConfig(
            shifts=4,
            overlap=0.5,
            segment_seconds=12.0,
            profile_version="run-b",
        ),
        torch_module=FakeTorch(),
        model_loader=loader,
        apply_model_fn=apply,
    )

    assert load_count == 1
    assert first.runtime_metadata["cache_hit"] is False
    assert second.runtime_metadata["cache_hit"] is True
    assert [
        (call["shifts"], call["overlap"], call["segment"])
        for call in calls
    ] == [(1, 0.25, None), (4, 0.5, 12.0)]


def test_tc021_07_accelerator_failure_retries_cpu_once(audio: np.ndarray) -> None:
    applied_devices: list[str] = []
    loaded_devices: list[str] = []

    def loader(name: str) -> FakeModel:
        model = FakeModel(name)
        original_to = model.to

        def tracked_to(device: str):
            loaded_devices.append(device)
            return original_to(device)

        model.to = tracked_to
        return model

    def apply(model: FakeModel, _tensor, *, device: str, **_kwargs):
        applied_devices.append(device)
        if device == "cuda":
            raise RuntimeError("accelerator kernel failed")
        return _output_for(model, audio.shape[0])

    bundle = split_stems(
        audio,
        44_100,
        stem_config=StemConfig(allow_device_fallback=True),
        torch_module=FakeTorch(cuda=True),
        model_loader=loader,
        apply_model_fn=apply,
    )

    assert applied_devices == ["cuda", "cpu"]
    assert loaded_devices == ["cuda", "cpu"]
    assert bundle.runtime_metadata["requested_device"] == "cuda"
    assert bundle.runtime_metadata["final_device"] == "cpu"
    assert bundle.runtime_metadata["fallback_point"] == "inference"
    assert bundle.runtime_metadata["fallback_reason"] == "RuntimeError: accelerator kernel failed"
    assert bundle.runtime_metadata["backend_error_context"] == bundle.runtime_metadata["fallback_reason"]


def test_tc021_08_strict_mode_preserves_original_failure(audio: np.ndarray) -> None:
    class AcceleratorFailure(RuntimeError):
        pass

    applied_devices: list[str] = []

    def apply(_model, _tensor, *, device: str, **_kwargs):
        applied_devices.append(device)
        raise AcceleratorFailure("strict accelerator failure")

    with pytest.raises(AcceleratorFailure, match="strict accelerator failure"):
        split_stems(
            audio,
            44_100,
            stem_config=StemConfig(allow_device_fallback=False),
            torch_module=FakeTorch(cuda=True),
            model_loader=FakeModel,
            apply_model_fn=apply,
        )

    assert applied_devices == ["cuda"]


def test_tc021_09_malformed_output_never_falls_back(audio: np.ndarray) -> None:
    applied_devices: list[str] = []

    def apply(model: FakeModel, _tensor, *, device: str, **_kwargs):
        applied_devices.append(device)
        return _output_for(model, audio.shape[0] - 1)

    with pytest.raises(ValueError, match="returned shape"):
        split_stems(
            audio,
            44_100,
            stem_config=StemConfig(allow_device_fallback=True),
            torch_module=FakeTorch(cuda=True),
            model_loader=FakeModel,
            apply_model_fn=apply,
        )

    assert applied_devices == ["cuda"]


def test_tc021_10_runtime_provenance_is_complete(audio: np.ndarray) -> None:
    bundle = split_stems(
        audio,
        48_000,
        stem_config=StemConfig(profile_version="provenance-v1"),
        torch_module=FakeTorch(),
        model_loader=FakeModel,
        apply_model_fn=lambda model, _tensor, **_kwargs: _output_for(model, audio.shape[0]),
    )
    metadata = bundle.runtime_metadata

    assert {
        "cache_schema_version",
        "cache_key",
        "cache_hit",
        "model_name",
        "requested_device",
        "final_device",
        "fallback_point",
        "fallback_reason",
        "backend_error_context",
        "profile",
        "torch_version",
        "demucs_version",
        "deterministic_settings",
        "effective_model_segment",
        "model_source_order",
        "canonical_source_order",
    } <= metadata.keys()
    assert metadata["cache_schema_version"] == CACHE_SCHEMA_VERSION
    assert metadata["cache_key"][0] == CACHE_SCHEMA_VERSION
    assert metadata["torch_version"] == "fake-torch-2.1"
    assert metadata["profile"]["version"] == "provenance-v1"
    # The product default model is htdemucs_6s (STORY-022 owner decision), so
    # the default StemConfig used here produces the six-stem source order.
    assert metadata["model_source_order"] == list(SIX_SOURCES)
    assert metadata["canonical_source_order"] == list(SIX_SOURCES)
    assert metadata["deterministic_settings"] == {
        "initial_seed": 20260817,
        "deterministic_algorithms": True,
        "cudnn_deterministic": True,
        "cudnn_benchmark": False,
    }