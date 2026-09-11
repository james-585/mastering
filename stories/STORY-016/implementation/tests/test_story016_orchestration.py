from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from orchestration import MasteringOrchestrator


SR = 48000

# Real reference track, not committed to the repo (large, commercially
# licensed audio) -- this is a local-only regression gate. Resolved relative
# to the repo root rather than hardcoded to one machine's home directory, and
# skipped (not failed) when the file isn't present, e.g. in CI.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_REAL_TRACK = _REPO_ROOT / "Reference Tracks" / "Sunday Club.wav"


def _stereo_sine(freq_hz=220.0, amplitude=0.25, width=0.12, duration=0.5):
    t = np.linspace(0.0, duration, int(SR * duration), endpoint=False)
    tone = np.sin(2.0 * np.pi * freq_hz * t)
    left = tone * amplitude
    right = tone * amplitude * (1.0 + width)
    return np.column_stack([left, right]).astype(np.float64)


def test_stage_order_and_traceability():
    audio = _stereo_sine()
    pipeline = MasteringOrchestrator()

    result = pipeline.run(audio, SR, stems={"drums": audio, "bass": audio, "vocals": audio, "synth": audio}, use_stems=True)

    # STORY-025 grounded review adds "pending_human_review": a positive verdict
    # (pass/refine) without a human review supplied defers rather than trusting
    # an unconfirmed automated "sounds good" (orchestration.py line ~159).
    # No human review is supplied here, so this is the expected outcome, not a
    # regression.
    assert result["decision"] in {"pass", "refine", "pending_human_review"}
    assert [s["stage"] for s in result["audit"]] == [
        "ingest",
        "analysis",
        "stem_choice",
        "transient_restoration",
        "harshness_control",
        "stereo_imaging",
        "bus_glue",
        "final_safety",
        "quality_review",
    ]
    assert all("summary" in step for step in result["audit"])


def test_fallback_requires_explicit_mode():
    audio = _stereo_sine()
    pipeline = MasteringOrchestrator()

    result = pipeline.run(audio, SR, stems=None, use_stems=True, allow_stereo_fallback=True)
    assert result["mode"] == "stereo_fallback"
    assert result["audit"][2]["status"] == "fallback"

    try:
        pipeline.run(audio, SR, stems=None, use_stems=True, allow_stereo_fallback=False)
    except ValueError as exc:
        assert "fallback" in str(exc).lower()
    else:
        raise AssertionError("Expected explicit fallback to be rejected when disabled")


def test_pass_reject_refine_flow():
    pipeline = MasteringOrchestrator()

    good = _stereo_sine(amplitude=0.28, width=0.12)
    good_proc = _stereo_sine(amplitude=0.24, width=0.18)

    poor = _stereo_sine(amplitude=0.26, width=0.16)
    poor_proc = np.clip(poor * 0.15, -0.8, 0.8)

    good_result = pipeline.run(good, SR, stems={"mix": good_proc}, use_stems=False)
    poor_result = pipeline.run(poor, SR, stems={"mix": poor_proc}, use_stems=False)

    # grounded_quality_review.evaluate_quality_review() returns "pending_human_review"
    # unconditionally whenever human_review=None (STORY-025; see its docstring:
    # "must not be treated as a trusted pass/reject/refine verdict") -- neither
    # branch below supplies human_review, so *both* good and poor audio now
    # legitimately land on pending_human_review regardless of quality. This
    # test can no longer distinguish good/poor via `decision` at all; doing so
    # again would require passing a real human_review={"decision": ...} payload,
    # which is a test-design decision (what counts as "the human said reject"
    # here?) rather than a mechanical fix -- flagging as a coverage gap rather
    # than guessing at a human_review fixture.
    assert good_result["decision"] == "pending_human_review"
    assert poor_result["decision"] == "pending_human_review"


def test_true_peak_safety_gate():
    audio = _stereo_sine(amplitude=0.96, width=0.03)
    audio = np.clip(audio, -0.98, 0.98)
    pipeline = MasteringOrchestrator()

    result = pipeline.run(audio, SR, stems={"mix": audio}, use_stems=False)

    assert result["final_peak"] <= 1.0 + 1e-6
    assert any(step["stage"] == "final_safety" for step in result["audit"])


@pytest.mark.skipif(not _REAL_TRACK.exists(), reason="local-only reference track not present")
def test_real_track_pipeline_runs_and_exports():
    data, sample_rate = sf.read(str(_REAL_TRACK), dtype="float64", always_2d=True)
    pipeline = MasteringOrchestrator()

    result = pipeline.run(data, sample_rate, stems=None, use_stems=True, allow_stereo_fallback=True)

    # See test_stage_order_and_traceability re: pending_human_review.
    assert result["decision"] in {"pass", "refine", "reject", "pending_human_review"}
    assert result["output"].shape == data.shape
    assert np.isfinite(result["output"]).all()
