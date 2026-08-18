"""STORY-002 AC12 -- N / contributing-tracks on every aggregate.
TC-340-TC-343."""
from __future__ import annotations

from suno_mastering.reference_analysis.aggregate import build_aggregates
from suno_mastering.report.reference_render import render_markdown
from suno_mastering.report.reference_builder import ReferenceSetReport

from .ref_helpers import make_stub_measurements, ref_config


def _mixed_six_set():
    return (
        [make_stub_measurements(f"a{i}", sample_rate=44100, lossless=True) for i in range(4)]
        + [make_stub_measurements("b0", sample_rate=48000, lossless=True)]
        + [make_stub_measurements("mono_mp3_48k", sample_rate=48000, lossless=False,
                                   container="mp3", is_mono=True)]
    )


def test_tc340_every_aggregate_carries_n_consistent_with_contributing_tracks():
    tracks = _mixed_six_set()
    agg = build_aggregates(tracks, ref_config())
    assert len(agg) > 0
    for a in agg:
        assert a.n >= 0
        assert a.contributing_tracks is not None
        assert a.n == len(a.contributing_tracks), f"{a.metric}: n={a.n} but {len(a.contributing_tracks)} tracks listed"


def test_tc341_n_reflects_actual_post_exclusion_membership():
    tracks = _mixed_six_set()
    agg = build_aggregates(tracks, ref_config())

    lufs = next(a for a in agg if a.metric == "integrated_lufs")
    assert lufs.n == 6  # no exclusion applies

    hf_44 = next(a for a in agg if a.metric == "hf_extension_hf_band_limit_hz.44100hz")
    assert hf_44.n == 4  # excludes 48kHz lossless track + mono mp3 track

    corr = next(a for a in agg if a.metric == "overall_correlation")
    assert corr.n == 5  # excludes only the mono track


def test_tc342_markdown_renders_n_as_a_column():
    tracks = _mixed_six_set()
    agg = build_aggregates(tracks, ref_config())
    report = ReferenceSetReport(
        generated_at_utc="2026-08-01T00:00:00Z",
        decoder_identity={"libsndfile": "1.2.2"},
        tool_version="0.1.0",
        config_summary={},
        per_track=tracks,
        aggregates=agg,
        comparison=None,
        failures=[],
    )
    md = render_markdown(report)
    assert "| N |" in md or "N=" in md
    hf_44 = next(a for a in agg if a.metric == "hf_extension_hf_band_limit_hz.44100hz")
    assert f"N={hf_44.n}" in md


def test_tc343_excluded_list_carries_distinct_reason_per_exclusion_type():
    tracks = _mixed_six_set()
    agg = build_aggregates(tracks, ref_config())

    hf_48 = next(a for a in agg if a.metric == "hf_extension_hf_band_limit_hz.48000hz")
    for e in hf_48.excluded:
        assert e["reason"]

    corr = next(a for a in agg if a.metric == "overall_correlation")
    for e in corr.excluded:
        assert e["reason"]

    hf_reason = next(e["reason"] for e in hf_48.excluded if e["track"] == "mono_mp3_48k")
    corr_reason = next(e["reason"] for e in corr.excluded if e["track"] == "mono_mp3_48k")
    assert hf_reason != corr_reason
