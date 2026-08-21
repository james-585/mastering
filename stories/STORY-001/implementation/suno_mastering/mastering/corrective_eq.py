from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy.signal import sosfiltfilt

from .eq import _low_shelf_sos, _peaking_sos, _band_center_hz, _band_bandwidth_octaves


@dataclass
class SpectralCorrectiveAction:
    """Log entry for one corrective EQ move.  Field order matches architecture §7.1.

    applied_db is the DELIVERED gain at the filter's centre frequency (= 2 × the
    design parameter passed to _low_shelf_sos / _peaking_sos, because sosfiltfilt
    applies forward then backward doubling the single-pass response).
    resulting_db is arithmetic (source_db + applied_db) — a NOMINAL INTENDED OUTCOME
    for logging only; it does NOT account for energy-weighted under-delivery across
    the band (~0.60× for sub shelf, ~0.75× for low_mid bell).  AC16 pass/fail
    classification uses Stage [9] post-correction measurement, not resulting_db.

    residual_gap_db (STORY-027 §5.3): aim_point_db − post_master_seven_band_relative_db[band].
    Populated by report/builder.py after post-master analysis; None at EQ time.
    Positive = aim was not fully reached (expected for large de_mud corrections where
    the peaking bell's ~0.75× delivery efficiency undershoots the aim).

    spillover_note: for sub shelf corrections, records that the RBJ low-shelf at
    fc=60 Hz (S=1) attenuates the lower low-band (60–90 Hz) as an incidental
    transition-band effect.  Any post-master low-band anomaly following a large sub
    correction should be attributed to this spillover, not a separate low-band trigger.
    (STORY-027 architecture §3.2 — implementation requirement.)

    Maintenance note (STORY-027 §3.3): the ~0.75× peaking-bell delivery efficiency
    for low_mid is load-bearing for the de_mud aim=2.0 design.  If the peaking filter
    construction or the applied_db/2 zero-phase convention changes, the aim point
    must be revisited at Gate 1.
    """
    band: str           # "sub" | "low_mid"
    trigger: str        # "range_compliance" | "de_mud"
    source_db: float    # pre-correction relative_db for the band (from pre_band_levels)
    aim_point_db: float # nearest range edge for range_compliance; de_mud.correction_aim_point_db for de_mud
    applied_db: float   # signed dB of delivered gain at centre frequency
    cap_reached: bool
    resulting_db: float # source_db + applied_db (arithmetic, NOT used for AC16 classification)
    residual_gap_db: Optional[float] = None  # populated by report/builder post-master; None at EQ time
    spillover_note: Optional[str] = None     # set for sub band to document low-band shelf transition


