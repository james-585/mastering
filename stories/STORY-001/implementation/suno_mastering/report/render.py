"""Renders a ReportData object to markdown or JSON (pipeline stage [10]).

The markdown rendering is the "form a producer can read without needing to
re-run analysis separately" (AC8); JSON is for machine consumption /
golden-file regression comparisons (AC10).
"""
from __future__ import annotations

import dataclasses
import json

from .builder import ReportData


def render_json(report: ReportData, indent: int = 2) -> str:
    return json.dumps(dataclasses.asdict(report), indent=indent, default=str)


def _fmt(value, digits=2) -> str:
    if value is None:
        return "n/a"
    try:
        if value != value or value in (float("inf"), float("-inf")):  # NaN/inf
            return str(value)
        return f"{value:.{digits}f}"
    except TypeError:
        return str(value)


def _band_row(name: str, band) -> str:
    flag = f"FLAGGED ({band.flag_name})" if band.flagged else "ok"
    return (
        f"| {name} | {band.range_hz[0]:g}-{band.range_hz[1]:g} Hz | "
        f"{_fmt(band.relative_db)} dB | {_fmt(band.reference_db)} dB | "
        f"{_fmt(band.deviation_db)} dB | {flag} |"
    )


def _measurements_section(title: str, m) -> str:
    lines = [f"### {title}", ""]
    lines.append(f"- Duration: {_fmt(m.duration_seconds, 1)} s")
    lines.append(f"- Channels: {m.channels} ({'mono' if m.is_mono else 'stereo'})")
    lines.append(f"- Integrated loudness: {_fmt(m.integrated_lufs)} LUFS")
    lines.append(f"- True peak: {_fmt(m.true_peak_dbtp)} dBTP")
    lines.append(f"- Dynamic range (TT DR): DR{_fmt(m.dynamic_range_db, 0)}")
    lines.append(
        f"- Clipping: {m.clipping.sample_peak_clipped_count} sample(s) clipped "
        f"({m.clipping.sample_peak_clip_events} event(s)), "
        f"{m.clipping.inter_sample_over_count} inter-sample over(s), "
        f"severity: {m.clipping.severity}"
    )
    if m.stereo_phase.is_mono:
        lines.append("- Stereo/mono compatibility: mono source, not applicable")
    else:
        lines.append(
            f"- Stereo/mono compatibility: overall correlation "
            f"{_fmt(m.stereo_phase.overall_correlation, 3)} "
            f"({'compatible' if m.stereo_phase.mono_compatible else 'NOT COMPATIBLE'}), "
            f"{len(m.stereo_phase.widened_regions)} stereo-widened region(s) identified"
        )
    lines.append("")
    lines.append("| Band | Range | Measured (rel. dB) | Reference (rel. dB) | Deviation | Flag |")
    lines.append("|---|---|---|---|---|---|")
    lines.append(_band_row("Low-end", m.frequency_balance.low_end))
    lines.append(_band_row("Low-mid/mud", m.frequency_balance.low_mid_mud))
    lines.append(_band_row("Presence/harsh", m.frequency_balance.presence_harsh))
    lines.append("")

    if m.sanity_warnings:
        lines.append("Sanity checks:")
        for w in m.sanity_warnings:
            prefix = "[FAIL]" if w.severity == "fail" else "[WARN]"
            lines.append(f"- {prefix} {w.metric}: {w.message}")
        lines.append("")

    return "\n".join(lines)


def _artifact_review_section(title: str, measurement) -> list[str]:
    lines = [f"### {title}", ""]
    artifact = getattr(measurement, "artifact_detection", None)
    warnings = getattr(measurement, "plausibility_warnings", []) or []

    if artifact is None:
        lines.append("- Artifact detection not run for this stage.")
        lines.append("")
        return lines

    if not artifact.artifact_flags:
        lines.append("- No artifact flags detected.")
        lines.append(f"- Density score: {artifact.overall_artifact_density_score:.4f}")
        lines.append("")
        return lines

    counts = {}
    for flag in artifact.artifact_flags:
        counts[flag.artifact_type] = counts.get(flag.artifact_type, 0) + 1

    highest_confidence = max((flag.confidence_score for flag in artifact.artifact_flags), default=0.0)
    lines.append(f"- Density score: {artifact.overall_artifact_density_score:.4f}")
    lines.append(f"- Total flags: {artifact.total_artifacts_found}")
    lines.append(f"- Highest-confidence issue: {highest_confidence:.2f}")
    lines.append("- Most common issue types:")
    for artifact_type, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:3]:
        lines.append(f"  - {artifact_type}: {count}")

    if warnings:
        lines.append("")
        lines.append("- Summary warnings:")
        for warning in warnings[:3]:
            lines.append(f"  - {warning}")
        if len(warnings) > 3:
            lines.append(f"  - ... and {len(warnings) - 3} more warning(s)")

    lines.append("")
    return lines


