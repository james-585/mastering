"""Disk cache for Demucs stem separation results.

Cache key = SHA-256(audio_bytes | sample_rate | model_name | shifts | overlap
                    | segment_seconds | demucs_version).
Stems are stored as a compressed .npz archive; runtime_metadata is embedded as
a JSON string under the reserved key '__cache_meta__'. A corrupt, missing, or
schema-mismatched entry is silently evicted and the caller falls back to live
Demucs inference.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .stem_separation import StemBundle

logger = logging.getLogger(__name__)

_CACHE_FORMAT_VERSION = "stem-disk-cache-v1"
_METADATA_KEY = "__cache_meta__"


def _compute_key(
    audio: np.ndarray,
    sample_rate: int,
    model_name: str,
    shifts: int,
    overlap: float,
    segment_seconds: float | None,
    demucs_version: str | None,
) -> str:
    h = hashlib.sha256()
    h.update(audio.tobytes())
    h.update(str(sample_rate).encode())
    h.update(model_name.encode())
    h.update(str(shifts).encode())
    h.update(f"{overlap:.6f}".encode())
    h.update(str(segment_seconds).encode())
    h.update((demucs_version or "unknown").encode())
    return h.hexdigest()


def _npz_path(cache_dir: Path, key: str) -> Path:
    return cache_dir / f"{key}.npz"


def load(
    cache_dir: Path,
    audio: np.ndarray,
    sample_rate: int,
    model_name: str,
    shifts: int,
    overlap: float,
    segment_seconds: float | None,
    demucs_version: str | None,
) -> "StemBundle | None":
    """Return a cached StemBundle, or None on miss or any read error."""
    from .stem_separation import StemBundle

    key = _compute_key(audio, sample_rate, model_name, shifts, overlap, segment_seconds, demucs_version)
    path = _npz_path(cache_dir, key)
    if not path.exists():
        return None
    try:
        data = np.load(path, allow_pickle=False)
        meta = json.loads(str(data[_METADATA_KEY]))
        if meta.get("cache_format_version") != _CACHE_FORMAT_VERSION:
            logger.debug("Stem cache schema mismatch, evicting %s", path.name)
            path.unlink(missing_ok=True)
            return None
        stems = {k: data[k] for k in data.files if k != _METADATA_KEY}
        meta["cache_hit"] = True
        logger.info("Stem cache hit (%s…) ← %s", key[:12], path)
        return StemBundle(stems, meta)
    except Exception as exc:
        logger.warning("Stem cache load failed (%s); evicting: %s", path.name, exc)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def save(
    cache_dir: Path,
    audio: np.ndarray,
    sample_rate: int,
    model_name: str,
    shifts: int,
    overlap: float,
    segment_seconds: float | None,
    demucs_version: str | None,
    bundle: "StemBundle",
) -> None:
    """Persist a StemBundle to disk. Silent on any write failure."""
    key = _compute_key(audio, sample_rate, model_name, shifts, overlap, segment_seconds, demucs_version)
    path = _npz_path(cache_dir, key)
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        meta = dict(bundle.runtime_metadata)
        meta["cache_format_version"] = _CACHE_FORMAT_VERSION
        meta["cache_hit"] = False
        arrays: dict[str, np.ndarray] = {k: v for k, v in bundle.items()}
        arrays[_METADATA_KEY] = np.array(json.dumps(meta))
        np.savez_compressed(path, **arrays)
        logger.info("Stem cache saved (%s…) → %s", key[:12], path)
    except Exception as exc:
        logger.warning("Stem cache save failed: %s", exc)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
