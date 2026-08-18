"""Renders a ReferenceSetReport to markdown or JSON (STORY-002
architecture.md Section 9). Mirrors report/render.py's existing pattern
(dataclasses.asdict + json.dumps) but is a separate module -- STORY-001's
render.py is UNCHANGED.

JSON-serialization note: every numeric field populated anywhere in
analysis/reference_types.py, reference_analysis/aggregate.py, and
report/reference_builder.py is explicitly cast to a plain Python
float/int/bool at the point it's computed (not left as a numpy scalar) --
`default=str` below is a defensive fallback for any truly unexpected
non-serializable value, not a mechanism this module relies on to coerce
numpy scalars, which would otherwise silently turn machine-readable
aggregate figures into quoted strings (a direct violation of AC9's
versioned-schema-of-real-numbers contract).
"""
from __future__ import annotations

import dataclasses
import json

from .reference_builder import ReferenceSetReport


def render_json(report: ReferenceSetReport, indent: int = 2) -> str:
    return json.dumps(dataclasses.asdict(report), indent=indent, default=str)


def _fmt(value, digits=2) -> str:
    if value is None:
        return "n/a"
    try:
        if value != value or value in (float("inf"), float("-inf")):
            return str(value)
        return f"{value:.{digits}f}"
    except TypeError:
        return str(value)


def _provenance_label(p) -> str:
    kind = "lossless" if p.lossless else "lossy"
    bitrate = f"{p.bitrate_kbps} kbps" if p.bitrate_kbps else "bitrate unknown"
    label = f"{p.container.upper()}, {kind}"
    if not p.lossless:
        label += f", {bitrate}"
    if p.suspected_transcode:
        label += " -- SUSPECTED LOSSY-SOURCE TRANSCODE (review before treating as clean reference)"
    return label


def _track_section(m) -> str:
    lines = [f"### `{m.track_path}`", ""]
    lines.append(f"- Source format: {_provenance_label(m.provenance)} (decoder: {m.provenance.decoder})")
    lines.append(f"- Duration: {_fmt(m.core.duration_seconds, 1)} s, {m.core.sample_rate} Hz, "
                 f"{'mono' if m.core.is_mono else 'stereo'}")
    lines.append(f"- Integrated loudness: {_fmt(m.core.integrated_lufs)} LUFS")
    lines.append(f"- Loudness range (LRA): {_fmt(m.lra.lra_lu)} LU "
                 f"(self-consistency check delta: {_fmt(m.lra.self_consistency_delta_lu, 3)} LU)")
    lines.append(
        f"- True peak: {_fmt(m.core.true_peak_dbtp)} dBTP "
        f"(informational only -- see standing caveat below; not validated to target-setting precision)"
    )
    lines.append(f"- Dynamic range (TT DR): DR{_fmt(m.dynamic_range_db_exact, 0)} (exact: {_fmt(m.dynamic_range_db_exact, 2)})")

    if m.core.is_mono:
        lines.append("- Stereo width / mono compatibility: mono source, not applicable (excluded from stereo aggregates)")
    elif m.mono_sum.mono_sum_both_channels_silent:
        # STORY-004 architecture.md Section 2.2/2.3/Section 4 item 10 (Gate 1
        # advisory): a silent file must never render indistinguishably from
        # ordinary, genuinely correlated (rho=1) stereo.
        lines.append(
            "- Mono-sum level change: both channels digitally silent -- "
            "mono-sum comparison not meaningful"
        )
    else:
        lines.append(f"- Overall stereo correlation: {_fmt(m.core.stereo_phase.overall_correlation, 3)}")
        lines.append(
            f"- Mono-sum level change: {_fmt(m.mono_sum.mono_sum_level_change_db)} dB "
            f"(rho=0/fully-decorrelated floor: -3.01 dB, DOMAIN.md Section 3 / "
            f"architecture.md Section 2.1; excess cancellation flagged: "
            f"{m.mono_sum.mono_sum_excess_cancellation})"
        )
        cancelled_bands = [b.band for b in m.mono_sum.band_cancellations if b.cancellation]
        if cancelled_bands:
            lines.append(f"- Band-specific mono-sum cancellation flagged in: {', '.join(cancelled_bands)}")

    if m.hf_extension.insufficient_duration:
        lines.append("- HF extension: insufficient track duration for band-limit analysis")
    elif m.hf_extension.hf_band_limit_hz is None:
        lines.append(
            "- HF extension: No artificial band-limit detected (full-band / clean material, or not "
            "measurable in the top of the range near Nyquist -- see architecture.md Section 3.5), "
            f"confidence {_fmt(m.hf_extension.hf_band_limit_confidence, 2)} "
            f"({'stable' if m.hf_extension.stable else 'UNSTABLE'})"
        )
    else:
        lines.append(
            f"- HF extension: {_fmt(m.hf_extension.hf_band_limit_hz, 0)} Hz, confidence "
            f"{_fmt(m.hf_extension.hf_band_limit_confidence, 2)} "
            f"({'stable' if m.hf_extension.stable else 'UNSTABLE'} across segments) "
            f"-- inherits true-peak-style near-Nyquist metering caveats; report-only, not target-setting"
        )
        if m.hf_extension.suspected_transcode:
            lines.append(f"  - {m.hf_extension.suspected_transcode_reason}")
        if m.hf_extension.hf_band_limit_robustness_db is not None:
            stable_caveat = (
                "; if stable=False, this minimum may reflect a per-segment "
                "false positive rather than the whole-track wall's fragility -- see DEF-205"
                if not m.hf_extension.stable else ""
            )
            lines.append(
                f"  - Per-segment localization robustness: "
                f"{_fmt(m.hf_extension.hf_band_limit_robustness_db, 2)} dB "
                f"(minimum of rightward and leftward j* margins across segments "
                f"that found a cliff; <0.5 dB within Welch estimator noise{stable_caveat})"
            )
        if m.hf_extension.per_segment_reliability_caveat is not None:
            lines.append(f"  - Per-segment reliability caveat: {m.hf_extension.per_segment_reliability_caveat}")
        if m.hf_extension.hf_band_limit_whole_track_margin_db is not None:
            lines.append(f"  - Whole-track j* margin: {_fmt(m.hf_extension.hf_band_limit_whole_track_margin_db, 2)} dB")

    lines.append("")
    lines.append("| Seven-band | Range | Relative dB |")
    lines.append("|---|---|---|")
    for b in m.seven_band.bands:
        lines.append(f"| {b.band} | {b.range_hz[0]:g}-{b.range_hz[1]:g} Hz | {_fmt(b.relative_db)} |")

    if m.per_band_stereo_width is not None:
        lines.append("")
        lines.append("| Per-band stereo width | Range | Width (0=mono, 1=decorrelated) |")
        lines.append("|---|---|---|")
        for b in m.per_band_stereo_width.bands:
            lines.append(f"| {b.band} | {b.range_hz[0]:g}-{b.range_hz[1]:g} Hz | {_fmt(b.width, 3)} |")

    if m.sanity_warnings:
        lines.append("")
        lines.append("Sanity checks:")
        for w in m.sanity_warnings:
            prefix = "[FAIL]" if w.severity == "fail" else "[WARN]"
            lines.append(f"- {prefix} {w.metric}: {w.message}")

    lines.append("")
    return "\n".join(lines)


