"""Section 13 -- sample rate/bit depth variability and malformed files.
TC-120..TC-126."""
from __future__ import annotations

import struct

import numpy as np
import pytest
import soundfile as sf

from suno_mastering import pipeline
from suno_mastering.errors import InvalidWavError, UnsupportedFormatError

from .conftest import make_dynamic_track, write_wav


@pytest.mark.parametrize("sr", [44100, 48000, 32000])
@pytest.mark.parametrize("subtype", ["PCM_16", "PCM_24", "FLOAT"])
def test_tc120_sample_rate_bit_depth_matrix(tmp_wav_dir, out_dir, default_config, sr, subtype):
    audio = make_dynamic_track(sr, 15.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = write_wav(tmp_wav_dir / f"tc120_{sr}_{subtype}.wav", audio, sr, subtype=subtype)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    info = sf.info(result.output_path)
    assert info.subtype == "PCM_24"
    expected_rate = sr if sr in default_config.supported_sample_rates else default_config.default_sample_rate
    assert info.samplerate == expected_rate
    assert result.before is not None
    assert result.after is not None


def test_tc121_corrupt_riff_header_fails_gracefully(tmp_wav_dir, out_dir, default_config):
    path = tmp_wav_dir / "tc121.wav"
    path.write_bytes(b"XXXX" + b"\x00" * 40)
    with pytest.raises(InvalidWavError):
        pipeline.master(str(path), output_dir=out_dir, config=default_config)


def test_tc122_zero_length_audio_fails_gracefully(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    path = tmp_wav_dir / "tc122.wav"
    sf.write(str(path), np.zeros((0, 2)), sr, subtype="PCM_24")
    with pytest.raises(InvalidWavError):
        pipeline.master(str(path), output_dir=out_dir, config=default_config)


def test_tc123_truncated_file_fails_gracefully(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 5.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = tmp_wav_dir / "tc123.wav"
    write_wav(path, audio, sr)

    full_bytes = path.read_bytes()
    truncated = full_bytes[: len(full_bytes) // 2]
    path.write_bytes(truncated)

    with pytest.raises(InvalidWavError):
        pipeline.master(str(path), output_dir=out_dir, config=default_config)


def test_tc124_unsupported_codec_rejected(tmp_wav_dir, out_dir, default_config):
    """Construct a minimal WAV with fmt tag = 17 (IMA ADPCM), which
    soundfile/libsndfile cannot decode as PCM/float -- should raise
    UnsupportedFormatError, not crash."""
    path = tmp_wav_dir / "tc124.wav"
    sr = 44100
    n_samples = 1000
    block_align = 256
    fmt_chunk = struct.pack(
        "<HHIIHHH", 17, 1, sr, sr * block_align // 505, block_align, 4, 2,
    )  # IMA ADPCM fmt (approximate; may not be perfectly valid ADPCM data, only the header matters for the codec check)
    data_chunk = b"\x00" * 512

    with open(path, "wb") as fh:
        content = b"fmt " + struct.pack("<I", len(fmt_chunk)) + fmt_chunk
        content += b"data" + struct.pack("<I", len(data_chunk)) + data_chunk
        fh.write(b"RIFF" + struct.pack("<I", len(content) + 4) + b"WAVE" + content)

    with pytest.raises((InvalidWavError, UnsupportedFormatError)):
        pipeline.master(str(path), output_dir=out_dir, config=default_config)


def test_tc125_non_wav_with_wav_extension_rejected(tmp_wav_dir, out_dir, default_config):
    path = tmp_wav_dir / "tc125.wav"
    # fake "MP3-like" binary content, definitely not a RIFF/WAVE file
    path.write_bytes(b"\xff\xfb\x90\x00" + bytes(range(256)) * 20)
    with pytest.raises((InvalidWavError, UnsupportedFormatError)):
        pipeline.master(str(path), output_dir=out_dir, config=default_config)


def test_tc126_extremely_short_valid_file_no_crash(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 0.05, body_amplitude=0.1, transient_amplitude=0.2,
                                transient_period_s=1.0)  # ~50ms, no transient will actually fire
    path = write_wav(tmp_wav_dir / "tc126.wav", audio, sr)

    from suno_mastering.errors import MasteringError
    try:
        result = pipeline.master(str(path), output_dir=out_dir, config=default_config)
        assert result.output_path is not None
    except MasteringError:
        pass  # acceptable: typed error for a stage with a genuine hard minimum-length requirement
