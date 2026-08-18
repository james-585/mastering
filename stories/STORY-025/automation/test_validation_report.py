"""TC-2541: build_validation_report() with no human_reviews and
interactive_review=False raises, naming the file (AC9, architecture.md §8 step 2)."""
from __future__ import annotations

import numpy as np
import pytest

from human_review_capture import HumanReviewRequiredError
import real_world_validation as rwv


def test_tc2541_no_human_reviews_raises_naming_the_file(tmp_path, monkeypatch):
    import soundfile as sf

    sr = 44100
    audio = 0.1 * np.sin(2 * np.pi * 440.0 * np.arange(int(sr * 2.0)) / sr)
    path = tmp_path / "no_review.wav"
    sf.write(str(path), np.column_stack([audio, audio]), sr)

    monkeypatch.setattr(rwv, "verify_stem_separation_environment", lambda: _FakeEnvResult())

    called = {"pipeline_run": False}

    class _FakePipeline:
        def run(self, *args, **kwargs):
            called["pipeline_run"] = True
            raise AssertionError("pipeline.run must not be invoked before human review is resolved")

    monkeypatch.setattr(rwv, "MasteringOrchestrator", _FakePipeline)

    with pytest.raises(HumanReviewRequiredError) as excinfo:
        rwv.build_validation_report(paths=[str(path)], human_reviews=None, interactive_review=False)

    # DEF-2505: the implementation no longer !r-formats the path (which doubled
    # backslashes on Windows); the plain path string appears in the message instead.
    assert str(path) in str(excinfo.value)
    assert called["pipeline_run"] is False


class _FakeEnvResult:
    model_name = "htdemucs_6s"
    stem_count = 6
    elapsed_s = 1.0
