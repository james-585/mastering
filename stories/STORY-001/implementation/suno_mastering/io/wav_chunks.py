"""Hand-rolled RIFF chunk extraction/splicing (architecture.md Section 2:
soundfile/libsndfile does not guarantee round-tripping arbitrary/unknown
RIFF chunks; AC9 requires not silently dropping existing metadata).

Uses stdlib struct/io only, no third-party dependency. Must fail gracefully
on unrecognized/nonstandard chunk structures -- pass through with a logged
warning, not abort the run (architecture.md Section 9, risk #4).
"""
from __future__ import annotations

import logging
import struct
from pathlib import Path
from typing import List, Tuple

from ..errors import InvalidWavError

logger = logging.getLogger(__name__)

_RIFF_MAGIC = b"RIFF"
_WAVE_MAGIC = b"WAVE"
_DEFAULT_EXCLUDE = (b"fmt ", b"data")

ChunkList = List[Tuple[bytes, bytes]]


def _read_header(fh) -> int:
    """Validate the RIFF/WAVE magic, return the declared RIFF size field."""
    riff_id = fh.read(4)
    if riff_id != _RIFF_MAGIC:
        raise InvalidWavError(f"Not a RIFF file (magic was {riff_id!r})")
    (riff_size,) = struct.unpack("<I", fh.read(4))
    wave_id = fh.read(4)
    if wave_id != _WAVE_MAGIC:
        raise InvalidWavError(f"RIFF file is not WAVE (form type was {wave_id!r})")
    return riff_size


def extract_preserved_chunks(path: str, exclude_ids=_DEFAULT_EXCLUDE) -> ChunkList:
    """Return every top-level RIFF chunk in `path` other than the ones in
    `exclude_ids` (by default 'fmt ' and 'data', which soundfile already
    handles), as (chunk_id, raw_data) pairs in file order.

    On any parse anomaly partway through the chunk list (truncated file,
    chunk size that would run past EOF, etc.), logs a warning and returns
    whatever chunks were already successfully parsed, rather than raising --
    per architecture.md Section 9 risk #4, chunk-structure oddities must not
    be treated as fatal.
    """
    file_size = Path(path).stat().st_size
    chunks: ChunkList = []
    with open(path, "rb") as fh:
        try:
            _read_header(fh)
        except InvalidWavError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise InvalidWavError(f"Could not parse RIFF header of {path}: {exc}") from exc

        while True:
            pos = fh.tell()
            if pos >= file_size:
                break
            header = fh.read(8)
            if len(header) < 8:
                if len(header) > 0:
                    logger.warning(
                        "wav_chunks: truncated chunk header at offset %d in %s; "
                        "stopping chunk scan, passing through what was already parsed.",
                        pos, path,
                    )
                break
            chunk_id, chunk_size = struct.unpack("<4sI", header)
            data_start = fh.tell()
            if data_start + chunk_size > file_size:
                logger.warning(
                    "wav_chunks: chunk %r at offset %d declares size %d which runs past "
                    "end of file (%s); stopping chunk scan, passing through what was "
                    "already parsed.",
                    chunk_id, pos, chunk_size, path,
                )
                break
            data = fh.read(chunk_size)
            if chunk_size % 2 == 1:
                fh.seek(1, 1)  # skip pad byte
            if chunk_id not in exclude_ids:
                chunks.append((chunk_id, data))
    return chunks


def inject_chunks(output_path: str, chunks: ChunkList) -> None:
    """Append `chunks` (as produced by extract_preserved_chunks) to the end
    of an already-written WAV file at `output_path`, then fix up the RIFF
    header's overall size field. `output_path` is the pipeline's OUTPUT
    file (already written by soundfile at this point) -- the
    read-only/non-destructive guarantee applies to the INPUT path, not
    here."""
    if not chunks:
        return
    with open(output_path, "r+b") as fh:
        try:
            _read_header(fh)
        except InvalidWavError as exc:
            logger.warning(
                "wav_chunks: could not inject preserved chunks into %s (%s); "
                "output WAV will be missing source metadata chunks.",
                output_path, exc,
            )
            return

        fh.seek(0, 2)  # end of file
        for chunk_id, data in chunks:
            fh.write(struct.pack("<4sI", chunk_id, len(data)))
            fh.write(data)
            if len(data) % 2 == 1:
                fh.write(b"\x00")

        new_size = fh.tell()
        fh.seek(4)
        fh.write(struct.pack("<I", new_size - 8))
