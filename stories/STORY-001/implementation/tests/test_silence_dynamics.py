"""Section 14 -- silence/near-silence dynamics handling (cross-cutting).
TC-140..TC-142."""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering import pipeline
from suno_mastering.analysis.clipping import detect_clipping
from suno_mastering.analysis.frequency_balance import measure_frequency_balance

from .conftest import make_dynamic_track, rms_amplitude_for_dbfs_sine, sine, to_stereo, write_wav
from .test_ac7_frequency_balance import _shaped_broadband


def _build_loud_quiet_loud(sr):
    # Loud sections need genuine dynamics (body+transients), not a pure
    # constant tone -- a pure tone has ~DR0-2 and is an unresolvable-solver
    # fixture (see DEF-001/DEF-006 discussion in defects.md), not a
    # representative "loud section" fixture.
    loud1 = make_dynamic_track(sr, 20.0, body_amplitude=rms_amplitude_for_dbfs_sine(-16.0),
                                transient_amplitude=0.5, transient_period_s=1.0, freq=220)
    quiet = to_stereo(sine(220, sr, 15.0, amplitude=rms_amplitude_for_dbfs_sine(-40.0)))
    loud2 = make_dynamic_track(sr, 20.0, body_amplitude=rms_amplitude_for_dbfs_sine(-16.0),
                                transient_amplitude=0.5, transient_period_s=1.0, freq=220)
    return np.concatenate([loud1, quiet, loud2], axis=0), (0, 20.0), (20.0, 35.0), (35.0, 55.0)


def test_tc140_quiet_breakdown_not_filled_up(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio, loud1_span, quiet_span, loud2_span = _build_loud_quiet_loud(sr)
    path = write_wav(tmp_wav_dir / "tc140.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    import soundfile as sf
    out_audio, out_sr = sf.read(result.output_path, dtype="float64", always_2d=True)

    def rms_db(signal):
        r = np.sqrt(np.mean(signal ** 2))
        return 20 * np.log10(max(r, 1e-12))

    def slice_span(buf, sr_, span):
        return buf[int(span[0] * sr_):int(span[1] * sr_)]

    before_loud_rms = rms_db(slice_span(audio, sr, loud1_span))
    before_quiet_rms = rms_db(slice_span(audio, sr, quiet_span))
    before_diff = before_loud_rms - before_quiet_rms

    after_loud_rms = rms_db(slice_span(out_audio, out_sr, loud1_span))
    after_quiet_rms = rms_db(slice_span(out_audio, out_sr, quiet_span))
    after_diff = after_loud_rms - after_quiet_rms

    assert abs(before_diff - after_diff) < 1.5  # broadband gain should preserve relative levels


def test_tc141_near_silent_passage_no_false_clipping(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio, loud1_span, quiet_span, loud2_span = _build_loud_quiet_loud(sr)
    before_result = detect_clipping(audio[int(quiet_span[0] * sr):int(quiet_span[1] * sr)], sr, default_config)
    assert before_result.sample_peak_clipped_count == 0

    path = write_wav(tmp_wav_dir / "tc141.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    import soundfile as sf
    out_audio, out_sr = sf.read(result.output_path, dtype="float64", always_2d=True)
    quiet_region = out_audio[int(quiet_span[0] * out_sr):int(quiet_span[1] * out_sr)]
    after_result = detect_clipping(quiet_region, out_sr, default_config)
    assert after_result.sample_peak_clipped_count == 0


def test_tc142_near_silent_passage_no_false_frequency_flag(default_config):
    sr = 44100
    loud = _shaped_broadband(sr, 15.0, {"low": -1.5, "mud": -3.0, "presence": -4.0})
    loud = to_stereo(loud)
    silent = to_stereo(sine(220, sr, 300.0, amplitude=rms_amplitude_for_dbfs_sine(-80.0)))
    full = np.concatenate([silent, loud], axis=0)

    fb_whole = measure_frequency_balance(full, sr, default_config)
    fb_loud_only = measure_frequency_balance(loud, sr, default_config)

    assert fb_whole.any_flagged is False
    # whole-track measurement should closely track the loud-only measurement
    assert abs(fb_whole.low_end.relative_db - fb_loud_only.low_end.relative_db) < 1.0
