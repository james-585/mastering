"""Stem separation using Demucs for pre-mastering DSP (STORY-008).

This module orchestrates the optional AI stem-separation stage that runs before
the main mastering pipeline. Four- and six-source Demucs models are supported.

Dependencies:
    - demucs (Facebook Research stem separator)
    - torch (PyTorch backend)

Both are treated as optional. If --split-stems is invoked without them
installed, the pipeline raises DependencyError with installation instructions
rather than crashing with raw ModuleNotFoundError.
"""
from __future__ import annotations

from contextlib import nullcontext
from importlib import metadata as importlib_metadata
import logging
import os
from pathlib import Path
import threading
from typing import Any, Callable

import numpy as np

from ..config import StemConfig
from ..errors import DependencyError

logger = logging.getLogger(__name__)


def _ensure_hf_token_env() -> None:
    """Load HF_TOKEN from the environment or a local .env before any HF-backed fetch."""
    if not os.getenv("HF_TOKEN"):
        try:
            from dotenv import find_dotenv, load_dotenv
        except ImportError:
            pass
        else:
            load_dotenv(find_dotenv(usecwd=True))
    token = os.getenv("HF_TOKEN")
    if token:
        # huggingface_hub also honors this legacy alias.
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", token)

MODEL_REGISTRY: dict[str, tuple[str, ...]] = {
    "htdemucs": ("drums", "bass", "other", "vocals"),
    "htdemucs_ft": ("drums", "bass", "other", "vocals"),
    "mdx_extra": ("drums", "bass", "other", "vocals"),
    "htdemucs_6s": ("drums", "bass", "other", "vocals", "piano", "guitar"),
}
CACHE_SCHEMA_VERSION = "demucs-model-cache-v1"

_MODEL_CACHE: dict[tuple[Any, ...], Any] = {}
_MODEL_CACHE_LOCK = threading.Lock()


class StemBundle(dict[str, np.ndarray]):
    """Dict-compatible separated stems with immutable per-run provenance."""

    def __init__(self, stems: dict[str, np.ndarray], runtime_metadata: dict[str, Any]) -> None:
        super().__init__(stems)
        self.runtime_metadata = runtime_metadata


def clear_model_cache() -> None:
    """Clear cached Demucs models, primarily for isolated runtime checks."""
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.clear()


def _dependency_version(package_name: str) -> str | None:
    try:
        return importlib_metadata.version(package_name)
    except importlib_metadata.PackageNotFoundError:
        return None


def _load_dependencies(
    torch_module: Any | None,
    model_loader: Callable[[str], Any] | None,
    apply_model_fn: Callable[..., Any] | None,
) -> tuple[Any, Callable[[str], Any], Callable[..., Any]]:
    try:
        if torch_module is None:
            import torch as torch_module
        if model_loader is None:
            from demucs.pretrained import get_model as model_loader
        if apply_model_fn is None:
            from demucs.apply import apply_model as apply_model_fn
    except Exception as exc:  # noqa: BLE001 - dependency diagnostics retain original context
        raise DependencyError(
            "Stem separation requires demucs and torch, which are not installed.\n"
            "Install with:\n"
            "    pip install demucs torch\n\n"
            f"Original import error: {type(exc).__name__}: {exc}"
        ) from exc
    return torch_module, model_loader, apply_model_fn


def resolve_device(torch_module: Any) -> str:
    """Resolve the preferred execution device in CUDA, MPS, CPU order."""
    cuda = getattr(torch_module, "cuda", None)
    if cuda is not None and callable(getattr(cuda, "is_available", None)):
        if cuda.is_available():
            return "cuda"
    mps = getattr(getattr(torch_module, "backends", None), "mps", None)
    if mps is not None and callable(getattr(mps, "is_available", None)):
        if mps.is_available():
            return "mps"
    return "cpu"


