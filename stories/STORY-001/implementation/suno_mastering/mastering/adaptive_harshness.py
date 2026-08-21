"""Adaptive harshness correction stage (STORY-010).

Corrects broadband 2-5 kHz excess via either a broad high-shelf or a narrow
peaking cut, selected based on presence_harsh.deviation_db vs thresholds.

STORY-027 wiring changes:
- The stage is now reachable from both shipped entrypoints:
  cli.py: --harshness-correction flag
  master_track.bat: optional --harshness-correction flag (documented in bat comment)
- Default remains AdaptiveHarshnessConfig.enabled = False pending targets.json
  threshold derivation (architecture §4.3, AC5 partially satisfied).

AC5 status: "reachable but default-off" — entrypoint-reachability delivered by
STORY-027; default-fire deferred until AdaptiveHarshnessConfig thresholds are
moved to targets.json with reference-derived values (Gate 1 DECISION 5).

STORY-010 third branch (reference-target mismatch, TC-0103): NOT implemented.
Explicitly deferred per STORY-027 architecture §4.4.  The two implemented branches
(broad_shelf, narrow_cut) are the only active classification paths.

Concern 3 (Gate 1): presence_harsh.reference_db is -4.0 dB (round number) while
the seven-band high_mid median is -6.714 dB (reference-derived) — both cover
2000-5000 Hz but disagree by 2.7 dB.  This must be reconciled before the stage
can be enabled by default.  Routed to the targets-derivation process.

Note: harshness_control.py (STORY-012) is the stem-supplemental path; its
_band_edges("mix") fallback (2500, 5000 Hz) is a known no-op on the stereo-
fallback path (requirements.md Finding 2 / architecture §4.5).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import sosfiltfilt

from ..analysis.types import FrequencyBalanceResult


@dataclass
class AdaptiveHarshnessConfig:
    enabled: bool = False
    # WARNING: these are round-number placeholders, not reference-derived values.
    # They must NOT be moved to default-on until transferred to targets.json with
    # derivations (STORY-027 architecture §4.3, Gate 1 DECISION 5).
    broad_threshold_db: float = 5.0
    narrow_threshold_db: float = 2.5
    broad_gain_db: float = -2.0
    narrow_gain_db: float = -3.0
    max_gain_db: float = 4.0


@dataclass
class AdaptiveHarshnessAction:
    method: str          # "broad_shelf" | "narrow_cut"
    reason: str
    center_hz: float
    gain_db: float       # designed gain at centre frequency
    bandwidth_octaves: float | None = None
    # DEF-027-006: AC19 before/after evidence fields required by architecture spec.
    # before_db: presence_harsh.relative_db measured before filter is applied.
    # after_db: estimated band level after filter (before_db + gain_db at centre).
    # classification: same as method — "broad_shelf" or "narrow_cut".
    # applied_db: gain delivered at centre frequency (equals gain_db; filter is
    #   designed for sosfiltfilt double-pass, so gain_db is the nominal delivered
    #   value at ω0 — see corrective_eq.py for the /2 design-parameter convention
    #   used by the STORY-006 path; this path uses a different convention where
    #   gain_db/40 is passed to the RBJ formula, giving gain_db at ω0 single-pass
    #   and 2×gain_db after sosfiltfilt — the discrepancy is a pre-existing
    #   STORY-010 design issue, not introduced here).
    before_db: float = 0.0
    after_db: float = 0.0
    classification: str = ""
    applied_db: float = 0.0


def _peaking_sos(sr: float, f0: float, gain_db: float, bandwidth_octaves: float):
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / sr
    sin_w0 = np.sin(w0)
    cos_w0 = np.cos(w0)
    alpha = sin_w0 * np.sinh((np.log(2) / 2) * bandwidth_octaves * (w0 / sin_w0))
    b0 = 1 + alpha * a
    b1 = -2 * cos_w0
    b2 = 1 - alpha * a
    a0 = 1 + alpha / a
    a1 = -2 * cos_w0
    a2 = 1 - alpha / a
    sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
    return sos


def _low_shelf_sos(sr: float, f0: float, gain_db: float):
    a = 10 ** (gain_db / 40.0)
    w0 = 2 * np.pi * f0 / sr
    sin_w0, cos_w0 = np.sin(w0), np.cos(w0)
    slope = 1.0
    alpha = (sin_w0 / 2) * np.sqrt((a + 1 / a) * (1 / slope - 1) + 2)
    two_sqrt_a_alpha = 2 * np.sqrt(a) * alpha
    b0 = a * ((a + 1) - (a - 1) * cos_w0 + two_sqrt_a_alpha)
    b1 = 2 * a * ((a - 1) - (a + 1) * cos_w0)
    b2 = a * ((a + 1) - (a - 1) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1) + (a - 1) * cos_w0 + two_sqrt_a_alpha
    a1 = -2 * ((a - 1) + (a + 1) * cos_w0)
    a2 = (a + 1) + (a - 1) * cos_w0 - two_sqrt_a_alpha
    sos = np.array([[b0 / a0, b1 / a0, b2 / a0, 1.0, a1 / a0, a2 / a0]])
    return sos


def _band_center_hz(band_hz: tuple) -> float:
    lo, hi = band_hz
    return float(np.sqrt(lo * hi))


def _band_width_octaves(band_hz: tuple) -> float:
    lo, hi = band_hz
    return float(np.log2(hi / lo))


def apply_adaptive_harshness(
    audio: np.ndarray,
    sr: int,
    freq_balance: FrequencyBalanceResult,
    config: AdaptiveHarshnessConfig | None = None,
):
    config = config or AdaptiveHarshnessConfig()
    if not config.enabled:
        return audio.copy(), []

    if sr <= 0:
        raise ValueError("Invalid sample rate")

    out = audio.copy()
    actions: list[AdaptiveHarshnessAction] = []
    presence = freq_balance.presence_harsh
    deviation = float(presence.deviation_db)
    low_mid_deviation = float(freq_balance.low_mid_mud.deviation_db)

    if deviation >= config.broad_threshold_db and low_mid_deviation < config.narrow_threshold_db:
        gain_db = -min(abs(config.broad_gain_db), config.max_gain_db)
        f0 = 3500.0
        before_db = float(presence.relative_db)
        sos = _low_shelf_sos(sr, f0, gain_db)
        out = sosfiltfilt(sos, out, axis=0)
        actions.append(AdaptiveHarshnessAction(
            method="broad_shelf",
            reason="broad_brighness",
            center_hz=f0,
            gain_db=gain_db,
            bandwidth_octaves=None,
            before_db=before_db,
            after_db=before_db + gain_db,
            classification="broad_shelf",
            applied_db=gain_db,
        ))
        return out, actions

    if deviation >= config.narrow_threshold_db:
        gain_db = -min(abs(config.narrow_gain_db), config.max_gain_db)
        f0 = _band_center_hz(presence.range_hz)
        bw = _band_width_octaves(presence.range_hz)
        before_db = float(presence.relative_db)
        sos = _peaking_sos(sr, f0, gain_db, bw)
        out = sosfiltfilt(sos, out, axis=0)
        actions.append(AdaptiveHarshnessAction(
            method="narrow_cut",
            reason="narrow_resonance",
            center_hz=f0,
            gain_db=gain_db,
            bandwidth_octaves=bw,
            before_db=before_db,
            after_db=before_db + gain_db,
            classification="narrow_cut",
            applied_db=gain_db,
        ))

    return out, actions
