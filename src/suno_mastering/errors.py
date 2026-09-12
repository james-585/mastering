"""Typed exception hierarchy for suno_mastering.

Every pipeline stage must raise one of these (or a subclass) rather than
letting raw ValueError/IndexError/etc. leak to the caller. See
architecture.md Section 6, "Error handling".
"""
from __future__ import annotations


class MasteringError(Exception):
    """Base class for all suno_mastering errors."""


class InvalidWavError(MasteringError):
    """Raised when a WAV file is corrupt, truncated, zero-length, or has an
    unparseable RIFF/fmt header."""


class UnsupportedFormatError(MasteringError):
    """Raised for a structurally valid WAV that uses a format this tool does
    not support (e.g. an unsupported PCM subtype, channel count the pipeline
    cannot reason about, or a sample rate that cannot be handled even via the
    conditional resample stage)."""


class UnresolvableMasteringConstraintError(MasteringError):
    """Raised by the loudness/true-peak/DR solver (mastering.loudness_limit)
    when NO evaluated candidate gain -- across the solver's full,
    deterministic bisection range -- can simultaneously satisfy the true-peak
    ceiling and the DR floor (architecture.md v4 Section 1: the two hard
    constraints). Narrowed in v4 (resolves DEF-001's residual): this is no
    longer scoped to "even at the -16 LUFS floor," since -16 is no longer a
    hard solver constraint -- landing below -16 LUFS (or below -14.5 LUFS) is
    an allowed, reported outcome (see MasteringResult.below_documented_lufs_floor
    / SolverOutcome.below_soft_band), never an error on its own. This is
    raised only when the hard constraints themselves are unsatisfiable at any
    gain -- genuinely rare, source-level pathological cases."""


class OutputPathConflictError(MasteringError):
    """Raised when the resolved output path would equal the input path.
    Enforces the non-destructive guarantee (AC11) as a hard guard rather
    than a convention."""


class NonDestructiveIntegrityError(MasteringError):
    """Raised when the input file's SHA-256 hash at the end of a run does
    not match the hash computed at the start of the run -- i.e. the
    non-destructive guarantee was somehow violated."""


class EmptyReferenceSetError(MasteringError):
    """STORY-002: raised by reference_analysis.pipeline.analyze_set() if,
    after per-file ingest/decode failures are excluded, zero tracks remain
    to analyze -- a genuinely different condition from "one file failed"
    (architecture.md Section 11, "Error handling")."""


class TargetsLoadError(MasteringError):
    """Raised when targets.json is absent, unreadable, or fails schema
    validation.  Propagates immediately from pipeline startup — no partial
    audio processing occurs when this is raised (architecture.md §16,
    STORY-006 DEF-606)."""

    def __init__(self, message: str, path: str = "") -> None:
        self.path = path
        super().__init__(message)


class DependencyError(MasteringError):
    """Raised when an optional dependency (e.g. demucs, torch) is required
    for a requested feature (e.g. --split-stems) but is not installed.

    STORY-008: Used by io.stem_separation when demucs/torch are missing,
    providing actionable pip install instructions rather than letting a raw
    ModuleNotFoundError propagate to the CLI.

    STORY-009: Also used by pipeline.master() when any of
    repair_whistles/shape_transients/collapse_swish is enabled but the
    `suno_dsp` C++ extension cannot be imported (architecture.md Section 10).
    """


class SubFrameAudioError(MasteringError):
    """STORY-009 (architecture.md Section 5): raised when
    `repair_whistles` is enabled but the input is shorter than one STFT
    analysis frame (4096 samples, ~93 ms at 44.1 kHz). The C++ extension
    silently returns zeroed (silent) output for sub-frame input; the
    wrapper refuses the call before it happens rather than accept that
    silent fallback."""


class MasteringConfigError(MasteringError):
    """STORY-009 (architecture.md Section 6/9): raised when a suno_dsp
    stage is enabled without a required, non-defaultable parameter being
    explicitly set -- e.g. `repair_whistles.enabled=True` with
    `prominence_floor_db=None`, or `collapse_swish.enabled=True` with
    `cutoff_freq_hz=0.0`. Distinguishes a caller's config mistake from a
    `suno_dsp`-raised runtime error."""