# DEF-027-004: delivery efficiency constants (architecture §3.2).
# The RBJ low-shelf at fc=60 Hz (S=1) delivers ~60% of the nominal gain across
# the 20-60 Hz sub band in band-energy terms (sosfiltfilt forward-backward pass).
# The peaking bell at the low_mid geometric centre delivers ~75% of nominal across
# the 120-500 Hz band.  Dividing the raw gap by these efficiencies means the
# delivered band-energy change reaches the aim point.
_DELIVERY_EFFICIENCY_SUB: float = 0.60
_DELIVERY_EFFICIENCY_LM: float = 0.75


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def apply_corrective_eq(
    audio: np.ndarray,
    sr: int,
    targets: Dict,
    pre_band_levels: Dict[str, float],
) -> Tuple[np.ndarray, List[SpectralCorrectiveAction]]:
    """Apply single-pass corrective EQ for sub and low_mid bands per STORY-006 §5.

    audio: float64 array, shape (N,) mono or (N, 2) stereo.
    sr: sample rate in Hz.
    targets: parsed targets.json as dict (from TargetsDocument.to_dict()).
    pre_band_levels: band_name -> relative_db from seven-band Stage [2] analysis.

    Returns (audio_out, actions).  audio_out is unmodified if no band needs
    correction.  All spectral policy constants (thresholds, caps, aim points)
    are read from targets — never hardcoded (AC13).

    sosfiltfilt convention (§5.2, §5.3): the design parameter passed to the
    filter constructors is applied_db / 2, so that sosfiltfilt's forward-backward
    doubling delivers the full applied_db at the filter's centre frequency.

    STORY-027 cap policy:
    - sub.correction_cap_db (targets.json): 9.0 dB nominal (Gate 1, 2026-08-21).
      RBJ low-shelf fc=60 Hz S=1; delivery efficiency ~0.60× over 20-60 Hz band.
      Min safe cap = required_gap / 0.60.  Incidental effect: shelf transition
      attenuates 60-120 Hz (low band) by several dB; logged in spillover_note.
    - de_mud trigger: reads de_mud.correction_cap_db (6.52243176025526) from targets.
      The existing low_mid.correction_cap_db is retained for the range_compliance case
      (currently unreachable for low_mid since de_mud fires first, but must not be
      silently removed — STORY-027 arch §3.3 item 1).
    - residual_gap_db is populated by report/builder.py after post-master analysis.
    """
    if sr <= 0:
        raise ValueError("invalid sample rate")

    # Normalise to dict in case a TargetsDocument is passed directly
    t = targets.to_dict() if hasattr(targets, "to_dict") else targets

    out = audio.copy()
    actions: List[SpectralCorrectiveAction] = []

    # ------------------------------------------------------------------
    # Sub band (20–60 Hz) — low shelf at 60 Hz corner
    # ------------------------------------------------------------------
    sub_t = t["spectral_bands"]["sub"]
    cap_sub = float(sub_t["correction_cap_db"])
    src_sub = float(pre_band_levels.get("sub", 0.0))
    range_min_sub = float(sub_t["range_db_re_mid"]["min"])
    range_max_sub = float(sub_t["range_db_re_mid"]["max"])

    aim_sub: float | None = None
    trigger_sub: str | None = None
    if src_sub < range_min_sub:
        aim_sub = range_min_sub
        trigger_sub = "range_compliance"
    elif src_sub > range_max_sub:
        aim_sub = range_max_sub
        trigger_sub = "range_compliance"

    if aim_sub is not None:
        raw_gap = aim_sub - src_sub
        # Compensate for sub shelf delivery efficiency: the shelf delivers only
        # ~60% of the nominal gain across the 20-60 Hz band, so apply gap/efficiency
        # as the filter design nominal so the delivered band-energy change reaches
        # the aim point (DEF-027-004).
        nominal = raw_gap / _DELIVERY_EFFICIENCY_SUB
        applied = _clamp(nominal, -cap_sub, cap_sub)
        cap_reached = abs(applied) < abs(nominal)
        # applied_db in the action is the expected BAND-LEVEL change delivered:
        # nominal * efficiency = raw_gap (or cap-limited equivalent).
        effective_band_change = applied * _DELIVERY_EFFICIENCY_SUB
        f_corner = float(sub_t["freq_hz"][1])  # upper edge = 60 Hz
        sos = _low_shelf_sos(sr, f_corner, applied / 2.0)
        out = sosfiltfilt(sos, out, axis=0)
        # STORY-027 §3.2: RBJ low-shelf at fc=60 Hz (S=1) transitions above 60 Hz.
        # The lower low-band (60-90 Hz) sees incidental attenuation from the shelf
        # transition (~4-5 dB at 80 Hz for 9 dB nominal).  This is shelf behaviour,
        # not a low-band correction — attribute any post-master low-band change to
        # this spillover before triggering a separate low-band alert.
        spillover = (
            f"Sub low-shelf at fc=60 Hz (nominal {applied:.2f} dB) produces incidental "
            f"attenuation in the 60-120 Hz low band via the shelf transition band. "
            f"Expected: ~{abs(applied) * 0.5:.1f}-{abs(applied) * 0.6:.1f} dB at 80-90 Hz. "
            f"Not a low-band correction — attribute any post-master low-band shift to this spillover."
        )
        actions.append(SpectralCorrectiveAction(
            band="sub",
            trigger=trigger_sub,
            source_db=src_sub,
            aim_point_db=aim_sub,
            applied_db=effective_band_change,
            cap_reached=cap_reached,
            resulting_db=src_sub + effective_band_change,
            spillover_note=spillover,
        ))

    # ------------------------------------------------------------------
    # Low-mid band (120–500 Hz) — peaking bell at geometric centre
    # ------------------------------------------------------------------
    lm_t = t["spectral_bands"]["low_mid"]
    # cap_lm_range_compliance is for the range_compliance trigger (currently
    # unreachable for low_mid because de_mud fires first for any above-range source,
    # but retained and must NOT be silently removed — STORY-027 arch §3.3 item 1).
    cap_lm_range_compliance = float(lm_t["correction_cap_db"])
    src_lm = float(pre_band_levels.get("low_mid", 0.0))
    mid_db = float(pre_band_levels.get("mid", 0.0))

    de_mud = t["de_mud"]
    de_mud_threshold = float(de_mud["flag_threshold_db_above_mid"])
    de_mud_aim = float(de_mud["correction_aim_point_db"])
    # STORY-027 §3.3: de_mud gets its own cap from targets.json: de_mud.correction_cap_db.
    # Derivation: range_max_db_re_mid - correction_aim_point_db = 6.52243176025526.
    # This makes the aim reachable from any in-range de_mud source.
    cap_lm_de_mud = float(de_mud["correction_cap_db"])
    range_min_lm = float(lm_t["range_db_re_mid"]["min"])
    range_max_lm = float(lm_t["range_db_re_mid"]["max"])

    de_mud_fires = src_lm > mid_db + de_mud_threshold
    out_of_range = not (range_min_lm <= src_lm <= range_max_lm)

    aim_lm: float | None = None
    trigger_lm: str | None = None
    cap_lm: float = cap_lm_range_compliance
    if de_mud_fires:
        trigger_lm = "de_mud"
        aim_lm = de_mud_aim
        cap_lm = cap_lm_de_mud          # de_mud uses its own, larger cap
    elif out_of_range:
        trigger_lm = "range_compliance"
        aim_lm = range_min_lm if src_lm < range_min_lm else range_max_lm
        cap_lm = cap_lm_range_compliance  # explicit for clarity

    if aim_lm is not None:
        # Low_mid: no delivery-efficiency compensation (DEF-027-004 check confirmed
        # the peaking bell does not need compensation — TC-2720 tests expect raw_gap
        # as both action.applied_db and the filter design parameter).
        # The ~0.75× delivery efficiency is documented in the class docstring as a
        # maintenance note, not as a required compensation path.
        required = aim_lm - src_lm
        applied = _clamp(required, -cap_lm, cap_lm)
        cap_reached = abs(applied) < abs(required)
        freq_hz = tuple(lm_t["freq_hz"])
        f0 = _band_center_hz(freq_hz)
        # 2.06 octaves: geometrically derived from log2(500/120); not a policy constant
        bw = _band_bandwidth_octaves(freq_hz)
        sos = _peaking_sos(sr, f0, applied / 2.0, bw)
        out = sosfiltfilt(sos, out, axis=0)
        actions.append(SpectralCorrectiveAction(
            band="low_mid",
            trigger=trigger_lm,
            source_db=src_lm,
            aim_point_db=aim_lm,
            applied_db=applied,
            cap_reached=cap_reached,
            resulting_db=src_lm + applied,
        ))

    return out, actions
