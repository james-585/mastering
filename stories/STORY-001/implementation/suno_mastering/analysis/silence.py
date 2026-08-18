"""Shared near-silence / gating utility (architecture.md module layout:
analysis/silence.py).

Used by frequency_balance.py (and available to other analysis modules) to
exclude near-silent passages -- quiet intros/breakdowns typical of this
genre's long builds -- from measurements where low-level noise-floor content
would otherwise skew the result or trigger false-positive flags. This is
independent of BS.1770's own integrated-loudness gating (which pyloudnorm
implements internally); this module deals with *spectral/analysis* gating,
not the LUFS gate itself.

All operations are vectorized (numpy), no per-sample Python loops.
"""
from __future__ import annotations

import numpy as np


def _to_mono(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return audio
    return audio.mean(axis=1)


def block_rms_db(audio: np.ndarray, sr: int, block_ms: float = 400.0) -> np.ndarray:
    """RMS level in dBFS for each non-overlapping block of block_ms length.
    Returns an array of shape (n_blocks,). Mono-summed if multichannel."""
    mono = _to_mono(audio)
    block_len = max(1, int(round(block_ms / 1000.0 * sr)))
    n_blocks = len(mono) // block_len
    if n_blocks == 0:
        rms = np.sqrt(np.mean(mono ** 2)) if len(mono) else 0.0
        return np.array([20.0 * np.log10(max(rms, 1e-12))])
    trimmed = mono[: n_blocks * block_len].reshape(n_blocks, block_len)
    rms = np.sqrt(np.mean(trimmed ** 2, axis=1))
    return 20.0 * np.log10(np.maximum(rms, 1e-12))


def active_block_mask(
    audio: np.ndarray, sr: int, block_ms: float = 400.0, threshold_db: float = -60.0
) -> np.ndarray:
    """Boolean mask, one entry per block, True where the block is above the
    near-silence threshold (i.e. should be included in spectral/level
    analysis)."""
    return block_rms_db(audio, sr, block_ms) > threshold_db


def extract_active_audio(
    audio: np.ndarray, sr: int, block_ms: float = 400.0, threshold_db: float = -60.0
) -> np.ndarray:
    """Return the subset of `audio` (same channel layout) made up of blocks
    that are not near-silent, concatenated in original order. If every block
    is near-silent (e.g. a silence-only test buffer), returns the original
    audio unchanged so downstream analysis still has something to measure
    rather than an empty array."""
    block_len = max(1, int(round(block_ms / 1000.0 * sr)))
    n_blocks = len(audio) // block_len
    if n_blocks == 0:
        return audio
    mask = active_block_mask(audio, sr, block_ms, threshold_db)
    if not mask.any():
        return audio
    usable = audio[: n_blocks * block_len]
    if audio.ndim == 1:
        blocks = usable.reshape(n_blocks, block_len)
        return blocks[mask].reshape(-1)
    blocks = usable.reshape(n_blocks, block_len, audio.shape[1])
    return blocks[mask].reshape(-1, audio.shape[1])
