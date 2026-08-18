"""soxr-based conditional resample (pipeline stage [3]).

Only invoked if the source sample rate is not one of the supported rates
(44.1kHz/48kHz); in that case it resamples to config.default_sample_rate
(44.1kHz) so every downstream DSP stage operates against one fixed sample
rate for the rest of the pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import soxr


@dataclass
class ResampleOutcome:
    audio: np.ndarray
    sample_rate: int
    was_resampled: bool
    source_sample_rate: int


def resample_if_needed(audio: np.ndarray, sr: int, config) -> ResampleOutcome:
    if sr in config.supported_sample_rates:
        return ResampleOutcome(audio=audio, sample_rate=sr, was_resampled=False, source_sample_rate=sr)

    target_sr = config.default_sample_rate
    resampled = soxr.resample(audio, sr, target_sr, quality="VHQ")
    return ResampleOutcome(
        audio=resampled, sample_rate=target_sr, was_resampled=True, source_sample_rate=sr
    )
