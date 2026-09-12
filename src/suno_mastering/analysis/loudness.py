"""BS.1770-4 integrated LUFS via pyloudnorm (architecture.md Section 2:
"Integrated loudness (BS.1770-4, gated) -- pyloudnorm").

pyloudnorm.Meter implements the absolute (-70 LUFS) and relative (-10 LU)
gating internally, matching requirements.md's resolved measurement standard.
"""
from __future__ import annotations

import numpy as np
import pyloudnorm as pyln

from ..errors import InvalidWavError


def measure_integrated_lufs(audio: np.ndarray, sr: int) -> float:
    """Compute BS.1770-4 gated integrated loudness in LUFS.

    `audio` is a plain numpy array, mono (samples,) or multichannel
    (samples, channels), float. Silence-only or extremely short buffers can
    legitimately produce -inf (fully gated out); callers should be prepared
    to handle that rather than treating it as an error.
    """
    if audio.size == 0:
        raise InvalidWavError("Cannot measure loudness of zero-length audio")
    meter = pyln.Meter(sr)  # defaults to BS.1770-4 gating (-70 LUFS abs, -10 LU rel)
    try:
        loudness = meter.integrated_loudness(audio)
    except Exception as exc:  # pyloudnorm raises plain exceptions on bad input
        raise InvalidWavError(f"BS.1770 loudness measurement failed: {exc}") from exc
    return float(loudness)
