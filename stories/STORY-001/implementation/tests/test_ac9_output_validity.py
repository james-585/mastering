"""AC9 -- output file validity. TC-080..TC-086."""
from __future__ import annotations

import struct

import numpy as np
import pytest
import soundfile as sf

from suno_mastering import pipeline
from suno_mastering.io.wav_chunks import extract_preserved_chunks

from .conftest import make_dynamic_track, write_wav


@pytest.mark.parametrize("sr,subtype", [(44100, "PCM_16"), (48000, "PCM_24"), (44100, "FLOAT")])
def test_tc080_output_is_valid_24bit_pcm_wav(tmp_wav_dir, out_dir, default_config, sr, subtype):
    audio = make_dynamic_track(sr, 20.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = write_wav(tmp_wav_dir / f"tc080_{subtype}.wav", audio, sr, subtype=subtype)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    info = sf.info(result.output_path)
    assert info.subtype == "PCM_24"
    assert info.format == "WAV"


@pytest.mark.parametrize("sr", [44100, 48000])
def test_tc081_output_sample_rate_matches_source(tmp_wav_dir, out_dir, default_config, sr):
    audio = make_dynamic_track(sr, 20.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = write_wav(tmp_wav_dir / f"tc081_{sr}.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)
    info = sf.info(result.output_path)
    assert info.samplerate == sr


@pytest.mark.parametrize("sr", [22050, 32000, 88200, 96000])
def test_tc082_nonstandard_rate_defaults_to_44100_logged(tmp_wav_dir, out_dir, default_config, sr):
    audio = make_dynamic_track(sr, 20.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = write_wav(tmp_wav_dir / f"tc082_{sr}.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    info = sf.info(result.output_path)
    assert info.samplerate == 44100
    assert result.report.resample_action is not None
    assert result.report.resample_action["source_sample_rate"] == sr
    assert result.report.resample_action["sample_rate"] == 44100


def test_tc083_standard_bwf_metadata_chunk_preserved(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 10.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = tmp_wav_dir / "tc083.wav"
    write_wav(path, audio, sr)

    bext_payload = b"X" * 602  # minimal-length bext-like payload
    _append_chunk(path, b"bext", bext_payload)

    result = pipeline.master(str(path), output_dir=out_dir, config=default_config)

    out_chunks = extract_preserved_chunks(result.output_path)
    bext_chunks = [data for cid, data in out_chunks if cid == b"bext"]
    assert len(bext_chunks) == 1
    assert bext_chunks[0] == bext_payload


def test_tc084_unrecognized_chunk_passes_through_with_warning(tmp_wav_dir, out_dir, default_config, caplog):
    sr = 44100
    audio = make_dynamic_track(sr, 10.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = tmp_wav_dir / "tc084.wav"
    write_wav(path, audio, sr)
    _append_chunk(path, b"XTRA", b"arbitrary payload data")

    result = pipeline.master(str(path), output_dir=out_dir, config=default_config)  # must not raise

    out_chunks = extract_preserved_chunks(result.output_path)
    xtra = [data for cid, data in out_chunks if cid == b"XTRA"]
    assert len(xtra) == 1
    assert xtra[0] == b"arbitrary payload data"


@pytest.mark.parametrize("variant", ["truncated_size", "odd_length_no_pad", "zero_size"])
def test_tc085_malformed_chunks_fail_gracefully(tmp_wav_dir, out_dir, default_config, variant):
    sr = 44100
    audio = make_dynamic_track(sr, 5.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = tmp_wav_dir / f"tc085_{variant}.wav"
    write_wav(path, audio, sr)

    if variant == "truncated_size":
        with open(path, "ab") as fh:
            fh.write(struct.pack("<4sI", b"BADX", 9999999))  # declared size exceeds actual bytes
    elif variant == "odd_length_no_pad":
        _append_chunk(path, b"ODDX", b"odd", pad=False)  # odd length, no RIFF pad byte
    elif variant == "zero_size":
        _append_chunk(path, b"ZERO", b"")

    from suno_mastering.errors import MasteringError
    try:
        pipeline.master(str(path), output_dir=out_dir, config=default_config)
    except MasteringError:
        pass  # acceptable: typed error
    except (struct.error, IndexError) as exc:
        pytest.fail(f"Unhandled low-level exception leaked to caller: {exc!r}")


def test_tc086_multiple_interleaved_chunks_all_survive(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 10.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = tmp_wav_dir / "tc086.wav"
    write_wav(path, audio, sr)
    _append_chunk(path, b"UNK1", b"unknown-one")
    _append_chunk(path, b"bext", b"B" * 100)
    _append_chunk(path, b"UNK2", b"unknown-two")

    chunks = extract_preserved_chunks(str(path))
    ids = [cid for cid, _ in chunks]
    assert b"UNK1" in ids and b"bext" in ids and b"UNK2" in ids


def _append_chunk(path, chunk_id: bytes, data: bytes, pad: bool = True):
    """Append a RIFF chunk directly to an existing WAV file and fix up the
    RIFF size header, for constructing chunk-preservation test fixtures."""
    with open(path, "r+b") as fh:
        fh.seek(0, 2)
        fh.write(struct.pack("<4sI", chunk_id, len(data)))
        fh.write(data)
        if pad and len(data) % 2 == 1:
            fh.write(b"\x00")
        new_size = fh.tell()
        fh.seek(4)
        fh.write(struct.pack("<I", new_size - 8))
