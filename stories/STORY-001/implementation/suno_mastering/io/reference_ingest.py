"""Reference-track ingest -- a separate, lighter-weight read path (STORY-002
architecture.md Section 6). NOT a modification of io/ingest.py: no RIFF
data-chunk truncation check (meaningless for FLAC/MP3), no
extract_preserved_chunks() (export-oriented BWF/metadata layer this
read-only story has no use for).

AC11 TRAP (architecture.md Section 6, stated explicitly so it is not
silently mis-implemented): for this function's output to be usable as an
input to the *identical* analysis/* functions STORY-001's stage [2] calls,
it must replicate ingest.py's exact array-shape convention --
`sf.read(dtype="float64", always_2d=True)` followed by squeezing to 1-D for
genuinely mono content. Getting this wrong would silently produce
*different* measurement values for the same underlying audio, without
raising any exception.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from ..errors import InvalidWavError, UnsupportedFormatError
from . import mp3_decode
from ..analysis.reference_types import ProvenanceResult

_HASH_CHUNK_SIZE = 1024 * 1024
_SUPPORTED_EXTENSIONS = {".wav": "wav", ".flac": "flac", ".mp3": "mp3"}
_SUPPORTED_CHANNELS = {1, 2}


@dataclass
class ReferenceIngestResult:
    audio: np.ndarray            # float64, (samples,) mono or (samples, 2) stereo
    sample_rate: int
    channels: int
    duration_seconds: float
    input_hash: str
    input_path: str
    provenance: ProvenanceResult


def compute_file_hash(path: str) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(_HASH_CHUNK_SIZE)
            if not block:
                break
            sha256.update(block)
    return sha256.hexdigest()


def _detect_container(path: Path) -> str:
    ext = path.suffix.lower()
    container = _SUPPORTED_EXTENSIONS.get(ext)
    if container is None:
        raise UnsupportedFormatError(
            f"Unsupported reference-track extension '{ext}' in {path}; "
            f"supported: {sorted(_SUPPORTED_EXTENSIONS)}"
        )
    return container


def ingest_reference_track(path: str, config) -> ReferenceIngestResult:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise InvalidWavError(f"Reference input file does not exist: {path}")
    if p.stat().st_size == 0:
        raise InvalidWavError(f"Reference input file is zero-length: {path}")

    container = _detect_container(p)
    input_hash = compute_file_hash(str(p))

    if container in ("wav", "flac"):
        # Tier 0 (architecture.md Section 6): plain soundfile.read(), same
        # call shape as ingest.py's own read call -- no truncation check,
        # no chunk extraction.
        try:
            info = sf.info(str(p))
        except Exception as exc:
            raise InvalidWavError(f"Could not read header for {path}: {exc}") from exc
        if info.frames == 0:
            raise InvalidWavError(f"Reference input file has zero audio frames: {path}")
        if info.channels not in _SUPPORTED_CHANNELS:
            raise UnsupportedFormatError(
                f"Unsupported channel count {info.channels} in {path}; "
                f"only mono (1) and stereo (2) are supported"
            )
        try:
            audio, sr = sf.read(str(p), dtype="float64", always_2d=True)
        except Exception as exc:
            raise InvalidWavError(f"Could not read audio data from {path}: {exc}") from exc
        if info.channels == 1:
            audio = audio[:, 0]
        channels = info.channels
        decoder = f"libsndfile-{sf.__libsndfile_version__}"
        bitrate_kbps = None
        lossless = True
    else:  # mp3
        result = mp3_decode.decode_mp3(str(p))
        audio = result.audio
        sr = result.sample_rate
        channels = result.channels
        decoder = result.decoder
        bitrate_kbps = result.bitrate_kbps
        lossless = False
        if channels not in _SUPPORTED_CHANNELS:
            raise UnsupportedFormatError(
                f"Unsupported channel count {channels} in {path}; "
                f"only mono (1) and stereo (2) are supported"
            )

    duration_seconds = audio.shape[0] / sr if sr else 0.0

    # suspected_transcode is populated later, once hf_extension's rolloff
    # analysis runs for this track (architecture.md Section 6: "a
    # corroborated, not purely container-level, signal" -- left
    # False/pending here and updated by reference_analysis/pipeline.py
    # within the same per-track analysis step).
    provenance = ProvenanceResult(
        container=container,
        lossless=lossless,
        bitrate_kbps=bitrate_kbps,
        decoder=decoder,
        suspected_transcode=False,
        suspected_transcode_reason=None,
    )

    return ReferenceIngestResult(
        audio=audio,
        sample_rate=sr,
        channels=channels,
        duration_seconds=duration_seconds,
        input_hash=input_hash,
        input_path=str(p),
        provenance=provenance,
    )
