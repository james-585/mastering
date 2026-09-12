"""MP3 decode tiering + provenance dispatch (STORY-002 architecture.md
Section 6).

Tier 0/1 -- soundfile/libsndfile direct read, gated behind a runtime
capability probe (`"MP3" in soundfile.available_formats()`), evaluated as an
injectable parameter (not a module-level constant frozen at import) so the
branch-selection logic itself is independently testable with the probe
result mocked/injected (architecture.md Section 12).

Tier 2 -- FFmpeg subprocess, stdout-only PCM pipe, used only if the tier-1
probe is False. Fully in-memory: no NamedTemporaryFile, no intermediate
WAV. The decode function's signature structurally enforces "never receives
a writable path" -- it takes only `path: str` and returns an in-memory
array; there is no output-path parameter anywhere in this module's call
chain.

MP3 bitrate (best-effort, resolved open question #9) is tier-coupled:
tier-2 reads it from the same ffprobe JSON call already needed for the
native sample rate; tier-1 uses `mutagen` (new, narrow, pure-Python
dependency -- libsndfile does not expose source bitrate).
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Optional

import numpy as np
import soundfile as sf

from ..errors import InvalidWavError


@dataclass
class Mp3DecodeResult:
    audio: np.ndarray       # float64, (samples,) mono or (samples, 2) stereo
    sample_rate: int
    channels: int
    bitrate_kbps: Optional[int]
    decoder: str             # e.g. "libsndfile-1.2.2" | "ffmpeg-8.1.2"


def mp3_read_supported(probe_fn=None) -> bool:
    """Runtime capability probe (architecture.md Section 6, Tier 1).
    `probe_fn` is injectable for unit-testing the dispatch logic
    independently of which branch happens to be live on a given machine."""
    probe_fn = probe_fn or sf.available_formats
    return "MP3" in probe_fn()


def _mutagen_bitrate_kbps(path: str) -> Optional[int]:
    try:
        from mutagen.mp3 import MP3
    except ImportError:
        return None
    try:
        info = MP3(path).info
        bitrate_bps = getattr(info, "bitrate", None)
        if not bitrate_bps:
            return None
        return int(round(bitrate_bps / 1000.0))
    except Exception:
        return None  # best-effort per resolved open question #9 -- never fabricate, never block


def _decode_tier1(path: str) -> Mp3DecodeResult:
    """soundfile/libsndfile direct read -- identical call shape to
    io/ingest.py's own read call."""
    try:
        info = sf.info(path)
        audio, sr = sf.read(path, dtype="float64", always_2d=True)
    except Exception as exc:
        raise InvalidWavError(f"Could not decode MP3 via libsndfile: {path}: {exc}") from exc

    if info.channels == 1:
        audio = audio[:, 0]

    return Mp3DecodeResult(
        audio=audio,
        sample_rate=sr,
        channels=info.channels,
        bitrate_kbps=_mutagen_bitrate_kbps(path),
        decoder=f"libsndfile-{sf.__libsndfile_version__}",
    )


def _ffprobe_json(path: str) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True, check=True,
    )
    return json.loads(proc.stdout)


def _decode_tier2(path: str) -> Mp3DecodeResult:
    """FFmpeg subprocess, stdout-only PCM pipe -- no temp file, no
    intermediate WAV (architecture.md Section 6, Tier 2)."""
    try:
        probe = _ffprobe_json(path)
    except Exception as exc:
        raise InvalidWavError(f"ffprobe failed to inspect {path}: {exc}") from exc

    audio_stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio_stream is None:
        raise InvalidWavError(f"No audio stream found in {path} via ffprobe")

    sr = int(audio_stream.get("sample_rate", 44100))
    channels = int(audio_stream.get("channels", 2))
    bitrate_raw = probe.get("format", {}).get("bit_rate") or audio_stream.get("bit_rate")
    bitrate_kbps = int(round(int(bitrate_raw) / 1000.0)) if bitrate_raw else None

    cmd = ["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", str(channels), "-ar", str(sr), "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, check=True)
    except Exception as exc:
        raise InvalidWavError(f"ffmpeg failed to decode {path}: {exc}") from exc

    raw = np.frombuffer(proc.stdout, dtype="<f4")
    if channels > 1:
        raw = raw.reshape(-1, channels)
    audio = raw.astype(np.float64)

    ffmpeg_version = _ffmpeg_version()
    return Mp3DecodeResult(
        audio=audio, sample_rate=sr, channels=channels,
        bitrate_kbps=bitrate_kbps, decoder=f"ffmpeg-{ffmpeg_version}",
    )


def _ffmpeg_version() -> str:
    try:
        proc = subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        first_line = proc.stdout.decode("utf-8", errors="replace").splitlines()[0]
        # "ffmpeg version 8.1.2-full_build-... Copyright ..."
        parts = first_line.split()
        return parts[2] if len(parts) > 2 else "unknown"
    except Exception:
        return "unknown"


def decode_mp3(path: str, probe_fn=None) -> Mp3DecodeResult:
    """Dispatches to tier 1 (libsndfile) if the runtime probe reports MP3
    support, else falls back to tier 2 (FFmpeg stdout pipe)."""
    if mp3_read_supported(probe_fn):
        return _decode_tier1(path)
    return _decode_tier2(path)
