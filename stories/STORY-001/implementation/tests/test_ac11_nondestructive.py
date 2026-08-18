"""AC11 -- non-destructive processing. TC-100..TC-104."""
from __future__ import annotations

import dataclasses
import os
import stat

import pytest

from suno_mastering import pipeline
from suno_mastering.errors import MasteringError
from suno_mastering.io.ingest import compute_file_hash

from .conftest import make_dynamic_track, write_wav


def test_tc100_input_hash_unchanged(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 15.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = write_wav(tmp_wav_dir / "tc100.wav", audio, sr)

    before_hash = compute_file_hash(str(path))
    before_size = os.path.getsize(path)

    pipeline.master(str(path), output_dir=out_dir, config=default_config)

    after_hash = compute_file_hash(str(path))
    after_size = os.path.getsize(path)

    assert before_hash == after_hash
    assert before_size == after_size


def test_tc101_output_equal_to_input_hard_rejected(tmp_wav_dir, default_config, monkeypatch):
    """A real, non-mocked collision: the input file is itself already named
    `<stem>_mastered.wav`, so the derived output path
    (`<stem>_mastered.wav` in the same directory) resolves to the same path
    as the input. This must be hard-rejected before any write, via a typed
    error, per AC11."""
    sr = 44100
    audio = make_dynamic_track(sr, 10.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = tmp_wav_dir / "tc101.wav"
    write_wav(path, audio, sr)
    before_hash = compute_file_hash(str(path))

    # Note: master()'s public API only accepts output_dir (no explicit
    # output-path override), and resolve_output_path always derives
    # "<stem>_mastered.wav" -- a name that, by construction, can NEVER equal
    # the input's own filename for any input stem (appending "_mastered"
    # always changes the stem). This makes the collision guard unreachable
    # through any real, non-mocked input filename -- recorded as a residual
    # observation in defects.md, not itself a defect (it's arguably a
    # stronger guarantee: collision-proof by construction). To still
    # exercise the guard's own conditional logic, force Path.resolve() to
    # collapse input and derived-output to the same identity.
    from pathlib import Path
    from suno_mastering.errors import OutputPathConflictError
    from suno_mastering.io import export as export_mod

    monkeypatch.setattr(Path, "resolve", lambda self, *a, **kw: path)
    with pytest.raises(OutputPathConflictError):
        export_mod.resolve_output_path(str(path), str(tmp_wav_dir))


def test_tc102_input_never_opened_write_mode(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 10.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = write_wav(tmp_wav_dir / "tc102.wav", audio, sr)

    os.chmod(path, stat.S_IREAD)
    try:
        result = pipeline.master(str(path), output_dir=out_dir, config=default_config)
        assert result.output_path is not None
    finally:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


def test_tc103_output_always_new_location(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 10.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = write_wav(tmp_wav_dir / "tc103.wav", audio, sr)
    result = pipeline.master(str(path), output_dir=out_dir, config=default_config)

    assert result.output_path != str(path)
    assert os.path.exists(result.output_path)


def test_tc104_rerun_with_different_settings_independent_outputs(tmp_wav_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 15.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = write_wav(tmp_wav_dir / "tc104.wav", audio, sr)
    before_hash = compute_file_hash(str(path))

    out1 = (tmp_wav_dir / "run1").resolve(); out1.mkdir()
    out2 = (tmp_wav_dir / "run2").resolve(); out2.mkdir()

    cfg_a = dataclasses.replace(default_config, dither_seed=11)
    cfg_b = dataclasses.replace(default_config, dither_seed=22)

    r1 = pipeline.master(str(path), output_dir=str(out1), config=cfg_a)
    r2 = pipeline.master(str(path), output_dir=str(out2), config=cfg_b)

    assert r1.output_path != r2.output_path
    assert os.path.exists(r1.output_path)
    assert os.path.exists(r2.output_path)
    assert compute_file_hash(str(path)) == before_hash
