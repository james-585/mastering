"""Iterative LUFS/true-peak/DR reconciliation solver (pipeline stage [6]),
architecture.md Section 1 "Note on the DR/loudness solver interaction" and
"Solver resolution for high-crest-factor sources (v4, resolves DEF-001
residual)", and Section 8/9.

Jointly satisfies, v4:
  - true peak <= -1.0 dBTP (HARD constraint, oversampled measurement);
  - DR >= max(DR8, source_DR - 3dB) (HARD constraint) -- compared against
    the TRUE original pre-processing source DR (passed in explicitly by the
    caller from stage [2]'s measurement), NOT this stage's own entry DR.
    This is deliberate: architecture.md flags comparing against the wrong
    baseline as an easy, subtle bug (small EQ/stereo-stage DR erosion would
    otherwise go uncounted).
  - integrated LUFS is a fully SOFT target: the solver prefers the
    [-14.5, -13.5] band, backs off toward -16 if that band isn't reachable
    without violating a hard constraint, and -- v4, resolves DEF-001's
    residual (defects.md) -- continues backing off *below* -16 with no
    lower bound at all if even -16 can't be held, rather than raising
    UnresolvableMasteringConstraintError purely for landing under -16.
    `config.lufs_floor` (-16.0 default) is retained as a report-escalation
    threshold only (see `below_documented_lufs_floor` below), not a hard
    solver constraint.

Candidate selection: among all DR/peak-feasible candidates evaluated during
the bounded bisection, select the one with the highest achieved_lufs
(closest to -13.5 from below). Because achieved-LUFS-vs-target-gain is not
guaranteed monotonic near the point where the limiter starts heavily
engaging, the best-feasible candidate is tracked across *all* evaluated
iterations, not assumed to be the most recently accepted bisection step.

UnresolvableMasteringConstraintError now fires only if NO evaluated
candidate is DR/peak-feasible at all (genuinely pathological source-level
cases), never merely for landing under -16 LUFS.

Uses bounded, deterministic iteration (fixed config.solver_max_iterations,
no wall-clock cutoffs) for AC10 reproducibility.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..analysis.loudness import measure_integrated_lufs
from ..analysis.true_peak import measure_true_peak, measure_true_peak_with_factor
from ..analysis.dynamic_range import measure_dynamic_range
from ..errors import UnresolvableMasteringConstraintError
from .limiter import apply_lookahead_limiter

_MIN_LINEAR = 1e-12

# At the true-peak ceiling, the worst-case inter-sample overshoot of a
# single-frequency tone is approximately +3.01 dB (Nyquist-adjacent sine at a
# 45-degree phase offset). If a candidate's sample peak is already more than
# ~3 dB below the hard ceiling, then an oversampled true-peak measurement can
# never push it over that ceiling; we can safely reject the expensive
# oversample path in that case while preserving the exact meter for the final
# feasibility gate and any candidate close enough to the limit to be risky.
_TRUE_PEAK_SAFETY_MARGIN_DB = 3.01


def _sample_peak_dbtp(audio: np.ndarray) -> float:
    if audio.size == 0:
        return float("-inf")
    sample_peak_linear = float(np.max(np.abs(audio)))
    return 20.0 * np.log10(max(sample_peak_linear, _MIN_LINEAR))


def _needs_exact_true_peak_scan(audio: np.ndarray, ceiling_dbtp: float) -> bool:
    if audio.size == 0:
        return False
    sample_peak_linear = float(np.max(np.abs(audio)))
    if sample_peak_linear <= _MIN_LINEAR:
        return False
    safe_sample_peak_linear = 10.0 ** ((ceiling_dbtp - _TRUE_PEAK_SAFETY_MARGIN_DB) / 20.0)
    return sample_peak_linear > safe_sample_peak_linear


@dataclass
class SolverCandidate:
    target_lufs: float
    gain_db: float
    audio: np.ndarray
    achieved_lufs: float
    achieved_true_peak_dbtp: float
    achieved_dr: float
    peak_convergence_iterations: int


@dataclass
class SolverOutcome:
    audio: np.ndarray
    target_lufs: float
    achieved_lufs: float
    achieved_true_peak_dbtp: float
    achieved_dr: float
    source_dr: float
    dr_floor_used: float
    gain_db_applied: float
    outer_iterations: int
    peak_convergence_iterations: int
    below_soft_band: bool
    below_documented_lufs_floor: bool
    rationale: Optional[str] = None


def _render_candidate(audio: np.ndarray, sr: int, target_lufs: float, config) -> SolverCandidate:
    current_lufs = measure_integrated_lufs(audio, sr)
    if not np.isfinite(current_lufs):
        # Fully-gated/silent buffer: no meaningful gain to compute; pass through unchanged.
        gain_db = 0.0
    else:
        gain_db = target_lufs - current_lufs

    gained = audio * (10.0 ** (gain_db / 20.0))

    margin_db = 0.0
    limited = gained
    tp_dbtp = None
    iterations_used = 0
    for i in range(config.solver_max_iterations):
        iterations_used = i + 1
        ceiling_linear = 10.0 ** ((config.true_peak_ceiling_dbtp - margin_db) / 20.0)
        outcome = apply_lookahead_limiter(gained, sr, ceiling_linear, config)
        limited = outcome.audio

        # Exact oversampled true-peak metering is the dominant runtime cost in
        # the solver. For most candidates the limiter keeps the signal well
        # below the ceiling, so use a cheap 4x provisional probe first and only
        # run the exact configured oversample factor when the candidate is close
        # enough to the ceiling that the final feasibility check matters.
        if not _needs_exact_true_peak_scan(limited, config.true_peak_ceiling_dbtp):
            tp_dbtp = _sample_peak_dbtp(limited)
        else:
            provisional_factor = max(1, min(4, int(config.true_peak_oversample_factor)))
            provisional = measure_true_peak_with_factor(limited, sr, provisional_factor)
            if provisional.dbtp <= config.true_peak_ceiling_dbtp - 0.25:
                tp_dbtp = provisional.dbtp
            else:
                tp_result = measure_true_peak(limited, sr, config)
                tp_dbtp = tp_result.dbtp

        if tp_dbtp <= config.true_peak_ceiling_dbtp + 1e-6:
            break
        # Oversampled true peak still exceeds ceiling (inter-sample overshoot
        # beyond what the 1x-rate lookahead limiter alone caught): tighten
        # the enforced ceiling and retry, bounded by solver_max_iterations.
        margin_db += max(tp_dbtp - config.true_peak_ceiling_dbtp, 0.01)

    achieved_lufs = measure_integrated_lufs(limited, sr)
    achieved_dr = measure_dynamic_range(limited, sr, config)

    return SolverCandidate(
        target_lufs=target_lufs,
        gain_db=gain_db,
        audio=limited,
        achieved_lufs=achieved_lufs,
        achieved_true_peak_dbtp=tp_dbtp,
        achieved_dr=achieved_dr,
        peak_convergence_iterations=iterations_used,
    )


def solve_loudness_and_limit(audio: np.ndarray, sr: int, source_dr_db: float, config) -> SolverOutcome:
    """`source_dr_db` MUST be the true, original, pre-processing source DR
    from stage [2] -- see module docstring."""
    dr_required = max(config.dr_floor, source_dr_db - config.dr_max_reduction_db)

    # v4 fix (2026-08-01, python-developer): the bisection's lower search
    # bound MUST reach down to (approximately) zero applied gain, not stop at
    # config.lufs_floor (-16.0). Architecture.md Section 1 point 4 defines
    # "unresolvable" as "even the most conservative, near-zero-gain
    # candidate cannot hold the DR floor" -- but for a quiet, high-crest-
    # factor source, reaching *target* -16 LUFS can itself already require
    # several dB of gain (BS.1770 gating means measured current_lufs for
    # this signal shape can sit well below -16 before any gain is applied),
    # so anchoring the conservative end of the search at target=-16 was
    # silently narrower than "near-zero gain" and could raise
    # UnresolvableMasteringConstraintError for a source that a lower target
    # (below -16) would have resolved cleanly. Anchor the conservative bound
    # at target_lufs == current_lufs instead (gain_db == 0 exactly), which
    # is the actual near-zero-gain candidate the architecture describes.
    current_lufs = measure_integrated_lufs(audio, sr)
    if np.isfinite(current_lufs):
        zero_gain_target = current_lufs
    else:
        # Fully-gated/near-silent source: _render_candidate's own guard
        # already forces gain_db=0 regardless of target in this case, so any
        # target value is equivalent here -- lufs_floor is a fine anchor.
        zero_gain_target = config.lufs_floor

    lo = min(zero_gain_target, config.lufs_floor)
    hi = config.lufs_ceiling
    if lo > hi:
        # Degenerate case: source is already louder than the ceiling even at
        # zero gain. Still search the (now-inverted-looking) range from the
        # ceiling down to lo isn't meaningful; clamp lo to hi so the solver
        # evaluates at least the single near-zero-gain candidate.
        lo = hi

    best: Optional[SolverCandidate] = None
    total_peak_iterations = 0
    outer_iterations = 0

    def _is_feasible(candidate: SolverCandidate) -> bool:
        # v4 (architecture.md Section 1, resolves DEF-001 residual):
        # feasibility is EXACTLY the two hard constraints -- DR floor and
        # true-peak ceiling. The achieved_lufs >= lufs_floor clause from the
        # v1-v3 code-level DEF-001 fix is deliberately removed: LUFS is now
        # a fully soft target with no lower bound (see module docstring).
        return (
            candidate.achieved_dr >= dr_required
            and candidate.achieved_true_peak_dbtp <= config.true_peak_ceiling_dbtp + 1e-6
        )

    def _consider(candidate: SolverCandidate) -> bool:
        """Feasibility-test a candidate and, if feasible, update `best` iff
        it has a higher achieved_lufs than the current best -- tracked
        across ALL evaluated iterations (not just the most recently accepted
        bisection step), since achieved-LUFS-vs-target-gain is not
        guaranteed monotonic near where the limiter starts heavily engaging
        (architecture.md Section 1, point 3)."""
        nonlocal best
        feasible = _is_feasible(candidate)
        if feasible and (best is None or candidate.achieved_lufs > best.achieved_lufs):
            best = candidate
        return feasible

    # Evaluate the most conservative end of the bisection range first (the
    # existing bisection mechanism is unchanged from v1-v3 -- only the
    # feasibility/selection/error-scoping logic changes, per architecture.md
    # Section 1 point 1). If even this candidate can't satisfy the DR floor
    # and true-peak ceiling, no amount of backing off further would help
    # (backing off only reduces gain/loudness, it doesn't relax DR or
    # true-peak pressure) -- the run is genuinely unresolvable.
    floor_candidate = _render_candidate(audio, sr, lo, config)
    total_peak_iterations += floor_candidate.peak_convergence_iterations
    outer_iterations += 1
    if not _consider(floor_candidate):
        # v4: narrowed to fire only when NO candidate is DR/peak-feasible at
        # all -- never merely for landing below -16 LUFS, which is now an
        # allowed, reported (below_documented_lufs_floor) outcome (see
        # errors.UnresolvableMasteringConstraintError docstring).
        raise UnresolvableMasteringConstraintError(
            f"Cannot satisfy DR floor ({dr_required:.1f}) and/or true-peak ceiling "
            f"({config.true_peak_ceiling_dbtp} dBTP) at any evaluated gain, including the "
            f"most conservative candidate in the solver's bisection range. "
            f"Achieved DR={floor_candidate.achieved_dr:.1f}, "
            f"true_peak={floor_candidate.achieved_true_peak_dbtp:.2f} dBTP. "
            f"Source DR={source_dr_db:.1f}."
        )

    # Bisection: search for the highest target LUFS that remains DR/peak
    # feasible. `best` (tracked via `_consider`) is the answer, independently
    # of which side of the bisection ultimately narrows to -- DR is
    # monotonically non-increasing as target LUFS rises (more gain -> more
    # limiting -> lower DR), so bisection over target-vs-feasibility is
    # well-founded, even though achieved_lufs itself isn't strictly
    # monotonic with target near heavy limiter engagement.
    for _ in range(config.solver_max_iterations):
        outer_iterations += 1
        mid = (lo + hi) / 2.0
        candidate = _render_candidate(audio, sr, mid, config)
        total_peak_iterations += candidate.peak_convergence_iterations
        feasible = _consider(candidate)
        if feasible:
            lo = mid
        else:
            hi = mid
        if (hi - lo) < config.solver_lufs_tolerance:
            break

    below_soft_band = best.achieved_lufs < config.lufs_target_low
    below_documented_lufs_floor = best.achieved_lufs < config.lufs_floor
    rationale = None
    if below_documented_lufs_floor:
        # v4: escalated rationale tier -- must name the specific hard
        # constraint that forced landing below the documented -16 LUFS
        # floor (architecture.md Section 1 point 5). In practice this is
        # always the DR floor, since the true-peak ceiling is enforced by
        # construction inside the limiter.
        rationale = (
            f"Landed at {best.achieved_lufs:.2f} LUFS, below the documented -16 LUFS floor "
            f"(config.lufs_floor={config.lufs_floor}, a soft report-escalation threshold as of "
            f"architecture.md v4, not a hard solver constraint). This was forced by the DR "
            f"floor hard constraint: source DR was {source_dr_db:.1f}, requiring the mastered "
            f"output to retain at least {dr_required:.1f} DR (max of DR floor {config.dr_floor} "
            f"and source minus {config.dr_max_reduction_db}dB); the achieved DR at the selected "
            f"candidate is {best.achieved_dr:.1f}. No higher-gain candidate could raise loudness "
            f"further without dropping achieved DR below this required {dr_required:.1f} floor "
            f"or exceeding the {config.true_peak_ceiling_dbtp} dBTP true-peak ceiling."
        )
    elif below_soft_band:
        rationale = (
            f"Landed at {best.achieved_lufs:.2f} LUFS, below the {config.lufs_target_low} to "
            f"{config.lufs_ceiling} LUFS target band, because reaching {config.lufs_ceiling} LUFS "
            f"would have required dynamic-range-destroying limiting: source DR was "
            f"{source_dr_db:.1f}, requiring the mastered output to retain at least "
            f"{dr_required:.1f} DR (max of DR floor {config.dr_floor} and source minus "
            f"{config.dr_max_reduction_db}dB). The solver backed off loudness rather than "
            f"violate the DR floor or the {config.true_peak_ceiling_dbtp} dBTP true-peak ceiling."
        )

    return SolverOutcome(
        audio=best.audio,
        target_lufs=best.target_lufs,
        achieved_lufs=best.achieved_lufs,
        achieved_true_peak_dbtp=best.achieved_true_peak_dbtp,
        achieved_dr=best.achieved_dr,
        source_dr=source_dr_db,
        dr_floor_used=dr_required,
        gain_db_applied=best.gain_db,
        outer_iterations=outer_iterations,
        peak_convergence_iterations=total_peak_iterations,
        below_soft_band=below_soft_band,
        below_documented_lufs_floor=below_documented_lufs_floor,
        rationale=rationale,
    )
