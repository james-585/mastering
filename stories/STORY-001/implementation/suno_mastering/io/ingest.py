"""Load + validate + format/channel detection (pipeline stage [1]).

Owns reading the source WAV, detecting sample rate/bit depth/format/channel
count, extracting every non-audio RIFF chunk verbatim for later
re-injection, and failing fast (with a typed error, not a crash) on corrupt
headers, zero-length audio, or unreadable files. This is also where the
"read-only" contract on the input file is enforced -- soundfile.read never
opens the path in a write/append mode, and this module never does either.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from ..errors import InvalidWavError, UnsupportedFormatError
from .wav_chunks import ChunkList, extract_preserved_chunks

_SUPPORTED_SUBTYPES = {"PCM_16", "PCM_24", "PCM_32", "FLOAT", "DOUBLE"}
_SUPPORTED_CHANNELS = {1, 2}
_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass
class IngestResult:
    audio: np.ndarray          # float64, (samples,) mono or (samples, channels) stereo
    sample_rate: int
    channels: int
    subtype: str
    duration_seconds: float
    preserved_chunks: ChunkList
    input_hash: str
    input_path: str


def compute_file_hash(path: str) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(_HASH_CHUNK_SIZE)
            if not block:
                break
            sha256.update(block)
    return sha256.hexdigest()


def _validate_data_chunk_not_truncated(path: str) -> None:
    """Detect a WAV whose `data` chunk header declares more bytes than are
    actually present in the file (e.g. a raw Suno export truncated
    mid-transfer/mid-save). This has to be checked against the file's own
    declared header field, not against soundfile/libsndfile's reported frame
    count (DEF-005): libsndfile silently clamps `sf.info().frames`/`sf.read`
    to however many complete frames are actually present on disk, so
    comparing the read result against `sf.info()` can never detect this --
    both already "agree" on the truncated count by the time either is
    called. Raises InvalidWavError with a clear message on truncation;
    logs/lets `wav_chunks.py` handle any other RIFF-structure oddity
    (architecture.md Section 9 risk #4 -- non-audio chunk anomalies must not
    be fatal), so this only ever inspects the `data` chunk specifically.
    """
    file_size = Path(path).stat().st_size
    with open(path, "rb") as fh:
        riff_id = fh.read(4)
        if riff_id != b"RIFF":
            return  # not a RIFF file at all; sf.info()/sf.read() will raise its own error
        fh.read(4)  # declared RIFF size field -- not needed here
        wave_id = fh.read(4)
        if wave_id != b"WAVE":
            return
        while True:
            header = fh.read(8)
            if len(header) < 8:
                return  # no data chunk found before EOF; let sf.read() surface this
            chunk_id, chunk_size = struct.unpack("<4sI", header)
            data_start = fh.tell()
            if chunk_id == b"data":
                actual_available = file_size - data_start
                if chunk_size > actual_available:
                    raise InvalidWavError(
                        f"Truncated WAV data in {path}: 'data' chunk header declares "
                        f"{chunk_size} bytes but only {actual_available} bytes are "
                        f"actually present in the file."
                    )
                return
            # Not the data chunk: skip past it (plus RIFF's even-byte pad) and
            # keep scanning for 'data'.
            fh.seek(chunk_size + (chunk_size % 2), 1)


def ingest(path: str, config) -> IngestResult:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise InvalidWavError(f"Input file does not exist: {path}")
    if p.stat().st_size == 0:
        raise InvalidWavError(f"Input file is zero-length: {path}")

    _validate_data_chunk_not_truncated(str(p))

    try:
        info = sf.info(str(p))
    except Exception as exc:
        raise InvalidWavError(f"Could not read WAV header for {path}: {exc}") from exc

    if info.frames == 0:
        raise InvalidWavError(f"Input file has zero audio frames: {path}")
    if info.subtype not in _SUPPORTED_SUBTYPES:
        raise UnsupportedFormatError(
            f"Unsupported WAV subtype '{info.subtype}' in {path}; "
            f"supported: {sorted(_SUPPORTED_SUBTYPES)}"
        )
    if info.channels not in _SUPPORTED_CHANNELS:
        raise UnsupportedFormatError(
            f"Unsupported channel count {info.channels} in {path}; "
            f"only mono (1) and stereo (2) are supported"
        )

    try:
        # Up-cast to float64 regardless of source bit depth (architecture.md
        # Section 3: "Audio is read once at ingest and immediately up-cast
        # to float64"). always_2d keeps a consistent (frames, channels)
        # shape from soundfile even for mono, which we then squeeze below.
        audio, sr = sf.read(str(p), dtype="float64", always_2d=True)
    except Exception as exc:
        raise InvalidWavError(f"Could not read audio data from {path}: {exc}") from exc

    if info.channels == 1:
        audio = audio[:, 0]

    try:
        preserved_chunks = extract_preserved_chunks(str(p))
    except InvalidWavError:
        raise
    except Exception:
        # wav_chunks already logs a warning and returns partial results for
        # recoverable anomalies; any other unexpected error here should not
        # abort ingest of otherwise-valid audio data.
        preserved_chunks = []

    input_hash = compute_file_hash(str(p))

    return IngestResult(
        audio=audio,
        sample_rate=sr,
        channels=info.channels,
        subtype=info.subtype,
        duration_seconds=info.frames / sr if sr else 0.0,
        preserved_chunks=preserved_chunks,
        input_hash=input_hash,
        input_path=str(p),
    )
