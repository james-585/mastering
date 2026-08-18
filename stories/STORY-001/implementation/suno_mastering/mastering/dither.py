"""TPDF dither + bit-depth conversion (pipeline stage [7]) -- the only
place bit depth is reduced, exactly once, immediately before export
(architecture.md Section 3).

TPDF = sum of two uniform random variables, each scaled to 1 LSB at the
target bit depth, giving a triangular probability density spanning
[-1 LSB, +1 LSB]. Uses a seeded numpy.random.default_rng (config-supplied
seed, fixed default) -- never unseeded randomness -- so runs are
byte-for-byte reproducible (AC10).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class DitherOutcome:
    audio: np.ndarray  # float64, quantized to the target bit depth's grid, still in [-1, 1)
    bit_depth: int
    seed: int


def tpdf_dither_and_quantize(audio: np.ndarray, bit_depth: int, seed: int) -> DitherOutcome:
    rng = np.random.default_rng(seed)
    levels = 2 ** (bit_depth - 1)
    lsb = 1.0 / levels

    r1 = rng.uniform(-0.5, 0.5, size=audio.shape) * lsb
    r2 = rng.uniform(-0.5, 0.5, size=audio.shape) * lsb
    dither_noise = r1 + r2  # triangular distribution, extent [-1 LSB, +1 LSB]

    dithered = audio + dither_noise
    quantized = np.round(dithered / lsb) * lsb
    # Guard against dither pushing an already-full-scale sample past +/-1.0.
    quantized = np.clip(quantized, -1.0, 1.0 - lsb)

    return DitherOutcome(audio=quantized, bit_depth=bit_depth, seed=seed)
