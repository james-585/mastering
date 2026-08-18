from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StageSpec:
    key: str
    label: str
    detail: str | None = None


STAGE_REGISTRY: tuple[StageSpec, ...] = (
    StageSpec("stem_split", "Stem Split"),
    StageSpec("lochness_eq", "Lochness EQ"),
    StageSpec("tighten_low_end", "Tighten Low End"),
    StageSpec("reintegrate_lows", "Reintegrate Lows"),
    StageSpec("loudness_normalize", "Loudness Normalize"),
    StageSpec("ready_for_release", "Ready for Release"),
)


class ProgressReporter(Protocol):
    def emit(self, stage: int, label: str, detail: str | None = None, *, total: int | None = None) -> None: ...


class NullReporter:
    def emit(self, stage: int, label: str, detail: str | None = None, *, total: int | None = None) -> None:
        return None


class ConsoleReporter:
    def __init__(self, stream=None, *, total: int = 6) -> None:
        self.stream = stream if stream is not None else sys.stdout
        self.total = total

    def emit(self, stage: int, label: str, detail: str | None = None, *, total: int | None = None) -> None:
        final_total = total if total is not None else self.total
        text = render_stage_bar(stage, label, stage, final_total, detail)
        print(text, file=self.stream)


def render_stage_bar(stage: int, label: str, done: int, total: int, detail: str | None = None) -> str:
    if total <= 0:
        total = 1
    filled = max(0, min(total, done))
    ratio = filled / total
    width = 30
    block_count = int(round(ratio * width))
    bar = "█" * block_count + "░" * (width - block_count)
    suffix = f" - {detail}" if detail else ""
    return f"[Stage {stage}] {label} |{bar}| {ratio * 100:.0f}%{suffix}"


def build_stage_progress(stage: int, total: int, label: str, detail: str | None = None) -> str:
    return render_stage_bar(stage, label, stage, total, detail)


def plan_stages(*, config=None, is_stereo: bool = True, stem_enabled: bool | None = None) -> list[StageSpec]:
    return list(STAGE_REGISTRY)


@dataclass(frozen=True)
class ProgressEvent:
    stage: int
    label: str
    detail: str | None = None
    total: int = 1
