"""Write final WAV + reinject preserved chunks (pipeline stage [8]).

Owns AC9 (valid WAV, metadata/BWF chunks preserved) and AC11 (new file,
original never touched). The output path is always derived and the
pipeline hard-fails if the resolved output path would equal the input path
-- an enforced guard, not just a convention (architecture.md Section 4).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from ..errors import OutputPathConflictError
from .wav_chunks import ChunkList, inject_chunks

_BIT_DEPTH_TO_SUBTYPE = {16: "PCM_16", 24: "PCM_24", 32: "PCM_32"}


def resolve_output_path(input_path: str, output_dir: str = None) -> str:
    in_path = Path(input_path).resolve()
    out_dir = Path(output_dir).resolve() if output_dir else in_path.parent
    out_path = out_dir / f"{in_path.stem}_mastered.wav"

    if out_path.resolve() == in_path:
        raise OutputPathConflictError(
            f"Resolved output path {out_path} would equal the input path {in_path}; "
            f"refusing to overwrite the source file."
        )
    return str(out_path)


def export_wav(audio: np.ndarray, sr: int, output_path: str, config, preserved_chunks: ChunkList = None) -> None:
    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    subtype = _BIT_DEPTH_TO_SUBTYPE.get(config.output_bit_depth)
    if subtype is None:
        raise ValueError(f"Unsupported output bit depth in config: {config.output_bit_depth}")

    sf.write(output_path, audio, sr, subtype=subtype)

    if preserved_chunks:
        inject_chunks(output_path, preserved_chunks)
