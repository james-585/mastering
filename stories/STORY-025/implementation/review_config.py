"""GroundedReviewConfig (STORY-025 architecture.md §7.1).

All comparison thresholds live in one dataclass -- never as literals in
grounded_quality_review.py -- per this repo's "derive every constant, never
assert one inline" convention.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_FOR_IMPORT = [
    _REPO_ROOT / "stories" / "STORY-001" / "implementation",
]
for _path in _FOR_IMPORT:
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from suno_mastering.reference_analysis.config import ReferenceAnalysisConfig


@dataclass
class GroundedReviewConfig:
    reference_analysis: ReferenceAnalysisConfig = field(default_factory=ReferenceAnalysisConfig)
    lufs_match_tolerance_lu: float = 0.5          # derived, §4.2 -- not a verdict threshold

    # Reused, not invented: STORY-006's already-derived DR policy constant.
    # dr_max_reduction_db (3.0) is the project's existing "never reduce DR by
    # more than this vs. source" cap (config.py); reused here as the same
    # magnitude that would flag a DR *regression* on before/after comparison.
    dr_regression_db: float = 3.0                 # = MasteringConfig.dr_max_reduction_db

    # PROVISIONAL -- no existing project data derives this. STORY-007 only
    # normalizes overall_artifact_density_score to [0.0, 1.0]; it never
    # defines a before/after comparison delta. Flagged for mastering-engineer
    # (§10) to validate/replace against real reference-track before/after
    # measurements before this is treated as a real gate.
    # Gate 1 action item (Finding 1): the raw artifact_density_delta value
    # and this PROVISIONAL label must both be surfaced in
    # evaluate_quality_review's audit trail (§7.3), not just the boolean
    # flag -- see gate1-review.md Finding 1, §12 revision history.
    artifact_density_regression: float = 0.05     # PROVISIONAL

    # PROVISIONAL -- RMS shift across the six non-reference seven-band deltas
    # (see §7.2) large enough to flag "the tonal balance moved substantially"
    # for human attention. Not a pass/fail threshold -- it only decides
    # whether a flag is raised for the human reviewer to weigh.
    # Gate 1 action item (Finding 2): same audit-surfacing requirement as
    # artifact_density_regression above -- see gate1-review.md Finding 2,
    # §12 revision history.
    spectral_shift_flag_db: float = 2.0           # PROVISIONAL
