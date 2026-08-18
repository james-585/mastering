"""lufs_matching.py (STORY-025 architecture.md §4).

CLAUDE.md §6.3: level-matching is mandatory before comparing a mastered
result to a reference, because the streaming-safe target can sound quieter
than the reference when heard unmatched. Here "the reference" the human is
judging against is the original (pre-master) file -- the human needs to know
whether the master itself, not a loudness difference, made the mix sound
better. `match_levels()` measures integrated LUFS of both via the existing
`measure_integrated_lufs`, then applies a single linear gain to `processed`
so its integrated LUFS equals the original's (§4.1).

This is the sole legal entry point for producing a level-matched pair --
grounded_quality_review.py has no code path that computes a spectral/DR/
artifact delta without calling this first (§4.3, resolving AC5/AC6
structurally rather than by convention).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FOR_IMPORT = [
    _REPO_ROOT / "stories" / "STORY-001" / "implementation",
]
for _path in _FOR_IMPORT:
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from suno_mastering.analysis.loudness import measure_integrated_lufs


@dataclass
class LevelMatchResult:
    original_lufs: float
    processed_lufs: float           # before matching
    matched_processed_lufs: float   # after matching, re-measured
    gain_applied_db: float
    matched_processed: np.ndarray
    within_tolerance: bool


class LevelMatchError(RuntimeError):
    """Raised when level-matching cannot bring processed audio within tolerance
    of the original's integrated LUFS (e.g. -inf LUFS on a near-silent input)."""


def match_levels(
    original: np.ndarray,
    processed: np.ndarray,
    sr: int,
    tolerance_lu: float = 0.5,
) -> LevelMatchResult:
    """Measure integrated LUFS for both via measure_integrated_lufs, apply a
    single linear gain to `processed` so its LUFS matches `original`, and
    re-measure to confirm. Raises LevelMatchError if either LUFS measurement
    is non-finite (e.g. silence-gated to -inf) or the re-measured match falls
    outside tolerance_lu. Never silently returns an unmatched result."""
    original = np.asarray(original, dtype=np.float64)
    processed = np.asarray(processed, dtype=np.float64)

    original_lufs = measure_integrated_lufs(original, sr)
    processed_lufs = measure_integrated_lufs(processed, sr)

    if not np.isfinite(original_lufs) or not np.isfinite(processed_lufs):
        raise LevelMatchError(
            f"Cannot level-match: non-finite integrated LUFS measured "
            f"(original={original_lufs}, processed={processed_lufs}); this is "
            f"consistent with BS.1770 gating a near-silent input to -inf."
        )

    # A linear gain of g dB shifts every ungated per-block power by exactly
    # g dB (§4.2), so a single computed gain step reproduces the target LUFS
    # to within numerical precision in the overwhelming majority of cases.
    gain_applied_db = original_lufs - processed_lufs
    gain_linear = 10.0 ** (gain_applied_db / 20.0)
    matched_processed = processed * gain_linear

    matched_processed_lufs = measure_integrated_lufs(matched_processed, sr)
    if not np.isfinite(matched_processed_lufs):
        raise LevelMatchError(
            f"Cannot level-match: re-measured matched_processed LUFS is "
            f"non-finite ({matched_processed_lufs}) after applying "
            f"{gain_applied_db:+.4f} dB gain."
        )

    delta_lu = abs(matched_processed_lufs - original_lufs)
    within_tolerance = delta_lu <= tolerance_lu
    if not within_tolerance:
        raise LevelMatchError(
            f"Level-matching failed to bring processed audio within "
            f"{tolerance_lu} LU of original ({original_lufs:.4f} LUFS): "
            f"matched_processed measured at {matched_processed_lufs:.4f} LUFS "
            f"after {gain_applied_db:+.4f} dB gain (delta {delta_lu:.4f} LU)."
        )

    return LevelMatchResult(
        original_lufs=original_lufs,
        processed_lufs=processed_lufs,
        matched_processed_lufs=matched_processed_lufs,
        gain_applied_db=gain_applied_db,
        matched_processed=matched_processed,
        within_tolerance=within_tolerance,
    )
