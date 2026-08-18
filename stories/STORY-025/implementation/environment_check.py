"""environment_check.py (STORY-025 architecture.md §5).

Demucs 4.1.0 / torch 2.13.0+cpu are confirmed installed and htdemucs_6s
already separated a full track successfully once (memories/repo/suno-mastering-
status.md). What is missing is a repeatable, lightweight, per-run check that
the specific environment build_validation_report() is executing in right now
can actually do real separation -- a short-clip smoke test, not a heavyweight
provisioning stage and not a re-run of the full-track job on every validation
pass (§5.1).

Reuses the project's existing real Demucs entry point (`split_stems`, STORY-008)
rather than re-implementing model loading/inference here.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FOR_IMPORT = [
    _REPO_ROOT / "stories" / "STORY-001" / "implementation",
]
for _path in _FOR_IMPORT:
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from suno_mastering.config import MasteringConfig
from suno_mastering.errors import DependencyError
from suno_mastering.io.stem_separation import split_stems

_DEFAULT_FIXTURE = _REPO_ROOT / "Reference Tracks" / "Sunday Club.wav"
_FIXTURE_CLIP_SECONDS = 8.0          # short slice -- smoke test, not a full-track re-run
_FIXTURE_CLIP_OFFSET_SECONDS = 30.0  # Gate 1 Finding 4 action item -- see architecture.md §5.2

# "Non-degenerate" (§5.2) reuses the project's existing silence-gate threshold
# (MasteringConfig.silence_gate_threshold_db = -60.0 dB) as the noise floor a
# stem's RMS must clear, rather than inventing a new numeric constant here.
_NOISE_FLOOR_LINEAR = 10.0 ** (MasteringConfig().silence_gate_threshold_db / 20.0)

# §5.2.1 (DEF-2503): sum-of-stems reconstruction-error smoke-test bound.
# PROVISIONAL, same category as artifact_density_regression/spectral_shift_flag_db.
_RECONSTRUCTION_ERROR_RATIO_MAX = 0.5

# §5.2.1 (DEF-2503): per model_name, the near-universal stem subset required to
# individually clear the noise floor -- not hardcoded per-call, so a different
# model_name does not silently reuse htdemucs_6s's subset.
_NEAR_UNIVERSAL_STEMS: Dict[str, List[str]] = {
    "htdemucs_6s": ["drums", "bass", "vocals"],
}


@dataclass
class EnvironmentCheckResult:
    available: bool
    torch_version: Optional[str]
    demucs_version: Optional[str]
    model_name: str
    stem_count: int
    elapsed_s: float
    checked_at: datetime
    error: Optional[str]
    # v1.2 additions (DEF-2503) -- surfaced for audit, not just a pass/fail bool:
    reconstruction_error_ratio: float
    verified_nonsilent_stems: List[str]
    noise_floor_checked_stems: List[str]


class EnvironmentVerificationError(RuntimeError):
    """Raised when real Demucs/Torch stem separation cannot be confirmed."""


def _read_clip(fixture_path: Path, clip_seconds: float, clip_offset_seconds: float) -> tuple[np.ndarray, int]:
    try:
        info = sf.info(str(fixture_path))
    except Exception as exc:
        raise EnvironmentVerificationError(
            f"Could not read fixture audio at {fixture_path}: {type(exc).__name__}: {exc}"
        ) from exc

    required_duration = clip_offset_seconds + clip_seconds
    if info.duration < required_duration:
        raise EnvironmentVerificationError(
            f"Fixture {fixture_path} is {info.duration:.2f}s long, shorter than the "
            f"required {required_duration:.2f}s (offset {clip_offset_seconds}s + clip "
            f"{clip_seconds}s); refusing to silently clip to a shorter window."
        )

    start_frame = int(round(clip_offset_seconds * info.samplerate))
    n_frames = int(round(clip_seconds * info.samplerate))
    try:
        clip, sr = sf.read(
            str(fixture_path), start=start_frame, frames=n_frames, dtype="float64", always_2d=True
        )
    except Exception as exc:
        raise EnvironmentVerificationError(
            f"Could not read {clip_seconds}s clip at offset {clip_offset_seconds}s from "
            f"{fixture_path}: {type(exc).__name__}: {exc}"
        ) from exc

    if clip.shape[1] == 1:
        clip = np.column_stack([clip[:, 0], clip[:, 0]])
    elif clip.shape[1] > 2:
        clip = clip[:, :2]
    return clip.astype(np.float64), sr


def verify_stem_separation_environment(
    fixture_path: Path = _DEFAULT_FIXTURE,
    clip_seconds: float = _FIXTURE_CLIP_SECONDS,
    clip_offset_seconds: float = _FIXTURE_CLIP_OFFSET_SECONDS,
    model_name: str = "htdemucs_6s",
) -> EnvironmentCheckResult:
    """Import torch and demucs, read clip_seconds of fixture_path starting at
    clip_offset_seconds (not the literal file start) in-memory (no
    intermediate file written), run real htdemucs_6s inference, and assert
    (a) every returned stem is finite (no NaN/Inf), (b) the stems sum back to
    approximately reconstruct the input clip (§5.2.1 -- proves real, coherent
    model execution regardless of any individual stem's content), and (c) the
    near-universal stem subset for model_name (from _NEAR_UNIVERSAL_STEMS)
    individually clears a noise floor (§5.2.1 -- proves the model is not
    silently zeroing its output for the stems expected to be active in
    virtually any mixed-music window). Other stems are NOT required to
    individually clear the noise floor -- see §5.2.1 for why. Raises
    EnvironmentVerificationError with a clear message on any import failure,
    inference failure, reconstruction-tolerance failure, or degenerate
    near-universal-stem result -- no silent fallback. Also raises if
    fixture_path's duration is shorter than clip_offset_seconds +
    clip_seconds, rather than silently clipping to a shorter window. Does not
    cache across process runs; each invocation re-verifies the environment it
    is actually running in.
    """
    checked_at = datetime.now(timezone.utc)
    start = time.monotonic()

    clip, sr = _read_clip(fixture_path, clip_seconds, clip_offset_seconds)

    try:
        stems = split_stems(clip, sr, model_name=model_name)
    except DependencyError as exc:
        raise EnvironmentVerificationError(
            f"Demucs/Torch stem separation dependencies unavailable: {exc}"
        ) from exc
    except Exception as exc:
        raise EnvironmentVerificationError(
            f"Real Demucs {model_name!r} inference failed on {fixture_path} "
            f"(offset {clip_offset_seconds}s, {clip_seconds}s clip): "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    for stem_name, stem_audio in stems.items():
        if not np.isfinite(stem_audio).all():
            raise EnvironmentVerificationError(
                f"Stem {stem_name!r} contains non-finite (NaN/Inf) values; "
                f"environment verification failed."
            )

    # §5.2.1 check (a): sum-of-stems reconstruction error -- proves real,
    # coherent separation occurred, independent of any single stem's content.
    reconstructed = sum(stems.values())
    residual = clip - reconstructed
    reconstruction_error_ratio = (
        float(np.sqrt(np.mean(residual ** 2))) / float(np.sqrt(np.mean(clip ** 2)) + 1e-12)
    )
    if reconstruction_error_ratio > _RECONSTRUCTION_ERROR_RATIO_MAX:
        raise EnvironmentVerificationError(
            f"Sum-of-stems reconstruction error ratio ({reconstruction_error_ratio:.3f}) "
            f"exceeds the smoke-test bound ({_RECONSTRUCTION_ERROR_RATIO_MAX}); the model "
            f"may not have produced coherent, real separation output."
        )

    # §5.2.1 check (b): near-universal stem subset must individually clear the
    # noise floor -- catches partial degeneracy the sum check could mask.
    noise_floor_checked_stems = list(_NEAR_UNIVERSAL_STEMS.get(model_name, []))
    verified_nonsilent_stems: List[str] = []
    for stem_name in noise_floor_checked_stems:
        stem_audio = stems.get(stem_name)
        if stem_audio is None:
            raise EnvironmentVerificationError(
                f"Expected near-universal stem {stem_name!r} for model {model_name!r} "
                f"was not present in the model's output."
            )
        stem_rms = float(np.sqrt(np.mean(np.square(stem_audio))))
        if stem_rms < _NOISE_FLOOR_LINEAR:
            raise EnvironmentVerificationError(
                f"Stem {stem_name!r} RMS ({stem_rms:.3e}) is at or below the "
                f"noise floor ({_NOISE_FLOOR_LINEAR:.3e}, from "
                f"MasteringConfig.silence_gate_threshold_db); the model may be "
                f"silently returning a degenerate (near-zero) stem."
            )
        verified_nonsilent_stems.append(stem_name)

    elapsed_s = time.monotonic() - start
    runtime_metadata = stems.runtime_metadata
    return EnvironmentCheckResult(
        available=True,
        torch_version=runtime_metadata.get("torch_version"),
        demucs_version=runtime_metadata.get("demucs_version"),
        model_name=model_name,
        stem_count=len(stems),
        elapsed_s=elapsed_s,
        checked_at=checked_at,
        error=None,
        reconstruction_error_ratio=reconstruction_error_ratio,
        verified_nonsilent_stems=verified_nonsilent_stems,
        noise_floor_checked_stems=noise_floor_checked_stems,
    )
