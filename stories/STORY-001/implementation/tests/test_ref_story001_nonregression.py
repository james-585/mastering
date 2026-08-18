"""STORY-002 -- STORY-001 non-regression. TC-390-TC-395.

TC-390 itself (run STORY-001's whole existing suite) is executed directly by
this QA pass as its own `pytest` invocation, not wrapped inside this file
(running a whole separate pytest session from within a test is fragile and
duplicates work) -- see the QA report for the STORY-001 full-suite pass/fail
counts. The tests below are the narrower, file-level regression checks
(TC-391-395) that *can* run as ordinary pytest tests.
"""
from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import pytest

from suno_mastering.analysis.types import Measurements
from suno_mastering.analysis.dynamic_range import measure_dynamic_range
from suno_mastering.analysis.frequency_balance import measure_frequency_balance
from suno_mastering.config import MasteringConfig

from .ref_helpers import sine, to_stereo, pink_noise_stereo

_REFERENCE_CURVE_PATH = (
    Path(__file__).resolve().parents[1] / "suno_mastering" / "reference" / "progressive_house_124bpm.json"
)


def test_tc391_measurements_dataclass_shape_unchanged():
    """Confirms the approved additive fields for the shared Measurements
    contract are present, without regressing STORY-001's core shape.

    The architecture-approved additions after STORY-003 are the
    `sanity_warnings` advisory list and the STORY-007 artifact-reporting
    fields (`artifact_detection` and `plausibility_warnings`). This test is
    intentionally validating the live contract rather than a stale pre-Story-003
    snapshot.
    """
    field_names = [f.name for f in dataclasses.fields(Measurements)]
    assert field_names == [
        "sample_rate", "channels", "duration_seconds", "is_mono",
        "integrated_lufs", "true_peak_dbtp", "dynamic_range_db",
        "frequency_balance", "stereo_phase", "clipping",
        "sanity_warnings", "artifact_detection", "plausibility_warnings",
    ]


@pytest.mark.skip(reason="TC-392: requires a pre-recorded golden-file JSON baseline captured "
                          "*before* this story's implementation landed -- none exists in-repo "
                          "(STORY-001's own equivalent golden-file test, TC-091, is itself "
                          "skipped for the same reason: no committed golden fixture). Flagged "
                          "residual dependency, same posture as STORY-001's TC-091, not a "
                          "failure of the current implementation.")
def test_tc392_render_json_byte_identical_on_golden_fixture():
    pass


def test_tc393_measure_dynamic_range_rounded_values_battery():
    sr = 44100
    config = MasteringConfig()
    for amplitude, transient in [(0.05, 0.3), (0.1, 0.5), (0.2, 0.9), (0.35, 0.99)]:
        n = int(20 * sr)
        body = sine(220, sr, 20.0, amplitude=amplitude)
        period = int(1.0 * sr)
        tlen = int(0.005 * sr)
        for start in range(period, n - tlen, period):
            body[start:start + tlen] = transient
        audio = to_stereo(body)
        dr = measure_dynamic_range(audio, sr, config)
        assert dr is not None
        assert dr >= 0.0


def test_tc394_measure_frequency_balance_output_battery():
    sr = 44100
    config = MasteringConfig()
    for seed in [1, 2, 3]:
        audio = pink_noise_stereo(sr, 20.0, seed=seed, amplitude=0.15)
        result = measure_frequency_balance(audio, sr, config)
        assert result.low_end is not None
        assert result.low_mid_mud is not None
        assert result.presence_harsh is not None


def test_tc395_progressive_house_reference_curve_still_matches_original_three_band_values():
    """No git history exists in this repo to diff against a pre-story
    baseline (fresh checkout, zero commits at the time of this QA pass) --
    so this cannot be a true content-hash-vs-recorded-baseline test as
    TC-395 literally describes. Falls back to asserting the file's content
    still matches STORY-001's own originally-documented three-band values
    (architecture.md v1's -1.5/-3.0/-4.0 dB curve) rather than some other,
    silently-changed value -- the closest available check without a
    baseline artifact. Recommend a future pass commit this file's hash as
    an actual baseline so a real diff-based TC-395 can run."""
    assert _REFERENCE_CURVE_PATH.exists()
    import json
    curve = json.loads(_REFERENCE_CURVE_PATH.read_text(encoding="utf-8"))
    assert curve["bands"]["low_end"]["relative_db"] == -1.5
    assert curve["bands"]["low_mid_mud"]["relative_db"] == -3.0
    assert curve["bands"]["presence_harsh"]["relative_db"] == -4.0
    assert curve["bands"]["low_end"]["range_hz"] == [20.0, 120.0]
    assert curve["bands"]["low_mid_mud"]["range_hz"] == [200.0, 500.0]
    assert curve["bands"]["presence_harsh"]["range_hz"] == [2000.0, 5000.0]
    digest = hashlib.sha256(_REFERENCE_CURVE_PATH.read_bytes()).hexdigest()
    print(f"progressive_house_124bpm.json sha256 (this pass): {digest}")
