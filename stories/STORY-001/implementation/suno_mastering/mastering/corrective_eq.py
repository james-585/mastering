from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Tuple
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
    """
    band: str           # "sub" | "low_mid"
    trigger: str        # "range_compliance" | "de_mud"
    source_db: float    # pre-correction relative_db for the band (from pre_band_levels)
    aim_point_db: float # nearest range edge for range_compliance; de_mud.correction_aim_point_db for de_mud
    applied_db: float   # signed dB of delivered gain at centre frequency
    cap_reached: bool
    resulting_db: float # source_db + applied_db (arithmetic, NOT used for AC16 classification)


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
        required = aim_sub - src_sub
        applied = _clamp(required, -cap_sub, cap_sub)
        cap_reached = abs(applied) < abs(required)
        f_corner = float(sub_t["freq_hz"][1])  # upper edge = 60 Hz
        sos = _low_shelf_sos(sr, f_corner, applied / 2.0)
        out = sosfiltfilt(sos, out, axis=0)
        actions.append(SpectralCorrectiveAction(
            band="sub",
            trigger=trigger_sub,
            source_db=src_sub,
            aim_point_db=aim_sub,
            applied_db=applied,
            cap_reached=cap_reached,
            resulting_db=src_sub + applied,
        ))

    # ------------------------------------------------------------------
    # Low-mid band (120–500 Hz) — peaking bell at geometric centre
    # ------------------------------------------------------------------
    lm_t = t["spectral_bands"]["low_mid"]
    cap_lm = float(lm_t["correction_cap_db"])
    src_lm = float(pre_band_levels.get("low_mid", 0.0))
    mid_db = float(pre_band_levels.get("mid", 0.0))

    de_mud = t["de_mud"]
    de_mud_threshold = float(de_mud["flag_threshold_db_above_mid"])
    de_mud_aim = float(de_mud["correction_aim_point_db"])
    range_min_lm = float(lm_t["range_db_re_mid"]["min"])
    range_max_lm = float(lm_t["range_db_re_mid"]["max"])

    de_mud_fires = src_lm > mid_db + de_mud_threshold
    out_of_range = not (range_min_lm <= src_lm <= range_max_lm)

    aim_lm: float | None = None
    trigger_lm: str | None = None
    if de_mud_fires:
        trigger_lm = "de_mud"
        aim_lm = de_mud_aim
    elif out_of_range:
        trigger_lm = "range_compliance"
        aim_lm = range_min_lm if src_lm < range_min_lm else range_max_lm

    if aim_lm is not None:
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