def _model_cache_key(model_name: str, device: str, torch_module: Any) -> tuple[Any, ...]:
    return (
        CACHE_SCHEMA_VERSION,
        model_name,
        None,  # model revision: Demucs registry default
        "demucs-pretrained",  # weights identity
        device,
        device,  # placement
        "model-default",  # dtype/precision
        (),  # construction options
        None,  # compile mode
        (),  # compile options
        _dependency_version("demucs"),
        getattr(torch_module, "__version__", _dependency_version("torch")),
    )


def _get_or_create_model(
    model_name: str,
    device: str,
    torch_module: Any,
    model_loader: Callable[[str], Any],
) -> tuple[Any, bool, tuple[Any, ...]]:
    cache_key = _model_cache_key(model_name, device, torch_module)
    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached, True, cache_key

        model = model_loader(model_name)
        move_to_device = getattr(model, "to", None)
        if callable(move_to_device):
            moved_model = move_to_device(device)
            if moved_model is not None:
                model = moved_model
        _MODEL_CACHE[cache_key] = model
        return model, False, cache_key


def _torch_runtime_state(torch_module: Any) -> dict[str, Any]:
    seed_fn = getattr(torch_module, "initial_seed", None)
    deterministic_fn = getattr(torch_module, "are_deterministic_algorithms_enabled", None)
    cudnn = getattr(getattr(torch_module, "backends", None), "cudnn", None)
    return {
        "initial_seed": seed_fn() if callable(seed_fn) else None,
        "deterministic_algorithms": deterministic_fn() if callable(deterministic_fn) else None,
        "cudnn_deterministic": getattr(cudnn, "deterministic", None),
        "cudnn_benchmark": getattr(cudnn, "benchmark", None),
    }


def _to_numpy(value: Any) -> np.ndarray:
    for method_name in ("detach", "cpu"):
        method = getattr(value, method_name, None)
        if callable(method):
            value = method()
    numpy_method = getattr(value, "numpy", None)
    if callable(numpy_method):
        value = numpy_method()
    return np.asarray(value)


def _validate_and_map_output(
    separated: Any,
    model: Any,
    model_name: str,
    input_samples: int,
) -> tuple[dict[str, np.ndarray], tuple[str, ...], tuple[str, ...]]:
    canonical_sources = MODEL_REGISTRY[model_name]
    reported_sources = tuple(getattr(model, "sources", ()))
    if len(reported_sources) != len(set(reported_sources)):
        raise ValueError(f"Model {model_name} returned duplicate source names: {reported_sources}")
    if set(reported_sources) != set(canonical_sources):
        raise ValueError(
            f"Model {model_name} returned source names {reported_sources}; "
            f"expected exactly {canonical_sources}"
        )

    separated_array = _to_numpy(separated)
    expected_shape = (1, len(canonical_sources), 2, input_samples)
    if separated_array.shape != expected_shape:
        raise ValueError(
            f"Model {model_name} returned shape {separated_array.shape}; "
            f"expected {expected_shape}"
        )

    by_reported_name: dict[str, np.ndarray] = {}
    for index, source_name in enumerate(reported_sources):
        stem = np.asarray(separated_array[0, index].T, dtype=np.float64)
        if stem.shape != (input_samples, 2):
            raise ValueError(f"Stem {source_name!r} has invalid shape {stem.shape}")
        if not np.isfinite(stem).all():
            raise ValueError(f"Stem {source_name!r} contains non-finite values")
        by_reported_name[source_name] = stem

    stems = {source_name: by_reported_name[source_name] for source_name in canonical_sources}
    return stems, reported_sources, canonical_sources


def _run_inference(
    model: Any,
    audio_tensor: Any,
    device: str,
    config: StemConfig,
    torch_module: Any,
    apply_model_fn: Callable[..., Any],
) -> Any:
    no_grad = getattr(torch_module, "no_grad", None)
    context = no_grad() if callable(no_grad) else nullcontext()
    with context:
        return apply_model_fn(
            model,
            audio_tensor,
            device=device,
            shifts=config.shifts,
            overlap=config.overlap,
            segment=config.segment_seconds,
            split=True,
            progress=False,
        )

