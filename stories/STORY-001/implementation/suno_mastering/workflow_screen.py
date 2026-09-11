"""STORY-024: operator-facing CLI workflow screen.

A thin, deterministic reporting layer above the mastering command execution.
It renders the active stage, run state, and blocking conditions in plain text
and never claims success before the underlying validation gates have passed.

Public API:
    render_screen(stage, context) -> str
    render_summary(result) -> str
    render_error(error) -> str
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

VALID_STATES: tuple[str, ...] = ("running", "waiting", "blocked", "complete", "failed")

_STATE_LABELS = {
    "running": "RUNNING",
    "waiting": "WAITING",
    "blocked": "BLOCKED",
    "complete": "COMPLETE",
    "failed": "FAILED",
}


@dataclass(frozen=True)
class ScreenContext:
    """Operator-visible workflow state for a single screen render."""

    operation: str
    input_file: str | None = None
    model: str | None = None
    profile: str | None = None
    state: str = "running"
    detail: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


_ERROR_GUIDANCE: dict[str, str] = {
    "DependencyError": "Install the missing dependency (e.g. pip install demucs torch) or rerun without --split-stems.",
    "TargetsLoadError": "Restore a valid targets.json at the repository root; mastering targets are required before any audio runs.",
    "EmptyReferenceSetError": "Provide at least one readable reference track in the reference folder.",
    "NonDestructiveIntegrityError": "The input file changed during processing. Re-copy the source WAV and rerun.",
    "FileNotFoundError": "Check the input path and rerun with an existing WAV file.",
    "ValueError": "Fix the reported configuration or stem validation problem and rerun.",
}

_DEFAULT_GUIDANCE = "Read the reason above, correct the blocking condition, and rerun the command."
_REFERENCE_WORKFLOW = (
    "Stem Split",
    "Lochness EQ",
    "Tighten Low End",
    "Reintegrate Lows",
    "Loudness Normalization",
    "Ready for Release",
)


def _format_stage_label(stage: str) -> str:
    label = str(stage).strip()
    if not label:
        raise ValueError("stage label must be a non-empty string")
    return label


def _format_context_values(context: ScreenContext) -> list[str]:
    lines: list[str] = []
    if context.input_file is not None:
        lines.append(f"  input:   {context.input_file}")
    if context.model is not None:
        lines.append(f"  model:   {context.model}")
    if context.profile is not None:
        lines.append(f"  profile: {context.profile}")
    for key in sorted(context.extra):
        lines.append(f"  {key}: {context.extra[key]}")
    return lines


def _render_status_line(state: str, detail: str | None = None) -> str:
    normalized = str(state).strip().lower()
    if normalized not in VALID_STATES:
        raise ValueError(f"unknown workflow state {state!r}; expected one of {VALID_STATES}")
    suffix = f" - {detail}" if detail else ""
    return f"  state:   {_STATE_LABELS[normalized]}{suffix}"


def render_screen(stage: str, context: ScreenContext) -> str:
    """Render the stage-oriented workflow screen for the current run state."""
    label = _format_stage_label(stage)
    lines = ["=" * 64, f"STAGE: {label}", "=" * 64]
    lines.extend(_format_context_values(context))
    lines.append(_render_status_line(context.state, context.detail))
    lines.append("  workflow: " + " → ".join(_REFERENCE_WORKFLOW))
    return "\n".join(lines)


def render_error(error: BaseException) -> str:
    """Render a failure screen that names the real blocking condition."""
    error_type = type(error).__name__
    guidance = _ERROR_GUIDANCE.get(error_type, _DEFAULT_GUIDANCE)
    lines = ["=" * 64, "RUN FAILED", "=" * 64]
    lines.append(f"  reason:  {error_type}: {error}")
    lines.append(f"  action:  {guidance}")
    lines.append(_render_status_line("failed"))
    return "\n".join(lines)


def render_summary(result: Any) -> str:
    """Render the end-of-run summary from verified result state only.

    The summary reports COMPLETE only when the non-destructive integrity check
    passed and the loudness/true-peak solver produced verified measurements;
    otherwise it reports the run as needing review rather than assumed success.
    """
    solver: Mapping[str, Any] = getattr(getattr(result, "report", None), "solver", {}) or {}
    integrity_verified = bool(getattr(result, "integrity_verified", False))
    achieved_lufs = solver.get("achieved_lufs")
    achieved_dbtp = solver.get("achieved_true_peak_dbtp")
    achieved_dr = solver.get("achieved_dr")

    verified = integrity_verified and achieved_lufs is not None and achieved_dbtp is not None
    state = "complete" if verified else "blocked"

    lines = ["=" * 64, "RUN SUMMARY", "=" * 64]
    lines.append(f"  output:  {getattr(result, 'output_path', 'n/a')}")
    lines.append(
        "  verified measurements: "
        f"loudness={_fmt_optional(achieved_lufs, ' LUFS')}, "
        f"true_peak={_fmt_optional(achieved_dbtp, ' dBTP')}, "
        f"dynamic_range={_fmt_optional(achieved_dr, ' DR')}"
    )
    lines.append(
        f"  integrity: {'PASSED' if integrity_verified else 'FAILED - input hash changed during processing'}"
    )

    review = getattr(result, "quality_review", None)
    if review is not None:
        decision = str(getattr(review, "decision", "unknown")).upper()
        lines.append(f"  quality review: {decision} - {getattr(review, 'summary', '')}")

    lines.append(_render_status_line(state, None if verified else "validation gates did not all pass"))
    return "\n".join(lines)


def _fmt_optional(value: Any, unit: str) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}{unit}"
    except (TypeError, ValueError):
        return f"{value}{unit}"


def render_run_header(
    *,
    input_file: str,
    model: str | None,
    profile: str | None,
    stem_enabled: bool,
) -> str:
    """Render the start-of-run screen shown before the pipeline executes."""
    context = ScreenContext(
        operation="master",
        input_file=input_file,
        model=model if stem_enabled else None,
        profile=profile if stem_enabled else None,
        state="running",
        detail="stem separation" if stem_enabled else "stereo fallback path",
        extra={"stem_separation": "enabled" if stem_enabled else "disabled"},
    )
    return render_screen("Stem Split", context)


__all__: Iterable[str] = (
    "ScreenContext",
    "VALID_STATES",
    "render_screen",
    "render_summary",
    "render_error",
    "render_run_header",
)