def _summary_line(label: str, before_value, after_value, unit: str = "") -> str:
    if before_value is None or after_value is None:
        return f"- {label}: {before_value} -> {after_value}"
    return f"- {label}: {_fmt(before_value)}{unit} -> {_fmt(after_value)}{unit}"


def render_markdown(report: ReportData) -> str:
    lines = []
    lines.append("# Mastering Report")
    lines.append("")
    lines.append("## At a glance")
    lines.append("")

    before = report.before
    after = report.after
    before_mud = before.frequency_balance.low_mid_mud
    after_mud = after.frequency_balance.low_mid_mud
    loudness_target = report.solver.get("target_lufs")
    loudness_achieved = after.integrated_lufs
    peak_ceiling = report.config_summary.get("true_peak_ceiling_dbtp")
    overall_result = "PASS" if after.integrated_lufs is not None and after.true_peak_dbtp is not None else "REVIEW"

    lines.append(f"- Overall result: {overall_result}")
    lines.append(f"- Loudness: {_fmt(before.integrated_lufs)} LUFS -> {_fmt(after.integrated_lufs)} LUFS (target {_fmt(loudness_target)} LUFS)")
    lines.append(f"- True peak: {_fmt(before.true_peak_dbtp)} dBTP -> {_fmt(after.true_peak_dbtp)} dBTP (ceiling {_fmt(peak_ceiling)} dBTP)")
    lines.append(
        "- Demuddification: low-mid energy improved from "
        f"{_fmt(before_mud.relative_db)} dB to {_fmt(after_mud.relative_db)} dB relative to reference, "
        f"and the muddiness flag changed from {'FLAGGED' if before_mud.flagged else 'clear'} to {'FLAGGED' if after_mud.flagged else 'clear'}."
    )
    lines.append("")

    lines.append(f"- Tool version: {report.tool_version}")
    lines.append(f"- Generated (UTC): {report.generated_at_utc}")
    lines.append(f"- Input: `{report.input_path}`")
    lines.append(f"- Output: `{report.output_path}`")
    lines.append(f"- Input SHA-256: `{report.input_hash}`")
    lines.append(f"- Output SHA-256: `{report.output_hash}`")
    lines.append(f"- Non-destructive integrity check: {'PASSED' if report.integrity_verified else 'FAILED'}")
    lines.append("")

    if report.stem_runtime:
        runtime = report.stem_runtime
        profile = runtime.get("profile", {})
        lines.append("## Stem separation runtime")
        lines.append("")
        lines.append(f"- Model: {runtime.get('model_name')}")
        lines.append(
            f"- Device: requested {runtime.get('requested_device')}, "
            f"finished on {runtime.get('final_device')}"
        )
        lines.append(
            f"- Profile: {profile.get('version')} "
            f"(shifts={profile.get('shifts')}, overlap={profile.get('overlap')}, "
            f"segment_seconds={profile.get('segment_seconds')})"
        )
        lines.append(f"- Model cache hit: {runtime.get('cache_hit')}")
        lines.append(f"- Stem order: {runtime.get('canonical_source_order')}")
        lines.append(
            f"- Uncorrected reconstruction residual: peak "
            f"{_fmt(runtime.get('residual_peak'), 6)}, energy ratio "
            f"{_fmt(runtime.get('residual_energy_ratio'), 6)}"
        )
        forensics = runtime.get("forensics")
        if forensics:
            lines.append(
                f"- Forensics gate (STORY-023): {str(forensics.get('status')).upper()} "
                f"(clipping={forensics.get('clipping_detected')}, "
                f"phase_mismatch={forensics.get('phase_mismatch_detected')}, "
                f"residual_max={_fmt(forensics.get('residual_error_max'), 6)}, "
                f"residual={_fmt(forensics.get('residual_error_dbfs'), 2)} dBFS)"
            )
            for reason in forensics.get("reasons", []):
                lines.append(f"  - {reason}")
        ms_boundary = runtime.get("ms_other_stem")
        if ms_boundary:
            lines.append(
                f"- M/S 'other' stem boundary (STORY-019): "
                f"{ms_boundary.get('status')} "
                f"(residual={_fmt(ms_boundary.get('residual'), 6)}, "
                f"safety={ms_boundary.get('safety')})"
            )
        if runtime.get("fallback_reason"):
            lines.append(
                f"- Device fallback at {runtime.get('fallback_point')}: "
                f"{runtime.get('fallback_reason')}"
            )
        lines.append("")

    lines.append(_measurements_section("Before (pre-master)", report.before))
    lines.append(_measurements_section("After (post-master)", report.after))

    lines.append("## Artifact summary")
    lines.extend(_artifact_review_section("Before (pre-master)", report.before))
    lines.extend(_artifact_review_section("After (post-master)", report.after))

    lines.append("## Corrective actions taken")
    lines.append("")
    if report.resample_action:
        ra = report.resample_action
        lines.append(f"- Resampled from {ra['source_sample_rate']} Hz to {ra['sample_rate']} Hz (source rate unsupported).")
    else:
        lines.append("- No resample needed (source sample rate already supported).")

    if report.eq_actions:
        for a in report.eq_actions:
            if hasattr(a, "filter_type"):
                lines.append(
                    f"- EQ: {a.filter_type} at {a.center_hz:.0f} Hz, "
                    f"{a.gain_db:+.2f} dB (reason: {a.reason})"
                )
            elif hasattr(a, "band"):
                lines.append(
                    f"- Spectral corrective EQ: band={a.band}, trigger={a.trigger}, "
                    f"applied={a.applied_db:+.2f} dB, resulting={a.resulting_db:+.2f} dB, "
                    f"cap_reached={a.cap_reached}"
                )
            else:
                lines.append(f"- EQ action: {a}")
    else:
        lines.append("- No corrective EQ applied (no frequency-balance flags triggered).")

    if report.stereo_actions:
        for a in report.stereo_actions:
            if hasattr(a, "start_time_s"):
                lines.append(
                    f"- Stereo narrowing: {a.start_time_s:.2f}s-{a.end_time_s:.2f}s, "
                    f"side scaled by {a.side_scale_factor:.3f} "
                    f"(correlation {a.original_correlation:.3f} -> {a.corrected_correlation:.3f})"
                )
            elif hasattr(a, "band"):
                lines.append(
                    f"- Width corrective action: band={a.band}, aim={a.aim_point:.2f}, "
                    f"applied={a.applied:+.2f}, cap_reached={a.cap_reached}"
                )
            else:
                lines.append(f"- Stereo action: {a}")
    else:
        lines.append("- No stereo narrowing applied (no non-compliant stereo-widened elements found).")

    if report.repair_whistles_actions:
        for a in report.repair_whistles_actions:
            if hasattr(a, "frequency_hz") and hasattr(a, "timestamp_start_s"):
                lines.append(
                    f"- Whistle repair: {a.frequency_hz:.1f} Hz, confidence={a.confidence_score:.2f}, "
                    f"prominence={a.prominence_db:+.2f} dB, window={a.timestamp_start_s:.2f}s-{a.timestamp_end_s:.2f}s"
                )
            elif hasattr(a, "frequencies_notched"):
                lines.append(
                    f"- Whistle repair summary: notched frequencies={a.frequencies_notched}, stage_ran={a.stage_ran}"
                )
            else:
                lines.append(f"- Whistle repair action: {a}")

    if report.collapse_swish_actions:
        for a in report.collapse_swish_actions:
            if hasattr(a, "cutoff_freq_hz"):
                lines.append(
                    f"- Swish collapse: cutoff={a.cutoff_freq_hz:.0f} Hz, side-energy Δ={a.side_energy_delta_db:+.2f} dB, "
                    f"PHASE_SWISH flags={a.phase_swish_flags_present}"
                )
            else:
                lines.append(f"- Swish collapse action: {a}")

    if report.shape_transients_actions:
        for a in report.shape_transients_actions:
            if hasattr(a, "attack_boost_db"):
                lines.append(
                    f"- Transient shaping: attack={a.attack_boost_db:+.2f} dB, sustain={a.sustain_cut_db:+.2f} dB, "
                    f"peak Δ={a.peak_delta_db:+.2f} dB, RMS Δ={a.rms_delta_db:+.2f} dB"
                )
            else:
                lines.append(f"- Transient action: {a}")

    if report.adaptive_harshness_actions:
        for a in report.adaptive_harshness_actions:
            lines.append(
                f"- Adaptive harshness: {a.method} ({a.reason}) at {a.center_hz:.0f} Hz, "
                f"gain={a.gain_db:+.2f} dB"
            )

    s = report.solver
    lines.append(
        f"- Loudness/limiting: target {_fmt(s['target_lufs'])} LUFS, achieved "
        f"{_fmt(s['achieved_lufs'])} LUFS, true peak {_fmt(s['achieved_true_peak_dbtp'])} dBTP, "
        f"DR{_fmt(s['achieved_dr'], 0)} (source DR{_fmt(s['source_dr'], 0)}, "
        f"floor DR{_fmt(s['dr_floor_used'], 0)}), gain applied {_fmt(s['gain_db_applied'])} dB "
        f"over {s['outer_iterations']} solver iteration(s)."
    )
    if s.get("rationale"):
        lines.append("")
        lines.append(f"> **Why the loudness ceiling was not reached:** {s['rationale']}")

    lines.append("")
    lines.append(f"- Dither: TPDF, seed={report.dither_seed}")
    lines.append("")
    lines.append("## Config used")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(report.config_summary, indent=2))
    lines.append("```")

    return "\n".join(lines)