def split_stems(
    audio_array: np.ndarray,
    sample_rate: int,
    model_name: str | StemConfig | None = None,
    *,
    stem_config: StemConfig | None = None,
    torch_module: Any | None = None,
    model_loader: Callable[[str], Any] | None = None,
    apply_model_fn: Callable[..., Any] | None = None,
) -> StemBundle:
    """Split stereo float64 audio into validated Demucs stems.

    Args:
        audio_array: float64, shape (samples, 2) stereo.
        sample_rate: int, sample rate in Hz.
        model_name: Legacy model-name argument. Prefer ``stem_config``.
        stem_config: Complete live inference and fallback configuration.
        torch_module: Optional injected Torch-compatible dependency.
        model_loader: Optional injected Demucs model loader.
        apply_model_fn: Optional injected Demucs inference function.

    Returns:
        Dict-compatible ``StemBundle`` mapping canonical source names to float64
        arrays of shape ``(samples, 2)`` and carrying ``runtime_metadata``.

    Raises:
        DependencyError: if demucs or torch are not installed.
        ValueError: if audio_array is not stereo or has invalid shape.

    """
    if isinstance(model_name, StemConfig):
        if stem_config is not None:
            raise ValueError("Provide StemConfig either positionally or by stem_config, not both")
        stem_config = model_name
        model_name = None
    if stem_config is None:
        stem_config = StemConfig(model_name=model_name or "htdemucs_6s")
    elif model_name is not None and model_name != stem_config.model_name:
        raise ValueError("model_name conflicts with stem_config.model_name")

    if not isinstance(audio_array, np.ndarray) or audio_array.dtype != np.float64:
        raise ValueError("split_stems requires a float64 NumPy audio array")
    if audio_array.ndim != 2 or audio_array.shape[1] != 2:
        raise ValueError(
            f"split_stems requires stereo audio with shape (samples, 2), "
            f"got shape {audio_array.shape}"
        )
    if not np.isfinite(audio_array).all():
        raise ValueError("split_stems requires finite input audio")
    if isinstance(sample_rate, bool) or not isinstance(sample_rate, int) or sample_rate <= 0:
        raise ValueError("sample_rate must be a positive integer")

    _ensure_hf_token_env()

    # --- Disk cache check ---
    _cache_dir_str = getattr(stem_config, "stem_cache_dir", None)
    _cache_dir = Path(_cache_dir_str) if _cache_dir_str else None
    if _cache_dir is not None:
        from importlib import metadata as _meta
        _demucs_ver = None
        try:
            _demucs_ver = _meta.version("demucs")
        except Exception:
            pass
        from . import stem_cache as _stem_cache
        _cached = _stem_cache.load(
            _cache_dir, audio_array, sample_rate,
            stem_config.model_name, stem_config.shifts,
            stem_config.overlap, stem_config.segment_seconds, _demucs_ver,
        )
        if _cached is not None:
            return _cached

    torch_module, model_loader, apply_model_fn = _load_dependencies(
        torch_module, model_loader, apply_model_fn
    )
    requested_device = resolve_device(torch_module)
    final_device = requested_device
    fallback_point: str | None = None
    fallback_reason: str | None = None
    backend_error_context: str | None = None

    audio_tensor = torch_module.from_numpy(audio_array.T).float().unsqueeze(0)
    try:
        model, cache_hit, cache_key = _get_or_create_model(
            stem_config.model_name, requested_device, torch_module, model_loader
        )
    except Exception as exc:  # noqa: BLE001 - accelerator load errors are fallback candidates
        if requested_device == "cpu" or not stem_config.allow_device_fallback:
            logger.error("Demucs model load failed on %s: %s: %s", requested_device, type(exc).__name__, exc)
            raise
        fallback_point = "model_load"
        fallback_reason = f"{type(exc).__name__}: {exc}"
        backend_error_context = fallback_reason
        final_device = "cpu"
        logger.warning("Demucs %s failed; retrying once on CPU: %s", fallback_point, fallback_reason)
        try:
            model, cache_hit, cache_key = _get_or_create_model(
                stem_config.model_name, final_device, torch_module, model_loader
            )
        except Exception as cpu_exc:  # noqa: BLE001 - preserve both backend contexts
            raise RuntimeError(
                f"Demucs accelerator model load failed ({fallback_reason}); "
                f"CPU fallback failed ({type(cpu_exc).__name__}: {cpu_exc})"
            ) from cpu_exc

    try:
        separated = _run_inference(
            model, audio_tensor, final_device, stem_config, torch_module, apply_model_fn
        )
    except Exception as exc:  # noqa: BLE001 - accelerator inference errors are fallback candidates
        if final_device == "cpu" or not stem_config.allow_device_fallback:
            logger.error("Demucs inference failed on %s: %s: %s", final_device, type(exc).__name__, exc)
            raise
        fallback_point = "inference"
        fallback_reason = f"{type(exc).__name__}: {exc}"
        backend_error_context = fallback_reason
        final_device = "cpu"
        logger.warning("Demucs inference failed; retrying once on CPU: %s", fallback_reason)
        try:
            model, cache_hit, cache_key = _get_or_create_model(
                stem_config.model_name, final_device, torch_module, model_loader
            )
            separated = _run_inference(
                model, audio_tensor, final_device, stem_config, torch_module, apply_model_fn
            )
        except Exception as cpu_exc:  # noqa: BLE001 - preserve both backend contexts
            raise RuntimeError(
                f"Demucs accelerator inference failed ({fallback_reason}); "
                f"CPU fallback failed ({type(cpu_exc).__name__}: {cpu_exc})"
            ) from cpu_exc

    stems, reported_sources, canonical_sources = _validate_and_map_output(
        separated, model, stem_config.model_name, audio_array.shape[0]
    )
    reconstructed = np.zeros_like(audio_array, dtype=np.float64)
    for stem in stems.values():
        reconstructed += stem
    residual = audio_array - reconstructed
    input_energy = float(np.sum(np.square(audio_array)))
    residual_energy = float(np.sum(np.square(residual)))
    residual_energy_ratio = residual_energy / input_energy if input_energy > 0.0 else None
    runtime_metadata = {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "cache_key": [str(value) if value is not None else None for value in cache_key],
        "cache_hit": cache_hit,
        "model_name": stem_config.model_name,
        "requested_device": requested_device,
        "final_device": final_device,
        "fallback_point": fallback_point,
        "fallback_reason": fallback_reason,
        "backend_error_context": backend_error_context,
        "profile": {
            "version": stem_config.profile_version,
            "shifts": stem_config.shifts,
            "overlap": float(stem_config.overlap),
            "segment_seconds": stem_config.segment_seconds,
        },
        "torch_version": getattr(torch_module, "__version__", _dependency_version("torch")),
        "demucs_version": _dependency_version("demucs"),
        "deterministic_settings": _torch_runtime_state(torch_module),
        "effective_model_segment": getattr(model, "segment", None),
        "model_source_order": list(reported_sources),
        "canonical_source_order": list(canonical_sources),
        "residual_peak": float(np.max(np.abs(residual))),
        "residual_energy_ratio": residual_energy_ratio,
        "stem_peaks": {name: float(np.max(np.abs(stem))) for name, stem in stems.items()},
    }
    logger.info(
        "Stem separation complete: model=%s device=%s profile=%s cache_hit=%s "
        "sources=%s residual_peak=%.6e residual_energy_ratio=%s",
        stem_config.model_name,
        final_device,
        stem_config.profile_version,
        cache_hit,
        list(canonical_sources),
        runtime_metadata["residual_peak"],
        residual_energy_ratio,
    )
    bundle = StemBundle(stems, runtime_metadata)

    # --- Disk cache save ---
    if _cache_dir is not None:
        _stem_cache.save(
            _cache_dir, audio_array, sample_rate,
            stem_config.model_name, stem_config.shifts,
            stem_config.overlap, stem_config.segment_seconds, _demucs_ver,
            bundle,
        )

    return bundle
