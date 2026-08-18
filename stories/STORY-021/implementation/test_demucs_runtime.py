import types

import pytest

from demucs_runtime import (
    DEVICE_REPORT,
    _MODEL_CACHE,
    build_cache_key,
    get_or_create_model,
    resolve_device,
    run_demucs_inference,
    safe_fallback,
)


class FakeCuda:
    def __init__(self, available: bool):
        self.available = available
        self.device_count = 1 if available else 0


class FakeMPS:
    def __init__(self, available: bool):
        self.available = available


class FakeTorch:
    def __init__(self, *, cuda_available: bool = False, mps_available: bool = False):
        self.cuda = FakeCuda(cuda_available)
        self.backends = types.SimpleNamespace(mps=FakeMPS(mps_available))


def test_tc021_01_cuda_selection_when_available():
    torch_module = FakeTorch(cuda_available=True, mps_available=True)
    device = resolve_device(torch_module=torch_module)
    assert device == "cuda"
    assert DEVICE_REPORT["selected_device"] == "cuda"
    assert DEVICE_REPORT["fallback_reason"] is None


def test_tc021_02_mps_selection_when_cuda_unavailable():
    torch_module = FakeTorch(cuda_available=False, mps_available=True)
    device = resolve_device(torch_module=torch_module)
    assert device == "mps"
    assert DEVICE_REPORT["selected_device"] == "mps"
    assert DEVICE_REPORT["fallback_reason"] == "cuda_unavailable"


def test_tc021_03_cpu_fallback_when_no_accelerator_exists():
    torch_module = FakeTorch(cuda_available=False, mps_available=False)
    device = resolve_device(torch_module=torch_module)
    assert device == "cpu"
    assert DEVICE_REPORT["selected_device"] == "cpu"
    assert DEVICE_REPORT["fallback_reason"] == "no_accelerator_available"


def test_tc021_04_cache_hit_reuses_model_instance():
    _MODEL_CACHE.clear()
    calls = []

    def loader(model_name, device, config=None):
        calls.append((model_name, device, config))
        return object()

    first = get_or_create_model("htdemucs", "cuda", {"overlap": 0.5}, loader=loader)
    second = get_or_create_model("htdemucs", "cuda", {"overlap": 0.5}, loader=loader)

    assert first is second
    assert len(calls) == 1
    assert build_cache_key("htdemucs", "cuda", {"overlap": 0.5}) in _MODEL_CACHE


def test_tc021_05_config_mismatch_rejected_by_cache():
    _MODEL_CACHE.clear()
    seen = []

    def loader(model_name, device, config=None):
        seen.append((model_name, device, dict(config)))
        return object()

    first = get_or_create_model("htdemucs", "cuda", {"shift_count": 2, "overlap": 0.5}, loader=loader)
    second = get_or_create_model("htdemucs", "cuda", {"shift_count": 3, "overlap": 0.5}, loader=loader)

    assert first is not second
    assert len(seen) == 2


def test_tc021_06_runtime_reports_clear_cpu_fallback_after_guarded_error():
    attempts = []

    def failing_loader(model_name, device, config=None):
        attempts.append(device)
        if device == "cuda":
            raise RuntimeError("CUDA init failed")
        if device == "mps":
            raise RuntimeError("MPS init failed")
        return object()

    model = run_demucs_inference(
        audio=None,
        sample_rate=44100,
        model_name="htdemucs",
        config={"segment_length": 4096},
        torch_module=FakeTorch(cuda_available=True, mps_available=True),
        loader=failing_loader,
    )

    assert model["device"] == "cpu"
    assert model["cache_status"] == "cpu_fallback"
    assert "CUDA init failed" in model["report"]["fallback_reason"]


def test_tc021_07_safe_fallback_keeps_original_error_context():
    def loader(model_name, device, config=None):
        raise RuntimeError("broken backend")

    with pytest.raises(RuntimeError, match="broken backend"):
        safe_fallback(loader, model_name="htdemucs", device="cuda", config={"x": 1})
