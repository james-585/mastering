"""Hardware-aware Demucs runtime with explicit device resolution and model caching.

This module is intentionally narrow: it does not change the mastering DSP path,
only selects the best available local runtime for Demucs model creation and
reuses a cached model instance only when the device/config pair matches.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from copy import deepcopy
from typing import Any, Callable, Dict, Iterable, Optional

logger = logging.getLogger(__name__)

MODEL_CACHE: Dict[str, Dict[str, Any]] = {}
_MODEL_CACHE = MODEL_CACHE
DEVICE_REPORT: Dict[str, Any] = {
    "selected_device": None,
    "preferred_device": None,
    "fallback_reason": None,
    "cache_status": "unset",
    "cache_key": None,
    "last_model_name": None,
    "last_error": None,
}


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


def _canonicalize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _canonicalize(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, set):
        return sorted(_canonicalize(item) for item in value)
    return repr(value)


def build_cache_key(model_name: str, device: str, config: Optional[Dict[str, Any]] = None) -> str:
    """Create a deterministic cache key from model name, device, and config."""
    payload = {
        "model_name": str(model_name),
        "device": str(device or "cpu"),
        "config": _canonicalize(config or {}),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"{payload['model_name']}|{payload['device']}|{digest}"


def _default_loader(model_name: str, device: str, config: Optional[Dict[str, Any]] = None):
    try:
        import torch  # type: ignore
        from demucs.pretrained import get_model as get_model_fn  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised via explicit dependency checks
        raise RuntimeError(f"Demucs model init failed for {model_name} on {device}: {exc}") from exc

    _ensure_hf_token_env()
    model = get_model_fn(model_name)
    if hasattr(model, "to"):
        model = model.to(device)
    return model


def _detect_cuda(torch_module: Any) -> bool:
    if torch_module is None:
        return False
    cuda = getattr(torch_module, "cuda", None)
    if cuda is None:
        return False

    is_available = getattr(cuda, "is_available", None)
    if callable(is_available):
        try:
            return bool(is_available()) and int(getattr(cuda, "device_count", 0) or 0) > 0
        except Exception:  # pragma: no cover - depends on backend runtime state
            return False
    if isinstance(cuda, bool):
        return cuda
    available = getattr(cuda, "available", None)
    if isinstance(available, bool):
        return available and int(getattr(cuda, "device_count", 0) or 0) > 0
    return False


def _detect_mps(torch_module: Any) -> bool:
    if torch_module is None:
        return False
    backends = getattr(torch_module, "backends", None)
    if backends is not None:
        mps = getattr(backends, "mps", None)
        if mps is not None:
            is_available = getattr(mps, "is_available", None)
            if callable(is_available):
                try:
                    return bool(is_available())
                except Exception:  # pragma: no cover - depends on backend runtime state
                    return False
            available = getattr(mps, "available", None)
            if isinstance(available, bool):
                return available
    has_mps = getattr(torch_module, "has_mps", None)
    if callable(has_mps):
        try:
            return bool(has_mps())
        except Exception:  # pragma: no cover
            return False
    return False


def resolve_device(torch_module: Optional[Any] = None) -> str:
    """Return the best available device: CUDA -> MPS -> CPU."""
    if torch_module is None:
        try:
            import torch  # type: ignore
        except Exception:
            torch_module = None
        else:
            torch_module = torch

    if _detect_cuda(torch_module):
        selected = "cuda"
        fallback_reason = None
    elif _detect_mps(torch_module):
        selected = "mps"
        fallback_reason = "cuda_unavailable"
    else:
        selected = "cpu"
        fallback_reason = "no_accelerator_available"

    DEVICE_REPORT.update(
        {
            "selected_device": selected,
            "preferred_device": selected,
            "fallback_reason": fallback_reason,
            "cache_status": DEVICE_REPORT.get("cache_status", "unset"),
        }
    )
    return selected


def get_or_create_model(
    model_name: str,
    device: str,
    config: Optional[Dict[str, Any]] = None,
    *,
    loader: Optional[Callable[[str, str, Optional[Dict[str, Any]]], Any]] = None,
):
    """Return a singleton model instance keyed by model/device/config."""
    key = build_cache_key(model_name, device, config)
    cached = MODEL_CACHE.get(key)
    if cached is not None:
        DEVICE_REPORT.update(
            {
                "cache_key": key,
                "cache_status": "hit",
                "last_model_name": model_name,
            }
        )
        logger.info("Demucs model cache hit for %s on %s (key=%s)", model_name, device, key)
        return cached["instance"]

    actual_loader = loader or _default_loader
    model = actual_loader(model_name, device, config)
    MODEL_CACHE[key] = {
        "model_name": str(model_name),
        "device": str(device),
        "config": deepcopy(config or {}),
        "instance": model,
        "cache_key": key,
    }
    DEVICE_REPORT.update(
        {
            "cache_key": key,
            "cache_status": "miss",
            "last_model_name": model_name,
        }
    )
    logger.info("Demucs model cache miss for %s on %s (key=%s)", model_name, device, key)
    return model


def safe_fallback(
    loader: Callable[[str, str, Optional[Dict[str, Any]]], Any],
    model_name: str,
    device: str,
    config: Optional[Dict[str, Any]] = None,
):
    """Execute the loader and re-raise the original error without silent masking."""
    try:
        return loader(model_name, device, config)
    except Exception:
        raise


def run_demucs_inference(
    audio: Any,
    sample_rate: int,
    model_name: str = "htdemucs",
    config: Optional[Dict[str, Any]] = None,
    *,
    torch_module: Optional[Any] = None,
    loader: Optional[Callable[[str, str, Optional[Dict[str, Any]]], Any]] = None,
) -> Dict[str, Any]:
    """Load and prepare a Demucs runtime while preserving explicit fallback logs.

    Returns a dict with the selected device and a report payload suitable for CLI
    output. The function is intentionally local-only and does not hide hardware or
    dependency failures.
    """
    config = deepcopy(config or {})
    actual_loader = loader or _default_loader
    runtime_errors: list[str] = []
    preferred_order = ["cuda", "mps", "cpu"]

    if torch_module is None:
        try:
            import torch  # type: ignore
        except Exception as exc:  # pragma: no cover - handled by caller during dependency checks
            raise RuntimeError("Demucs requires torch for runtime selection") from exc
        torch_module = torch

    available = {
        "cuda": _detect_cuda(torch_module),
        "mps": _detect_mps(torch_module),
        "cpu": True,
    }

    selected = resolve_device(torch_module)
    preferred_order = [device for device in preferred_order if available.get(device, False) or device == "cpu"]
    if selected not in preferred_order:
        preferred_order.insert(0, selected)

    last_error = None
    for device in preferred_order:
        try:
            model = get_or_create_model(model_name, device, config, loader=actual_loader)
            cache_entry = MODEL_CACHE.get(build_cache_key(model_name, device, config))
            cache_hit = bool(cache_entry and cache_entry.get("instance") is model)
            resolved_cache_status = "hit" if cache_hit else "miss"
            if device != selected:
                resolved_cache_status = "fallback"
            if device == "cpu" and selected != "cpu":
                resolved_cache_status = "cpu_fallback"

            if device == "cpu" and selected != "cpu":
                fallback_reason = "; ".join(runtime_errors) + "; explicit CPU fallback after guard"
            else:
                fallback_reason = None if device == selected else f"{selected}_unavailable"

            DEVICE_REPORT.update(
                {
                    "selected_device": device,
                    "preferred_device": selected,
                    "fallback_reason": fallback_reason,
                    "cache_status": resolved_cache_status,
                    "last_model_name": model_name,
                }
            )
            report = {
                "selected_device": device,
                "preferred_device": selected,
                "fallback_reason": fallback_reason,
                "cache_status": resolved_cache_status,
                "cache_key": build_cache_key(model_name, device, config),
                "model_name": model_name,
                "sample_rate": int(sample_rate),
                "audio_shape": getattr(audio, "shape", None),
            }
            logger.info(
                "Demucs runtime resolved device=%s for model=%s (cache_status=%s)",
                device,
                model_name,
                report["cache_status"],
            )
            return {"model": model, "device": device, "cache_status": report["cache_status"], "report": report}
        except Exception as exc:  # pragma: no cover - exercised by explicit runtime fallback tests
            last_error = exc
            runtime_errors.append(f"{device}: {exc}")
            logger.warning("Demucs backend %s failed for %s; preserving original error and checking fallback.", device, model_name)
            if device == "cpu":
                break

    if last_error is not None:
        fallback_error = last_error
        device = "cpu"
        try:
            model = get_or_create_model(model_name, device, config, loader=actual_loader)
            cache_entry = MODEL_CACHE.get(build_cache_key(model_name, device, config))
            cache_hit = bool(cache_entry and cache_entry.get("instance") is model)
            if selected != "cpu":
                reason = "; ".join(runtime_errors) + "; explicit CPU fallback after guard"
            else:
                reason = "no_accelerator_available"
            DEVICE_REPORT.update(
                {
                    "selected_device": "cpu",
                    "preferred_device": selected,
                    "fallback_reason": reason,
                    "cache_status": "cpu_fallback",
                    "last_error": str(fallback_error),
                }
            )
            report = {
                "selected_device": "cpu",
                "preferred_device": selected,
                "fallback_reason": reason,
                "cache_status": "cpu_fallback",
                "cache_key": build_cache_key(model_name, device, config),
                "model_name": model_name,
                "sample_rate": int(sample_rate),
                "audio_shape": getattr(audio, "shape", None),
                "runtime_errors": runtime_errors,
            }
            logger.warning("Demucs CPU fallback activated: %s", reason)
            return {"model": model, "device": "cpu", "cache_status": "cpu_fallback", "report": report}
        except Exception:
            raise

    raise RuntimeError("No valid Demucs runtime backend could be initialized.")


__all__ = [
    "DEVICE_REPORT",
    "MODEL_CACHE",
    "_MODEL_CACHE",
    "build_cache_key",
    "get_or_create_model",
    "resolve_device",
    "run_demucs_inference",
    "safe_fallback",
]