def _aggregate_row(agg) -> str:
    n_str = f"N={agg.n}"
    note = f" ({agg.note})" if agg.note else ""
    if agg.n == 0:
        if agg.metric.startswith("hf_extension_hf_band_limit_hz."):
            return f"| {agg.metric} | No artificial band-limit detected | No artificial band-limit detected | No artificial band-limit detected | {n_str}{note} |"
        return f"| {agg.metric} | n/a | n/a | n/a | {n_str}{note} |"
    return (
        f"| {agg.metric} | {_fmt(agg.median, 3)} | {_fmt(agg.min, 3)} | {_fmt(agg.max, 3)} | "
        f"{n_str}{note} |"
    )


def render_markdown(report: ReferenceSetReport) -> str:
    lines = []
    lines.append("# Reference Track Set Analysis Report")
    lines.append("")
    lines.append(f"- Schema version: {report.schema_version}")
    lines.append(f"- Tool version: {report.tool_version}")
    lines.append(f"- Generated (UTC): {report.generated_at_utc}")
    lines.append(f"- Decoder identity: {json.dumps(report.decoder_identity)}")
    lines.append("")
    lines.append(
        "> **Standing caveat**: true-peak (dBTP) and HF-extension figures in this report inherit a "
        "bounded, direction-known near-Nyquist under-read from the shared true-peak metering FIR filter "
        "(flat to <0.01 dB only up to ~80% of Nyquist, ~0.4 dB at 90%, ~1.5-2 dB at 94-95%, ~5.9 dB at "
        "99.9% -- always attenuation, never over-read). These figures are report-only, not validated to "
        "target-setting precision (resolved open question #5). MP3-decoded true-peak figures additionally "
        "carry a SEPARATE, opposite-direction bias (inter-sample peaks introduced by lossy decoding push "
        "measured true peak UP) -- the two effects are stated separately here, never netted against each "
        "other."
    )
    lines.append("")

    if report.failures:
        lines.append("## Per-file failures")
        lines.append("")
        for f in report.failures:
            lines.append(f"- `{f['path']}`: {f['reason']}")
        lines.append("")

    lines.append("## Per-track measurements")
    lines.append("")
    for m in report.per_track:
        lines.append(_track_section(m))

    lines.append("## Aggregate statistics (median / min / max, N and contributing tracks per AC12)")
    lines.append("")
    lines.append("| Metric | Median | Min | Max | N |")
    lines.append("|---|---|---|---|---|")
    for agg in report.aggregates:
        lines.append(_aggregate_row(agg))
    lines.append("")
    for agg in report.aggregates:
        if agg.excluded:
            lines.append(f"**{agg.metric}** exclusions:")
            for exc in agg.excluded:
                lines.append(f"- `{exc['track']}`: {exc['reason']}")
            lines.append("")

    if report.comparison:
        lines.append("## Suno-export comparison (AC3)")
        lines.append("")
        gaps = report.comparison["gaps"]
        for metric, g in gaps.items():
            if g is None:
                continue
            lines.append(
                f"- {metric}: Suno export = {_fmt(g['suno_export_value'])}, "
                f"reference median = {_fmt(g['reference_median'])}, gap = {_fmt(g['gap'])}"
            )
        lines.append("")

    lines.append("## Config used")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.config_summary, indent=2))
    lines.append("```")

    return "\n".join(lines)
